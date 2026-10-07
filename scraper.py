import argparse,json,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
BASE='https://globoplay.globo.com'; CATALOG=BASE+'/catalogo/'
STATE=Path('channels.json'); PLAYLIST=Path('lista.m3u'); DIAG=Path('diagnostico.json')
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36'
KNOWN={'TV Globo':'/tv-globo/ao-vivo/6120663/','Multishow':'/multishow/ao-vivo/','GloboNews':'/globonews/ao-vivo/','sportv':'/sportv/ao-vivo/','GNT':'/gnt/ao-vivo/','Globoplay Novelas':'/globoplay-novelas/ao-vivo/','Gloob':'/gloob/ao-vivo/','Canal Brasil':'/canal-brasil/ao-vivo/','Canal OFF':'/canal-off/ao-vivo/','Modo Viagem':'/modo-viagem/ao-vivo/'}
BAD=('api.globovideos.com/videos/','/callback/','wmplayerplaylistloaded')
M3U=re.compile(r'https?://[^"\'<>\s]+\.m3u8(?:\?[^"\'<>\s]*)?',re.I); MPD=re.compile(r'https?://[^"\'<>\s]+\.mpd(?:\?[^"\'<>\s]*)?',re.I)
def now(): return datetime.now(timezone.utc).isoformat()
def valid(u):
    x=u.lower(); return u.startswith(('http://','https://')) and not any(b in x for b in BAD) and ('.m3u8' in x or '.mpd' in x)
def discover():
    found={BASE+p:{'name':n,'url':BASE+p} for n,p in KNOWN.items()}
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True); page=b.new_page(user_agent=UA)
        try:
            page.goto(CATALOG,wait_until='domcontentloaded',timeout=25000); page.wait_for_timeout(2500)
            soup=BeautifulSoup(page.content(),'html.parser')
            for a in soup.select('a[href]'):
                href=urljoin(CATALOG,a['href']).split('#')[0]; path=urlparse(href).path.lower(); text=' '.join(a.stripped_strings).strip()
                if href.startswith(BASE+'/') and ('/canais/' in path or '/canal/' in path): found.setdefault(href,{'name':text or path.rstrip('/').split('/')[-1].replace('-',' ').title(),'url':href})
        except Exception as e: print('Catálogo:',e,flush=True)
        b.close()
    return list(found.values())
def worker(ch):
    hits=set()
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True); page=b.new_page(user_agent=UA)
        def on_response(r):
            if valid(r.url): hits.add(r.url)
        page.on('response',on_response)
        try:
            page.goto(ch['url'],wait_until='domcontentloaded',timeout=12000); page.wait_for_timeout(1800)
            for u in M3U.findall(page.content())+MPD.findall(page.content()):
                if valid(u): hits.add(u)
            try:
                for u in page.evaluate("performance.getEntriesByType('resource').map(x=>x.name)"):
                    if valid(u): hits.add(u)
            except Exception: pass
        except Exception: pass
        b.close()
    s=requests.Session(); s.headers['User-Agent']=UA
    for u in list(hits)[:8]:
        try:
            r=s.get(u,timeout=8,allow_redirects=True); body=r.text[:20000]
            if r.status_code==200 and (('#EXTM3U' in body) or ('<MPD' in body.upper())): return {'name':ch['name'],'group':ch['name'],'page':ch['url'],'stream':r.url,'checked_at':now()}
        except Exception: pass
    return None
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--verbose',action='store_true'); args=ap.parse_args()
    chans=discover(); print('Páginas descobertas:',len(chans),flush=True); fresh=[]
    with ThreadPoolExecutor(max_workers=5) as ex:
        fs={ex.submit(worker,c):c for c in chans}
        for i,f in enumerate(as_completed(fs),1):
            c=fs[f]
            try:
                r=f.result()
                if r: fresh.append(r); print(f'[{i}/{len(chans)}] OK {r["name"]}',flush=True)
                elif args.verbose: print(f'[{i}/{len(chans)}] -- {c["name"]}',flush=True)
            except Exception as e: print(f'[{i}/{len(chans)}] ERRO {c["name"]}: {e}',flush=True)
    try: old=json.loads(STATE.read_text()).get('channels',[])
    except Exception: old=[]
    if fresh:
        fresh.sort(key=lambda x:x['name'].lower()); STATE.write_text(json.dumps({'updated_at':now(),'channels':fresh},ensure_ascii=False,indent=2))
        out=['#EXTM3U']
        for c in fresh:
            slug=re.sub(r'[^a-z0-9]+','-',c['name'].lower()).strip('-')
            out += [f'#EXTINF:-1 tvg-id="globoplay-{slug}" tvg-name="{c["name"]}" tvg-logo="https://upload.wikimedia.org/wikipedia/commons/7/7d/Globo_logo.png" group-title="{c["group"]}",{c["name"]}',c['stream']]
        PLAYLIST.write_text('\n'.join(out)+'\n',encoding='utf-8')
    else: print('Nenhum stream verificável; playlist anterior preservada.',flush=True)
    DIAG.write_text(json.dumps({'updated_at':now(),'discovered_pages':len(chans),'verified_streams':len(fresh),'previous_streams':len(old),'playlist_preserved':not bool(fresh)},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
