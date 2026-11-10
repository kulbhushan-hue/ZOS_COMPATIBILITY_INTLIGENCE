"""Optional, operator-initiated Playwright rendering for vendor JS report shells.

Never accesses authenticated pages or bypasses access controls. User should first
run the regular crawler so that robots/public URL restrictions are assessed.
Raw snapshots can then be safely replayed with ``deep_scraper.py --reparse-cache``.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup
from multi_vendor import safe_public_url
from source_cache_v11 import ResponseCache, describe_document


def is_report_shell(url, body):
    """Conservative indicator for *potentially* JS-populated IBM reports."""
    if not re.search(r'(?i)ibm\.com/software/reports/compatibility/', url):
        return False
    soup=BeautifulSoup(body, 'lxml')
    txt=soup.get_text(' ',strip=True)
    scripts=len(soup.find_all('script'))
    return not soup.find('table') and scripts>=2 and len(txt)<1800


def candidate_rows(csv_path):
    """Use actual successful crawl URLs, not arbitrary URLs from the internet."""
    with Path(csv_path).open(encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            if r.get('vendor')=='IBM' and r.get('state')=='Read' and re.search(r'/software/reports/compatibility/',r.get('url','')):
                yield r


def allowed_by_robots(url, session):
    parts=urlsplit(url)
    robots=f'{parts.scheme}://{parts.hostname}/robots.txt'
    if not safe_public_url(robots,'IBM'):return False
    try:
        response=session.get(robots,timeout=10,allow_redirects=False)
        if response.status_code!=200:return False  # fail closed
        parser=RobotFileParser()
        parser.parse(response.text[:100000].splitlines())
        return parser.can_fetch('zOS-Compatibility-Intelligence/1.0',url)
    except requests.RequestException:
        return False


def capture(output, limit=40, delay=1.5, timeout_ms=25000, force=False):
    """Produce real rendered HTML snapshots for offline reparse; no scraping assertions."""
    from playwright.sync_api import sync_playwright  # optional package, installed separately
    output=Path(output); src=output/'vendor_scraping_results.csv'
    if not src.is_file():raise FileNotFoundError('Run the ordinary source crawl before browser capture')
    cache=ResponseCache(output/'source_cache')
    manifest=[]
    previous={(e['vendor'],e['url']):e for e,_ in cache.entries()}
    choices=list(candidate_rows(src))
    with requests.Session() as session, sync_playwright() as pw:
        # On standard Windows installs, Edge often works without downloading Chromium.
        # Never silently install a >1 GB browser while the user is launching Streamlit.
        browser=None
        failures=[]
        for options in ({'channel':'msedge'}, {'channel':'chrome'}, {}):
            try:
                browser=pw.chromium.launch(headless=True, **options)
                break
            except Exception as exc:
                failures.append(f"{options.get('channel','bundled chromium')}: {str(exc)[:140]}")
        if browser is None:
            raise RuntimeError('No compatible installed browser for optional capture. ' + '; '.join(failures))
        context=browser.new_context(user_agent='zOS-Compatibility-Intelligence/1.0',accept_downloads=False)
        try:
            for record in choices[:limit]:
                url=record['url'];prior=previous.get(('IBM',url));reason=''
                if not safe_public_url(url,'IBM'):reason='Rejected: unsafe URL'
                elif not allowed_by_robots(url,session):reason='Rejected: robots unavailable or disallow'
                elif prior and not force and not is_report_shell(url, next((b for e,b in cache.entries() if e['url']==url and e['vendor']=='IBM'),b'')):
                    reason='Skipped: original response is not an SPCR shell'
                if reason:
                    manifest.append(dict(vendor='IBM',url=url,state='Skipped',reason=reason));continue
                page=context.new_page()
                try:
                    page.goto(url,wait_until='domcontentloaded',timeout=timeout_ms)
                    try:page.wait_for_load_state('networkidle',timeout=min(timeout_ms,8000))
                    except Exception:pass
                    html=page.content().encode('utf-8')
                    final=page.url
                    if not safe_public_url(final,'IBM'):
                        raise ValueError('Redirect outside allowed IBM vendor domain')
                    entry=cache.save('IBM',url,final,'text/html; rendered-by-playwright',html,time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
                    info=describe_document('IBM',url,'text/html',html,entry['sha256'],'Rendered')
                    manifest.append(dict(vendor='IBM',url=url,state='Captured',reason=info['reason'],
                                         bytes=len(html),tables=info['html_tables'],sha256=entry['sha256']))
                except Exception as exc:
                    manifest.append(dict(vendor='IBM',url=url,state='Failed',reason=f'{type(exc).__name__}: {str(exc)[:180]}'))
                finally:page.close()
                if delay:time.sleep(delay)
        finally:browser.close()
    target=output/'vendor_browser_capture.csv'
    with target.open('w',encoding='utf-8-sig',newline='') as f:
        fields=['vendor','url','state','reason','bytes','tables','sha256']
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(manifest)
    return {'candidates':len(choices),'attempted':len(manifest),'captured':sum(x['state']=='Captured' for x in manifest),
            'report':str(target),'note':'Run deep_scraper.py --reparse-cache to process rendered snapshots'}


def main():
    p=argparse.ArgumentParser(description='Optional IBM SPCR browser snapshot capture; no dashboard changes.')
    p.add_argument('--output',default='exports/deep');p.add_argument('--limit',type=int,default=40)
    p.add_argument('--delay',type=float,default=1.5);p.add_argument('--force',action='store_true')
    a=p.parse_args();print(json.dumps(capture(a.output,max(1,a.limit),max(0.5,a.delay),force=a.force),indent=2))
if __name__=='__main__':main()
