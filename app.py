import base64
import html
import math
import re
from datetime import datetime, timedelta
from io import BytesIO
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
import streamlit as st
from bs4 import BeautifulSoup
from PIL import Image

st.set_page_config(page_title="trustedDialog Countdown Preview", page_icon="⏳", layout="wide")

UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"}
DEFAULT = {"primary": "#0B3C6E", "accent": "#FFD500"}


# ----------------------------------------------------------------------------
# Website-Analyse
# ----------------------------------------------------------------------------
def norm_url(v: str) -> str:
    v = v.strip()
    return v if v.startswith(("http://", "https://")) else "https://" + v


def to_data_uri(blob: bytes, ctype: str) -> str:
    return f"data:{ctype.split(';')[0]};base64,{base64.b64encode(blob).decode()}"


def fetch_image(u: str, min_w=240, min_h=120):
    try:
        r = requests.get(u, headers=UA, timeout=8)
        r.raise_for_status()
        if len(r.content) > 5_000_000:
            return None
        im = Image.open(BytesIO(r.content))
        im.load()
        w, h = im.size
        if w < min_w or h < min_h:
            return None
        ctype = r.headers.get("content-type", "image/jpeg")
        if not ctype.startswith("image/"):
            ctype = "image/jpeg"
        return {"url": u, "data": to_data_uri(r.content, ctype), "w": w, "h": h}
    except Exception:
        return None


def score_image(item, attrs, keywords):
    w, h = item["w"], item["h"]
    ratio = w / max(h, 1)
    s = min(w * h / 100000, 20)
    if 1.15 <= ratio <= 2.8:
        s += 20
    a = attrs.lower()
    if any(x in a for x in ["hero", "banner", "stage", "campaign", "teaser", "product"]):
        s += 22
    if any(x in a for x in ["logo", "icon", "sprite", "payment", "flag", "badge"]):
        s -= 40
    if any(k in a for k in keywords):
        s += 8
    return s


def short_brand(soup, host: str) -> str:
    """Kurzer Markenname: og:site_name > Domain-Label. Nie der komplette <title>."""
    site = soup.find("meta", attrs={"property": "og:site_name"}) if soup else None
    if site and site.get("content") and len(site["content"].strip()) <= 24:
        return site["content"].strip()
    label = host.split(".")[0]
    return label[:1].upper() + label[1:]


@st.cache_data(ttl=1800, show_spinner=False)
def analyze(raw: str):
    u = norm_url(raw)
    host = urlparse(u).netloc.replace("www.", "")
    out = {"url": u, "domain": host, "brand": host.split(".")[0].title(), "description": "",
           "website_images": [], **DEFAULT}
    try:
        r = requests.get(u, headers=UA, timeout=12)
        r.raise_for_status()
        soup = BeautifulSoup(r.text[:2_000_000], "html.parser")
        out["brand"] = short_brand(soup, host)
        desc = soup.find("meta", attrs={"name": re.compile("description", re.I)})
        out["description"] = desc.get("content", "") if desc else ""
        theme = soup.find("meta", attrs={"name": "theme-color"})
        if theme and re.fullmatch(r"#[0-9a-fA-F]{6}", (theme.get("content") or "").strip()):
            out["primary"] = theme["content"].strip()

        candidates, logos = [], []
        og = soup.find("meta", attrs={"property": "og:image"})
        if og and og.get("content"):
            candidates.append((urljoin(u, og["content"]), "og:image hero"))
        for tag in soup.find_all("img"):
            attrs = " ".join(str(tag.get(x, "")) for x in ["alt", "class", "id", "title"])
            src = tag.get("data-src") or tag.get("data-lazy-src") or tag.get("src")
            srcset = tag.get("srcset", "")
            if srcset:
                parts = [p.strip().split(" ")[0] for p in srcset.split(",") if p.strip()]
                src = parts[-1] if parts else src
            if src and not str(src).startswith("data:"):
                (logos if "logo" in attrs.lower() else candidates).append((urljoin(u, src), attrs))
        for tag in soup.find_all(style=re.compile("background-image", re.I)):
            m = re.search(r"url\([\"']?([^\"')]+)", tag.get("style", ""))
            if m:
                candidates.append((urljoin(u, m.group(1)), str(tag.get("class", "")) + " hero background"))

        for lu, _ in logos[:10]:
            try:
                rr = requests.get(lu, headers=UA, timeout=6)
                rr.raise_for_status()
                if rr.headers.get("content-type", "").startswith("image/") and "svg" not in rr.headers.get("content-type", ""):
                    out["logo"] = to_data_uri(rr.content, rr.headers["content-type"])
                    break
            except Exception:
                pass

        keys = [x for x in re.findall(r"[a-zäöü]{4,}", (out["description"] + " " + host).lower())][:12]
        ranked, seen = [], set()
        for iu, attrs in candidates[:70]:
            if iu in seen:
                continue
            seen.add(iu)
            item = fetch_image(iu)
            if item:
                item["score"] = score_image(item, attrs, keys)
                ranked.append(item)
        ranked.sort(key=lambda x: x["score"], reverse=True)
        out["website_images"] = ranked[:6]
    except Exception:
        out["warning"] = "Die Website konnte nur eingeschränkt analysiert werden. Ein Motiv kann alternativ per Bild-Upload ergänzt werden."
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
    if any(k in t for k in ["mode", "fashion", "schuhe", "bekleidung", "accessoires"]):
        return ("Nur noch kurze Zeit: Aktionspreise auf Mode", "Ausgewählte Favoriten zum Aktionspreis",
                "Entdecke aktuelle Styles, solange die Aktion läuft.", "Jetzt entdecken")
    return ("Nur noch kurze Zeit: Vorteil sichern", "Aktionsvorteil endet bald",
            "Entdecke ausgewählte Angebote, solange die Aktion läuft.", "Angebot ansehen")


