import base64, html, re
from datetime import datetime, timedelta
from io import BytesIO
from urllib.parse import urljoin, urlparse
import requests
import streamlit as st
from bs4 import BeautifulSoup
from PIL import Image

st.set_page_config(page_title='trustedDialog Countdown Preview', page_icon='⏳', layout='wide')
UA={'User-Agent':'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15'}
DEFAULT={'primary':'#0B3C6E','accent':'#FFD500','background':'#FFFFFF','text':'#111111'}

def url(v):
 v=v.strip(); return v if v.startswith(('http://','https://')) else 'https://'+v

def data_uri(blob,ctype): return f"data:{ctype.split(';')[0]};base64,{base64.b64encode(blob).decode()}"

def fetch_image(u):
 try:
  r=requests.get(u,headers=UA,timeout=8); r.raise_for_status()
  if len(r.content)>5_000_000:return None
  im=Image.open(BytesIO(r.content)); im.load(); w,h=im.size
  if w<240 or h<120:return None
  return {'url':u,'data':data_uri(r.content,r.headers.get('content-type','image/jpeg')),'w':w,'h':h}
 except Exception:return None

def score_image(item,attrs,keywords):
 w,h=item['w'],item['h']; ratio=w/max(h,1); s=min(w*h/100000,20)
 if 1.15<=ratio<=2.8:s+=20
 a=attrs.lower()
 if any(x in a for x in ['hero','banner','stage','campaign','teaser','product']):s+=22
 if any(x in a for x in ['logo','icon','sprite','payment','flag','badge']):s-=40
 if any(k in a for k in keywords):s+=8
 return s

@st.cache_data(ttl=1800,show_spinner=False)
def analyze(raw):
 u=url(raw); host=urlparse(u).netloc.replace('www.',''); out={'url':u,'domain':host,'brand':host.split('.')[0].title(),**DEFAULT}
 try:
  r=requests.get(u,headers=UA,timeout=12); r.raise_for_status(); soup=BeautifulSoup(r.text[:2_000_000],'html.parser')
  if soup.title: out['brand']=re.split(r'[|–—-]',soup.title.get_text(' ',strip=True))[0].strip() or out['brand']
  desc=soup.find('meta',attrs={'name':re.compile('description',re.I)}); out['description']=desc.get('content','') if desc else ''
  candidates=[]; logos=[]
  og=soup.find('meta',attrs={'property':'og:image'})
  if og and og.get('content'): candidates.append((urljoin(u,og['content']),'og:image hero'))
  for tag in soup.find_all('img'):
   attrs=' '.join([str(tag.get(x,'')) for x in ['alt','class','id','title']])
   src=tag.get('data-src') or tag.get('data-lazy-src') or tag.get('src')
   srcset=tag.get('srcset','')
   if srcset:
    parts=[p.strip().split(' ')[0] for p in srcset.split(',') if p.strip()]; src=parts[-1] if parts else src
   if src:
    target=(urljoin(u,src),attrs)
    (logos if 'logo' in attrs.lower() else candidates).append(target)
  for tag in soup.find_all(style=re.compile('background-image',re.I)):
   m=re.search(r'url\(["\']?([^"\')]+)',tag.get('style',''))
   if m:candidates.append((urljoin(u,m.group(1)),str(tag.get('class',''))+' hero background'))
  for lu,_ in logos[:10]:
   try:
    rr=requests.get(lu,headers=UA,timeout=6); rr.raise_for_status(); out['logo']=data_uri(rr.content,rr.headers.get('content-type','image/png')); break
   except Exception:pass
  keys=[x for x in re.findall(r'[a-zäöü]{4,}',(out['description']+' '+host).lower()) if x not in {'www','https'}][:12]
  ranked=[]; seen=set()
  for iu,attrs in candidates[:70]:
   if iu in seen:continue
   seen.add(iu); item=fetch_image(iu)
   if item: item['score']=score_image(item,attrs,keys); ranked.append(item)
  ranked.sort(key=lambda x:x['score'],reverse=True); out['website_images']=ranked[:6]
 except Exception as e: out['warning']='Die Website konnte nur eingeschränkt analysiert werden. Bilder können alternativ per URL ergänzt werden.'
 return out

