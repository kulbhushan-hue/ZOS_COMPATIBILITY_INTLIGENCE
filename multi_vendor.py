"""Controlled vendor-source discovery and evidence capture.

For vendors other than Broadcom, public pages vary widely. This module collects
verifiable textual evidence and PTF identifiers; it never infers compatibility
or installation status merely because a product and an OS appear on the page.
Site access is performed on demand or by an external scheduler, not on every UI rerun.
"""
from __future__ import annotations
import io
import ipaddress
import re
import socket
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from quality import ptf_ids
from workbook_data import vendor_name
from compatibility_db import SOURCES
from vendor_assertions import extract_extra_assertions, extract_official_document_tables
from evidence_pipeline import review_candidates

USER_AGENT = 'zOS-Compatibility-Intelligence/1.0 (source audit; contact site administrator)'
VERSIONS = ('3.2', '3.1', '2.5')
MAX_BYTES = 2_000_000
# Do not automatically follow arbitrary external links or deep-crawl login systems.
OFFICIAL = {
    'IBM': ('ibm.com',), 'BMC': ('bmc.com','docs.bmc.com'),
    'Rocket': ('rocketsoftware.com',), 'ASG': ('rocketsoftware.com',),
    'Precisely': ('precisely.com',), 'Broadcom': ('broadcom.com',),
    '21CS': ('21cs.com',), 'Action Software International': ('actionsoftware.com',),
    'Chicago-Soft, Ltd': ('chicago-soft.com',),
    'NewEra Software, Inc.': ('newera-info.com',),
    'VANGUARD Integrity Prof.': ('go2vanguard.com',),
}
SKIP_URL_TERMS = ('login', 'signin', 'sso', 'auth/', 'account/login')
PRODUCT_WINDOW = 240


def safe_public_url(url: str, vendor: str = '', resolve_dns: bool = False) -> bool:
    """Reject private hosts, userinfo, non-HTTP links and unapproved host redirects.
    DNS is checked in production requests to resist DNS rebinding / SSRF.
    """
    try:
        u = urlparse(str(url).strip())
        if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password:
            return False
        host = u.hostname.lower().rstrip('.')
        if host in ('localhost',) or host.endswith(('.local', '.internal')) or host.count('.') < 1:
            return False
        try:
            if not ipaddress.ip_address(host).is_global: return False
        except ValueError: pass
        if vendor in OFFICIAL and not any(host == h or host.endswith('.'+h) for h in OFFICIAL[vendor]):
            return False
        if any(term in u.path.lower() for term in SKIP_URL_TERMS): return False
        if resolve_dns:
            for item in socket.getaddrinfo(host, 443 if u.scheme == 'https' else 80, proto=socket.IPPROTO_TCP):
                if not ipaddress.ip_address(item[4][0]).is_global:return False
        return True
    except (ValueError, OSError):
        return False


def sources_for_vendors(amxt, sheet_urls: dict, selected: list[str] | None = None,
                        max_urls_per_vendor: int = 4, extra_sources=None) -> dict[str, list[dict]]:
    """Collect vendor-specific official URLs from workbook + curated links.
    User-supplied third-party links are shown in the workbook but are not
    fetched automatically unless they belong to the vendor's official domains.
    """
    grouped = defaultdict(list)
    def add(v, url, label, origin):
        v=vendor_name(v)
        if not safe_public_url(url, v) or any(x['url']==url for x in grouped[v]):return
        grouped[v].append({'vendor':v,'url':url,'label':str(label)[:150], 'origin':origin})
    for v, title, url, desc in SOURCES:
        add(v, url, title, 'Curated directory')
    # Prioritize workbook references most likely to be product-specific.
    for _, row in amxt.iterrows():
        v=vendor_name(row.get('Vendor',''))
        add(v, str(row.get('Link to verify compatibility report','')).strip(),
            str(row.get('Product','')), 'AMXT product reference')
    for v,u in sheet_urls.items():add(v,u,'Workbook vendor directory','Workbook Sheet1')
    for item in (extra_sources or []):
        add(item.get('Vendor',''),str(item.get('URL','')).strip(),'Operator-supplied official URL','Operator-supplied CSV')
    vendors=selected if selected is not None else sorted({vendor_name(v) for v in amxt['Vendor']} | set(grouped))
    result={}
    for v in vendors:
        links=grouped.get(v,[])
        # Product-specific pages before general company homes.
        links.sort(key=lambda d:(
            not any(token in d['url'].lower() for token in ('support-matrix','software-requirements-running-zos','ironstream-for-ibm-z-now-compatible','mfx-support-lifecycle','release-history','bacm262','bacm263')),
            d['origin'] not in ('AMXT product reference', 'Operator-supplied CSV'),
            d['origin']!='Curated directory'))
        result[v]=links[:max_urls_per_vendor]
    return result


