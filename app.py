import base64
import colorsys
import html
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import numpy as np
import requests
import streamlit as st
from bs4 import BeautifulSoup
from PIL import Image, ImageFilter

try:  # optional: bessere Gesichts-/Personenerkennung fuer den Bildausschnitt
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

st.set_page_config(page_title="trustedDialog Countdown Preview", page_icon="⏳", layout="wide")

APP_VERSION = "v6"
OUT_W, OUT_H = 576, 300          # Hero-Bild (2x von 288 x 150 CSS-px)
HERO_CSS_H = 150
AVATAR_FALLBACK_BG, AVATAR_FALLBACK_FG = "#B8DDFD", "#0B3C6E"   # wie im tD Preview Builder
DEFAULT_PRIMARY, DEFAULT_ACCENT = "#0B3C6E", "#FFD500"
UA_SETS = [
    {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1",
     "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"},
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
     "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"},
]
# Originales trustedDialog-Siegel (Base64-SVG wie im tD Preview Builder)
SEAL_B64 = ("PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTExLjcyMTQgMi42NzA0MkMxMS44NzY2IDIuNTE5NzggMTIuMTIzNCAyLjUxOTc4IDEyLjI3ODYgMi42NzA0MkwxNC43MjIyIDUuMDQyMzdDMTQuNzk1NCA1LjExMzM5IDE0Ljg5MjkgNS4xNTM3OCAxNC45OTQ5IDUuMTU1M0wxOC40IDUuMjA1OTlDMTguNjE2MyA1LjIwOTIxIDE4Ljc5MDggNS4zODM3NCAxOC43OTQgNS41OTk5OUwxOC44NDQ3IDkuMDA1MTJDMTguODQ2MiA5LjEwNzA3IDE4Ljg4NjYgOS4yMDQ2IDE4Ljk1NzYgOS4yNzc3NkwyMS4zMjk2IDExLjcyMTRDMjEuNDgwMiAxMS44NzY2IDIxLjQ4MDIgMTIuMTIzNCAyMS4zMjk2IDEyLjI3ODZMMTguOTU3NiAxNC43MjIyQzE4Ljg4NjYgMTQuNzk1NCAxOC44NDYyIDE0Ljg5MjkgMTguODQ0NyAxNC45OTQ5TDE4Ljc5NCAxOC40QzE4Ljc5MDggMTguNjE2MyAxOC42MTYzIDE4Ljc5MDggMTguNCAxOC43OTRMMTQuOTk0OSAxOC44NDQ3QzE0Ljg5MjkgMTguODQ2MiAxNC43OTU0IDE4Ljg4NjYgMTQuNzIyMiAxOC45NTc2TDEyLjI3ODYgMjEuMzI5NkMxMi4xMjM0IDIxLjQ4MDIgMTEuODc2NiAyMS40ODAyIDExLjcyMTQgMjEuMzI5Nkw5LjI3Nzc3IDE4Ljk1NzZDOS4yMDQ2MSAxOC44ODY2IDkuMTA3MDggMTguODQ2MiA5LjAwNTEyIDE4Ljg0NDdMNS42IDE4Ljc5NEM1LjM4Mzc1IDE4Ljc5MDggNS4yMDkyMiAxOC42MTYzIDUuMjA2IDE4LjRMNS4xNTUzMSAxNC45OTQ5QzUuMTUzNzkgMTQuODkyOSA1LjExMzM5IDE0Ljc5NTQgNS4wNDIzNyAxNC43MjIyTDIuNjcwNDMgMTIuMjc4NkMyLjUxOTc5IDEyLjEyMzQgMi41MTk3OSAxMS44NzY2IDIuNjcwNDMgMTEuNzIxNEw1LjA0MjM3IDkuMjc3NzZDNS4xMTMzOSA5LjIwNDYgNS4xNTM3OSA5LjEwNzA3IDUuMTU1MzEgOS4wMDUxMkw1LjIwNiA1LjU5OTk5QzUuMjA5MjIgNS4zODM3NCA1LjM4Mzc1IDUuMjA5MjEgNS42IDUuMjA1OTlMOS4wMDUxMiA1LjE1NTNDOS4xMDcwOCA1LjE1Mzc4IDkuMjA0NjEgNS4xMTMzOSA5LjI3Nzc3IDUuMDQyMzdMMTEuNzIxNCAyLjY3MDQyWiIgZmlsbD0iIzQ2N0RDRCIvPgo8cGF0aCBkPSJNMTAuNiAxMy4xMkwxNC43MyA4Ljk5MDAyQzE0Ljg1ODMgOC44NjE2OCAxNS4wMjE3IDguNzk3NTIgMTUuMjIgOC43OTc1MkMxNS40MTgzIDguNzk3NTIgMTUuNTgxNyA4Ljg2MTY4IDE1LjcxIDguOTkwMDJDMTUuODM4MyA5LjExODM1IDE1LjkwMjUgOS4yODE2OCAxNS45MDI1IDkuNDgwMDJDMTUuOTAyNSA5LjY3ODM1IDE1LjgzODMgOS44NDE2OCAxNS43MSA5Ljk3MDAyTDExLjA5IDE0LjU5QzEwLjk1IDE0LjczIDEwLjc4NjcgMTQuOCAxMC42IDE0LjhDMTAuNDEzMyAxNC44IDEwLjI1IDE0LjczIDEwLjExIDE0LjU5TDguMjkgMTIuNzdDOC4xNjE2NiAxMi42NDE3IDguMDk3NSAxMi40NzgzIDguMDk3NSAxMi4yOEM4LjA5NzUgMTIuMDgxNyA4LjE2MTY2IDExLjkxODMgOC4yOSAxMS43OUM4LjQxODMzIDExLjY2MTcgOC41ODE2NiAxMS41OTc1IDguNzggMTEuNTk3NUM4Ljk3ODMzIDExLjU5NzUgOS4xNDE2NiAxMS42NjE3IDkuMjcgMTEuNzlMMTAuNiAxMy4xMloiIGZpbGw9IndoaXRlIi8+Cjwvc3ZnPgo=")


# ----------------------------------------------------------------------------
# Farb-Helfer (WCAG-Kontrast, damit Texte nie unsichtbar werden)
# ----------------------------------------------------------------------------
def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#%02X%02X%02X" % tuple(int(max(0, min(255, c))) for c in rgb)


