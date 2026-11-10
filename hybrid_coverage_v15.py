"""Evidence coverage reporting; URL reachability is never confused with product verification.

This module reports separately on source discovery, successful reads, accepted
compatibility/PTF claims, published documentary facts and data gaps.
"""
from __future__ import annotations
import csv
from collections import Counter, defaultdict
from pathlib import Path

COLUMNS = ('vendor','inventory_products','configured_urls','urls_checked','urls_read',
           'urls_failed','urls_with_exact_claims','compatibility_claims','ptf_claims',
           'document_facts','evidence_only_observations','dynamic_shell_pages',
           'coverage_state','next_action')
PRODUCT_COLUMNS = ('vendor','product','release','source_url','url_state',
                   'exact_compatibility_claims','ptf_claims','document_facts',
                   'verification_state','next_action')

def _read(path):
    if not Path(path).is_file():return []
    with open(path,encoding='utf-8-sig',newline='') as fh:return list(csv.DictReader(fh))

def _write(path, rows, fields):
    with open(path,'w',encoding='utf-8-sig',newline='') as fh:
        writer=csv.DictWriter(fh,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)

def build_reports(output, inventory=None, source_candidates=None, product_worklist=None):
    """Pure file-based reporting; no additional vendor calls and no promotions."""
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    scrapes=_read(output/'vendor_scraping_results.csv')
    comps=_read(output/'all_vendor_extracted_compatibility.csv')
    ptfs=_read(output/'all_vendor_extracted_ptfs.csv')
    facts=_read(output/'vendor_document_facts.csv')
    observations=_read(output/'vendor_release_observations.csv')
    diagnostics=_read(output/'vendor_page_diagnostics.csv')
    seen_urls=defaultdict(set);read_urls=defaultdict(set);bad_urls=defaultdict(set)
    for r in scrapes:
        v=r.get('vendor','');u=r.get('url','');seen_urls[v].add(u)
        if str(r.get('state','')).lower().startswith('read'):read_urls[v].add(u)
        if 'failed' in r.get('state','').lower() or 'blocked' in r.get('state','').lower():bad_urls[v].add(u)
    configured=defaultdict(set)
    for item in (source_candidates or []):
        if item.get('url'):configured[item['vendor']].add(item['url'])
    count_inv={v:len(set((str(item.get('product','')),str(item.get('release',''))) for item in entries))
               for v,entries in (inventory or {}).items()}
    grouped={}
    for vendor in set(count_inv)|set(configured)|set(seen_urls)|{r.get('vendor','') for records in (comps,ptfs,facts,observations) for r in records}:
        if not vendor:continue
        c=[r for r in comps if r.get('vendor')==vendor]
        p=[r for r in ptfs if r.get('vendor')==vendor]
        f=[r for r in facts if r.get('vendor')==vendor]
        o=[r for r in observations if r.get('vendor')==vendor]
        d=[r for r in diagnostics if r.get('vendor')==vendor and r.get('potential_dynamic_content')=='Yes']
        goodurls={r.get('source_url') for r in c+p if r.get('source_url')}
        if c or p:state='Structured records extracted'
        elif f or o:state='Evidence only — no exact compatibility claim'
        elif seen_urls[vendor]:state='Checked — no structured evidence'
        else:state='No fetched source URL'
        action=('Review accepted claims against product/release evidence' if c or p else
                'Review document facts; obtain exact release evidence' if f or o else
                'Capture permitted rendered report and inspect linked documents' if d else
                'Identify an accessible official product-specific source')
        grouped[vendor]=dict(vendor=vendor,inventory_products=count_inv.get(vendor,0),
            configured_urls=len(configured[vendor]),urls_checked=len(seen_urls[vendor]),
            urls_read=len(read_urls[vendor]),urls_failed=len(bad_urls[vendor]),
            urls_with_exact_claims=len(goodurls),compatibility_claims=len(c),ptf_claims=len(p),
            document_facts=len(f),evidence_only_observations=len(o),
            dynamic_shell_pages=len({r.get('url') for r in d}),coverage_state=state,next_action=action)
    coverage=list(sorted(grouped.values(),key=lambda x:x['vendor'].casefold()))
    _write(output/'vendor_extraction_coverage.csv',coverage,COLUMNS)

    worklist=product_worklist
    if worklist is None:worklist=Path(__file__).resolve().parent/'reference'/'vendor_product_source_worklist.csv'
    products=[]
    for row in _read(worklist):
        vendor=row.get('Vendor') or row.get('vendor') or ''
        product=row.get('Product') or row.get('product') or ''
        release=row.get('Release') or row.get('vrm') or ''
        url=row.get('Approved source URL') or row.get('URL') or row.get('link') or ''
        if not vendor or not product:continue
        status=next((r.get('state','') for r in scrapes if r.get('vendor')==vendor and r.get('url')==url),'Not checked')
        exact=[r for r in comps if r.get('vendor','').casefold()==vendor.casefold() and
               r.get('product','').casefold()==product.casefold() and r.get('release','').casefold()==release.casefold()]
        pts=[r for r in ptfs if r.get('vendor','').casefold()==vendor.casefold() and
               r.get('product','').casefold()==product.casefold() and r.get('release','').casefold()==release.casefold()]
        relevant_facts=[r for r in facts if r.get('vendor','').casefold()==vendor.casefold() and
                       r.get('product','').casefold()==product.casefold() and r.get('release','').casefold()==release.casefold()]
        verified=any(r.get('match_status')=='Exact inventory match' for r in exact)
        state=('Exact inventory-matched compatibility claim' if verified else
               'Structured assertion — verify inventory release' if exact else
               'PTF mentions — applicability not independently verified' if pts else
               'Published facts only' if relevant_facts else 'No product-level assertion')
        products.append(dict(vendor=vendor,product=product,release=release,source_url=url,
                             url_state=status,exact_compatibility_claims=len(exact),ptf_claims=len(pts),
                             document_facts=len(relevant_facts),verification_state=state,
                             next_action='' if verified else 'Find exact product and release statement in official source'))
    _write(output/'vendor_product_extraction_coverage.csv',products,PRODUCT_COLUMNS)
    return {'vendors_reported':len(coverage),'products_reported':len(products),
            'vendors_with_structured_claims':sum(bool(r['compatibility_claims'] or r['ptf_claims']) for r in coverage),
            'vendors_with_evidence_only':sum(bool(r['document_facts'] or r['evidence_only_observations']) for r in coverage)}
