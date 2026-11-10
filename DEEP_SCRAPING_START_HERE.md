# V7 — Backend-first deep vendor scraping

**Scope:** This update does NOT redesign or change the Streamlit dashboard. The new `deep_scraper.py` collects product compatibility and maintenance evidence from approved, accessible source links in the existing workbook, vendor CSVs, curated sources, and the provided V6 product worklist.

## Requirements

- Python 3.11 or 3.12, internet access from the machine running the crawler.
- Vendor websites must permit automated access; use an authorized exported document for login-protected or 403 pages.
- The package includes the prior 9-page Streamlit application, but scraping works independently of the UI.

### Windows (PowerShell)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover -s tests -q
python deep_scraper.py --max-pages 100 --depth 2 --output exports/deep
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -q
python deep_scraper.py --max-pages 100 --depth 2 --output exports/deep
```

Run additional batches with the **same command**. Completed URLs and pending links are stored in `exports/deep/deep_scrape_checkpoint.json`. Runs pick up where they left off.

### Refresh and retry

```bash
# Continue pending URLs (the default)
python deep_scraper.py --max-pages 200 --output exports/deep

# Start a new verification cycle and re-fetch all input source URLs
python deep_scraper.py --fresh --max-pages 250 --output exports/deep

# Re-attempt failed URLs without refreshing all successful sources
python deep_scraper.py --retry-failed --max-pages 100 --output exports/deep

# Optional extra official URLs; CSV headers: Vendor,URL,Product,Release
python deep_scraper.py --sources my_vendor_links.csv --max-pages 200
```

The source queue includes *all distinct accessible approved HTTP addresses* (rather than only 2 per vendor), and follows relevant same-vendor links up to two hops. It avoids login and unrelated links; max pages and per-host throttling protect vendor sites. This is not a browser automation engine. JavaScript-only interfaces, and hash fragment routes that require browser state, may not yield data through HTTP parsing and require an authorized document export or a vendor API.

### Handle 403 or authenticated vendor portals

Export the exact page as HTML or PDF using your authorized vendor account. Create `documents.csv`:

```csv
Vendor,Path,SourceURL,Product,Release
BMC,authorized_docs/bmc_support.html,https://docs.bmc.com/your-official-url,BMC AMI Example,1.0
IBM,authorized_docs/ibm_requirements.pdf,https://www.ibm.com/docs/example,IBM Example,2.0
```

Then:

```bash
python deep_scraper.py --max-pages 10 --documents-manifest documents.csv
```

The parser will label such data **Operator-supplied document (not live)**. The tool does not bypass logins, MFA, paywalls or robots restrictions. Do not put credentials in the CSV.

### Files generated in `exports/deep/`

| Output | Meaning |
|---|---|
| `all_vendor_extracted_compatibility.csv` | Explicit compatibility table cells, with vendor, product, release, target z/OS, source, excerpt, match status |
| `all_vendor_extracted_ptfs.csv` | Maintenance identifiers extracted from local rows/sections, source excerpts and availability/install labels |
| `vendor_source_evidence.csv` | Traceable evidence, original URL and document SHA256 |
| `vendor_scraping_results.csv` | URL-by-URL status, table/record counts and discovered links |
| `vendor_failed_links.csv` | Network, access, robots and parser failures |
| `deep_scrape_checkpoint.json` | Resumable crawl state |

**Do not interpret extracted IDs as PTFs installed or necessarily applicable to an installed release.** Status is only promoted with an explicit vendor table and a verified release match; otherwise evidence remains for review. A source URL being readable does not establish that the product is supported.

## Automation

Use an external job scheduler (cron, Windows Task Scheduler, CI scheduled job, or a cloud job runner) to execute `python deep_scraper.py --fresh --max-pages 250 --output exports/deep`. Large crawls may require several runs to drain the queue. Store the output directory on durable storage: Streamlit Community Cloud local filesystem is ephemeral. For daily collection, schedule batches at an interval compatible with the required number of URLs and vendor site rate limits.

## Coverage and limitations

- Original worklist has 623 baseline product records and around 130 approved vendor URL variants; many distinct hash-fragment routes can share one HTTP document. The crawler normalizes these to fetchable HTTP endpoints. Such JavaScript route variants need a browser-based or exported-document adapter to collect distinct dynamic states.
- Some vendors in the workbook have no approved source URL. They are **not** fabricated or inferred from unrelated domain content.
- Some PDF tables, JavaScript-only source matrices, login-only reports, and vendor-specific identifiers need additional adapters and real-site testing.
- Crawling has **not** been run live by this package build. Offline tests validate parsing, queuing, checkpointing, and safety behavior; use the generated audit file to measure actual deployment results.

## Existing dashboard

The existing app remains available:

```bash
python -m streamlit run app.py
```

The new backend reports are separate and are **not automatically merged into compatibility decisions on the dashboard**. First review source evidence and exact product/release matching before promoting claims into migration-readiness decisions.
