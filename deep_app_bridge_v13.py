"""Conservative read-only bridge from verified crawler exports to dashboard records.

Changes existing cells only for an unambiguous vendor+product+release match,
explicit z/OS release, and explicit source support status. No false inference
from evidence-only, minimum OS, or browser shell records.
"""
from __future__ import annotations
import csv
from collections import defaultdict
from pathlib import Path
from quality import match_key
from compatibility_db import VER


def merge_verified_deep(frame, csv_path):
    path=Path(csv_path)
    if not path.is_file():return frame
    try:
        with path.open(encoding='utf-8-sig',newline='') as f:
            rows=list(csv.DictReader(f))
    except (OSError, UnicodeError, csv.Error):return frame
    # Include a claim only when the exact source release appears and is matched
    # to exactly one existing inventory row. Never silently add unverified items.
    index=defaultdict(list)
    for i,row in frame.iterrows():
        index[match_key(row.get('vendor',''),row.get('product',''),row.get('vrm',''))].append(i)
    accepted=defaultdict(list)
    for r in rows:
        vendor=r.get('vendor',''); product=r.get('product','');release=r.get('release','')
        os=r.get('zos_version',''); status=r.get('compatibility','')
        if not (vendor and product and release and release!='Not established'
                and os in VER and status in ('Yes','No')):continue
        # Deep extractor statuses refer to source assertions; do not copy
        # unassigned review observations or generic minimum-OS statements.
        if 'minimum' in r.get('evidence_level','').lower():continue
        k=match_key(vendor,product,release)
        if len(index[k])!=1:continue
        accepted[(index[k][0],os)].append(r)
    if not accepted:return frame
    result=frame.copy()
    for (idx,os),rs in accepted.items():
        statuses={r['compatibility'] for r in rs}
        if len(statuses)!=1:continue
        col=VER[os][0]
        # Do not overwrite independently tracked Broadcom snapshots.
        if rs[0].get('vendor','').casefold()=='broadcom':continue
        result.at[idx,col]=next(iter(statuses))
        result.at[idx,f'provenance_{os}']='Exact live vendor source (not installation verified)'
    return result
