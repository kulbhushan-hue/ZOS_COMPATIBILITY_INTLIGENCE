"""One-shot multi-vendor audit for an EXTERNAL scheduler (cron/CI/Cloud jobs).

Examples:
  python refresh_all_vendors.py --vendors IBM BMC Rocket Precisely ASG --per-vendor 2
  python refresh_all_vendors.py --all --per-vendor 2

This audits approved official sources and stores evidence; it does not invent
product compatibility statuses. Broadcom structured extraction uses refresh_once.py.
"""
from __future__ import annotations
import argparse
import csv
import json
import os
from pathlib import Path
from compatibility_db import CompatibilityDB
from workbook_data import NAME, load_workbook, merge_workbook
from multi_vendor import audit_all, sources_for_vendors
from store import DEFAULT_DB, save_vendor_audits


def main(argv=None):
    p=argparse.ArgumentParser()
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--all',action='store_true',help='Audit all vendors in the workbook')
    group.add_argument('--vendors',nargs='+',help='Vendor names, e.g. IBM BMC')
    p.add_argument('--per-vendor',type=int,default=2,help='URLs per vendor (1–5)')
    p.add_argument('--timeout',type=int,default=10,help='Per URL timeout (5–25 seconds)')
    p.add_argument('--sources',help='CSV of additional official sources: Vendor,URL')
    opts=p.parse_args(argv)
    root=Path(__file__).resolve().parent
    _,amxt,urls=load_workbook(root/NAME)
    base=CompatibilityDB(merge_workbook(CompatibilityDB.load(str(root/'data')).df,amxt,urls))
    chosen=None if opts.all else opts.vendors
    extra=[]
    if opts.sources:
        with open(opts.sources,newline='',encoding='utf-8-sig') as stream:
            extra=list(csv.DictReader(stream))[:150]
        if any('Vendor' not in r or 'URL' not in r for r in extra):p.error('--sources CSV must have Vendor and URL headers')
    rows=audit_all(amxt,urls,base.df,chosen,max(1,min(5,opts.per_vendor)),max(5,min(25,opts.timeout)),extra_sources=extra)
    save_vendor_audits(rows,Path(os.getenv('ZOS_DB_PATH',str(DEFAULT_DB))))
    summary={'sources_checked':len(rows),'read':sum(x['state']=='Read' for x in rows),
             'failed':sum(x['state']=='Blocked / failed' for x in rows),
             'without_approved_url':sum(x['state']=='No approved source URL' for x in rows),
             'matched_product_mentions':sum(x['matched_products'] for x in rows),
             'warning':'Mentions are evidence, not confirmed product compatibility'}
    print(json.dumps(summary,indent=2))
    return 0 if summary['failed']==0 else 2
if __name__=='__main__':raise SystemExit(main())
