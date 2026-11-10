# z/OS Compatibility Intelligence — V6

## What changed

V6 retains the existing nine-page dashboard, Broadcom deep-link PTF crawler, CSV baselines and AMXT workbook. This release adds **per-inventory-record source coverage**, a **single-product source-check action** in Source Monitor, and conservative extraction of explicitly delimited IBM/BMC tables from authorized vendor PDF/text exports. It does **not** claim automatic PTF coverage for all 29 vendors.

### Important distinction

- **Vendor URL read:** a page was accessible, not proof of compatibility.
- **Product mention:** a name was near a z/OS reference, not proof of support.
- **Minimum product level:** a documented prerequisite, not proof your installed copy meets it.
- **Exact-release assertion:** a source table explicitly identifies vendor + product + release + target z/OS. Still needs review.
- **Installed PTF:** requires SMP/E or mainframe inventory evidence; cannot be inferred by web scraping.

## Local setup (Windows PowerShell)

1. Extract the project ZIP. Keep the `data` folder and `ISV Compatibility assessment -Data.xlsx` alongside `app.py`.
2. Install Python 3.11 or 3.12 (check `py -3.11 --version`).
3. Open PowerShell in the folder containing `app.py`.
4. Run:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

If activation is blocked by your PowerShell policy, use `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.\.venv\Scripts\python.exe -m streamlit run app.py` instead.

## Local setup (Linux / macOS)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open http://localhost:8501 (unless Streamlit reports another port).

## Source Monitor workflow

1. **Broadcom:** Click **Refresh Broadcom now**. Extracted PTF numbers are shown separately from availability and installed status.
2. **Other vendors:** Choose vendors, click **Check selected vendor sources**; public access or login blocking will be shown accurately.
3. Open **Product-by-product source coverage and missing evidence** to see baseline inventory rows that have an official-domain URL, those needing one, blocked source checks, and exact-release observations for manual review.
4. Export `vendor_product_source_worklist.csv`. Do not interpret URL coverage as verified compatibility.
5. For a specific inventory item, use **Check one product-specific official reference now**, which checks only that source and does not crawl unrelated vendor content.
6. For 401/403 sources, use **Import an authorized vendor HTML/PDF reference** (up to 2 MB). A PDF may contain readable prose but not machine-recognizable tables: a missing observation means *not extracted*, not *not compatible*.
7. Re-run exports after successfully reading new source evidence. Non-Broadcom findings remain in **Published vendor observations** for human review, not automatically overwritten in the Compatibility Matrix.

### Additional official URLs

A file with headers `Vendor,URL` can be uploaded to Source Monitor. Addresses must be public HTTP(S) and belong to the allowed official domain for that vendor; unsafe/private URLs are rejected. The list is per session, not a persistent configuration. The example `vendor_sources_template.csv` is included.

## Command-line run and tests

```bash
python -m unittest discover -s tests -q
python refresh_all_vendors.py --vendors IBM BMC Rocket Precisely ASG --per-vendor 3
python refresh_once.py
```

The source refresh commands perform network requests and may be blocked by vendor auth, proxy restrictions, rate limiting, or server-side changes. For unattended refreshes, use an external scheduler. Set `ZOS_DB_PATH` to a **persistent** location; Streamlit Community Cloud local files are not reliable durable storage.

## Streamlit Community Cloud deployment

1. Create a private GitHub repo and upload the extracted app files and directories (do not upload `.venv`, `state`, caches or private credentials).
2. Set the app entry point to `app.py` and Python 3.11 / 3.12.
3. Install from `requirements.txt` (Streamlit Cloud does this automatically).
4. Confirm all 9 pages render with the bundled CSV and Excel; refresh a small number of public vendor sources.
5. Use external durable storage for real audit history; otherwise reboot/redeploy may reset SQLite history.

## Troubleshooting

- **HTTP 403 / login:** Obtain vendor-approved access or use a legally obtained HTML/PDF export. Do not attempt to bypass authentication.
- **No PTF IDs after readable page:** Source may lack PTFs, contain dynamic JavaScript, or produce PDFs without extractable table text. Source Monitor will record the gap; it does not imply no PTFs are required.
- **Broadcom PTF list looks stale:** Use a new Broadcom refresh and verify its timestamp and linked source, then check exported CSV.
- **Products visible in workbook but not in live scrape:** This is expected until product-specific source evidence is acquired; the baseline is retained.

## Test status

55 offline unit/regression tests passed in the packaging environment. Python code compilation passed. A complete live vendor crawl and browser deployment **were not verified** in this environment.