def luminance(rgb):
    def f(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def text_on(hex_color):
    rgb = hex_to_rgb(hex_color)
    return "#FFFFFF" if contrast_ratio(rgb, (255, 255, 255)) >= contrast_ratio(rgb, (17, 17, 17)) else "#111111"


def darken_for_white(rgb, min_ratio=4.5):
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    for _ in range(40):
        cur = tuple(c * 255 for c in colorsys.hsv_to_rgb(h, s, v))
        if contrast_ratio(cur, (255, 255, 255)) >= min_ratio:
            return tuple(int(c) for c in cur)
        v *= 0.92
    return (11, 60, 110)


def dominant_colors(img, n=8):
    """Gesaettigte Markenfarben (ohne Weiss/Grau), nach Haeufigkeit sortiert."""
    try:
        im = flatten(img).resize((90, 90))
        q = im.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
        pal = q.getpalette()[: n * 3]
        counts = sorted(q.getcolors() or [], reverse=True)
        out = []
        for cnt, idx in counts:
            rgb = tuple(pal[idx * 3: idx * 3 + 3])
            h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
            if s >= 0.35 and 0.15 <= v <= 0.98:
                out.append((rgb, cnt * (0.6 + s)))
        out.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in out]
    except Exception:
        return []


def pick_colors(theme, images):
    cands = []
    if theme and re.fullmatch(r"#[0-9a-fA-F]{6}", theme.strip()):
        rgb = hex_to_rgb(theme.strip())
        h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
        if s >= 0.3 and v >= 0.15:
            cands.append(rgb)
    for im in images:
        cands.extend(dominant_colors(im))
    primary = darken_for_white(cands[0]) if cands else hex_to_rgb(DEFAULT_PRIMARY)
    accent = None
    for c in cands[1:]:
        if sum(abs(a - b) for a, b in zip(c, primary)) > 140:
            accent = c
            break
    accent = accent or hex_to_rgb(DEFAULT_ACCENT)
    return rgb_to_hex(primary), rgb_to_hex(accent)


# ----------------------------------------------------------------------------
# Bild-Helfer
# ----------------------------------------------------------------------------
def flatten(img, bg=(255, 255, 255)):
    img = img.convert("RGBA")
    canvas = Image.new("RGBA", img.size, bg + (255,))
    canvas.alpha_composite(img)
    return canvas.convert("RGB")


def corner_color(img):
    a = np.asarray(img.resize((64, 64)), dtype=np.int16)
    ring = np.concatenate([a[:2].reshape(-1, 3), a[-2:].reshape(-1, 3), a[:, :2].reshape(-1, 3), a[:, -2:].reshape(-1, 3)])
    return tuple(int(x) for x in np.median(ring, axis=0)), float(ring.std(axis=0).mean())


def is_logo_like(img):
    """Grafik mit grossflaechig einfarbigem Hintergrund (Logo, Freisteller)."""
    bg, spread = corner_color(img)
    a = np.asarray(img.resize((64, 64)), dtype=np.int16)
    frac = float((np.abs(a - np.array(bg)).max(axis=2) < 22).mean())
    return frac > 0.55 and spread < 14


