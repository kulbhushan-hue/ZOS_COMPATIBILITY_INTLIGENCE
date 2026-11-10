"""Launch the permitted vendor crawler on Streamlit startup without extra commands.

Does not block the UI or require Docker. Reports results to a JSON status file.
Playwright is optional and attempted only on Windows if its package is installed.
"""
from __future__ import annotations
import json
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

STATUS = 'auto_scrape_status.json'
_STARTED = False
_MUTEX = threading.Lock()

def _save_status(root, state, **fields):
    output = root/'exports'/'deep'
    output.mkdir(parents=True,exist_ok=True)
    target=output/STATUS
    data={'state':state,'timestamp_utc':datetime.now(timezone.utc).isoformat(),**fields}
    tmp=target.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,indent=2),encoding='utf-8')
    tmp.replace(target)

def _run(root:Path, browser_enabled:bool, max_pages:int):
    lockfile=root/'exports'/'deep'/'.auto_scrape.lock'
    lockfile.parent.mkdir(parents=True,exist_ok=True)
    fd=None
    owned=False
    try:
        try:
            fd=os.open(str(lockfile), os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        except FileExistsError:
            if time.time()-lockfile.stat().st_mtime>6*3600:
                lockfile.unlink(missing_ok=True)
                fd=os.open(str(lockfile),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            else:return
        owned=True
        os.write(fd,str(os.getpid()).encode())
        os.close(fd);fd=None
        from deep_scraper import main as scrape
        _save_status(root,'Scraping',message='Background source refresh started')
        # A completed checkpoint with zero pending URLs is not a refresh.
        # When startup is allowed (24-hour interval has elapsed), run a fresh
        # source cycle. Preserve partial queue runs so they can resume.
        checkpoint=root/'exports'/'deep'/'deep_scrape_checkpoint.json'
        fresh=False
        if checkpoint.exists():
            try:
                saved=json.loads(checkpoint.read_text(encoding='utf-8'))
                fresh=not bool(saved.get('queue'))
            except (ValueError,OSError):
                fresh=True
        args=['--output','exports/deep','--max-pages',str(max_pages),'--depth','2',
              '--sources',str(root/'reference'/'vendor_sources_v13.csv')]
        if fresh:args.append('--fresh')
        scrape(args)
        if browser_enabled and sys.platform=='win32':
            # Windows Edge is preferred to avoid a separate Chromium installation.
            # Browser rendering is optional; never prevent static extraction.
            try:
                import importlib.util
                if importlib.util.find_spec('playwright'):
                    from dynamic_capture_v12 import capture
                    report=capture(root/'exports'/'deep',limit=30,delay=1.5)
                    if report.get('captured',0):
                        scrape(['--output','exports/deep','--reparse-cache'])
            except Exception as exc:
                _save_status(root,'Partial',message='Static scraping completed. Optional browser capture unavailable',browser_error=str(exc)[:500])
                return
        _save_status(root,'Completed',message='URL crawl completed; check vendor_extraction_coverage.csv for actual evidence coverage',coverage_report='vendor_extraction_coverage.csv',product_report='vendor_product_extraction_coverage.csv')
    except Exception as exc:
        _save_status(root,'Failed',error=str(exc)[:500],error_type=type(exc).__name__)
    finally:
        if fd is not None:os.close(fd)
        if owned and lockfile.exists():
            try:lockfile.unlink()
            except OSError:pass

def launch(root, *, max_pages=200, interval_seconds=24*3600, browser_enabled=True):
    """Nonblocking, process-local, once-per-refresh startup hook."""
    global _STARTED
    root=Path(root).resolve()
    if os.getenv('ZOS_AUTO_SCRAPE','1').strip().lower() in ('0','false','off','no'):return False
    with _MUTEX:
        if _STARTED:return False
        status=root/'exports'/'deep'/STATUS
        if status.is_file():
            try:
                data=json.loads(status.read_text(encoding='utf-8'))
                age=time.time()-datetime.fromisoformat(data['timestamp_utc']).timestamp()
                if 0<=age<interval_seconds and data.get('state') in ('Completed','Partial','Scraping'):
                    _STARTED=True;return False
            except (ValueError,KeyError,TypeError):pass
        _STARTED=True
    threading.Thread(target=_run,args=(root,browser_enabled,max(1,int(max_pages))),
                     daemon=True,name='zos-vendor-source-refresh').start()
    return True