# ----------------------------------------------------------------------------
# iPhone-Mockup (Maße 1:1 aus der Vorlage; Platzhalter statt f-String)
# ----------------------------------------------------------------------------
def seal_svg() -> str:
    pts = []
    for i in range(0, 361, 6):
        a = math.radians(i)
        r = 9.2 + 1.1 * math.cos(10 * a)
        pts.append(f"{12 + r * math.cos(a):.2f},{12 + r * math.sin(a):.2f}")
    return ('<svg class="seal" width="15" height="15" viewBox="0 0 24 24" aria-label="trustedDialog Siegel">'
            f'<polygon points="{" ".join(pts)}" fill="#467DCD" stroke="#467DCD" stroke-width="1" stroke-linejoin="round"/>'
            '<path d="M8.3 12.4l2.6 2.6 4.9-5.2" fill="none" stroke="#fff" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round"/></svg>')


CSS = """
*{box-sizing:border-box}html,body{margin:0;background:transparent}
.stage{position:relative;width:348px;height:716px;margin:0 auto;font-family:Roboto,-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;color:#111}
.sidebtn{position:absolute;background:linear-gradient(90deg,#7d7d7d,#e4e4e4 45%,#8a8a8a);border:1px solid #3a3a3a;border-radius:2px;z-index:0}
.phone{position:absolute;left:8px;top:7px;width:330px;height:702px;border-radius:54px;background:#121212;z-index:1;
 box-shadow:0 0 0 1px #0d0d0d,0 0 0 3.5px #d2d2d2,0 0 0 5px #161616}
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
.avatar{position:absolute;left:17px;top:163px;width:33px;height:33px;border-radius:50%;background:#B8DDFD;color:#0B3C6E;display:grid;place-items:center;font-size:14px;font-weight:700}
.name{position:absolute;left:61px;top:165px;max-width:150px;display:flex;align-items:center;gap:4px;color:#2b5fa8;font-size:14px;font-weight:700}
.seal{flex-shrink:0}
.name span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.date{position:absolute;left:61px;top:187px;font-size:10.5px;color:#8f8f8f}
.one{position:absolute;left:268px;top:172px;font-size:11px;color:#9b9b9b}
.chev{position:absolute;left:285px;top:174px}
.line{position:absolute;left:15px;top:217px;width:248px;border-top:1px solid #dcdcdc}
.subject{position:absolute;left:15px;top:238px;width:272px;font-size:15.5px;line-height:1.2;font-weight:700;color:#222}
.mailbody{position:absolute;left:8px;top:292px;width:288px;bottom:66px;overflow-y:auto;overflow-x:hidden;background:#fff;border:1px solid #eee;scrollbar-width:none}
.mailbody::-webkit-scrollbar{display:none}
.brandbar{height:36px;display:flex;align-items:center;justify-content:center;background:#fff;font-size:14px;font-weight:800;color:__PRIMARY__}
.brandbar span{max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.brandbar img{max-width:120px;max-height:26px;object-fit:contain}
.hero{display:block;width:100%;height:116px;object-fit:cover}
.missing{height:100px;display:grid;place-items:center;background:#eee;color:#777;font-size:10px}
.content{text-align:center;padding:10px 12px 14px}
.headline{font-size:16px;line-height:1.15;font-weight:800;color:__PRIMARY__}
.timer{display:flex;gap:4px;justify-content:center;margin:9px 0 8px}
.unit{width:50px;background:__PRIMARY__;color:#fff;border-radius:6px;padding:5px 0 4px}
.num{font-size:17px;font-weight:800;line-height:1.1;font-variant-numeric:tabular-nums}
.lab{font-size:6.5px;text-transform:uppercase;letter-spacing:.4px;opacity:.9}
.txt{font-size:9.5px;line-height:1.35;color:#555;margin:0 0 9px}
.cta{display:inline-block;background:__ACCENT__;color:__CTATEXT__;font-size:10px;font-weight:800;padding:8px 16px;border-radius:5px}
.fade{position:absolute;left:0;bottom:0;width:100%;height:92px;background:linear-gradient(rgba(243,243,243,0),#f3f3f3 78%);pointer-events:none}
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

<span class="avatar">__INITIAL__</span>
<div class="name"><span>__BRAND__</span>__SEAL__</div>
<div class="date">Heute um __DATE__</div>
<span class="one">1</span>
<svg class="chev" width="8" height="13" viewBox="0 0 8 13" fill="none" stroke="#b3b3b3" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M1.5 1.5 6.3 6.5 1.5 11.5"/></svg>
<div class="line"></div>
<div class="subject">__SUBJECT__</div>

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


def contrast_text(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#111111" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#FFFFFF"


def render(d, subject, headline, body, cta, end, primary, accent, img) -> str:
    brand = d["brand"] or d["domain"]
    now = datetime.now(ZoneInfo("Europe/Berlin"))
    esc = html.escape
    logo = (f'<img src="{d["logo"]}" alt="{esc(brand)}">' if d.get("logo") else f"<span>{esc(brand)}</span>")
    hero = (f'<img class="hero" src="{img["data"]}" alt="Website-Motiv">' if img
            else '<div class="missing">Kein Website-Motiv gefunden</div>')
    css = (CSS.replace("__PRIMARY__", primary).replace("__ACCENT__", accent)
           .replace("__CTATEXT__", contrast_text(accent)))
    repl = {
        "__NOW__": now.strftime("%H:%M"),
        "__DATE__": (now - timedelta(minutes=3)).strftime("%H:%M"),
        "__INITIAL__": esc(brand[:1].upper()), "__BRAND__": esc(brand), "__SEAL__": seal_svg(),
        "__SUBJECT__": esc(subject), "__LOGO__": logo, "__HERO__": hero,
        "__HEADLINE__": esc(headline), "__BODY__": esc(body), "__CTA__": esc(cta),
        "__END__": end.isoformat(),
    }
    body_html = BODY
    for k, v in repl.items():
        body_html = body_html.replace(k, v)
    return f"<style>{css}</style>{body_html}"


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------
if __name__ == "__main__" or True:
    st.title("trustedDialog Countdown Preview v5")
    st.caption("Domain eingeben → CI-nahe Countdown-Mail als geöffnete GMX-Mail im iPhone-Mockup.")
    with st.sidebar:
        raw = st.text_input("Domain oder URL", placeholder="z. B. fressnapf.de")
        if st.button("Domain analysieren", type="primary", use_container_width=True) and raw:
            st.session_state.data = analyze(raw)
    if "data" not in st.session_state:
        st.info("Domain eingeben und Analyse starten.")
        st.stop()

    d = dict(st.session_state.data)
    if d.get("warning"):
        st.warning(d["warning"])
    sub0, head0, body0, cta0 = copy_for(d)

    left, right = st.columns([0.43, 0.57], gap="large")
    with left:
        d["brand"] = st.text_input("Markenname (Absender)", d["brand"])
        subject = st.text_input("Betreffzeile", sub0,
                                help="Wird identisch in Mailliste und geöffneter Mail verwendet.")
        headline = st.text_input("Newsletter-Headline", head0)
        body = st.text_area("Newsletter-Text", body0, height=80)
        cta = st.text_input("CTA", cta0)
        enddate = st.date_input("Countdown-Enddatum", (datetime.now() + timedelta(days=7)).date())
        endtime = st.time_input("Endzeit", datetime.strptime("23:59", "%H:%M").time())
        imgs = d.get("website_images", [])
        chosen = None
        if imgs:
            idx = st.selectbox("Website-Motiv", range(len(imgs)),
                               format_func=lambda i: f"Motiv {i + 1} · {imgs[i]['w']}×{imgs[i]['h']}")
            chosen = imgs[idx]
            st.image(chosen["data"], width=260)
        else:
            st.error("Kein ausreichend großes Website-Motiv gefunden – bitte eigenes Bild hochladen.")
        up = st.file_uploader("Optional: eigenes Motiv", type=["png", "jpg", "jpeg", "webp"])
        if up is not None:
            blob = up.getvalue()
            im = Image.open(BytesIO(blob))
            chosen = {"data": to_data_uri(blob, up.type or "image/jpeg"), "w": im.size[0], "h": im.size[1]}
        primary = st.color_picker("Primärfarbe", d.get("primary", DEFAULT["primary"]))
        accent = st.color_picker("CTA-Farbe", d.get("accent", DEFAULT["accent"]))
    with right:
        out = render(d, subject, headline, body, cta, datetime.combine(enddate, endtime), primary, accent, chosen)
        st.components.v1.html(out, height=730, scrolling=False)
    st.download_button("HTML-Preview herunterladen", out.encode("utf-8"),
                       f"trustedDialog_countdown_{d['domain'].replace('.', '_')}.html", "text/html",
                       use_container_width=True)
