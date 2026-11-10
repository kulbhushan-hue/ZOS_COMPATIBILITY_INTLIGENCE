"""Backend-only, resumable deep extraction of approved vendor links.

Run: python deep_scraper.py --max-pages 300 --depth 2 --output exports/deep
No compatibility claims are inferred from arbitrary mentions. PTF IDs are only
associated with the source section/row containing them. Vendor authentication
and robots policies are respected; the crawler does not bypass access controls.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import re
import shutil
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import pandas as pd
import requests
from bs4 import BeautifulSoup

from multi_vendor import _get_public, safe_public_url, OFFICIAL, extract_text
from compatibility_db import SOURCES
from quality import ptf_ids, maintenance_availability, installation_status, match_key
from workbook_data import load_workbook, NAME, vendor_name
from vendor_assertions import extract_extra_assertions, extract_official_document_tables
from multi_vendor import extract_bmc_support_matrix, extract_action_release_matrix
from vendor_adapters_v10 import extract_vendor_matrix, extract_ibm_report_table
from vendor_content_v13 import extract_v13
from vendor_facts_v14 import extract_document_facts
from source_cache_v11 import ResponseCache, describe_document
from hybrid_coverage_v15 import build_reports

USER_AGENT = 'zOS-Compatibility-Intelligence/1.0 (respectful document collection)'
OS_PATTERN = re.compile(r'(?i)\bz\s*/\s*OS\s*(?:v|version\s*)?([235])(?:\.|\s*r)([125])\b')
MAINT = re.compile(r'\b(?:PTFs?|APARs?|USERMODs?|SYSMODs?|FIXCAT|FMID|maintenance|prerequisite|fixes|service)\b',re.I)
LINK_TERMS = ('ptf','apar','usermod','sysmod','fixcat','additional information',
              'compatibility','support matrix','software requirements','maintenance',
              'prerequisite','supported platforms','release notes','technical requirements',
              'product lifecycle','software support','minimum levels')
BLOCK_LINK = ('logout','login','signin','signup','privacy','terms','cart','contact','social','facebook','twitter')
CSV_FIELDS = {
 'all_vendor_extracted_compatibility.csv':['vendor','product','release','zos_version','compatibility','evidence_level','source_url','source_excerpt','source_timestamp','document_sha256','match_status'],
 'all_vendor_extracted_ptfs.csv':['vendor','product','release','zos_version','ptf_id','maintenance_type','publication_status','installation_status','component','source_url','source_excerpt','source_timestamp','evidence_level','match_status'],
 'vendor_scraping_results.csv':['vendor','url','parent_url','depth','state','format','http_status','checked_at','tables','compatibility_rows','ptf_rows','discovered_links','message','final_url','response_sha256','cache_status'],
 'vendor_failed_links.csv':['vendor','url','parent_url','state','http_status','message','checked_at'],
 'vendor_source_evidence.csv':['vendor','product','release','zos_version','evidence_kind','source_url','source_excerpt','source_timestamp','document_sha256','match_status'],
 'vendor_conflicting_claims.csv':['vendor','product','release','zos_version','observed_statuses','source_urls','review_reason'],
 'vendor_release_observations.csv':['vendor','product','release','zos_version','assertion','observation_type','source_url','source_excerpt','source_timestamp','reason'],
 'vendor_consolidated_ptfs.csv':['vendor','product','release','zos_version','ptf_id','publication_status','installation_status','source_count','source_urls','review_status'],
 'vendor_source_quality.csv':['vendor','url','state','http_status','compatibility_rows','ptf_rows','release_unspecified_rows','result_class','raw_compatibility_rows','raw_ptf_rows','unique_compatibility_rows','unique_ptf_rows','response_sha256','cache_status'],
 'vendor_document_facts.csv':['vendor','product','release','zos_version','fact_type','value','source_url','source_excerpt','source_timestamp','verification','evidence_scope'],
 'vendor_page_diagnostics.csv':['vendor','url','format','response_sha256','cache_status','bytes','html_tables','table_rows','title','script_tags','potential_dynamic_content','reason'],
}

def now():return datetime.now(timezone.utc).isoformat()
def text(v):return re.sub(r'\s+',' ',str(v or '')).strip()
def normurl(url):
    url=urldefrag(text(url))[0]
    return url.rstrip('/') if url else ''
def _domain(url):return (urlsplit(url).hostname or '').lower().rstrip('.')
def same_domain(url,root):
    a,b=_domain(url),_domain(root)
    return bool(a and b and (a==b or a.endswith('.'+b) or b.endswith('.'+a)))

def inventory_and_queue(root:Path, worklist:Path|None=None, source_csv:Path|None=None):
    """All *distinct* official URLs from workbook, baseline CSV, and optional worklist.

    Critically this does NOT cap each vendor to two sources. Each starting URL is
    tied to its original product if supplied, so evidence can be matched later.
    """
    _, amxt, directory = load_workbook(root/NAME)
    inventory=[]; candidates=[]
    def add(v,p,r,u,origin):
        v=vendor_name(v);p=text(p);r=text(r);u=normurl(u)
        if not v or not u or not safe_public_url(u,v):return
        candidates.append({'vendor':v,'product':p,'release':r,'url':u,'origin':origin})
    for _,row in amxt.iterrows():
        v=vendor_name(row.get('Vendor',''));p=text(row.get('Product',''));r=text(row.get('Version',''))
        if v and p:inventory.append({'vendor':v,'product':p,'release':r})
        add(v,p,r,row.get('Link to verify compatibility report',''),'AMXT')
    for v,u in directory.items():add(v,'','',u,'Workbook Sheet1')
    for v,label,u,desc in SOURCES:add(v,'','',u,'Curated official source')
    for fname in (root/'data').glob('*_compat.csv'):
        try:df=pd.read_csv(fname,dtype=str,keep_default_na=False)
        except Exception:continue
        cols={c.casefold().strip():c for c in df.columns}
        for _,r in df.iterrows():
            v=text(r.get(cols.get('vendor','Vendor'),fname.stem.split('_')[0]))
            p=text(r.get(cols.get('product','Product'),''))
            ver=text(r.get(cols.get('vrm','VRM'),''))
            if v and p:inventory.append({'vendor':vendor_name(v),'product':p,'release':ver})
            for c in df.columns:
                if 'link' in c.lower() or 'source' in c.lower():
                    val=text(r.get(c,''))
                    if val.startswith(('http://','https://')):add(v,p,ver,val,'vendor CSV')
    if worklist and worklist.is_file():
        with worklist.open(encoding='utf-8-sig',newline='') as stream:
          for row in csv.DictReader(stream):
            inventory.append({'vendor':vendor_name(row.get('Vendor','')),'product':row.get('Product',''), 'release':row.get('Release','')})
            add(row.get('Vendor',''),row.get('Product',''),row.get('Release',''),row.get('Approved source URL',''),'Product worklist')
    if source_csv and source_csv.is_file():
        with source_csv.open(encoding='utf-8-sig',newline='') as stream:
          for row in csv.DictReader(stream):
            add(row.get('Vendor',''),row.get('Product',''),row.get('Release',''),row.get('URL',''),'Operator CSV')
    # Dedupe URLs, while preserving all product associations.
    groups={}
    for c in candidates:
        key=(c['vendor'].casefold(),c['url'])
        if key not in groups:groups[key]={**c,'contexts':[]}
        if c['product'] and (c['product'],c['release']) not in groups[key]['contexts']:
            groups[key]['contexts'].append((c['product'],c['release']))
    unique={}
    for row in inventory:
        v,p,r=map(text,(row['vendor'],row['product'],row['release']))
        if v and p:unique[match_key(v,p,r)]=(v,p,r)
    byvendor=defaultdict(list)
    for v,p,r in unique.values():byvendor[v].append({'product':p,'release':r})
    return list(groups.values()),byvendor


def versions(s):
    return sorted({f'{a}.{b}' for a,b in OS_PATTERN.findall(text(s))})
def explicit_status(s):
    t=text(s).casefold()
    if re.fullmatch(r'(yes|y|supported|compatible|certified|✔|✓|x)',t):return 'Yes'
    if re.fullmatch(r'(no|n|unsupported|not compatible|not supported)',t):return 'No'
    if re.fullmatch(r'(in progress|under evaluation|pending)',t):return 'In Progress'
    return ''

def match_product(vendor,product,release,byvendor):
    """Never fuzzy-promote status: exact vendor+name+release only."""
    if not product or not release:return 'Release unspecified'
    key=match_key(vendor,product,release)
    return 'Exact inventory match' if any(match_key(vendor,p['product'],p['release'])==key for p in byvendor.get(vendor,[])) else 'No exact inventory match'

def product_in_text(vendor,chunk,byvendor,preferred=()):
    """Find the most specific named product in a local section, not in whole-page text."""
    opts=[]
    for item in byvendor.get(vendor,[]):
        name=text(item['product']); rel=text(item['release'])
        if len(name)<5:continue
        if re.search(r'(?<![A-Za-z0-9])'+re.escape(name)+r'(?![A-Za-z0-9])',chunk,re.I):
            opts.append((len(name),name,rel))
    if opts:
        opts.sort(reverse=True)
        _,p,r=opts[0]
        return p,r
    for p,r in preferred:
        if p:return p,r
    return '',''

def find_fmid(chunk):
    m=re.search(r'(?i)\b(?:FMID|component)\s*[:=#-]?\s*([A-Z0-9]{6,9})\b',chunk)
    return m.group(1) if m else ''

def extract_html_legacy(body:bytes, vendor:str, url:str, byvendor, contexts, stamp:str):
    soup=BeautifulSoup(body,'lxml')
    for tag in soup(['script','style','nav','footer']):tag.decompose()
    digest=hashlib.sha256(body).hexdigest(); comps=[];ptfs=[];ev=[]
    def addptf(chunk,kind,source,product='',release='',version=''):
        ids=ptf_ids(chunk)
        if not ids:return
        p,r=(product,release) if product else product_in_text(vendor,chunk,byvendor,contexts)
        vset=[version] if version else versions(chunk)
        if not vset:vset=['Not stated']
        for ver in vset:
            for ident in ids:
                ptfs.append(dict(vendor=vendor,product=p,release=r,zos_version=ver,ptf_id=ident,
                    maintenance_type=kind,publication_status=maintenance_availability(chunk),
                    installation_status=installation_status(chunk),component=find_fmid(chunk),
                    source_url=source,source_excerpt=text(chunk)[:700],source_timestamp=stamp,
                    evidence_level='HTML local section; applicability requires review',
                    match_status=match_product(vendor,p,r,byvendor)))
    # Handle semantic HTML tables with explicit z/OS column headers, release and cell values.
    for table in soup.find_all('table'):
        rows=table.find_all('tr')
        if len(rows)<2:continue
        head=[text(c.get_text(' ',strip=True)) for c in rows[0].find_all(['th','td'],recursive=False)]
        if len(head)<2:continue
        indexed=[(i,versions(h)) for i,h in enumerate(head)]
        oscols={i:vs for i,vs in indexed if vs}
        for tr in rows[1:]:
            cells=[text(c.get_text(' ',strip=True)) for c in tr.find_all(['td','th'],recursive=False)]
            if not cells:continue
            rowtxt=' | '.join(cells)
            p,r=product_in_text(vendor,rowtxt,byvendor,contexts)
            if not p and len(cells[0])>3:p=cells[0][:160];r=''
            if oscols:
                for i,oslist in oscols.items():
                    if i>=len(cells):continue
                    status=explicit_status(cells[i]);
                    if not status:continue
                    for os in oslist:
                        comps.append(dict(vendor=vendor,product=p,release=r,zos_version=os,
                            compatibility=status,evidence_level='Explicit HTML table cell; release must be independently matched',
                            source_url=url,source_excerpt=rowtxt[:700],source_timestamp=stamp,
                            document_sha256=digest,match_status=match_product(vendor,p,r,byvendor)))
            # z/OS version row / product header columns (BMC style)
            elif versions(cells[0]):
                for i,h in enumerate(head[1:],1):
                    if i>=len(cells):continue
                    status=explicit_status(cells[i])
                    if not status:continue
                    product,release=product_in_text(vendor,h,byvendor,contexts)
                    if not product:product=h
                    for os in versions(cells[0]):
                        comps.append(dict(vendor=vendor,product=product,release=release,zos_version=os,
                            compatibility=status,evidence_level='Explicit vendor support matrix; release may be unspecified',
                            source_url=url,source_excerpt=rowtxt[:700],source_timestamp=stamp,
                            document_sha256=digest,match_status=match_product(vendor,product,release,byvendor)))
            if MAINT.search(rowtxt):addptf(rowtxt,'PTF/APAR reference',url,p,r)
    # Broadcom-like linked anchors: extract until next section anchor, with local table contents.
    for a in soup.find_all('a',href=True):
        label=text(a.get_text(' ',strip=True)); href=a.get('href','').strip()
        if not href or not any(t in (label+' '+href).casefold() for t in LINK_TERMS):continue
        dest=urljoin(url,href)
        if href.startswith('#'):
            target=soup.find(id=href[1:]) or soup.find('a',attrs={'name':href[1:]})
            if target:
                parts=[];cursor=target
                for _ in range(35):
                    cursor=cursor.find_next(['tr','p','div','li','h2','h3','h4','a'])
                    if not cursor:break
                    if cursor.name=='a' and (cursor.has_attr('name') or cursor.has_attr('id')) and parts:break
                    if cursor.name=='tr':parts.append(text(cursor.get_text(' ',strip=True)))
                    elif cursor.name in ('p','li','h2','h3','h4'):parts.append(text(cursor.get_text(' ',strip=True)))
                    if sum(map(len,parts))>4500:break
                chunk=' '.join(parts)
                if chunk:addptf(chunk,'Linked maintenance section',dest)
    # Paragraph-sized local context; never blindly assign a page-wide PTF to all products.
    for tag in soup.find_all(['p','li','h2','h3','h4']):
        chunk=text(tag.get_text(' ',strip=True))
        if not 10<len(chunk)<2000:continue
        if MAINT.search(chunk) and ptf_ids(chunk):addptf(chunk,'Local maintenance statement',url)
    # vendor adapters retained, with explicit evidence-level labels.
    adapters=[]
    if vendor=='BMC':adapters+=extract_bmc_support_matrix(body,url)
    if vendor=='Action Software International':adapters+=extract_action_release_matrix(body,url)
    adapters+=extract_extra_assertions(vendor,body,url)
    for a in adapters:
        os=text(a.get('zos_version'));p=text(a.get('product'));r=text(a.get('vrm'))
        evidence=text(a.get('evidence_level'))
        assertion=text(a.get('compatibility'))
        if assertion in ('Yes','No','In Progress') and os in ('2.5','3.1','3.2'):
            comps.append(dict(vendor=vendor,product=p,release=r,zos_version=os,compatibility=assertion,
                evidence_level=evidence,source_url=url,source_excerpt=text(a.get('required_level') or a.get('source_text') or a.get('note'))[:700],
                source_timestamp=stamp,document_sha256=digest,match_status=match_product(vendor,p,r,byvendor)))
        for ident in ptf_ids(a.get('maintenance_ids','')):
            ptfs.append(dict(vendor=vendor,product=p,release=r,zos_version=os or 'Not stated',ptf_id=ident,
                maintenance_type='Published requirement',publication_status='Unknown',installation_status='Unknown',
                component='',source_url=url,source_excerpt=text(a.get('required_level'))[:700],source_timestamp=stamp,
                evidence_level=evidence,match_status=match_product(vendor,p,r,byvendor)))
    for c in comps:
        ev.append(dict(vendor=vendor,product=c['product'],release=c['release'],zos_version=c['zos_version'],
            evidence_kind='Compatibility table',source_url=url,source_excerpt=c['source_excerpt'],
            source_timestamp=stamp,document_sha256=digest,match_status=c['match_status']))
    for p in ptfs:
        ev.append(dict(vendor=vendor,product=p['product'],release=p['release'],zos_version=p['zos_version'],
            evidence_kind='Maintenance ID '+p['ptf_id'],source_url=p['source_url'],source_excerpt=p['source_excerpt'],
            source_timestamp=stamp,document_sha256=digest,match_status=p['match_status']))
    return comps,ptfs,ev,len(soup.find_all('table')),soup


from safe_extract_v8 import extract_html_safe as extract_html, safe_install_status, explicit_line_identity, scoped_fixcat_version, valid_product_name

def extract_pdf(body:bytes,vendor,url,byvendor,contexts,stamp):
    raw,fmt=extract_text(body,'application/pdf')
    digest=hashlib.sha256(body).hexdigest();comps=[];ptfs=[];ev=[]
    # Existing PDF-specific parser handles structured tabular sources.
    assertions=extract_official_document_tables(vendor,raw,url)
    for a in assertions:
        p=text(a.get('product'));r=text(a.get('vrm'));os=text(a.get('zos_version'))
        c=text(a.get('compatibility'))
        if c in ('Yes','No','In Progress') and os in ('3.2','3.1','2.5'):
            comps.append(dict(vendor=vendor,product=p,release=r,zos_version=os,compatibility=c,
                evidence_level=text(a.get('evidence_level')),source_url=url,
                source_excerpt=text(a.get('required_level') or a.get('note'))[:700],source_timestamp=stamp,
                document_sha256=digest,match_status=match_product(vendor,p,r,byvendor)))
    for line in raw.splitlines():
        chunk=text(line)
        ids=ptf_ids(chunk)
        if not ids:continue
        p,r=explicit_line_identity(vendor,chunk,byvendor)
        scoped,has_fixcat=scoped_fixcat_version(chunk)
        if not p or not r:
            ev.append(dict(vendor=vendor,product='',release='',zos_version='Not stated',
                evidence_kind='Unassigned PDF maintenance mention: '+', '.join(ids),
                source_url=url,source_excerpt=chunk[:700],source_timestamp=stamp,document_sha256=digest,
                match_status='Review: product/release not established'))
            continue
        for os in (scoped if has_fixcat else versions(chunk)) or ['Not stated']:
            for ident in ids:
                ptfs.append(dict(vendor=vendor,product=p,release=r,zos_version=os,ptf_id=ident,
                    maintenance_type='PDF line reference',publication_status=maintenance_availability(chunk),
                    installation_status=safe_install_status(chunk),component=find_fmid(chunk),source_url=url,
                    source_excerpt=chunk[:700],source_timestamp=stamp,evidence_level='PDF text; local context only',
                    match_status=match_product(vendor,p,r,byvendor)))
    for c in comps:ev.append(dict(vendor=vendor,product=c['product'],release=c['release'],zos_version=c['zos_version'],evidence_kind='Compatibility table',source_url=url,source_excerpt=c['source_excerpt'],source_timestamp=stamp,document_sha256=digest,match_status=c['match_status']))
    for p in ptfs:ev.append(dict(vendor=vendor,product=p['product'],release=p['release'],zos_version=p['zos_version'],evidence_kind='Maintenance ID '+p['ptf_id'],source_url=url,source_excerpt=p['source_excerpt'],source_timestamp=stamp,document_sha256=digest,match_status=p['match_status']))
    return comps,ptfs,ev,0,None


def relevant_links(soup,base,vendor,root_url,max_links=20):
    if soup is None:return []
    ranked={}
    for a in soup.find_all('a',href=True):
        label=text(a.get_text(' ',strip=True));href=text(a['href'])
        if not href or href.startswith(('#','mailto:','javascript:')):continue
        url=normurl(urljoin(base,href))
        if not url or url==normurl(base):continue
        # Permit cross-subdomain official links (e.g. docs.vendor.com to support.vendor.com).
        # safe_public_url below still enforces the vendor domain allowlist.
        if not (same_domain(url,root_url) or (vendor in OFFICIAL and safe_public_url(url,vendor))):continue
        if not safe_public_url(url,vendor):continue
        val=(label+' '+url).casefold()
        if any(term in val for term in BLOCK_LINK):continue
        score=sum(2 if term in label.casefold() else 1 for term in LINK_TERMS if term in val)
        if score<1:continue
        if any(x in url.lower() for x in ('.zip','.exe','.jar','.png','.jpg','.svg','.mp4')):continue
        ranked[url]=max(ranked.get(url,0),score)
    return [u for u,_ in sorted(ranked.items(),key=lambda x:(-x[1],x[0]))[:max_links]]


def unique_rows(records,fields):
    out={}
    for r in records:
        # exclude scrape time; newer page evidence wins on identical claims
        key=tuple(text(r.get(k,'')) for k in fields)
        out[key]=r
    return list(out.values())


def conflicting_claims(rows):
    """Report contradictory claims without picking a winner or hiding source evidence."""
    grouped=defaultdict(list)
    for row in rows:
        key=tuple(text(row.get(k,'')) for k in ('vendor','product','release','zos_version'))
        if all(key):grouped[key].append(row)
    output=[]
    for key,records in grouped.items():
        statuses=sorted(set(text(r.get('compatibility')) for r in records if text(r.get('compatibility'))))
        if len(statuses)>1:
            output.append(dict(zip(('vendor','product','release','zos_version'),key),
                observed_statuses='; '.join(statuses),
                source_urls='; '.join(sorted({text(r.get('source_url')) for r in records if text(r.get('source_url'))})),
                review_reason='Conflicting source values — do not auto-promote this product/release'))
    return output


def consolidate_ptfs(rows):
    """One worklist claim per vendor/product/release/OS/PTF; all source URLs retained.

    Does not infer requirement, availability, or installation from conflicting sources.
    """
    groups=defaultdict(list)
    for row in rows:
        key=tuple(text(row.get(k)) for k in ('vendor','product','release','zos_version','ptf_id'))
        if not all(key):continue
        groups[key].append(row)
    result=[]
    for key,group in sorted(groups.items()):
        urls=sorted(set(text(x.get('source_url')) for x in group if text(x.get('source_url'))))
        pubs=set(text(x.get('publication_status')) for x in group if text(x.get('publication_status')))
        inst=set(text(x.get('installation_status')) for x in group if text(x.get('installation_status')))
        ambiguous=(len(pubs)>1 or len(inst)>1 or key[3]=='Not stated')
        result.append(dict(zip(('vendor','product','release','zos_version','ptf_id'),key),
            publication_status=next(iter(pubs)) if len(pubs)==1 else 'Review: inconsistent statements',
            installation_status=next(iter(inst)) if len(inst)==1 else 'Unknown',
            source_count=len(urls),source_urls='; '.join(urls),
            review_status='Needs applicability/status review' if ambiguous else 'Source claims consolidated; installation not independently verified'))
    return result


def source_quality(scrapes,observations,compatibility=(),ptfs=()):
    """Report UNIQUE accepted evidence per URL; raw parser counts are separate.

    Duplicate URL aliases may correctly reference the same rows. Per-URL totals
    must not be summed as if they were distinct claims across the crawl.
    """
    byurl=defaultdict(set)
    for row in observations:
        byurl[(text(row.get('vendor')),text(row.get('source_url'))) ].add(
            (text(row.get('product')),text(row.get('zos_version')),text(row.get('assertion')),text(row.get('source_excerpt'))))
    counts=defaultdict(lambda:{'c':set(),'p':set()})
    for row in compatibility:
        counts[(text(row.get('vendor')),text(row.get('source_url')))]['c'].add(
            tuple(text(row.get(k)) for k in ('vendor','product','release','zos_version','compatibility','source_excerpt')))
    for row in ptfs:
        counts[(text(row.get('vendor')),text(row.get('source_url')))]['p'].add(
            tuple(text(row.get(k)) for k in ('vendor','product','release','zos_version','ptf_id')))
    out=[]
    for row in scrapes:
        vendor,url=text(row.get('vendor')),text(row.get('url'))
        key=(vendor,url)
        # URL redirects are separately recorded; parsing evidence uses final URL.
        final=text(row.get('final_url')) or url
        key=(vendor,final)
        c=len(counts[key]['c']);pt=len(counts[key]['p'])
        obs=len(byurl[key]);state=text(row.get('state'))
        classification=('Blocked or failed' if state.startswith('Blocked') else
                        'Exact structured extraction' if c or pt else
                        'Evidence-only (release not established)' if obs else
                        'Read, no usable structured assertions')
        out.append(dict(vendor=vendor,url=url,state=state,http_status=row.get('http_status',''),
            compatibility_rows=c,ptf_rows=pt,release_unspecified_rows=obs,result_class=classification,
            raw_compatibility_rows=row.get('compatibility_rows',0),raw_ptf_rows=row.get('ptf_rows',0),
            unique_compatibility_rows=c,unique_ptf_rows=pt,response_sha256=row.get('response_sha256',''),
            cache_status=row.get('cache_status','')))
    return out


def save_csv(path,rows,fields):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)


class DeepCrawler:
    def __init__(self, output:Path, byvendor, session=None, delay=0.7, timeout=15,
                 depth=2, max_pages=250, max_links=12, respect_robots=True):
        self.output=Path(output);self.byvendor=byvendor;self.session=session or requests.Session()
        self.delay=max(0,float(delay));self.timeout=timeout;self.depth=depth;self.max_pages=max_pages
        self.max_links=max_links;self.respect_robots=respect_robots;self.robots={};self.last={}
        self.state=self.output/'deep_scrape_checkpoint.json';self.rows={k:[] for k in CSV_FIELDS};self.seen=set()
        self.queue=deque()
        self.cache=ResponseCache(self.output/'source_cache')
        if self.state.exists():
            state=json.loads(self.state.read_text(encoding='utf-8'))
            self.seen=set(tuple(x) for x in state.get('seen',[]))
            self.queue=deque(state.get('queue',[]))
        for fn,fields in CSV_FIELDS.items():
            path=self.output/fn
            if path.exists():
                with path.open(encoding='utf-8-sig',newline='') as f:self.rows[fn]=list(csv.DictReader(f))
    def seed(self,candidates):
        keys={(q['vendor'],q['url']) for q in self.queue}
        for c in candidates:
            key=(c['vendor'],c['url'])
            if key not in keys and key not in self.seen:
                self.queue.append({**c,'depth':0,'parent_url':'','root_url':c['url']});keys.add(key)
    def allowed_robots(self,url):
        if not self.respect_robots:return True
        host=_domain(url)
        if host not in self.robots:
            robots_url=f'{urlsplit(url).scheme}://{host}/robots.txt'
            parser=RobotFileParser()
            try:
                # Restrict robots fetch to known public/vendor address as well.
                if not safe_public_url(robots_url):raise ValueError('Unsafe robots URL')
                response=self.session.get(robots_url,timeout=min(self.timeout,6),allow_redirects=False)
                if response.status_code==200:parser.parse(response.text[:100000].splitlines())
                else:parser.parse([])
            except Exception:parser.parse([])
            self.robots[host]=parser
        return self.robots[host].can_fetch(USER_AGENT,url)
    def persist(self):
        self.output.mkdir(parents=True,exist_ok=True)
        for fn,fields in CSV_FIELDS.items():
            if fn in ('vendor_conflicting_claims.csv','vendor_consolidated_ptfs.csv','vendor_source_quality.csv'):continue
            if fn=='all_vendor_extracted_compatibility.csv':keys=('vendor','product','release','zos_version','compatibility','source_url','source_excerpt')
            elif fn=='all_vendor_extracted_ptfs.csv':keys=('vendor','product','release','zos_version','ptf_id','source_url')
            elif fn=='vendor_scraping_results.csv':keys=('vendor','url')
            elif fn=='vendor_failed_links.csv':keys=('vendor','url')
            elif fn=='vendor_page_diagnostics.csv':keys=('vendor','url','response_sha256')
            elif fn=='vendor_document_facts.csv':keys=('vendor','product','release','zos_version','fact_type','value','source_url','source_excerpt')
            else:keys=('vendor','product','release','zos_version','evidence_kind','source_url','source_excerpt')
            self.rows[fn]=unique_rows(self.rows[fn],keys)
            save_csv(self.output/fn,self.rows[fn],fields)
        consolidated=consolidate_ptfs(self.rows['all_vendor_extracted_ptfs.csv'])
        self.rows['vendor_consolidated_ptfs.csv']=consolidated
        save_csv(self.output/'vendor_consolidated_ptfs.csv',consolidated,CSV_FIELDS['vendor_consolidated_ptfs.csv'])
        quality=source_quality(self.rows['vendor_scraping_results.csv'],self.rows['vendor_release_observations.csv'],self.rows['all_vendor_extracted_compatibility.csv'],self.rows['all_vendor_extracted_ptfs.csv'])
        self.rows['vendor_source_quality.csv']=quality
        save_csv(self.output/'vendor_source_quality.csv',quality,CSV_FIELDS['vendor_source_quality.csv'])
        conflicts=conflicting_claims(self.rows['all_vendor_extracted_compatibility.csv'])
        self.rows['vendor_conflicting_claims.csv']=conflicts
        save_csv(self.output/'vendor_conflicting_claims.csv',conflicts,CSV_FIELDS['vendor_conflicting_claims.csv'])
        tmp=self.state.with_suffix('.tmp')
        tmp.write_text(json.dumps({'seen':sorted(map(list,self.seen)),'queue':list(self.queue)},indent=2),encoding='utf-8')
        tmp.replace(self.state)
    def reparse_cache(self, vendor_filter=''):
        """Rebuild extracted outputs from archived raw responses, without network calls.

        Keeps cache immutable and does NOT mistake cached data for fresh vendor checks.
        """
        cached=list(self.cache.entries())
        if not cached:
            raise ValueError('No verified cached responses available; existing exports were preserved')
        retained={'vendor_scraping_results.csv','vendor_failed_links.csv'}
        for key in self.rows:
            if key not in retained:self.rows[key]=[]
        for entry,body in cached:
            vendor=entry['vendor'];url=entry['url'];final=entry.get('final_url',url)
            if vendor_filter and vendor.casefold()!=vendor_filter.casefold():continue
            stamp=entry.get('fetched_at','');kind=entry.get('content_type','text/html')
            contexts=entry.get('contexts',[])
            if 'pdf' in kind or final.lower().split('?')[0].endswith('.pdf'):
                c,p,e,tables,_=extract_pdf(body,vendor,final,self.byvendor,contexts,stamp);fmt='PDF';claims=[];notes=[]
            else:
                c,p,e,tables,_=extract_html(body,vendor,final,self.byvendor,contexts,stamp);fmt='HTML'
                claims,notes=extract_vendor_matrix(body,vendor,final,self.byvendor,stamp)
                if vendor=='IBM':
                    ic,io=extract_ibm_report_table(body,final,self.byvendor,stamp)
                    claims+=ic;notes+=io
                vc13,vo13,vp13=extract_v13(body,vendor,final,self.byvendor,stamp)
                claims+=vc13;notes+=vo13;p+=vp13
            self.rows['all_vendor_extracted_compatibility.csv']+=c+claims
            self.rows['all_vendor_extracted_ptfs.csv']+=p
            self.rows['vendor_source_evidence.csv']+=e
            if fmt=='HTML':self.rows['vendor_document_facts.csv']+=extract_document_facts(body,vendor,final,stamp)
            self.rows['vendor_release_observations.csv']+=notes
            digest=entry['sha256']
            self.rows['vendor_page_diagnostics.csv'].append(describe_document(vendor,url,kind,body,digest,'Replayed'))
            existing=next((r for r in self.rows['vendor_scraping_results.csv'] if r.get('vendor')==vendor and r.get('url')==url),None)
            if existing is None:
                existing={'vendor':vendor,'url':url,'state':'Read: cached response','format':fmt,'checked_at':stamp}
                self.rows['vendor_scraping_results.csv'].append(existing)
            existing.update(final_url=final,response_sha256=digest,cache_status='Replayed',
                compatibility_rows=len(c)+len(claims),ptf_rows=len(p),tables=tables)
        self.persist()
        return {'cached_documents':len(self.rows['vendor_page_diagnostics.csv']),
                'compatibility_rows':len(self.rows['all_vendor_extracted_compatibility.csv']),
                'ptf_rows':len(self.rows['all_vendor_extracted_ptfs.csv'])}

    def run(self):
        done=0
        while self.queue and done<self.max_pages:
            item=self.queue.popleft();vendor=item['vendor'];url=item['url'];key=(vendor,url)
            if key in self.seen:continue
            self.seen.add(key);done+=1;stamp=now()
            rec=dict(vendor=vendor,url=url,parent_url=item.get('parent_url',''),depth=item.get('depth',0),
                     state='Not checked',format='',http_status='',checked_at=stamp,tables=0,
                     compatibility_rows=0,ptf_rows=0,discovered_links=0,message='')
            try:
                if not safe_public_url(url,vendor):raise ValueError('Unsafe or non-vendor URL')
                if not self.allowed_robots(url):raise PermissionError('Disallowed by robots.txt')
                host=_domain(url); wait=self.delay-(time.monotonic()-self.last.get(host,-1e9))
                if wait>0:time.sleep(wait)
                self.last[host]=time.monotonic()
                final,typ,body=_get_public(self.session,url,vendor,self.timeout)
                cache_entry=self.cache.save(vendor,url,final,typ,body,stamp,item)
                rec.update(response_sha256=cache_entry['sha256'],cache_status='Saved',final_url=final)
                self.rows['vendor_page_diagnostics.csv'].append(describe_document(vendor,url,typ,body,cache_entry['sha256'],'Saved'))
                if 'pdf' in typ or final.lower().split('?')[0].endswith('.pdf'):
                    c,p,e,tables,soup=extract_pdf(body,vendor,final,self.byvendor,item.get('contexts',[]),stamp);fmt='PDF'
                else:
                    c,p,e,tables,soup=extract_html(body,vendor,final,self.byvendor,item.get('contexts',[]),stamp);fmt='HTML'
                self.rows['all_vendor_extracted_compatibility.csv']+=c
                self.rows['all_vendor_extracted_ptfs.csv']+=p
                self.rows['vendor_source_evidence.csv']+=e
                if fmt=='HTML':self.rows['vendor_document_facts.csv']+=extract_document_facts(body,vendor,final,stamp)
                observations=[]
                if fmt=='HTML':
                    vendor_claims, observations=extract_vendor_matrix(body,vendor,final,self.byvendor,stamp)
                    if vendor=='IBM':
                        ic,io=extract_ibm_report_table(body,final,self.byvendor,stamp)
                        vendor_claims+=ic;observations+=io
                    vc13,vo13,vp13=extract_v13(body,vendor,final,self.byvendor,stamp)
                    vendor_claims+=vc13;observations+=vo13
                    self.rows['all_vendor_extracted_ptfs.csv']+=vp13
                    existing={(r['vendor'],r['product'],r['release'],r['zos_version'],r['compatibility'],r['source_url']) for r in c}
                    for claim in vendor_claims:
                        key=(claim['vendor'],claim['product'],claim['release'],claim['zos_version'],claim['compatibility'],claim['source_url'])
                        if key not in existing:
                            self.rows['all_vendor_extracted_compatibility.csv'].append(claim);existing.add(key)
                    self.rows['vendor_release_observations.csv']+=observations
                    for obs in observations:
                        self.rows['vendor_source_evidence.csv'].append(dict(vendor=vendor,product=obs['product'],release=obs['release'],zos_version=obs['zos_version'],
                            evidence_kind=obs['observation_type'],source_url=obs['source_url'],source_excerpt=obs['source_excerpt'],source_timestamp=stamp,
                            document_sha256=hashlib.sha256(body).hexdigest(),match_status=obs['reason']))
                rec.update(state='Read',format=fmt,tables=tables,compatibility_rows=len(c)+len(vendor_claims) if fmt=='HTML' else len(c),ptf_rows=len(p)+(len(vp13) if fmt=='HTML' else 0))
                self.rows['vendor_failed_links.csv']=[r for r in self.rows['vendor_failed_links.csv'] if not (r.get('vendor')==vendor and r.get('url')==url)]
                if item['depth']<self.depth:
                    links=relevant_links(soup,final,vendor,item.get('root_url',url),self.max_links)
                    existing={(x['vendor'],x['url']) for x in self.queue}
                    for target in links:
                        k=(vendor,target)
                        if k in self.seen or k in existing:continue
                        self.queue.append({'vendor':vendor,'url':target,'depth':item['depth']+1,
                                           'root_url':item.get('root_url',url),'parent_url':url,
                                           'origin':'Discovered relevant link','contexts':item.get('contexts',[])})
                        existing.add(k)
                    rec['discovered_links']=len(links)
            except Exception as exc:
                m=str(exc)[:350];code=''
                if isinstance(exc,requests.HTTPError) and exc.response is not None:code=str(exc.response.status_code)
                rec.update(state='Blocked / failed',http_status=code,message=f'{type(exc).__name__}: {m}')
                self.rows['vendor_failed_links.csv'].append({k:rec.get(k,'') for k in CSV_FIELDS['vendor_failed_links.csv']})
            self.rows['vendor_scraping_results.csv'].append(rec)
            # Crash-safe checkpoint after each page. Rewrite files at bounded intervals.
            if done%10==0:self.persist()
        self.persist()
        return dict(processed_this_run=done,pending=len(self.queue),total_visited=len(self.seen),
                    compatibility_rows=len(self.rows['all_vendor_extracted_compatibility.csv']),
                    ptf_rows=len(self.rows['all_vendor_extracted_ptfs.csv']),
                    failures=len(self.rows['vendor_failed_links.csv']),output=str(self.output))


def import_authorized_documents(manifest:Path, output:Path, byvendor):
    """Parse operator-exported HTML/PDF using the same extraction engine.

    Manifest columns: Vendor,Path,SourceURL,Product,Release. The resulting
    evidence is marked as supplied, NOT as fetched live.
    """
    if not manifest or not manifest.is_file():return 0
    output.mkdir(parents=True,exist_ok=True)
    gathered={k:[] for k in CSV_FIELDS};n=0
    with manifest.open(encoding='utf-8-sig',newline='') as f:
      for row in csv.DictReader(f):
        vendor=vendor_name(row.get('Vendor',''))
        path=Path(row.get('Path',''))
        if not path.is_absolute():path=manifest.parent/path
        url=text(row.get('SourceURL',''))
        if not vendor or not path.is_file() or path.suffix.lower() not in ('.html','.htm','.pdf'):
            continue
        if url and not safe_public_url(url,vendor):continue
        body=path.read_bytes()
        if len(body)>2_000_000:continue
        stamp=now();src=url or 'authorized-local-document://'+hashlib.sha256(body).hexdigest()
        contexts=[(text(row.get('Product')),text(row.get('Release')))]
        try:
            if path.suffix.lower()=='.pdf':
                c,p,e,tables,_=extract_pdf(body,vendor,src,byvendor,contexts,stamp)
            else:
                c,p,e,tables,_=extract_html(body,vendor,src,byvendor,contexts,stamp)
            for r in c+p:
                r['evidence_level']='Operator-supplied document (not live) — '+r.get('evidence_level','')
            for r in e:r['evidence_kind']='Operator-supplied: '+r.get('evidence_kind','')
            gathered['all_vendor_extracted_compatibility.csv']+=c
            gathered['all_vendor_extracted_ptfs.csv']+=p
            gathered['vendor_source_evidence.csv']+=e
            if path.suffix.lower()!='.pdf':
                vc,vo=extract_vendor_matrix(body,vendor,src,byvendor,stamp)
                if vendor=='IBM':
                    ic,io=extract_ibm_report_table(body,src,byvendor,stamp);vc+=ic;vo+=io
                vc13,vo13,vp13=extract_v13(body,vendor,src,byvendor,stamp)
                gathered['all_vendor_extracted_compatibility.csv']+=vc+vc13
                gathered['all_vendor_extracted_ptfs.csv']+=vp13
                gathered['vendor_release_observations.csv']+=vo+vo13
                gathered['vendor_document_facts.csv']+=extract_document_facts(body,vendor,src,stamp)
            gathered['vendor_scraping_results.csv'].append(dict(vendor=vendor,url=src,parent_url='',depth=0,state='Read: authorized document',format=path.suffix.lower(),http_status='',checked_at=stamp,tables=tables,compatibility_rows=len(c),ptf_rows=len(p),discovered_links=0,message='Not a live source check'))
            n+=1
        except Exception as exc:
            gathered['vendor_failed_links.csv'].append(dict(vendor=vendor,url=src,parent_url='',state='Parser failed',http_status='',message=str(exc)[:250],checked_at=stamp))
    for fn,fields in CSV_FIELDS.items():
        old=[];path=output/fn
        if path.exists():
            with path.open(encoding='utf-8-sig',newline='') as f:old=list(csv.DictReader(f))
        save_csv(path,old+gathered[fn],fields)
    return n


def main(argv=None):
    p=argparse.ArgumentParser(description='Backend-only deep multi-vendor source extractor. Does not modify the dashboard.')
    p.add_argument('--output',default='exports/deep',help='Directory for CSV exports and resumable checkpoint')
    p.add_argument('--worklist',default='',help='Product worklist CSV; default: bundled/parent worklist if present')
    p.add_argument('--sources',default='',help='Additional approved source CSV with Vendor,URL headers')
    p.add_argument('--max-pages',type=int,default=200,help='Maximum URL fetches in this run')
    p.add_argument('--depth',type=int,default=2,help='Max relevant link hops from each starting URL (0–3)')
    p.add_argument('--max-links',type=int,default=10,help='Max relevant links on each fetched page (1–30)')
    p.add_argument('--delay',type=float,default=0.8,help='Minimum delay per hostname in seconds')
    p.add_argument('--timeout',type=int,default=15)
    p.add_argument('--reparse-cache',action='store_true',help='Offline: rebuild evidence and quality reports from cached raw responses without fetching')
    p.add_argument('--vendor',default='',help='Optional vendor filter for cache replay')
    p.add_argument('--fresh',action='store_true',help='Re-check all starting URLs, replacing latest results without deleting previous evidence')
    p.add_argument('--retry-failed',action='store_true',help='Requeue earlier failed links and retry')
    p.add_argument('--documents-manifest',default='',help='CSV of authorized vendor document exports: Vendor,Path,SourceURL,Product,Release')
    p.add_argument('--no-robots',action='store_true',help='Only use where permission explicitly authorizes ignoring robots; normally do not use')
    a=p.parse_args(argv)
    root=Path(__file__).resolve().parent
    worklist=Path(a.worklist) if a.worklist else (root/'reference/vendor_product_source_worklist.csv')
    candidates,inventory=inventory_and_queue(root,worklist if worklist.is_file() else None,Path(a.sources) if a.sources else None)
    engine=DeepCrawler(root/a.output,inventory,delay=a.delay,timeout=max(3,a.timeout),depth=max(0,min(3,a.depth)),
                       max_pages=max(1,a.max_pages),max_links=max(1,min(30,a.max_links)),respect_robots=not a.no_robots)
    if a.reparse_cache:
        replay=engine.reparse_cache(a.vendor)
        coverage=build_reports(root/a.output,inventory,candidates,worklist)
        print(json.dumps({'mode':'offline cache replay','run':replay,'coverage':coverage},indent=2))
        return
    if a.fresh:
        # Archive last cycle so stale evidence is not presented as newly checked.
        archive=root/a.output/'archive'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
        archive.mkdir(parents=True,exist_ok=True)
        for file in [*(root/a.output).glob('*.csv'),root/a.output/'deep_scrape_checkpoint.json']:
            if file.is_file():shutil.move(str(file),str(archive/file.name))
        engine.seen.clear();engine.queue.clear()
        engine.rows={k:[] for k in CSV_FIELDS}
    elif a.retry_failed:
        failed={(x.get('vendor',''),x.get('url','')) for x in engine.rows['vendor_failed_links.csv']}
        engine.seen.difference_update(failed)
    engine.seed(candidates)
    result=engine.run()
    imported=import_authorized_documents(Path(a.documents_manifest),root/a.output,inventory) if a.documents_manifest else 0
    if imported:
        # Recompute derived reports after authorized documents were merged.
        engine=DeepCrawler(root/a.output,inventory,delay=a.delay,timeout=max(3,a.timeout),depth=0,max_pages=1)
        engine.persist()
    coverage=build_reports(root/a.output,inventory,candidates,worklist)
    print(json.dumps({'initial_distinct_urls':len(candidates),'vendor_count':len(inventory),'run':result,'authorized_documents_imported':imported,'coverage':coverage},indent=2))
if __name__=='__main__':main()