def _get_public(session, url, vendor, timeout):
    current=url
    for _ in range(4):
        if not safe_public_url(current,vendor,resolve_dns=True):raise ValueError('Non-public or non-vendor URL blocked')
        res=session.get(current,timeout=timeout,allow_redirects=False,
            headers={'User-Agent':USER_AGENT,'Accept':'text/html,application/pdf;q=0.8'},stream=True)
        if res.status_code in (301,302,303,307,308):
            target=urljoin(current,res.headers.get('Location',''))
            res.close()
            current=target
            continue
        res.raise_for_status()
        typ=res.headers.get('Content-Type','').lower()
        if not any(t in typ for t in ('html','text/plain','pdf','application/xhtml+xml')):
            res.close();raise ValueError('Unsupported content type: '+typ[:70])
        chunks=[];total=0
        for chunk in res.iter_content(chunk_size=32768):
            total+=len(chunk)
            if total>MAX_BYTES:
                res.close();raise ValueError('Page exceeds size limit')
            chunks.append(chunk)
        body=b''.join(chunks);res.close()
        return current,typ,body
    raise ValueError('Too many redirects')


def extract_text(body: bytes, content_type: str) -> tuple[str,str]:
    if 'pdf' in content_type:
        from pypdf import PdfReader
        pdf=PdfReader(io.BytesIO(body),strict=False)
        text='\n'.join((p.extract_text() or '') for p in pdf.pages[:15]);return text[:200_000],'PDF'
    soup=BeautifulSoup(body,'lxml')
    for tag in soup(['script','style','nav','footer']):tag.decompose()
    text=soup.get_text(' ',strip=True)
    return re.sub(r'\s+',' ',text)[:200_000],'HTML'


def evidence_for_products(text: str, products: list[dict], source: dict, fetched_url: str):
    """Capture *contextual mentions*, not unsupported compatibility decisions.
    A row is evidence only when both product and z/OS version occur close together.
    """
    matches=[]
    normal=re.sub(r'\s+',' ',text)
    for r in products:
        name=str(r['product']).strip()
        if len(name)<5:continue
        # Strict word boundaries and product length to avoid random short-term collisions.
        pat=re.compile(r'(?<![\w])'+re.escape(name)+r'(?![\w])',re.I)
        for hit in list(pat.finditer(normal))[:3]:
            excerpt=normal[max(0,hit.start()-PRODUCT_WINDOW):min(len(normal),hit.end()+PRODUCT_WINDOW)]
            oses=sorted(set(re.findall(r'(?:z\s*/\s*OS\s*(?:V|version)?\s*|z/OS\s*V[0-9]R)(3\.2|3\.1|2\.5)',excerpt,re.I)))
            # z/OS V3R2 notation
            oses += [f'{a}.{b}' for a,b in re.findall(r'z/OS\s*V([235])R([125])',excerpt,re.I)]
            oses=sorted(set(v for v in oses if v in VERSIONS))
            if not oses:continue
            matches.append({'product':name,'vrm':str(r.get('vrm','')),'zos_mentions':oses,
                            'ptf_ids':ptf_ids(excerpt),'excerpt':excerpt[:540],
                            'source_url':fetched_url,'source_origin':source['origin'],
                            'evidence_level':'Mention only — compatibility not confirmed'})
            break
    return matches


