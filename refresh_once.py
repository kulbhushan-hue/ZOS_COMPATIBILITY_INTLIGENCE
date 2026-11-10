"""One-shot Broadcom refresh for an EXTERNAL scheduler (cron, job runner).

Example: ZOS_DB_PATH=/persistent/compatibility.sqlite3 python refresh_once.py
No persistent storage => no reliable multi-run history on ephemeral Cloud hosts.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from crawler import crawl_broadcom
from store import DEFAULT_DB, save, record_error


def main() -> int:
    db=Path(os.getenv('ZOS_DB_PATH',str(DEFAULT_DB)))
    try:
        records,stats=crawl_broadcom(follow_external=os.getenv('ZOS_FOLLOW_DETAILS','0')=='1')
        if len(records)<30:raise ValueError('Too few extracted records; refusing to publish partial snapshot')
        snapshot=save(records,stats,db)
        print(json.dumps({'result':'Success','snapshot':snapshot,'records':len(records),'database':str(db),'stats':stats}))
        return 0
    except Exception as exc:
        try:record_error('Broadcom',f'{type(exc).__name__}: {exc}',db)
        except Exception:pass
        print(json.dumps({'result':'Failed','error':f'{type(exc).__name__}: {exc}'}),file=sys.stderr)
        return 1

if __name__=='__main__':raise SystemExit(main())