def copy_for(d):
 t=(d.get('domain','')+' '+d.get('brand','')+' '+d.get('description','')).lower()
 if any(k in t for k in ['fressnapf','tier','pet','hund','katze']): return ('Nur für kurze Zeit: Aktionsvorteile sichern','Lieblingsprodukte zum Aktionsvorteil','Sichere dir ausgewählte Angebote für deinen tierischen Alltag, solange die Aktion läuft.','Angebote entdecken')
 if any(k in t for k in ['foto','photo','print','druck']): return ('Nur noch kurze Zeit für deinen Aktionsvorteil','Jetzt Aktionsvorteil sichern','Gestalte dein Fotoprodukt innerhalb des Aktionszeitraums und sichere dir den aktuellen Vorteil.','Jetzt gestalten')
 if any(k in t for k in ['reise','travel','hotel','urlaub']): return ('Dein Reiseangebot endet bald','Dein Reisevorteil endet bald','Entdecke das aktuelle Angebot und sichere dir deinen Vorteil innerhalb des Aktionszeitraums.','Angebot entdecken')
 return ('Nur noch kurze Zeit: Vorteil sichern','Aktionsvorteil endet bald','Entdecke ausgewählte Angebote und sichere dir deinen Vorteil, solange die Aktion läuft.','Angebot ansehen')