def discover_compatibility_links(body: bytes, page_url: str, vendor: str, limit: int = 2) -> list[dict]:
    """Find explicit, same-vendor compatibility documents linked from official hubs.

    No generic home-page crawling. The target must be visibly described as a
    compatibility/requirements/support matrix, and requests remain independently
    subject to the same URL and DNS restrictions as starting URLs.
    """
    if vendor not in ('BMC', 'IBM', 'Rocket', 'ASG', 'Precisely'):
        return []
    soup = BeautifulSoup(body, 'lxml')
    results = []
    terms = ('compatibility database', 'compatibility matrix', 'support matrix',
             'software requirements', 'detailed system requirements',
             'product availability and compatibility', 'z/os compatibility')
    for a in soup.find_all('a', href=True):
        label = ' '.join(a.get_text(' ', strip=True).split())[:140]
        if not any(t in label.casefold() for t in terms):
            continue
        href = a['href'].strip()
        if not href or href.startswith('#'):
            continue
        target = urljoin(page_url, href)
        if target.split('#', 1)[0].rstrip('/') == page_url.split('#', 1)[0].rstrip('/'):
            continue
        if not safe_public_url(target, vendor) or target in [x['url'] for x in results]:
            continue
        results.append({'vendor': vendor, 'url': target, 'origin': 'Discovered on official vendor source', 'label': label})
        if len(results) >= limit:
            break
    return results


def audit_vendor(vendor: str, sources: list[dict], products: list[dict],
                 timeout=12, session=None, follow_discovered=True, max_discovered=2):
    """Fetch approved vendor sources and at most two explicit related documents.

    This is a bounded one-hop discovery, not an open crawler. Errors and access
    blocks remain visible; neither a successful HTTP response nor a nearby PTF
    mention certifies an installed product release.
    """
    session=session or requests.Session()
    results=[]
    queue=list(sources)
    seen=set()
    added=0
    for depth in range(2):
        next_level=[]
        for s in queue:
            target=s['url']
            if target in seen:continue
            seen.add(target)
            row={'vendor':vendor,'url':target,'origin':s['origin'],
                 'checked_at':datetime.now(timezone.utc).isoformat(),'state':'Not checked',
                 'http_status':'','access_status':'Not checked','format':'','matched_products':0,'ptf_mentions':0,
                 'note':'','matches':[],'assertions':[]}
            try:
                url,typ,body=_get_public(session,target,vendor,timeout)
                text,fmt=extract_text(body,typ)
                matches=evidence_for_products(text,products,s,url)
                assertions=extract_bmc_support_matrix(body,url) if vendor=='BMC' and fmt=='HTML' and 'docs.bmc.com' in url else []
                if vendor=='Action Software International' and fmt=='HTML' and 'actionsoftware.com' in url:
                    assertions += extract_action_release_matrix(body,url)
                if fmt=='HTML':
                    assertions += extract_extra_assertions(vendor,body,url)
                    if follow_discovered and depth==0 and added<max_discovered:
                        links=discover_compatibility_links(body,url,vendor,max_discovered-added)
                        for item in links:
                            if item['url'] not in seen and item['url'] not in [x['url'] for x in next_level]:
                                next_level.append(item);added+=1
                if fmt=='PDF':
                    assertions += extract_official_document_tables(vendor,text,url)
                row['assertions']=assertions
                row.update(url=url,state='Read',access_status='Public source read',format=fmt,matched_products=len(matches),
                           ptf_mentions=sum(len(m['ptf_ids']) for m in matches),
                           matches=matches,note=(f'Source read; {len(assertions)} structured observation(s), {len(matches)} contextual match(es)' if assertions else ('Source read; product references require review' if matches else 'Source read; no exact product+OS evidence matched')))
            except requests.HTTPError as exc:
                code=exc.response.status_code if exc.response is not None else None
                label='Access blocked / authentication may be required' if code in (401,403) else ('Source URL not found' if code==404 else 'HTTP request failed')
                row.update(state='Blocked / failed',http_status=str(code or ''),access_status=label,note=f'{label}: HTTP {code}; do not treat as absent compatibility evidence')
            except Exception as exc:
                row.update(state='Blocked / failed',access_status='Network / parser error',note=f'{type(exc).__name__}: {str(exc)[:220]}')
            results.append(row)
        queue=next_level
        if not queue:break
    if not sources:
        results.append({'vendor':vendor,'url':'','origin':'','checked_at':datetime.now(timezone.utc).isoformat(),
            'state':'No approved source URL','http_status':'','access_status':'No public official URL configured','format':'','matched_products':0,
            'ptf_mentions':0,'note':'Add official vendor documentation URL before live checks', 'matches':[], 'assertions':[]})
    return results


