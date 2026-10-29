import base64
import html
import json
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

        logo_candidates = []
        for tag in soup.find_all(["img", "link", "meta"]):
            attrs = " ".join(str(v) for v in tag.attrs.values()).lower()
            src = tag.get("src") or tag.get("href") or tag.get("content")
            if src and ("logo" in attrs or "og:image" in attrs or "icon" in attrs):
                logo_candidates.append(urljoin(url, src))
        for candidate in logo_candidates[:8]:
            data_uri = fetch_image_data_uri(candidate)
            if data_uri:
                result["logo"] = data_uri
                palette = extract_palette(data_uri)
                if palette:
                    result.update(palette)
                break
    except Exception as exc:
        result["warning"] = f"Die Website konnte nicht vollständig analysiert werden: {exc.__class__.__name__}. Die Vorschau nutzt neutrale Startwerte."
        result.setdefault("brand", result["domain"].split(".")[0].title())
        result.setdefault("description", "")
    return result


def campaign_copy(domain: str, brand: str, description: str):
    text = f"{domain} {brand} {description}".lower()
    if any(k in text for k in ["reise", "travel", "hotel", "urlaub", "flug"]):
        return {"eyebrow": "Nur für kurze Zeit", "headline": "Jetzt Vorfreude sichern", "body": "Buche dein ausgewähltes Angebot, bevor der Aktionszeitraum endet.", "cta": "Angebot entdecken", "subject": "Dein Angebot endet bald"}
    if any(k in text for k in ["mode", "fashion", "bekleidung", "schuhe", "shop"]):
        return {"eyebrow": "Limited Offer", "headline": "Dein Style. Dein Zeitfenster.", "body": "Sichere dir ausgewählte Favoriten zum Aktionspreis, solange die Aktion läuft.", "cta": "Jetzt entdecken", "subject": "Nur noch kurze Zeit: ausgewählte Styles"}
    if any(k in text for k in ["tier", "pet", "hund", "katze"]):
        return {"eyebrow": "Aktionsangebot", "headline": "Vorräte rechtzeitig auffüllen", "body": "Entdecke ausgewählte Lieblingsprodukte zum zeitlich begrenzten Vorteil.", "cta": "Vorteil sichern", "subject": "Countdown für deinen Aktionsvorteil"}
    if any(k in text for k in ["foto", "photo", "druck", "print"]):
        return {"eyebrow": "Endspurt", "headline": "Deine Erinnerungen verdienen einen Platz", "body": "Gestalte dein Fotoprodukt innerhalb des Aktionszeitraums und sichere dir den Vorteil.", "cta": "Jetzt gestalten", "subject": "Nur noch kurze Zeit für dein Fotoprojekt"}
    return {"eyebrow": "Zeitlich limitiert", "headline": "Jetzt Vorteil sichern", "body": "Entdecke das aktuelle Angebot, bevor der Aktionszeitraum endet.", "cta": "Angebot ansehen", "subject": "Dein Vorteil endet bald"}


