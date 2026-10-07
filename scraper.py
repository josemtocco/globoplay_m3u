import argparse,json,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
BASE='https://globoplay.globo.com'; CATALOG=BASE+'/catalogo/'
BAD=('api.globovideos.com/videos/','playlist/without_resources/callback/','wmplayerplaylistloaded','callback/wmplayer')
M3U_RE=re.compile(r'https?://[^\"\'\s<>]+\.m3u8(?:\?[^\"\'\s<>]*)?',re.I)
MPD_RE=re.compile(r'https?://[^\"\'\s<>]+\.mpd(?:\?[^\"\'\s<>]*)?',re.I)
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36'
KNOWN={'TV Globo':'/tv-globo/ao-vivo/6120663/','Multishow':'/multishow/ao-vivo/','GloboNews':'/globonews/ao-vivo/','sportv':'/sportv/ao-vivo/','GNT':'/gnt/ao-vivo/','Globoplay Novelas':'/globoplay-novelas/ao-vivo/','Gloob':'/gloob/ao-vivo/','Canal Brasil':'/canal-brasil/ao-vivo/','Canal OFF':'/canal-off/ao-vivo/','Modo Viagem':'/modo-viagem/ao-vivo/'}
def now(): return datetime.now(timezone.utc).isoformat()
def good(u): return bool(u and u.startswith(('http://','https://')) and not any(x in u.lower() for x in BAD) and re.search(r'\.(m3u8|mpd)(?:$|[?#])',u,re.I))
def norm(u,b=BASE): return urljoin(b,u).split('#')[0]
def discover(page):
 page.goto(CATALOG,wait_until='domcontentloaded',timeout=60000)
 try: page.wait_for_load_state('networkidle',timeout=12000)
 except: pass
 for _ in range(4): page.mouse.wheel(0,2500); page.wait_for_timeout(1000)
 soup=BeautifulSoup(page.content(),'html.parser'); out={}
 for a in soup.select('a[href]'):
  u=norm(a.get('href',''),CATALOG); path=urlparse(u).path.rstrip('/'); text=' '.join(a.stripped_strings).strip()
  if not u.startswith(BASE+'/') or path in ('','/','/catalogo'): continue
  hay=(text+' '+path).lower()
  if '/canais/' in path or '/canal/' in path or any(k.lower() in hay for k in KNOWN): out[u]={'name':text or path.rsplit('/',1)[-1].replace('-',' ').title(),'url':u}
 for n,p in KNOWN.items(): out.setdefault(BASE+p,{'name':n,'url':BASE+p})
 return sorted(out.values(),key=lambda x:x['name'].lower())
def page_streams(page,ch):
 found=set()
 def resp(r):
  u=r.url; ct=(r.headers.get('content-type') or '').lower()
  if good(u) or 'mpegurl' in ct or 'dash+xml' in ct: found.add(u)
 page.on('response',resp)
 try:
  page.goto(ch['url'],wait_until='domcontentloaded',timeout=60000)
  try: page.wait_for_load_state('networkidle',timeout=10000)
  except: pass
  for sel in ["button[aria-label*='play' i]","button[title*='play' i]","[data-testid*='play' i]","video"]:
   try:
    x=page.locator(sel).first
    if x.count() and x.is_visible(): x.click(timeout=1200); page.wait_for_timeout(2500); break
   except: pass
  page.wait_for_timeout(3500)
  try:
   for u in page.evaluate("performance.getEntriesByType('resource').map(x=>x.name)"):
    if good(u): found.add(u)
  except: pass
  html=page.content()
  found.update(M3U_RE.findall(html)); found.update(MPD_RE.findall(html))
 finally:
  try: page.remove_listener('response',resp)
  except: pass
 return [u for u in found if good(u)]
def verify(u,s):
 try:
  r=s.get(u,headers={'User-Agent':UA,'Accept':'*/*'},timeout=15,allow_redirects=True)
  if r.status_code!=200:return None
  b=r.text[:16000]; ct=(r.headers.get('content-type') or '').lower()
  if '.m3u8' in u.lower() and ('#EXTM3U' in b or 'mpegurl' in ct): return r.url
  if '.mpd' in u.lower() and ('<MPD' in b.upper() or 'dash+xml' in ct): return r.url
 except requests.RequestException: pass
 return None
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--verbose',action='store_true'); a=ap.parse_args()
 old=json.loads(Path('channels.json').read_text()) if Path('channels.json').exists() else {'channels':[]}; session=requests.Session(); session.headers['User-Agent']=UA
 with sync_playwright() as p:
  b=p.chromium.launch(headless=True); ctx=b.new_context(user_agent=UA,locale='pt-BR',viewport={'width':1440,'height':1000}); page=ctx.new_page(); pages=discover(page); print('Paginas descobertas:',len(pages)); fresh=[]
  for i,ch in enumerate(pages,1):
   print(f'[{i}/{len(pages)}] {ch["name"]}')
   for u in page_streams(page,ch):
    v=verify(u,session)
    if v:
     fresh.append({'name':ch['name'],'group':ch['name'],'page':ch['url'],'stream':v,'checked_at':now()}); print('  OK:',v[:180]); break
   else: print('  sem manifesto publico verificavel')
  b.close()
 if fresh:
  Path('channels.json').write_text(json.dumps({'updated_at':now(),'channels':fresh},ensure_ascii=False,indent=2))
  out=['#EXTM3U']
  for c in sorted(fresh,key=lambda x:x['name'].lower()):
   slug=re.sub('[^a-z0-9]+','-',c['name'].lower()).strip('-') or 'canal'; logo='https://upload.wikimedia.org/wikipedia/commons/7/7d/Globo_logo.png'
   out.append(f'#EXTINF:-1 tvg-id="globoplay-{slug}" tvg-name="{c["name"]}" tvg-logo="{logo}" group-title="{c["group"]}",{c["name"]}\n{c["stream"]}')
  Path('lista.m3u').write_text('\n'.join(out)+'\n')
  result={'ok':True,'updated_at':now(),'discovered_pages':len(pages),'verified_streams':len(fresh),'previous_streams':len(old.get('channels',[])),'note':'Somente HLS/DASH verificados; callbacks api.globovideos.com sao rejeitados.'}
 else:
  result={'ok':False,'updated_at':now(),'discovered_pages':len(pages),'verified_streams':0,'preserved_previous_playlist':Path('lista.m3u').exists(),'note':'Nenhum manifesto verificavel; playlist anterior preservada.'}
 Path('diagnostico.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)); print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