def render(d,subject,headline,body,cta,end,primary,accent,img):
 brand=html.escape(d['brand']); logo=d.get('logo'); pic=img.get('data','') if img else ''
 logo_html=f'<img src="{logo}" style="max-width:115px;max-height:32px">' if logo else f'<b style="color:{primary}">{brand}</b>'
 hero=f'<img src="{pic}" style="display:block;width:100%;height:178px;object-fit:cover" alt="Website-Motiv">' if pic else '<div class="missing">Kein Website-Motiv gefunden</div>'
 return f'''<style>
*{{box-sizing:border-box}}body{{margin:0}}.stage{{width:348px;height:662px;position:relative;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial;color:#111}}.sidebtn{{position:absolute;background:linear-gradient(90deg,#777,#dedede,#333);border:1px solid #222;border-radius:2px;z-index:0}}.phone{{position:absolute;left:8px;top:5px;width:330px;height:650px;border-radius:52px;background:linear-gradient(120deg,#777,#111 18%,#050505 75%,#888);box-shadow:0 2px 2px #555}}.l1,.l2,.l3,.bezel{{position:absolute;border-radius:49px;inset:2px;border:1px solid #e8e8e8}}.l2{{inset:5px;border-color:#333}}.l3{{inset:7px;border-color:#999}}.bezel{{inset:9px;background:#070707;border:0}}.screen{{position:absolute;left:13px;top:13px;width:304px;height:624px;background:#fff;border-radius:39px;overflow:hidden}}.abs{{position:absolute}}.time{{left:25px;top:14px;font-size:10px;font-weight:700}}.island{{left:105px;top:10px;width:99px;height:22px;background:#050505;border-radius:18px}}.island i{{position:absolute;right:8px;top:7px;width:7px;height:7px;border-radius:50%;background:#142347;box-shadow:0 0 3px #2853a0 inset}}.signal{{left:222px;top:17px}}.wifi{{left:245px;top:17px}}.battery{{left:268px;top:13px;background:#111;color:#fff;border-radius:4px;font-size:7px;font-weight:700;padding:3px 5px}}.top{{position:absolute;top:46px;width:100%;height:52px;border-bottom:1px solid #eee}}.back{{position:absolute;left:8px;top:8px;width:37px;height:37px;border-radius:50%;box-shadow:0 2px 13px #ddd;display:grid;place-items:center;font-size:28px;font-weight:200}}.title{{position:absolute;left:52px;top:9px;font-size:14px;font-weight:750}}.mail{{position:absolute;left:52px;top:26px;color:#aaa;font-size:9px}}.pager{{position:absolute;right:9px;top:7px;width:78px;height:39px;border-radius:22px;box-shadow:0 2px 13px #ddd;display:flex;justify-content:space-around;align-items:center;font-size:23px}}.tools{{position:absolute;top:98px;width:100%;height:35px;background:#f0f2f5;border-bottom:1px solid #ddd}}.pill{{position:absolute;left:8px;top:9px;font-size:8px;color:#3272bd;background:#fff;padding:3px 8px;border-radius:11px}}.unsub{{position:absolute;right:12px;top:10px;color:#1a66c4;font-size:9px}}.senderrow{{position:absolute;top:133px;width:100%;height:67px;background:#fff}}.avatar{{position:absolute;left:15px;top:20px;width:30px;height:30px;border-radius:50%;display:grid;place-items:center;background:#b8ddfd;color:#0b3c6e;font-size:13px}}.name{{position:absolute;left:54px;top:18px;color:#467dcc;font-size:13px;font-weight:750}}.date{{position:absolute;left:54px;top:36px;color:#999;font-size:9px}}.count{{position:absolute;right:19px;top:20px;color:#aaa;font-size:10px}}.subject{{position:absolute;top:200px;left:0;width:100%;height:43px;padding:14px 15px;font-size:14px;font-weight:800;border-top:1px solid #f5f5f5}}.mailbody{{position:absolute;top:243px;left:7px;width:290px;height:310px;overflow:hidden;background:#fff;border-top:1px solid #eee}}.brand{{height:47px;display:flex;justify-content:center;align-items:center}}.missing{{height:120px;display:grid;place-items:center;background:#eee;color:#777;font-size:11px}}.content{{text-align:center;padding:10px 13px 13px}}.headline{{font-size:18px;line-height:1.12;font-weight:850;color:{primary}}}.body{{font-size:10px;line-height:1.35;color:#555;margin:6px 0}}.timer{{display:flex;gap:3px;justify-content:center;margin:8px 0}}.unit{{background:{primary};color:#fff;min-width:47px;padding:5px 2px;border-radius:5px}}.num{{font-size:16px;font-weight:850}}.lab{{font-size:6px;text-transform:uppercase}}.cta{{display:inline-block;background:{accent};color:#111;font-size:9px;font-weight:800;padding:8px 15px;border-radius:4px}}.ai{{position:absolute;right:9px;bottom:72px;color:#9aa0a6;font-size:7px}}.dock{{position:absolute;left:15px;right:15px;bottom:17px;height:46px;display:flex;gap:15px}}.dockbar{{flex:1;border-radius:24px;background:#fff;box-shadow:0 2px 13px #ddd;display:flex;justify-content:space-around;align-items:center;font-size:17px}}.compose{{width:46px;border-radius:50%;box-shadow:0 2px 13px #ddd;display:grid;place-items:center;font-size:21px}}.home{{left:94px;bottom:5px;width:115px;height:4px;background:#111;border-radius:4px}}
</style><div id="td" class="stage"><div class="sidebtn" style="left:4px;top:129px;width:5px;height:22px"></div><div class="sidebtn" style="left:4px;top:174px;width:5px;height:44px"></div><div class="sidebtn" style="left:4px;top:235px;width:5px;height:44px"></div><div class="sidebtn" style="left:331.5px;top:208px;width:6px;height:71px"></div><div class="phone"><div class="l1"></div><div class="l2"></div><div class="l3"></div><div class="bezel"></div><div class="screen"><span class="abs time">09:35</span><span class="abs island"><i></i></span><span class="abs signal">▮▮▮▮</span><span class="abs wifi">◔</span><span class="abs battery">93</span><div class="top"><span class="back">‹</span><span class="title">1 von 5</span><span class="mail">trusteddialog99@gmx.net</span><span class="pager">⌃⌄</span></div><div class="tools"><span class="pill">Newsletter</span><span class="unsub">Newsletter abbestellen&nbsp; ⚙</span></div><div class="senderrow"><span class="avatar">{brand[0]}</span><span class="name">{brand} ✓</span><span class="date">Heute um 09:32</span><span class="count">1&nbsp; ›</span></div><div class="subject">{html.escape(subject)}</div><div class="mailbody"><div class="brand">{logo_html}</div>{hero}<div class="content"><div class="headline">{html.escape(headline)}</div><div class="body">{html.escape(body)}</div><div class="timer" data-end="{end.isoformat()}">{''.join(f'<div class="unit"><div class="num" id="{k}">00</div><div class="lab">{l}</div></div>' for k,l in [('days','Tage'),('hours','Std.'),('mins','Min.'),('secs','Sek.')])}</div><span class="cta">{html.escape(cta)}</span></div></div><span class="ai">KI-optimiert</span><div class="dock"><div class="dockbar"><span>↪</span><span>♜</span><span>↶</span><span style="color:#5b57be">◴</span><span>•••</span></div><div class="compose">↗</div></div><span class="abs home"></span></div></div></div><script>(function(){{let r=document.getElementById('td'),e=new Date(r.querySelector('[data-end]').dataset.end).getTime();function t(){{let d=Math.max(0,e-Date.now()),v={{days:Math.floor(d/86400000),hours:Math.floor(d/3600000)%24,mins:Math.floor(d/60000)%60,secs:Math.floor(d/1000)%60}};Object.keys(v).forEach(k=>r.querySelector('#'+k).textContent=String(v[k]).padStart(2,'0'))}}t();setInterval(t,1000)}}</script>'''