def audit_all(amxt, sheet_urls: dict, baseline, vendors: list[str] | None = None,
              per_vendor: int = 2, timeout: int = 12, session=None, extra_sources=None):
    source_map=sources_for_vendors(amxt,sheet_urls,vendors,max_urls_per_vendor=per_vendor,extra_sources=extra_sources)
    reports=[]
    for v,sources in source_map.items():
        rows=baseline[baseline['vendor']==v].to_dict('records')
        reports.extend(audit_vendor(v,sources,rows,timeout=timeout,session=session))
    return reports


def extract_bmc_support_matrix(body: bytes, source_url: str) -> list[dict]:
    """Extract explicit support cells in BMC's public product support matrix.

    Returns vendor assertions with *unknown product release*, never merging
    them into a VRM-specific historical record.
    """
    soup=BeautifulSoup(body,'lxml')
    results=[]
    for table in soup.find_all('table'):
        rows=table.find_all('tr')
        if not rows:continue
        head=[x.get_text(' ',strip=True) for x in rows[0].find_all(['td','th'],recursive=False)]
        if not head or not any('mainframe' in x.casefold() or 'performance' in x.casefold() for x in head[1:]):continue
        for tr in rows[1:]:
            cells=[x.get_text(' ',strip=True) for x in tr.find_all(['td','th'],recursive=False)]
            if len(cells)<2:continue
            m=re.search(r'(?i)z\s*/\s*OS\s*(?:V)?([235])(?:\.|R)([125])',cells[0])
            if not m:continue
            os=f'{m.group(1)}.{m.group(2)}'
            if os not in VERSIONS:continue
            support_note=next((c for j,c in enumerate(cells) if j<len(head) and 'comment' in head[j].lower()),'')
            for i,product in enumerate(head[1:],1):
                if not product or i>=len(cells):continue
                value=cells[i].strip().upper()
                if value not in ('X','YES','NO','N','Y','✓','✔'):continue
                results.append({'vendor':'BMC','product':product,'vrm':'Not stated',
                                'zos_version':os,'compatibility':'Yes' if value in ('X','YES','Y','✓','✔') else 'No',
                                'evidence_level':'Explicit table cell; product release unspecified',
                                'source_url':source_url,'required_level':support_note,
                                'maintenance_ids':'','note':'Product release not individually certified by this table'})
    return results


def extract_action_release_matrix(body:bytes, source_url:str) -> list[dict]:
    """Action Software published release-history support ranges with concrete VRMs."""
    soup=BeautifulSoup(body,'lxml')
    results=[]
    for tr in soup.select('tr'):
        cells=[x.get_text(' ',strip=True) for x in tr.find_all(['th','td'],recursive=False)]
        if len(cells)<4:continue
        item=cells[0]
        match=re.search(r'(?i)\b(eventACTION|ussACTION)\s+(\d+\.\d+)\b',item)
        if not match:continue
        product=match.group(1);vrm=match.group(2)
        compat=' '.join(cells[1:])
        span=re.search(r'(?i)z\s*/\s*OS\s*([0-9]+\.[0-9]+)\s*[–—-]\s*z\s*/\s*OS\s*([0-9]+\.[0-9]+)',compat)
        if not span:continue
        def num(x):return tuple(int(p) for p in x.split('.'))
        for os in VERSIONS:
            results.append({'vendor':'Action Software International','product':product,'vrm':vrm,
              'zos_version':os,'compatibility':'Yes' if num(span.group(1))<=num(os)<=num(span.group(2)) else 'No',
              'evidence_level':'Explicit published support range; check EOS and maintenance',
              'source_url':source_url,'support_range':span.group(0),'source_text':compat[:350]})
    return results