def build_email_html(data, copy, end_iso, colors, hero_url=""):
    brand = html.escape(data.get("brand") or data.get("domain", "Marke"))
    logo = data.get("logo", "")
    hero = fetch_image_data_uri(hero_url) if hero_url else ""
    p, a, bg, txt = [safe_hex(colors[k], DEFAULT_COLORS[k]) for k in ["primary", "accent", "background", "text"]]
    logo_html = f'<img src="{logo}" alt="{brand}" style="max-width:150px;max-height:42px;object-fit:contain">' if logo else f'<div style="font-size:24px;font-weight:800;color:{p}">{brand}</div>'
    hero_html = f'<img src="{hero}" alt="Kampagnenmotiv" style="width:100%;height:190px;object-fit:cover;display:block">' if hero else f'<div style="height:175px;background:linear-gradient(135deg,{p},{a});display:flex;align-items:center;justify-content:center;color:white;font-size:52px">✦</div>'
    return f"""
<div id="td-preview" style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;background:#e9edf2;padding:18px;color:{txt}">
  <div style="max-width:390px;margin:auto;background:#111;border:10px solid #111;border-radius:46px;padding:10px;box-shadow:0 18px 45px rgba(0,0,0,.25)">
    <div style="height:24px;color:white;font-size:11px;display:flex;justify-content:space-between;padding:0 15px;align-items:center"><span>9:41</span><span>● ᴡɪꜰɪ ▰</span></div>
    <div style="background:white;border-radius:31px;overflow:hidden;min-height:720px">
      <div style="padding:13px 16px;border-bottom:1px solid #e8e8e8;display:flex;justify-content:space-between;color:#1d5fd0"><span>‹ Postfach</span><span>•••</span></div>
      <div style="padding:14px 18px 10px"><div style="font-weight:750;font-size:16px">{html.escape(copy['subject'])}</div><div style="font-size:12px;color:#6b7280;margin-top:4px">{brand} · an mich</div></div>
      <div style="background:{bg}">
        <div style="background:white;padding:18px;text-align:center">{logo_html}</div>
        {hero_html}
        <div style="padding:24px 22px 28px;text-align:center">
          <div style="font-size:12px;letter-spacing:1.6px;text-transform:uppercase;color:{p};font-weight:800">{html.escape(copy['eyebrow'])}</div>
          <h1 style="font-size:28px;line-height:1.12;margin:10px 0 12px;color:{txt}">{html.escape(copy['headline'])}</h1>
          <p style="font-size:15px;line-height:1.5;margin:0 0 18px;color:#4b5563">{html.escape(copy['body'])}</p>
          <div data-end="{end_iso}" style="display:flex;justify-content:center;gap:7px;margin:18px 0 22px">
            {''.join(f'<div style="min-width:58px;background:{p};color:white;border-radius:11px;padding:10px 5px"><div id="td-{key}" style="font-size:24px;font-weight:800">00</div><div style="font-size:9px;opacity:.8;text-transform:uppercase">{label}</div></div>' for key,label in [('days','Tage'),('hours','Std.'),('mins','Min.'),('secs','Sek.')])}
          </div>
          <a href="#" onclick="return false" style="display:inline-block;background:{a};color:{txt};text-decoration:none;font-weight:800;padding:13px 24px;border-radius:8px">{html.escape(copy['cta'])}</a>
          <div style="font-size:10px;color:#8a8f98;margin-top:22px">Exemplarische trustedDialog Countdown Preview</div>
        </div>
      </div>
    </div>
  </div>
</div>
<script>
(function(){{
 const root=document.getElementById('td-preview');
 const end=new Date(root.querySelector('[data-end]').dataset.end).getTime();
 function tick(){{
   const d=Math.max(0,end-Date.now());
   const vals={{days:Math.floor(d/86400000),hours:Math.floor(d/3600000)%24,mins:Math.floor(d/60000)%60,secs:Math.floor(d/1000)%60}};
   Object.keys(vals).forEach(k=>root.querySelector('#td-'+k).textContent=String(vals[k]).padStart(2,'0'));
 }}
 tick(); setInterval(tick,1000);
}})();
</script>"""

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
    hero_url = st.text_input("Optional: Bild-URL", placeholder="https://…/kampagne.jpg")
    st.markdown("**Farben**")
    c1, c2 = st.columns(2)
    primary = c1.color_picker("Primär", data.get("primary", DEFAULT_COLORS["primary"]))
    accent = c2.color_picker("Akzent / CTA", data.get("accent", DEFAULT_COLORS["accent"]))
    background = c1.color_picker("Mail-Hintergrund", DEFAULT_COLORS["background"])
    text = c2.color_picker("Text", DEFAULT_COLORS["text"])

copy = {"subject": subject, "eyebrow": eyebrow, "headline": headline, "body": body, "cta": cta}
end_dt = datetime.combine(end_date, end_time)
email_html = build_email_html(data, copy, end_dt.isoformat(), {"primary":primary,"accent":accent,"background":background,"text":text}, hero_url)

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