st.title('trustedDialog Countdown Preview v3')
st.caption('Domainbasierte Kampagnenvorschau mit Website-Motiv und pixelnaher geöffneter GMX-Mail.')
with st.sidebar:
 raw=st.text_input('Domain oder URL',placeholder='z. B. fressnapf.de')
 if st.button('Domain analysieren',type='primary',use_container_width=True) and raw: st.session_state.data=analyze(raw)
if 'data' not in st.session_state: st.info('Domain eingeben und Analyse starten.'); st.stop()
d=st.session_state.data
if d.get('warning'):st.warning(d['warning'])
sub0,head0,body0,cta0=copy_for(d)
a,b=st.columns([.43,.57],gap='large')
with a:
 d['brand']=st.text_input('Markenname',d['brand'])
 subject=st.text_input('Betreffzeile',sub0,help='Diese eine Betreffzeile wird identisch in Mailliste und geöffneter Mail verwendet.')
 headline=st.text_input('Newsletter-Headline',head0); body=st.text_area('Newsletter-Text',body0); cta=st.text_input('CTA',cta0)
 enddate=st.date_input('Countdown-Enddatum',(datetime.now()+timedelta(days=7)).date()); endtime=st.time_input('Endzeit',datetime.strptime('23:59','%H:%M').time())
 imgs=d.get('website_images',[]); idx=0
 if imgs:
  idx=st.selectbox('Automatisch priorisiertes Website-Motiv',range(len(imgs)),format_func=lambda i:f'Motiv {i+1} · {imgs[i]["w"]}×{imgs[i]["h"]}')
  st.image(imgs[idx]['data'],width=280)
 else: st.error('Auf dieser Website wurde kein ausreichend großes, direkt abrufbares Motiv gefunden.')
 primary=st.color_picker('Primärfarbe',d.get('primary',DEFAULT['primary'])); accent=st.color_picker('CTA-Farbe',d.get('accent',DEFAULT['accent']))
with b:
 out=render(d,subject,headline,body,cta,datetime.combine(enddate,endtime),primary,accent,imgs[idx] if imgs else None)
 st.components.v1.html(out,height=690,scrolling=False)
st.download_button('HTML-Preview herunterladen',out.encode(),f'trustedDialog_countdown_{d["domain"].replace(".","_")}.html','text/html',use_container_width=True)
