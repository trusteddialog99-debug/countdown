import base64
import html
import re
from datetime import datetime, timedelta
from io import BytesIO
from urllib.parse import urljoin, urlparse

import requests
import streamlit as st
from bs4 import BeautifulSoup
from PIL import Image

st.set_page_config(page_title="trustedDialog Countdown Preview", page_icon="⏳", layout="wide")

DEFAULT_COLORS = {"primary": "#123C69", "accent": "#F4B400", "background": "#F5F7FA", "text": "#17202A"}


def normalize_url(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    return raw


def safe_hex(value: str, fallback: str) -> str:
    value = (value or "").strip()
    return value if re.fullmatch(r"#[0-9a-fA-F]{6}", value) else fallback


def image_to_data_uri(content: bytes, content_type: str = "image/png") -> str:
    return f"data:{content_type};base64,{base64.b64encode(content).decode('ascii')}"


def fetch_image_data_uri(url: str) -> str:
    try:
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        if len(r.content) > 3_000_000:
            return ""
        ctype = r.headers.get("content-type", "image/png").split(";")[0]
        Image.open(BytesIO(r.content)).verify()
        return image_to_data_uri(r.content, ctype)
    except Exception:
        return ""


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % rgb


def extract_palette(image_data_uri: str):
    if not image_data_uri:
        return None
    try:
        payload = image_data_uri.split(",", 1)[1]
        img = Image.open(BytesIO(base64.b64decode(payload))).convert("RGB")
        img.thumbnail((160, 160))
        colors = img.quantize(colors=8).convert("RGB").getcolors(256 * 256)
        candidates = sorted(colors or [], reverse=True)
        selected = []
        for _, rgb in candidates:
            mx, mn = max(rgb), min(rgb)
            if mx < 40 or mn > 235:
                continue
            if mx - mn < 22:
                continue
            selected.append(rgb_to_hex(rgb))
        if selected:
            return {"primary": selected[0], "accent": selected[1] if len(selected) > 1 else DEFAULT_COLORS["accent"]}
    except Exception:
        pass
    return None


@st.cache_data(ttl=1800, show_spinner=False)
def analyze_domain(raw_url: str):
    url = normalize_url(raw_url)
    if not url:
        return {}
    result = {"url": url, "domain": urlparse(url).netloc.replace("www.", ""), **DEFAULT_COLORS}
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0 (compatible; trustedDialogPreview/1.0)"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text[:1_500_000], "html.parser")
        result["brand"] = (soup.title.get_text(" ", strip=True).split("|")[0].split("–")[0].strip() if soup.title else result["domain"].split(".")[0].title())
        desc = soup.find("meta", attrs={"name": re.compile("description", re.I)})
        result["description"] = desc.get("content", "")[:300] if desc else ""

        logo_candidates, visual_candidates = [], []
        og = soup.find("meta", attrs={"property": "og:image"})
        if og and og.get("content"):
            visual_candidates.append(urljoin(url, og.get("content")))
        for tag in soup.find_all(["img", "link", "meta"]):
            attrs = " ".join(str(v) for v in tag.attrs.values()).lower()
            src = tag.get("src") or tag.get("data-src") or tag.get("data-lazy-src") or tag.get("href") or tag.get("content")
            if not src or str(src).startswith("data:"):
                continue
            absolute = urljoin(url, src)
            if "logo" in attrs or "icon" in attrs:
                logo_candidates.append(absolute)
            else:
                visual_candidates.append(absolute)
        for candidate in logo_candidates[:10]:
            data_uri = fetch_image_data_uri(candidate)
            if data_uri:
                result["logo"] = data_uri
                palette = extract_palette(data_uri)
                if palette:
                    result.update(palette)
                break
        website_images = []
        seen = set()
        for candidate in visual_candidates[:35]:
            if candidate in seen:
                continue
            seen.add(candidate)
            data_uri = fetch_image_data_uri(candidate)
            if data_uri:
                website_images.append(data_uri)
            if len(website_images) >= 4:
                break
        result["website_images"] = website_images
    except Exception as exc:
        result["warning"] = f"Die Website konnte nicht vollständig analysiert werden: {exc.__class__.__name__}. Die Vorschau nutzt neutrale Startwerte."
        result.setdefault("brand", result["domain"].split(".")[0].title())
        result.setdefault("description", "")
    return result


def campaign_copy(domain: str, brand: str, description: str):
    text = f"{domain} {brand} {description}".lower()
    # Branchenbezogen, aber bewusst markenneutral statt generischer Fashion-Sprache.
    if any(k in text for k in ["tier", "pet", "hund", "katze", "fressnapf"]):
        return {"eyebrow": "Nur für kurze Zeit", "headline": "Lieblingsprodukte zum Aktionsvorteil", "body": "Sichere dir ausgewählte Angebote für deinen tierischen Alltag, solange die Aktion läuft.", "cta": "Angebote entdecken", "subject": "Nur noch kurze Zeit: Aktionsvorteile sichern"}
    if any(k in text for k in ["reise", "travel", "hotel", "urlaub", "flug"]):
        return {"eyebrow": "Nur für kurze Zeit", "headline": "Dein Reisevorteil endet bald", "body": "Entdecke das aktuelle Angebot und sichere dir deinen Vorteil innerhalb des Aktionszeitraums.", "cta": "Angebot entdecken", "subject": "Dein Reiseangebot endet bald"}
    if any(k in text for k in ["foto", "photo", "druck", "print"]):
        return {"eyebrow": "Endspurt", "headline": "Jetzt Aktionsvorteil sichern", "body": "Gestalte dein Fotoprodukt innerhalb des Aktionszeitraums und sichere dir den aktuellen Vorteil.", "cta": "Jetzt gestalten", "subject": "Nur noch kurze Zeit für deinen Aktionsvorteil"}
    if any(k in text for k in ["mode", "fashion", "bekleidung", "schuhe"]):
        return {"eyebrow": "Limited Offer", "headline": "Ausgewählte Angebote nur für kurze Zeit", "body": "Entdecke aktuelle Favoriten zum Aktionspreis, solange die Aktion läuft.", "cta": "Jetzt entdecken", "subject": "Nur noch kurze Zeit: ausgewählte Angebote"}
    return {"eyebrow": "Nur für kurze Zeit", "headline": "Aktionsvorteil endet bald", "body": "Entdecke ausgewählte Angebote und sichere dir deinen Vorteil, solange die Aktion läuft.", "cta": "Angebot ansehen", "subject": "Nur noch kurze Zeit: Vorteil sichern"}


def build_email_html(data, copy, end_iso, colors, hero_url="", selected_image=0):
    brand = html.escape(data.get("brand") or data.get("domain", "Marke"))
    logo = data.get("logo", "")
    website_images = data.get("website_images", [])
    hero = fetch_image_data_uri(hero_url) if hero_url else (website_images[selected_image] if website_images and selected_image < len(website_images) else "")
    p, a, bg, txt = [safe_hex(colors[k], DEFAULT_COLORS[k]) for k in ["primary", "accent", "background", "text"]]
    brand_mark = f'<img src="{logo}" alt="{brand}" style="max-width:115px;max-height:30px;object-fit:contain">' if logo else f'<span style="font-weight:800;color:{p}">{brand}</span>'
    hero_html = f'<img src="{hero}" alt="Kampagnenmotiv von der Website" style="width:100%;height:188px;object-fit:cover;display:block">' if hero else f'<div style="height:150px;background:linear-gradient(135deg,{p},{a});display:flex;align-items:center;justify-content:center;color:white;font-size:42px">✦</div>'
    return f"""
<div id="td-preview" style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;background:#f3f4f6;padding:10px;color:{txt}">
 <div style="max-width:320px;margin:auto;background:linear-gradient(145deg,#181818,#4a4a4a);padding:3px;border-radius:45px;box-shadow:0 12px 30px rgba(0,0,0,.25)">
  <div style="background:#f8f8f8;border:4px solid #111;border-radius:42px;overflow:hidden;min-height:690px;position:relative">
   <div style="height:34px;display:grid;grid-template-columns:1fr 1.2fr 1fr;align-items:center;padding:0 18px;font-size:10px;font-weight:700"><span>09:35</span><span style="justify-self:center;width:92px;height:22px;border-radius:15px;background:#111"></span><span style="justify-self:end">▮▮ ◔ ▣</span></div>
   <div style="height:56px;background:#fff;border-bottom:1px solid #eee;display:flex;align-items:center;padding:0 14px;gap:12px"><span style="font-size:30px;font-weight:200">‹</span><div style="flex:1"><div style="font-weight:800;font-size:14px">1 von 5</div><div style="font-size:10px;color:#aaa">trustedDialog Preview</div></div><div style="display:flex;gap:8px"><span style="background:#fafafa;box-shadow:0 2px 12px #ddd;border-radius:50%;width:37px;height:37px;display:grid;place-items:center">⌃</span><span style="background:#fafafa;box-shadow:0 2px 12px #ddd;border-radius:50%;width:37px;height:37px;display:grid;place-items:center">⌄</span></div></div>
   <div style="height:34px;background:#f2f4f7;border-bottom:1px solid #e4e7eb;display:flex;align-items:center;justify-content:space-between;padding:0 13px;font-size:9px"><span style="background:white;border-radius:12px;padding:3px 8px;color:#4b76be">Newsletter</span><span style="color:#3675c5">Newsletter abbestellen&nbsp; ⚙</span></div>
   <div style="background:white;display:flex;align-items:center;padding:12px 14px 9px;gap:9px"><div style="width:30px;height:30px;border-radius:50%;background:#caeaff;color:#3273a8;display:grid;place-items:center;font-weight:700">{brand[:1]}</div><div style="flex:1"><div style="font-size:13px;font-weight:750;color:#3976ba">{brand} ✓</div><div style="font-size:9px;color:#999">Heute um 09:32</div></div><span style="color:#aaa;font-size:11px">1 ›</span></div>
   <div style="font-size:15px;font-weight:800;padding:12px 15px 16px;background:white;border-top:1px solid #f5f5f5">{html.escape(copy['subject'])}</div>
   <div style="background:{bg};margin:0 10px 82px;border-radius:3px;overflow:hidden;box-shadow:0 1px 8px rgba(0,0,0,.05)">
     <div style="background:#fff;padding:13px;text-align:center">{brand_mark}</div>{hero_html}
     <div style="padding:17px 16px 20px;text-align:center"><div style="font-size:9px;letter-spacing:1.2px;text-transform:uppercase;color:{p};font-weight:800">{html.escape(copy['eyebrow'])}</div><div style="font-size:21px;line-height:1.15;font-weight:850;margin:7px 0;color:{txt}">{html.escape(copy['headline'])}</div><div style="font-size:12px;line-height:1.45;color:#555">{html.escape(copy['body'])}</div>
     <div data-end="{end_iso}" style="display:flex;justify-content:center;gap:4px;margin:13px 0">{''.join(f'<div style="min-width:48px;background:{p};color:white;border-radius:6px;padding:7px 2px"><div id="td-{key}" style="font-size:18px;font-weight:850">00</div><div style="font-size:7px;opacity:.85;text-transform:uppercase">{label}</div></div>' for key,label in [('days','Tage'),('hours','Std.'),('mins','Min.'),('secs','Sek.')])}</div>
     <a href="#" onclick="return false" style="display:inline-block;background:{a};color:{txt};text-decoration:none;font-weight:800;font-size:11px;padding:10px 18px;border-radius:5px">{html.escape(copy['cta'])}</a></div>
   </div>
   <div style="position:absolute;right:13px;bottom:65px;font-size:8px;color:#9aa0a6;background:rgba(255,255,255,.88);padding:3px 5px;border-radius:5px">KI-optimiert</div>
   <div style="position:absolute;bottom:11px;left:18px;right:18px;display:flex;align-items:center;gap:17px"><div style="height:45px;flex:1;background:#fff;border-radius:24px;box-shadow:0 2px 14px #ddd;display:flex;align-items:center;justify-content:space-around;font-size:17px"><span>↪</span><span>♜</span><span>↶</span><span style="color:#6357e9">◴</span><span>•••</span></div><div style="width:45px;height:45px;border-radius:50%;background:#fff;box-shadow:0 2px 14px #ddd;display:grid;place-items:center;font-size:21px">↗</div></div>
   <div style="position:absolute;bottom:2px;left:50%;transform:translateX(-50%);width:115px;height:4px;border-radius:4px;background:#111"></div>
  </div>
 </div>
</div>
<script>(function(){{const root=document.getElementById('td-preview'),end=new Date(root.querySelector('[data-end]').dataset.end).getTime();function tick(){{const d=Math.max(0,end-Date.now()),v={{days:Math.floor(d/86400000),hours:Math.floor(d/3600000)%24,mins:Math.floor(d/60000)%60,secs:Math.floor(d/1000)%60}};Object.keys(v).forEach(k=>root.querySelector('#td-'+k).textContent=String(v[k]).padStart(2,'0'));}}tick();setInterval(tick,1000);}})();</script>"""

st.title("trustedDialog Countdown Preview")
st.caption("Unabhängiger Prototyp: Domain analysieren, CI-nahe E-Mail erzeugen und als geöffnete Mail im iPhone-Mockup darstellen.")

with st.sidebar:
    st.header("1. Kundendomain")
    domain = st.text_input("Domain oder URL", placeholder="z. B. fressnapf.de")
    analyze = st.button("Domain analysieren", type="primary", use_container_width=True)

if analyze and domain:
    st.session_state["brand_data"] = analyze_domain(domain)

data = st.session_state.get("brand_data", {})
if not data:
    st.info("Gib links eine Domain ein und starte die Analyse.")
    st.stop()

if data.get("warning"):
    st.warning(data["warning"])

copy_default = campaign_copy(data.get("domain", ""), data.get("brand", ""), data.get("description", ""))

left, right = st.columns([0.42, 0.58], gap="large")
with left:
    st.subheader("2. Kampagne & CI")
    brand = st.text_input("Markenname", value=data.get("brand", ""))
    data["brand"] = brand
    subject = st.text_input("Betreff", value=copy_default["subject"])
    eyebrow = st.text_input("Aktionslabel", value=copy_default["eyebrow"])
    headline = st.text_input("Headline", value=copy_default["headline"])
    body = st.text_area("Text", value=copy_default["body"], height=100)
    cta = st.text_input("CTA", value=copy_default["cta"])
    end_date = st.date_input("Countdown-Enddatum", value=(datetime.now() + timedelta(days=7)).date())
    end_time = st.time_input("Endzeit", value=datetime.strptime("23:59", "%H:%M").time())
    imgs = data.get("website_images", [])
    selected_image = 0
    if imgs:
        selected_image = st.selectbox("Website-Grafik", options=list(range(len(imgs))), format_func=lambda i: f"Website-Motiv {i+1}")
        st.image(imgs[selected_image], caption="Automatisch von der Website übernommen", width=260)
    hero_url = st.text_input("Optional: eigene Bild-URL überschreibt Website-Motiv", placeholder="https://…/kampagne.jpg")
    st.markdown("**Farben**")
    c1, c2 = st.columns(2)
    primary = c1.color_picker("Primär", data.get("primary", DEFAULT_COLORS["primary"]))
    accent = c2.color_picker("Akzent / CTA", data.get("accent", DEFAULT_COLORS["accent"]))
    background = c1.color_picker("Mail-Hintergrund", DEFAULT_COLORS["background"])
    text = c2.color_picker("Text", DEFAULT_COLORS["text"])

copy = {"subject": subject, "eyebrow": eyebrow, "headline": headline, "body": body, "cta": cta}
end_dt = datetime.combine(end_date, end_time)
email_html = build_email_html(data, copy, end_dt.isoformat(), {"primary":primary,"accent":accent,"background":background,"text":text}, hero_url, selected_image)

with right:
    st.subheader("3. Live Preview")
    st.components.v1.html(email_html, height=870, scrolling=True)

st.download_button("HTML-Preview herunterladen", data=email_html.encode("utf-8"), file_name=f"trustedDialog_countdown_{data.get('domain','preview').replace('.','_')}.html", mime="text/html", use_container_width=True)

with st.expander("Was die App bewusst macht"):
    st.markdown("""
- übernimmt verfügbare Branding-Signale der Kundendomain, soweit technisch abrufbar
- schlägt einen zum erkannten Geschäftsmodell passenden Aktionskontext vor
- lässt Texte, Ablaufdatum, Farben und Motiv manuell korrigieren
- zeigt einen echten, sekündlich laufenden Countdown in einer geöffneten E-Mail
- erzeugt eine eigenständige HTML-Datei für Reviews und Tests

**Hinweis:** Das ist eine visuelle Konzeptvorschau. Versandfähige interaktive E-Mail-Widgets benötigen zusätzlich eine geprüfte Mailix-/ESP-Integration und einen geeigneten Fallback für nicht unterstützende Mailclients.
""")
