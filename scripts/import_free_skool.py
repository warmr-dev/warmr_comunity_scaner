"""Import only Skool communities whose public /about page says free."""
from __future__ import annotations
import argparse, json, re, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from uuid import uuid4
import httpx
from sqlalchemy import create_engine, text
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from community_scanner.config import get_settings
from community_scanner.invites import _SKOOL_BLOCKED
from community_scanner.normalize import normalize_url
HEADERS={'User-Agent':'Mozilla/5.0 (compatible; WarmrFreeSkoolAudit/1.0)'}
SLUG_RE=re.compile(r'(?:https?://(?:www\d*\.)?skool\.com/|"slug"\s*:\s*")([a-z0-9][a-z0-9_-]{1,40})',re.I)
FREE_RE=re.compile(r'\b(?:free|no cost|$0|0\s*/\s*month|join for free|free to join)\b',re.I)
PAID_RE=re.compile(r'(?:\$\s*[1-9]\d*(?:\.\d+)?\s*(?:/\s*(?:month|mo|year|yr))?|paid membership|pricing)',re.I)

def get_slugs(q:int)->set[str]:
    niches=['ai','marketing','business','fitness','crypto','coaching','agency','saas','trading','ecommerce','sales','investing','real estate','health','mindset','productivity']
    try:
        lines=(ROOT/'data'/'niches_usa.txt').read_text(encoding='utf-8').splitlines()
        niches += [x.strip().replace('-',' ') for x in lines if x.strip() and not x.startswith('#')]
    except OSError: pass
    urls=['https://www.skool.com/discovery']+[f'https://www.skool.com/discovery?q={x.replace(" ","+")}' for x in niches[:q]]
    out=set()
    with httpx.Client(headers=HEADERS,timeout=30,follow_redirects=True) as c:
        for i,u in enumerate(urls,1):
            try: html=c.get(u).text
            except Exception: continue
            out.update(m.group(1).lower() for m in SLUG_RE.finditer(html))
            print(f'discovery {i}/{len(urls)} unique={len(out)}',flush=True)
    return {s for s in out if s not in _SKOOL_BLOCKED and s not in {'discovery','academy','agent','amanda','amharic'}}

def inspect(slug:str):
    url=f'https://www.skool.com/{slug}/about'
    try:
        with httpx.Client(headers=HEADERS,timeout=20,follow_redirects=True) as c:
            r=c.get(url)
        if r.status_code>=400: return slug,False,'http_'+str(r.status_code),None
        html=r.text or ''
        text_blob=re.sub(r'<[^>]+>',' ',html).replace('&nbsp;',' ')
        text_blob=' '.join(text_blob.split())
        if PAID_RE.search(text_blob) and not re.search(r'free\s+(?:community|to join)',text_blob,re.I):
            return slug,False,'paid',text_blob[:500]
        if FREE_RE.search(text_blob): return slug,True,'free',text_blob[:500]
        return slug,False,'unclear',text_blob[:500]
    except Exception as e: return slug,False,'error_'+type(e).__name__,None

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--queries',type=int,default=120); ap.add_argument('--workers',type=int,default=24); args=ap.parse_args()
    e=create_engine(get_settings().database_url,pool_pre_ping=True)
    with e.connect() as c: existing={r[0] for r in c.execute(text('SELECT canonical_key FROM community_scanner'))}
    slugs=get_slugs(args.queries); print('slugs',len(slugs),flush=True)
    free=[]; counts={}
    with ThreadPoolExecutor(max_workers=args.workers) as p:
        fs=[p.submit(inspect,s) for s in slugs]
        for f in as_completed(fs):
            slug,ok,reason,preview=f.result(); counts[reason]=counts.get(reason,0)+1
            if ok: free.append((slug,preview))
    rows=[]
    for slug,preview in free:
        n=normalize_url(f'https://www.skool.com/{slug}')
        if n.is_blocked or n.canonical_key in existing: continue
        existing.add(n.canonical_key)
        rows.append({'id':str(uuid4()),'canonical_key':n.canonical_key,'canonical_domain':n.canonical_domain,'platform':'skool','platform_id':slug,'website':f'https://www.skool.com/{slug}','name':slug,'niche':None,'audience':None,'geo':'USA','join_url':f'https://www.skool.com/{slug}','source_queries':json.dumps(['skool:free/about']),'raw_signals':json.dumps({'source':'skool_about','free_access':True,'about_preview':preview})})
    sql=text('''INSERT INTO community_scanner (id,canonical_key,canonical_domain,platform,platform_id,website,name,niche,audience,geo,join_url,contacts,access_status,value_score,value_tier,relevance_score,source_queries,raw_signals,sync_status) VALUES (:id,:canonical_key,:canonical_domain,:platform,:platform_id,:website,:name,:niche,:audience,:geo,:join_url,'{}'::jsonb,'join',35,'medium',0,CAST(:source_queries AS jsonb),CAST(:raw_signals AS jsonb),'pending') ON CONFLICT (canonical_key) DO NOTHING''')
    inserted=0
    with e.begin() as c:
        for i in range(0,len(rows),500): inserted += int(c.execute(sql,rows[i:i+500]).rowcount or 0)
        total=c.execute(text('SELECT count(*) FROM community_scanner')).scalar()
    print(f'done found={len(free)} new={len(rows)} inserted={inserted} total={total} reasons={counts}',flush=True)
if __name__=='__main__': main()