def contain_on(img, bg, margin=26):
    canvas = Image.new("RGB", (OUT_W, OUT_H), bg)
    box_w, box_h = OUT_W - 2 * margin, OUT_H - 2 * margin
    s = min(box_w / img.width, box_h / img.height)
    fg = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)
    canvas.paste(fg, ((OUT_W - fg.width) // 2, (OUT_H - fg.height) // 2))
    return canvas


def blur_fill(img):
    """Ganzes Bild sichtbar (nichts wird abgeschnitten), Rest = unscharfe Fortsetzung des Bildes."""
    s = max(OUT_W / img.width, OUT_H / img.height)
    bgim = img.resize((int(img.width * s) + 1, int(img.height * s) + 1), Image.LANCZOS)
    l, t = (bgim.width - OUT_W) // 2, (bgim.height - OUT_H) // 2
    bgim = bgim.crop((l, t, l + OUT_W, t + OUT_H)).filter(ImageFilter.GaussianBlur(18))
    s2 = min(OUT_W / img.width, OUT_H / img.height)
    fg = img.resize((max(1, int(img.width * s2)), max(1, int(img.height * s2))), Image.LANCZOS)
    bgim.paste(fg, ((OUT_W - fg.width) // 2, (OUT_H - fg.height) // 2))
    return bgim


_CASCADES = {}


def detect_faces(img):
    """Gesichter als (x, y, w, h) in Originalkoordinaten."""
    if cv2 is None:
        return []
    try:
        scale = min(1.0, 640 / img.width)
        small = np.asarray(img.resize((int(img.width * scale), int(img.height * scale))).convert("L"))
        small = cv2.equalizeHist(small)
        found = []
        for name in ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml", "haarcascade_profileface.xml"):
            if name not in _CASCADES:
                _CASCADES[name] = cv2.CascadeClassifier(cv2.data.haarcascades + name)
            r = _CASCADES[name].detectMultiScale(small, 1.1, 5, minSize=(max(24, int(small.shape[1] * 0.05)),) * 2)
            found.extend(r.tolist() if len(r) else [])
            if found:
                break
        return [(x / scale, y / scale, w / scale, h / scale) for x, y, w, h in found]
    except Exception:
        return []


def detect_person(img):
    """Person (x, y, w, h) per HOG, falls kein Gesicht gefunden wurde."""
    if cv2 is None:
        return None
    try:
        scale = min(1.0, 420 / img.width)
        small = cv2.cvtColor(np.asarray(img.resize((int(img.width * scale), int(img.height * scale)))), cv2.COLOR_RGB2BGR)
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        rects, weights = hog.detectMultiScale(small, winStride=(8, 8), padding=(8, 8), scale=1.05)
        if len(rects) == 0:
            return None
        i = int(np.argmax(weights))
        if float(np.ravel(weights)[i]) < 0.6:
            return None
        x, y, w, h = rects[i]
        return (x / scale, y / scale, w / scale, h / scale)
    except Exception:
        return None


def window_start(profile, win, top_bias=0.0):
    n = len(profile)
    if win >= n:
        return 0
    c = np.concatenate([[0.0], np.cumsum(profile)])
    scores = np.array([c[i + win] - c[i] for i in range(n - win + 1)])
    scores = scores * np.linspace(1 + top_bias, 1, len(scores))
    return int(np.argmax(scores))


def saliency_profiles(img):
    s = min(1.0, 200 / max(img.size))
    g = np.asarray(img.resize((max(8, int(img.width * s)), max(8, int(img.height * s)))).convert("L"), dtype=np.float32)
    gy, gx = np.gradient(g)
    mag = np.hypot(gx, gy)
    return mag.sum(axis=1), mag.sum(axis=0), s


def hero_image(img, manual=None):
    """Liefert (PIL-Bild OUT_W x OUT_H, Modus-Text). Ziel: sauber zentriert, Koepfe nie abgeschnitten."""
    img = flatten(img)
    W, H = img.size
    ratio = OUT_W / OUT_H
    if manual is None and is_logo_like(img):
        return contain_on(img, corner_color(img)[0]), "Logo/Freisteller – vollständig auf Hintergrundfarbe zentriert"
    cw, ch = (H * ratio, H) if W / H >= ratio else (W, W / ratio)
    sx, sy = W - cw, H - ch
    x0, y0, mode = sx / 2, sy / 2, "Mitte"
    if manual is not None:
        x0, y0, mode = manual[0] * sx, manual[1] * sy, "manuell"
    else:
        faces = detect_faces(img)
        person = None if faces else detect_person(img)
        if faces:
            fx0 = min(f[0] for f in faces); fx1 = max(f[0] + f[2] for f in faces)
            fy0 = min(f[1] for f in faces); fy1 = max(f[1] + f[3] for f in faces)
            fh = max(f[3] for f in faces)
            x0 = (fx0 + fx1) / 2 - cw / 2
            y0 = fy0 - 0.8 * fh                       # Platz fuer Haare / Kopfhoehe
            x0, y0 = min(max(x0, 0), sx), min(max(y0, 0), sy)
            fits = (y0 <= fy0 - 0.35 * fh) and (y0 + ch >= fy1 + 0.2 * fh) and (x0 <= fx0) and (x0 + cw >= fx1)
            if not fits:
                return blur_fill(img), "Gesicht erkannt – ganzes Bild sichtbar, damit der Kopf nicht abgeschnitten wird"
            mode = "Gesicht erkannt – Kopf vollständig, zentriert"
        elif person:
            px, py, pw, ph = person
            x0 = px + pw / 2 - cw / 2
            y0 = py - 0.06 * ph
            x0, y0 = min(max(x0, 0), sx), min(max(y0, 0), sy)
            mode = "Person erkannt – Kopfbereich oben im Ausschnitt"
        else:
            rows, cols, s = saliency_profiles(img)
            if sy > 0:
                y0 = window_start(rows, int(ch * s), top_bias=0.35 if H >= W else 0.1) / s
            if sx > 0:
                x0 = window_start(cols, int(cw * s)) / s
            mode = "Motiv-Schwerpunkt (automatisch)"
    box = (int(round(x0)), int(round(y0)), int(round(x0 + cw)), int(round(y0 + ch)))
    return img.crop(box).resize((OUT_W, OUT_H), Image.LANCZOS), mode


@st.cache_data(show_spinner=False)
def hero_bytes(blob: bytes, manual=None):
    im = Image.open(io.BytesIO(blob))
    im.load()
    out, mode = hero_image(im, manual)
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=88)
    return buf.getvalue(), mode


def process_avatar(img):
    """Quadratisches PNG (144 px) mit weissem Hintergrund; Logos werden mit Rand eingepasst, nie abgeschnitten."""
    had_alpha = img.mode in ("RGBA", "LA") or "transparency" in img.info
    rgba = img.convert("RGBA")
    if had_alpha:
        bbox = rgba.getchannel("A").point(lambda a: 255 if a > 10 else 0).getbbox()
        if bbox:
            rgba = rgba.crop(bbox)
    flat = flatten(rgba)
    w, h = flat.size
    side = max(w, h)
    squareish = 0.9 <= w / h <= 1.1
    pad = 0 if (squareish and not had_alpha) else int(side * 0.14)
    canvas = Image.new("RGB", (side + 2 * pad,) * 2, (255, 255, 255))
    canvas.paste(flat, ((canvas.width - w) // 2, (canvas.height - h) // 2))
    out = canvas.resize((144, 144), Image.LANCZOS)
    a = np.asarray(out, dtype=np.int16)
    coverage = float((np.abs(a - 255).max(axis=2) > 30).mean())
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue(), coverage


def ahash(img):
    g = np.asarray(flatten(img).convert("L").resize((16, 16)), dtype=np.float32)
    return (g > g.mean()).flatten()


def data_uri(blob: bytes, ctype: str) -> str:
    return f"data:{ctype.split(';')[0]};base64,{base64.b64encode(blob).decode()}"


# ----------------------------------------------------------------------------
# Website-Analyse
# ----------------------------------------------------------------------------
def norm_url(v: str) -> str:
    v = v.strip()
    return v if v.startswith(("http://", "https://")) else "https://" + v


def fetch_page(u):
    host = urlparse(u).netloc
    variants = [u]
    if host.startswith("www."):
        variants.append(u.replace("://www.", "://", 1))
    elif host.count(".") == 1:
        variants.append(u.replace("://", "://www.", 1))
    last = None
    for headers in UA_SETS:
        for v in variants:
            try:
                r = requests.get(v, headers=headers, timeout=(6, 14))
                if r.status_code < 400 and r.text:
                    return r
                last = f"HTTP {r.status_code}"
            except Exception as exc:
                last = exc.__class__.__name__
    raise RuntimeError(str(last))


def fetch_raw(u):
    try:
        r = requests.get(u, headers=UA_SETS[1], timeout=(5, 9))
        r.raise_for_status()
        if len(r.content) > 6_000_000:
            return None
        return u, r.content, r.headers.get("content-type", "")
    except Exception:
        return None


def meta_content(soup, *keys):
    for key in keys:
        node = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if node and node.get("content"):
            return node["content"].strip()
    return ""


def _jsonld_names(value):
    names = []
    if isinstance(value, dict):
        kind = value.get("@type", "")
        kinds = kind if isinstance(kind, list) else [kind]
        if any(str(k).lower() in {"organization", "corporation", "brand", "website", "onlinebusiness", "store"} for k in kinds):
            n = value.get("name") or value.get("legalName")
            if isinstance(n, str) and n.strip():
                names.append(n.strip())
        for v in value.values():
            names.extend(_jsonld_names(v))
    elif isinstance(value, list):
        for v in value:
            names.extend(_jsonld_names(v))
    return names


def _jsonld_logos(value):
    logos = []
    if isinstance(value, dict):
        lg = value.get("logo")
        if isinstance(lg, str):
            logos.append(lg)
        elif isinstance(lg, dict) and isinstance(lg.get("url"), str):
            logos.append(lg["url"])
        for v in value.values():
            logos.extend(_jsonld_logos(v))
    elif isinstance(value, list):
        for v in value:
            logos.extend(_jsonld_logos(v))
    return logos


def extract_brand(soup, host):
    cands = [meta_content(soup, k) for k in ("og:site_name", "application-name", "apple-mobile-web-app-title")]
    ld = []
    for sc in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(sc.string or sc.get_text() or "")
            cands.extend(_jsonld_names(payload))
            ld.extend(_jsonld_logos(payload))
        except Exception:
            pass
    for im in soup.find_all("img"):
        marker = (" ".join(im.get("class", [])) + " " + (im.get("id") or "")).lower()
        if "logo" in marker and (im.get("alt") or "").strip():
            cands.append(im["alt"].strip())
    if soup.title:
        cands.append(soup.title.get_text(" ", strip=True))
    label = host.split(".")[0]
    cands.append(label)
    generic = {"home", "homepage", "startseite", "online shop", "onlineshop", "shop"}
    for c in cands:
        c = re.sub(r"\s+", " ", c or "").strip()
        c = re.split(r"\s*[|–—]\s*", c)[0].strip()
        c = re.sub(r"\s+-\s+.*$", "", c).strip()
        c = re.sub(r"^(willkommen bei|welcome to)\s+", "", c, flags=re.I).strip()
        if c and c.lower() not in generic and len(c) <= 40:
            return c, ld
    return label.title(), ld


def collect_avatar_urls(soup, base, ld_logos):
    items = []  # (url, kind, declared_size)

    def size_of(tag):
        m = re.search(r"(\d+)x(\d+)", tag.get("sizes", "") or "")
        return int(m.group(1)) if m else 0

    for tag in soup.find_all("link", href=True):
        rel = " ".join(tag.get("rel", [])).lower()
        if "apple-touch-icon" in rel:
            items.append((urljoin(base, tag["href"]), "apple-touch-icon", size_of(tag) or 180))
        elif "icon" in rel:
            items.append((urljoin(base, tag["href"]), "favicon", size_of(tag)))
        elif "manifest" in rel:
            try:
                mj = requests.get(urljoin(base, tag["href"]), headers=UA_SETS[1], timeout=6).json()
                for ic in mj.get("icons", []):
                    m = re.search(r"(\d+)x(\d+)", ic.get("sizes", "") or "")
                    items.append((urljoin(urljoin(base, tag["href"]), ic.get("src", "")), "manifest", int(m.group(1)) if m else 0))
            except Exception:
                pass
    for lg in ld_logos:
        items.append((urljoin(base, lg), "schema-logo", 0))
    for key in ("og:logo", "logo"):
        v = meta_content(soup, key)
        if v:
            items.append((urljoin(base, v), "meta-logo", 0))
    for im in soup.find_all(["img", "meta"]):
        if im.name == "meta" and im.get("itemprop") != "logo":
            continue
        marker = " ".join(str(im.get(x, "")) for x in ("class", "id", "alt", "itemprop", "src")).lower() if im.name == "img" else "logo"
        src = im.get("src") or im.get("data-src") or im.get("content")
        if src and "logo" in marker and not str(src).startswith("data:"):
            items.append((urljoin(base, src), "logo", 0))
    items.append((urljoin(base, "/apple-touch-icon.png"), "apple-touch-icon", 180))
    items.append((urljoin(base, "/favicon.ico"), "favicon", 0))
    seen, uniq = set(), []
    for it in items:
        if it[0] not in seen:
            seen.add(it[0])
            uniq.append(it)
    return uniq[:16]


KIND_PRIO = {"apple-touch-icon": 30, "manifest": 28, "schema-logo": 26, "meta-logo": 24, "logo": 22, "favicon": 8}


def build_avatars(items):
    with ThreadPoolExecutor(8) as ex:
        fetched = list(ex.map(lambda it: fetch_raw(it[0]), items))
    cands, hashes = [], []
    for it, res in zip(items, fetched):
        if not res:
            continue
        url, blob, ctype = res
        kind = it[1]
        if "svg" in ctype or url.lower().split("?")[0].endswith(".svg"):
            try:
                txt = blob.decode("utf-8", "ignore")
                if "<svg" not in txt:
                    continue
            except Exception:
                continue
            cands.append({"kind": kind, "svg": data_uri(blob, "image/svg+xml"), "png": None, "side": 0,
                          "score": KIND_PRIO.get(kind, 5) + 10, "label": f"{kind} · SVG", "hash": None})
            continue
        try:
            im = Image.open(io.BytesIO(blob))
            im.load()
        except Exception:
            continue
        side = min(im.size)
        if side < 48:
            continue
        png, coverage = process_avatar(im)
        if coverage < 0.03:          # Kontrast-Regel: fast weisse Logos sind auf Weiss unlesbar
            continue
        ratio = im.width / im.height
        score = KIND_PRIO.get(kind, 5) + min(side, 512) / 20 + (15 if 0.85 <= ratio <= 1.18 else 0)
        cands.append({"kind": kind, "svg": None, "png": png, "side": side, "score": score,
                      "label": f"{kind} · {im.width}×{im.height}", "hash": ahash(im), "img": im})
    cands.sort(key=lambda c: c["score"], reverse=True)
    result = []
    for c in cands:      # visuell identische Avatare nur einmal (nur die beste Auflösung)
        if c["hash"] is not None and any(h is not None and int((c["hash"] != h).sum()) <= 12 for h in hashes):
            continue
        hashes.append(c["hash"])
        c.pop("hash", None)
        result.append(c)
        if len(result) >= 5:
            break
    return result


def score_image(w, h, attrs, keywords, logo_like):
    ratio = w / max(h, 1)
    s = min(w * h / 100000, 20)
    if 1.1 <= ratio <= 2.8:
        s += 18
    a = attrs.lower()
    if any(x in a for x in ["hero", "banner", "stage", "campaign", "teaser", "product", "kampagne"]):
        s += 22
    if any(x in a for x in ["logo", "icon", "sprite", "payment", "flag", "badge"]):
        s -= 40
    if any(k in a for k in keywords):
        s += 8
    if logo_like:
        s -= 30     # echte Fotos/Kampagnenmotive vor Logo-Grafiken
    return s


@st.cache_data(ttl=1800, show_spinner=False)
def analyze(raw: str):
    u = norm_url(raw)
    host = urlparse(u).netloc.replace("www.", "")
    out = {"url": u, "domain": host, "brand": host.split(".")[0].title(), "description": "",
           "website_images": [], "avatars": [], "primary": DEFAULT_PRIMARY, "accent": DEFAULT_ACCENT}
    try:
        r = fetch_page(u)
    except Exception as exc:
        out["warning"] = f"Website nicht abrufbar ({exc}). Bitte Motiv und Avatar per Upload ergänzen."
        return out
    soup = BeautifulSoup(r.text[:2_500_000], "html.parser")
    base = r.url
    out["brand"], ld_logos = extract_brand(soup, host)
    out["description"] = meta_content(soup, "description", "og:description")

    # --- Avatare
    try:
        out["avatars"] = build_avatars(collect_avatar_urls(soup, base, ld_logos))
    except Exception:
        out["avatars"] = []

    # --- Motive
    cands, seen = [], set()
    ogi = meta_content(soup, "og:image")
    if ogi:
        cands.append((urljoin(base, ogi), "og:image hero"))
    for tag in soup.find_all("img"):
        attrs = " ".join(str(tag.get(x, "")) for x in ["alt", "class", "id", "title"])
        src = tag.get("data-src") or tag.get("data-lazy-src") or tag.get("src")
        srcset = tag.get("srcset", "") or tag.get("data-srcset", "")
        if srcset:
            parts = [p.strip().split(" ")[0] for p in srcset.split(",") if p.strip()]
            src = parts[-1] if parts else src
        if src and not str(src).startswith("data:") and "logo" not in attrs.lower():
            cands.append((urljoin(base, src), attrs))
    for tag in soup.find_all(style=re.compile("background-image", re.I)):
        m = re.search(r"url\([\"']?([^\"')]+)", tag.get("style", ""))
        if m:
            cands.append((urljoin(base, m.group(1)), str(tag.get("class", "")) + " hero background"))
    uniq = []
    for cu, attrs in cands[:60]:
        if cu not in seen and not cu.lower().split("?")[0].endswith((".svg", ".gif", ".ico")):
            seen.add(cu)
            uniq.append((cu, attrs))
    keys = re.findall(r"[a-zäöü]{4,}", (out["description"] + " " + host).lower())[:12]
    with ThreadPoolExecutor(8) as ex:
        fetched = list(ex.map(lambda it: fetch_raw(it[0]), uniq))
    ranked, hashes = [], []
    for (cu, attrs), res in zip(uniq, fetched):
        if not res:
            continue
        try:
            im = Image.open(io.BytesIO(res[1]))
            im.load()
        except Exception:
            continue
        if im.width < 320 or im.height < 160:
            continue
        flat = flatten(im)
        h = ahash(flat)
        if any(int((h != o).sum()) <= 12 for o in hashes):
            continue
        hashes.append(h)
        ranked.append({"blob": res[1], "w": im.width, "h": im.height,
                       "score": score_image(im.width, im.height, attrs, keys, is_logo_like(flat))})
    ranked.sort(key=lambda x: x["score"], reverse=True)
    out["website_images"] = ranked[:6]

    # --- Markenfarben (Avatar/Logo > Theme-Farbe > Motiv)
    imgs = []
    for a in out["avatars"][:2]:
        if a.get("img") is not None:
            imgs.append(a["img"])
    if ranked and not imgs:
        try:
            imgs.append(Image.open(io.BytesIO(ranked[0]["blob"])))
        except Exception:
            pass
    out["primary"], out["accent"] = pick_colors(meta_content(soup, "theme-color", "msapplication-TileColor"), imgs)
    for a in out["avatars"]:
        a.pop("img", None)
    return out


def copy_for(d):
    t = f"{d.get('domain','')} {d.get('brand','')} {d.get('description','')}".lower()
    if any(k in t for k in ["fressnapf", "tier", "pet", "hund", "katze"]):
        return ("Nur für kurze Zeit: Aktionsvorteile sichern", "Lieblingsprodukte zum Aktionsvorteil",
                "Sichere dir ausgewählte Angebote für deinen tierischen Alltag.", "Angebote entdecken")
    if any(k in t for k in ["foto", "photo", "print", "druck"]):
        return ("Nur noch kurze Zeit für deinen Aktionsvorteil", "Jetzt Aktionsvorteil sichern",
                "Gestalte dein Fotoprodukt im Aktionszeitraum und sichere dir den Vorteil.", "Jetzt gestalten")
    if any(k in t for k in ["reise", "travel", "hotel", "urlaub"]):
        return ("Dein Reiseangebot endet bald", "Dein Reisevorteil endet bald",
                "Sichere dir das aktuelle Angebot innerhalb des Aktionszeitraums.", "Angebot entdecken")
    if any(k in t for k in ["mode", "fashion", "schuhe", "bekleidung", "accessoires", "zalando"]):
        return ("Nur noch kurze Zeit: Aktionspreise auf Mode", "Ausgewählte Favoriten zum Aktionspreis",
                "Entdecke aktuelle Styles, solange die Aktion läuft.", "Jetzt entdecken")
    return ("Nur noch kurze Zeit: Vorteil sichern", "Aktionsvorteil endet bald",
            "Entdecke ausgewählte Angebote, solange die Aktion läuft.", "Angebot ansehen")


# ----------------------------------------------------------------------------
# iPhone-Mockup (Maße 1:1 aus der Vorlage)
# ----------------------------------------------------------------------------
CSS = """
*{box-sizing:border-box}html,body{margin:0;background:transparent}
.stage{position:relative;width:348px;height:716px;margin:0 auto;font-family:Roboto,-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;color:#111}
.sidebtn{position:absolute;background:linear-gradient(90deg,#7d7d7d,#e4e4e4 45%,#8a8a8a);border:1px solid #3a3a3a;border-radius:2px;z-index:0}
.phone{position:absolute;left:8px;top:7px;width:330px;height:702px;border-radius:54px;background:#121212;z-index:1;box-shadow:0 0 0 1px #0d0d0d,0 0 0 3.5px #d2d2d2,0 0 0 5px #161616}
.screen{position:absolute;left:13px;top:13px;width:304px;height:676px;background:#fff;border-radius:41px;overflow:hidden}
.abs{position:absolute}
.time{left:22px;top:13px;font-size:13px;font-weight:700;letter-spacing:.2px;color:#000}
.island{left:113px;top:12px;width:78px;height:22px;background:#0d0d0d;border-radius:14px}
.island i{position:absolute;right:7px;top:6px;width:9px;height:9px;border-radius:50%;background:radial-gradient(circle,#0b1f66 0 35%,#14183a 36% 100%)}
.signal{left:218px;top:17px}.wifi{left:243px;top:17px}
.battery{left:260px;top:14px;width:22px;height:14px;border-radius:5px;background:#111;color:#fff;font-size:9px;font-weight:800;text-align:center;line-height:14px}
.battip{left:283px;top:19px;width:2px;height:5px;border-radius:0 2px 2px 0;background:#9a9a9a}
.round{left:3px;top:50px;width:36px;height:36px}
.hicon{position:absolute;left:11px;top:10px;fill:none;stroke:#111;stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round}
.t{position:absolute;white-space:nowrap}.title{left:51px;top:51px;font-size:15px;font-weight:700;color:#000}
.mailaddr{left:51px;top:70px;font-size:10px;color:#a0a0a0}
.pager{position:absolute;right:12px;top:50px;width:70px;height:38px;border-radius:20px;box-shadow:0 2px 12px rgba(0,0,0,.09);background:#fff}
.pager svg{position:absolute;top:14px}
.band{position:absolute;left:0;top:93px;width:100%;height:56px;background:#f2f2f2}
.pill{position:absolute;left:15px;top:15px;height:25px;padding:0 11px;border:1px solid #e3e3e3;border-radius:14px;background:#fff;color:#2a62ae;font-size:10.5px;line-height:23px;font-weight:500}
.unsub{position:absolute;right:34px;top:19px;color:#1a66c4;font-size:11px}
.unsubic{position:absolute;right:12px;top:19px}
.avatar{position:absolute;left:15px;top:162px;width:36px;height:36px;border-radius:50%;background:__FALLBACK_BG__;color:__FALLBACK_FG__;display:grid;place-items:center;font-size:14px;font-weight:700;overflow:hidden}
img.avatar{object-fit:cover;background:#fff;display:block}
img.avatar.svg{object-fit:contain;padding:6px}
.name{position:absolute;left:61px;top:165px;max-width:150px;display:flex;align-items:center;gap:4px;color:#2b5fa8;font-size:14px;font-weight:700}
.name span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.seal{flex-shrink:0;width:15px;height:15px}
.date{position:absolute;left:61px;top:187px;font-size:10.5px;color:#8f8f8f}
.one{position:absolute;left:268px;top:172px;font-size:11px;color:#9b9b9b}
.chev{position:absolute;left:285px;top:174px}
.line{position:absolute;left:15px;top:217px;width:248px;border-top:1px solid #dcdcdc}
.subject{position:absolute;left:15px;top:233px;width:272px;font-size:15.5px;line-height:1.2;font-weight:700;color:#222;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.mailbody{position:absolute;left:8px;top:292px;width:288px;bottom:66px;overflow-y:auto;overflow-x:hidden;background:#fff;border:1px solid #eee;scrollbar-width:none}
.mailbody::-webkit-scrollbar{display:none}
.brandbar{height:34px;display:flex;align-items:center;justify-content:center;background:#fff;font-size:14px;font-weight:800;color:__HEADCOLOR__}
.brandbar img{max-width:120px;max-height:24px;object-fit:contain}
.brandbar span{max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hero{display:block;width:286px;height:__HEROH__px;object-fit:cover}
.missing{height:__HEROH__px;display:grid;place-items:center;background:#eee;color:#777;font-size:10px}
.content{text-align:center;padding:10px 12px 14px}
.headline{font-size:16px;line-height:1.15;font-weight:800;color:__HEADCOLOR__;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.timer{display:flex;gap:4px;justify-content:center;margin:9px 0 8px}
.unit{width:50px;background:__PRIMARY__;color:__UNITTEXT__;border:1px solid __UNITBORDER__;border-radius:6px;padding:5px 0 4px}
.num{font-size:17px;font-weight:800;line-height:1.1;font-variant-numeric:tabular-nums}
.lab{font-size:6.5px;text-transform:uppercase;letter-spacing:.4px;opacity:.9}
.txt{font-size:9.5px;line-height:1.35;color:#555;margin:0 0 9px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.cta{display:inline-block;background:__ACCENT__;color:__CTATEXT__;font-size:10px;font-weight:800;padding:8px 16px;border-radius:5px}
.fade{position:absolute;left:8px;bottom:66px;width:288px;height:34px;background:linear-gradient(rgba(255,255,255,0),#fff);pointer-events:none}
.ai{position:absolute;right:12px;bottom:67px;font-size:7px;color:#9aa0a6;z-index:3}
.dockbg{position:absolute;left:13px;top:614px;width:227px;height:44px;border-radius:23px;background:#fff;box-shadow:0 1px 14px rgba(0,0,0,.08)}
.compose{position:absolute;left:250px;top:613px;width:42px;height:46px;border-radius:50%;background:#fff;box-shadow:0 1px 14px rgba(0,0,0,.08);display:grid;place-items:center}
.om-ic{position:absolute}
.home{left:94px;top:663px;width:115px;height:4px;border-radius:4px;background:#111}
"""

BODY = """
<div class="stage" id="td">
<div class="sidebtn" style="left:4px;top:129px;width:5px;height:22px"></div>
<div class="sidebtn" style="left:4px;top:174px;width:5px;height:44px"></div>
<div class="sidebtn" style="left:4px;top:235px;width:5px;height:44px"></div>
<div class="sidebtn" style="left:331.5px;top:208px;width:6px;height:71px"></div>
<div class="phone"><div class="screen">
<span class="abs time">__NOW__</span>
<span class="abs island"><i></i></span>
<span class="abs signal"><svg width="18" height="11" viewBox="0 0 18 11"><rect x="1.2" y="6.2" width="2.7" height="4.5" rx=".7" fill="#111"/><rect x="5.8" y="4.7" width="2.7" height="6" rx=".7" fill="#c6c6c6"/><rect x="10.4" y="2.9" width="2.7" height="7.8" rx=".7" fill="#c6c6c6"/><rect x="15" y="1" width="2.7" height="9.7" rx=".7" fill="#c6c6c6"/></svg></span>
<span class="abs wifi"><svg width="13" height="9.5" viewBox="0 0 13 9.5"><path d="M1 3.6a7.9 7.9 0 0 1 11 0" fill="none" stroke="#c9c9c9" stroke-width="1.7" stroke-linecap="round"/><path d="M3.1 5.7a4.9 4.9 0 0 1 6.8 0" fill="none" stroke="#000" stroke-width="1.7" stroke-linecap="round"/><path d="M6.5 9.1 4.9 7.5a2.3 2.3 0 0 1 3.2 0z" fill="#000" stroke="#000" stroke-width=".9" stroke-linejoin="round"/></svg></span>
<span class="abs battery">93</span><span class="abs battip"></span>
<span class="abs round"><svg class="hicon" width="16" height="16" viewBox="0 0 16 16"><path d="M11 1.6 4.6 8l6.4 6.4"/></svg></span>
<span class="t title">1 von 5</span><span class="t mailaddr">trusteddialog99@gmx.net</span>
<span class="pager">
<svg style="left:19px" width="17" height="10" viewBox="0 0 17 10" fill="none" stroke="#111" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M1.5 8.5 8.5 1.5l7 7"/></svg>
<svg style="left:46px" width="17" height="10" viewBox="0 0 17 10" fill="none" stroke="#111" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M1.5 1.5l7 7 7-7"/></svg>
</span>
<div class="band"><span class="pill">Newsletter</span><span class="unsub">Newsletter abbestellen</span>
<svg class="unsubic" width="17" height="17" viewBox="0 0 17 17" fill="none" stroke="#1A66C4" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2.4 5.2V3.6h8.2"/><path d="M14.4 7.2v7.4h-3.2"/><circle cx="5.9" cy="11.2" r="3.7" stroke-width="2"/><path d="M4.2 11.2h3.4" stroke-width="1.9"/><path d="m11.3 1.3 3.4 3.4m0-3.4-3.4 3.4" stroke-width="2"/></svg></div>
__AVATAR__
<div class="name"><span>__BRAND__</span><img class="seal" src="__SEAL__" alt="trustedDialog Siegel"></div>
<div class="date">Heute um __DATE__</div>
<span class="one">1</span>
<svg class="chev" width="8" height="13" viewBox="0 0 8 13" fill="none" stroke="#b3b3b3" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M1.5 1.5 6.3 6.5 1.5 11.5"/></svg>
<div class="line"></div>
<div class="subject" id="subject">__SUBJECT__</div>
<div class="mailbody" id="mailbody">
<div class="brandbar">__LOGO__</div>
__HERO__
<div class="content">
<div class="headline">__HEADLINE__</div>
<div class="timer" id="timer" data-end="__END__">
<div class="unit"><div class="num" id="d">00</div><div class="lab">Tage</div></div>
<div class="unit"><div class="num" id="h">00</div><div class="lab">Std.</div></div>
<div class="unit"><div class="num" id="m">00</div><div class="lab">Min.</div></div>
<div class="unit"><div class="num" id="s">00</div><div class="lab">Sek.</div></div>
</div>
<p class="txt">__BODY__</p>
<span class="cta">__CTA__</span>
</div></div>
<div class="fade"></div>
<span class="ai">KI-optimiert</span>
<div class="dockbg"></div>
<span class="om-ic" style="left:23.5px;top:628px"><svg width="19" height="16" viewBox="0 0 19 16" fill="none" stroke="#111" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12.5 1.5h3.6a1.6 1.6 0 0 1 1.6 1.6v9.8a1.6 1.6 0 0 1-1.6 1.6H5.2"/><path d="M1.5 8h9.6M7.9 4.6 11.3 8l-3.4 3.4"/><path d="M5.2 14.5H4"/></svg></span>
<span class="om-ic" style="left:70px;top:626px"><svg width="18" height="19" viewBox="0 0 18 19" fill="none" stroke="#111" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M2 4.6h14M6.6 4.6V2.6c0-.6.4-1 1-1h2.8c.6 0 1 .4 1 1v2M3.6 4.6l.7 11.1c.1.9.7 1.5 1.6 1.5h6.2c.9 0 1.5-.6 1.6-1.5l.7-11.1M7.2 8v5.8M10.8 8v5.8"/></svg></span>
<span class="om-ic" style="left:115.5px;top:627.5px"><svg width="20" height="17" viewBox="0 0 20 17" fill="none" stroke="#111" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M8.2 1.8 2 7.4l6.2 5.6V9.6c4.6-.4 7.8.9 9.8 4.6-.4-5.4-3.7-8.7-9.8-8.9z"/></svg></span>
<span class="om-ic" style="left:162px;top:626.5px"><svg width="19" height="19" viewBox="0 0 19 19" fill="none" stroke="#5B57BE" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="9.5" cy="10.4" r="6.6"/><path d="M9.5 6.9v3.8l2.4 1.5M2.2 4.2 5 1.8M16.8 4.2 14 1.8"/></svg></span>
<span class="om-ic" style="left:207.5px;top:634px"><svg width="17" height="4" viewBox="0 0 17 4"><circle cx="2" cy="2" r="1.7" fill="#111"/><circle cx="8.5" cy="2" r="1.7" fill="#111"/><circle cx="15" cy="2" r="1.7" fill="#111"/></svg></span>
<span class="compose"><svg width="19" height="19" viewBox="0 0 19 19"><path d="M8.5 3.2H4.2A1.7 1.7 0 0 0 2.5 4.9v9.9a1.7 1.7 0 0 0 1.7 1.7h9.9a1.7 1.7 0 0 0 1.7-1.7v-4.3" fill="none" stroke="#111" stroke-width="2" stroke-linecap="round"/><path d="M14.6 1.7a1.6 1.6 0 0 1 2.3 2.3l-7.2 7.2-3.2.9.9-3.2z" fill="#111"/></svg></span>
<div class="abs home"></div>
</div></div></div>
<script>
(function(){
 var t=document.getElementById('timer'); if(!t) return;
 var end=new Date(t.getAttribute('data-end')).getTime();
 function pad(n){return String(n).padStart(2,'0');}
 function tick(){
  var d=Math.max(0,end-Date.now());
  document.getElementById('d').textContent=pad(Math.floor(d/86400000));
  document.getElementById('h').textContent=pad(Math.floor(d/3600000)%24);
  document.getElementById('m').textContent=pad(Math.floor(d/60000)%60);
  document.getElementById('s').textContent=pad(Math.floor(d/1000)%60);
 }
 tick(); setInterval(tick,1000);
})();
</script>
"""


def render(d, subject, headline, body, cta, end, primary, accent, hero_jpg, avatar):
    esc = html.escape
    brand = d.get("brand") or d.get("domain", "")
    now = datetime.now(ZoneInfo("Europe/Berlin"))
    prim_rgb = hex_to_rgb(primary)
    light = contrast_ratio(prim_rgb, (255, 255, 255)) < 3            # helle Primaerfarbe -> dunkle Schrift, Rand
    head_color = "#111111" if light else primary
    unit_text = text_on(primary)
    unit_border = "#C9C9C9" if light else primary
    if avatar and avatar.get("png"):
        av = f'<img class="avatar" src="{data_uri(avatar["png"], "image/png")}" alt="{esc(brand)}">'
    elif avatar and avatar.get("svg"):
        av = f'<img class="avatar svg" src="{avatar["svg"]}" alt="{esc(brand)}">'
    else:
        av = f'<span class="avatar">{esc(brand[:1].upper())}</span>'
    logo = (f'<img src="{data_uri(avatar["png"], "image/png")}" alt="{esc(brand)}">' if avatar and avatar.get("png")
            else (f'<img src="{avatar["svg"]}" alt="{esc(brand)}">' if avatar and avatar.get("svg")
                  else f"<span>{esc(brand)}</span>"))
    hero = (f'<img class="hero" src="{data_uri(hero_jpg, "image/jpeg")}" alt="Website-Motiv">' if hero_jpg
            else '<div class="missing">Kein Website-Motiv gefunden</div>')
    css = (CSS.replace("__FALLBACK_BG__", AVATAR_FALLBACK_BG).replace("__FALLBACK_FG__", AVATAR_FALLBACK_FG)
           .replace("__HEADCOLOR__", head_color).replace("__PRIMARY__", primary).replace("__UNITTEXT__", unit_text)
           .replace("__UNITBORDER__", unit_border).replace("__ACCENT__", accent).replace("__CTATEXT__", text_on(accent))
           .replace("__HEROH__", str(HERO_CSS_H)))
    try:
        base64.b64decode(SEAL_B64)
        seal_src = f"data:image/svg+xml;base64,{SEAL_B64}"
    except Exception:  # pragma: no cover
        seal_src = ""
    repl = {
        "__NOW__": now.strftime("%H:%M"), "__DATE__": (now - timedelta(minutes=3)).strftime("%H:%M"),
        "__AVATAR__": av, "__BRAND__": esc(brand), "__SEAL__": seal_src, "__SUBJECT__": esc(subject),
        "__LOGO__": logo, "__HERO__": hero, "__HEADLINE__": esc(headline), "__BODY__": esc(body),
        "__CTA__": esc(cta), "__END__": end.isoformat(),
    }
    body_html = BODY
    for k, v in repl.items():
        body_html = body_html.replace(k, v)
    return f"<style>{css}</style>{body_html}"


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------
def main():
    st.title(f"trustedDialog Countdown Preview {APP_VERSION}")
    st.caption("Domain eingeben → CI-nahe Countdown-Mail als geöffnete GMX-Mail im iPhone-Mockup.")
    with st.sidebar:
        st.header("Kundendomain")
        with st.form("domain_form", border=False):      # ENTER im Feld startet die Analyse
            raw = st.text_input("Domain oder URL", placeholder="z. B. fressnapf.de")
            go = st.form_submit_button("Domain analysieren", type="primary", use_container_width=True)
        if go and raw.strip():
            with st.spinner("Website wird analysiert …"):
                st.session_state.data = analyze(raw.strip())
    if "data" not in st.session_state:
        st.info("Domain eingeben und mit ENTER oder „Domain analysieren“ starten.")
        st.stop()

    d = dict(st.session_state.data)
    key = d["domain"]
    if d.get("warning"):
        st.warning(d["warning"])
    sub0, head0, body0, cta0 = copy_for(d)

    left, right = st.columns([0.43, 0.57], gap="large")
    with left:
        d["brand"] = st.text_input("Markenname (Absender)", d["brand"], key=f"brand_{key}")
        subject = st.text_input("Betreffzeile", sub0, key=f"subj_{key}",
                                help="Wird identisch in Mailliste und geöffneter Mail verwendet.")
        headline = st.text_input("Newsletter-Headline", head0, key=f"head_{key}")
        body = st.text_area("Newsletter-Text", body0, height=80, key=f"body_{key}")
        cta = st.text_input("CTA", cta0, key=f"cta_{key}")
        enddate = st.date_input("Countdown-Enddatum", (datetime.now() + timedelta(days=7)).date(), key=f"ed_{key}")
        endtime = st.time_input("Endzeit", datetime.strptime("23:59", "%H:%M").time(), key=f"et_{key}")

        st.markdown("**Motiv**")
        imgs = d.get("website_images", [])
        hero_jpg, mode = None, ""
        blob = None
        if imgs:
            idx = st.selectbox("Website-Motiv", range(len(imgs)), key=f"img_{key}",
                               format_func=lambda i: f"Motiv {i + 1} · {imgs[i]['w']}×{imgs[i]['h']}")
            blob = imgs[idx]["blob"]
        else:
            st.error("Kein ausreichend großes Website-Motiv gefunden – bitte eigenes Bild hochladen.")
        up = st.file_uploader("Optional: eigenes Motiv", type=["png", "jpg", "jpeg", "webp"], key=f"upimg_{key}")
        if up is not None:
            blob = up.getvalue()
        if blob:
            manual = None
            if st.checkbox("Bildausschnitt manuell anpassen", key=f"man_{key}"):
                fx = st.slider("Horizontal", 0, 100, 50, key=f"fx_{key}") / 100
                fy = st.slider("Vertikal (0 = oben)", 0, 100, 0, key=f"fy_{key}") / 100
                manual = (fx, fy)
            hero_jpg, mode = hero_bytes(blob, manual)
            st.image(hero_jpg, caption=f"Ausschnitt: {mode}", width=290)

        st.markdown("**Avatar (Absender-Kreis)**")
        avs = d.get("avatars", [])
        avatar = None
        options = ["Initialen (Fallback)"] + [a["label"] for a in avs]
        pick = st.selectbox("Avatar von der Website", options, index=1 if avs else 0, key=f"av_{key}")
        if avs and pick != options[0]:
            avatar = avs[options.index(pick) - 1]
        avup = st.file_uploader("Optional: eigener Avatar (PNG, JPG, SVG – z. B. aus dem Preview Builder)",
                                type=["png", "jpg", "jpeg", "webp", "svg"], key=f"upav_{key}")
        if avup is not None:
            ab = avup.getvalue()
            if avup.name.lower().endswith(".svg"):
                avatar = {"svg": data_uri(ab, "image/svg+xml"), "png": None}
            else:
                png, _ = process_avatar(Image.open(io.BytesIO(ab)))
                avatar = {"png": png, "svg": None}
        if avatar and avatar.get("png"):
            st.image(avatar["png"], width=56)
        elif not avs and avup is None:
            st.caption("Kein Avatar gefunden – es werden Initialen auf #B8DDFD verwendet.")

        st.markdown("**Farben**")
        primary = st.color_picker("Primärfarbe (Countdown)", d.get("primary", DEFAULT_PRIMARY), key=f"pc_{key}")
        accent = st.color_picker("CTA-Farbe", d.get("accent", DEFAULT_ACCENT), key=f"ac_{key}")
    with right:
        out = render(d, subject, headline, body, cta, datetime.combine(enddate, endtime), primary, accent, hero_jpg, avatar)
        st.components.v1.html(out, height=730, scrolling=False)
    st.download_button("HTML-Preview herunterladen", out.encode("utf-8"),
                       f"trustedDialog_countdown_{d['domain'].replace('.', '_')}.html", "text/html",
                       use_container_width=True)


main()
