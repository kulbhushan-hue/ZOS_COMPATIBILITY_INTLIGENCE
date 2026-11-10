"""Audit V8/V9 CSV output without modifying or certifying source evidence.

Usage: python audit_v9_exports.py --input exports/deep
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from safe_extract_v8 import valid_product_name, scoped_fixcat_version

def read(path):
    if not path.exists():return []
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def audit(folder):
    folder=Path(folder)
    comps=read(folder/'all_vendor_extracted_compatibility.csv')
    ptfs=read(folder/'all_vendor_extracted_ptfs.csv')
    failed=read(folder/'vendor_failed_links.csv')
    invalid=[r for r in comps if not valid_product_name(r.get('product',''))]
    mismatch=[]
    non_zos=[]
    for row in ptfs:
        vers,has_cat=scoped_fixcat_version(row.get('source_excerpt',''))
        assigned=row.get('zos_version','')
        if has_cat and not vers:non_zos.append(row)
        if vers and assigned not in vers:mismatch.append(row)
    duplicate_ptfs=sum(v-1 for v in Counter(tuple(row.get(k,'') for k in ('vendor','product','release','zos_version','ptf_id','source_url')) for row in ptfs).values() if v>1)
    unnamed=[r for r in ptfs if not r.get('product') or not r.get('release')]
    return {
        'compatibility_rows':len(comps), 'ptf_rows':len(ptfs),
        'invalid_product_rows':len(invalid),
        'fixcat_to_zos_mismatches':len(mismatch),
        'ptfs_in_non_zos_fixcats_review':len(non_zos),
        'repeat_ptf_claims_same_source':duplicate_ptfs,
        'ptfs_without_full_product_release':len(unnamed),
        'failed_url_rows':len(failed),
        'compatibility_by_vendor':dict(Counter(r.get('vendor','') for r in comps)),
        'ptfs_by_vendor':dict(Counter(r.get('vendor','') for r in ptfs)),
        'examples':{
          'invalid_products':[r.get('product','') for r in invalid[:5]],
          'fixcat_version_mismatch':[{'product':r.get('product'),'ptf_id':r.get('ptf_id'),'assigned':r.get('zos_version'),'excerpt':r.get('source_excerpt','')[:150]} for r in mismatch[:5]],
        }
    }

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',default='exports/deep')
    args=parser.parse_args()
    print(json.dumps(audit(args.input),indent=2))