def reconcile_observations(observations: list[dict], inventory) -> list[dict]:
    """Traceable exact vendor/product/release matches for the audit worklist.

    Never overwrite historical inventory, and never promote release-unspecified
    or minimum-level evidence to certification. This gives operators an explicit
    match/exception report, without silently changing Compatibility Matrix.
    """
    from quality import match_key
    keys = {match_key(r['vendor'], r['product'], r['vrm']):r for r in inventory.to_dict('records')}
    output=[]
    for o in observations:
        vendor=o.get('vendor','');prod=o.get('product','');vrm=o.get('vrm','')
        exact=bool(vrm and str(vrm).casefold() not in ('not stated','unknown','nan'))
        matched=keys.get(match_key(vendor,prod,vrm)) if exact else None
        candidates=review_candidates(o, inventory.to_dict('records')) if matched is None else []
        level=str(o.get('evidence_level',''))
        qualified=(matched is not None and o.get('zos_version') in VERSIONS and
                   str(o.get('compatibility','')).strip() in ('Yes','No') and
                   'Explicit vendor table: product, release' in level)
        output.append({**o,'baseline_match':'Exact vendor/product/VRM' if matched is not None else 'No exact match',
            'matrix_promotion':'Eligible for manual review' if qualified else 'Evidence only — not promoted',
            'baseline_product':str(matched.get('product','')) if matched is not None else '',
            'baseline_vrm':str(matched.get('vrm','')) if matched is not None else '',
            'review_candidate':'; '.join(str(c.get('product',''))+' / '+str(c.get('vrm','')) for c in candidates),
            'source_checked_at':o.get('source_checked_at',''),
            'ptf_verified_at':'Not verified — source observation only'})
    return output


def audit_uploaded_document(vendor: str, filename: str, body: bytes, products: list[dict],
                            source_url: str = '') -> dict:
    """Extract evidence from an operator-authorized exported HTML/PDF file.

    A file is *not* a live vendor response. The URL must be an optional official
    public source reference; evidence is always labelled as operator supplied.
    """
    from pathlib import Path
    import hashlib
    if len(body)>MAX_BYTES or not body:
        raise ValueError('Reference file must be non-empty and 2 MB or smaller')
    suffix=Path(filename).suffix.casefold()
    if suffix not in ('.html','.htm','.pdf'):
        raise ValueError('Only official exported HTML or PDF files are supported')
    if source_url and not safe_public_url(source_url,vendor):
        raise ValueError('The optional evidence URL must belong to this vendor\'s official domain')
    source_url=source_url or ('operator-upload://'+hashlib.sha256(body).hexdigest())
    fmt='application/pdf' if suffix=='.pdf' else 'text/html'
    text,kind=extract_text(body,fmt)
    matches=evidence_for_products(text,products,{'origin':'Operator-supplied document'},source_url)
    assertions=[]
    if kind=='PDF':
        assertions+=extract_official_document_tables(vendor,text,source_url)
    if kind=='HTML':
        if vendor=='BMC':assertions+=extract_bmc_support_matrix(body,source_url)
        if vendor=='Action Software International':assertions+=extract_action_release_matrix(body,source_url)
        # Only use the regular URL-gated parsers if the operator has included a
        # valid official source URL; otherwise do not fabricate the source.
        if source_url.startswith(('http://','https://')):
            assertions+=extract_extra_assertions(vendor,body,source_url)
    return {'vendor':vendor,'url':source_url,'origin':'Operator-uploaded document (not live)',
      'checked_at':datetime.now(timezone.utc).isoformat(),'state':'Read',
      'http_status':'','access_status':'Uploaded document; authenticity not independently verified',
      'format':kind,'matched_products':len(matches),
      'ptf_mentions':sum(len(m['ptf_ids']) for m in matches),
      'matches':matches,'assertions':assertions,
      'note':f'Uploaded {Path(filename).name}; {len(assertions)} structured observations, {len(matches)} contextual matches; not a live HTTP check'}
