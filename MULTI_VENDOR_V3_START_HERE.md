# z/OS Compatibility Intelligence — Multi-Vendor V3

## What this version changes
- Keeps the original nine Streamlit pages and Broadcom deep-link PTF crawler.
- Prioritizes IBM's z/OS 3.2 requirements page in the official-source audit, extracting published minimum product levels and recognized maintenance IDs **without certifying** an installed product release.
- Continues to parse BMC's explicitly published AMI Capacity Management matrix, capturing its stated starting-release note. If BMC returns HTTP 403, the audit reports the access restriction and does not fabricate compatibility.
- Adds an explicit product + release + z/OS matrix parser for accessible Rocket/ASG HTML pages. General product webpages and ASG PDFs are **not** sufficient to certify a release.
- Adds exact inventory-release matching to published observations with a separate `matrix_promotion` and `baseline_match` review status. **No automatic overwrite** of historical CSV / AMXT compatibility data from unreviewed observations.
- Removes the known-broken Rocket `/node/56111` source link.
- Classifies missing/authentication-blocked sources separately from readable sources.

## Install (Windows)
1. Install Python 3.11 or 3.12 from python.org (enable Add to PATH).
2. Unzip this archive, open PowerShell inside the folder containing `app.py`.
3. Run:
   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   python -m streamlit run app.py
   ```
   If Python 3.11 is unavailable, use your installed supported Python version for `-m venv`.
4. Open http://localhost:8501 .

## Install (Linux / macOS)
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## How to verify multi-vendor extraction
1. Open **Source Monitor**. Broadcom remains available through **Refresh Broadcom now**.
2. Select **IBM, BMC, Rocket, Precisely, ASG**, with 2-4 URLs/vendor and a reasonable timeout.
3. Click **Check selected vendor sources**. Refresh can take time and is dependent on public website access.
4. Check **Result**, **Access status**, **Structured observations**, and **Details**. A 401/403 means the vendor source restricts automated access; it does NOT mean its products are incompatible.
5. Download `vendor_source_audit.csv` and `vendor_published_observations.csv`. Review exact `product`, `vrm`, `zos_version`, `compatibility`, `source_url`, `baseline_match`, and `matrix_promotion` values.
6. Only consider product/release evidence confirmed when both the vendor document and specific release support it. Entries with `Not stated` are not release certification.
7. **Compatibility Matrix** continues to display original AMXT/CSV data and Broadcom verified snapshots; other vendor observations appear in Source Monitor for review, not automatic override.

## Automated scheduled source auditing
```bash
python refresh_all_vendors.py --vendors IBM BMC Rocket Precisely ASG --per-vendor 3
python refresh_once.py
```
Run these through an external scheduler (cron, CI, or a persistent task runner). Streamlit itself does not provide a durable unattended scheduler. SQLite needs persistent disk on cloud deployments.

## Add official product-specific source URLs
Create `official_sources.csv` with headers `Vendor,URL`, then upload it through Source Monitor or run:
```bash
python refresh_all_vendors.py --vendors IBM BMC Rocket ASG --sources official_sources.csv --per-vendor 5
```
Only explicitly allowed official public vendor domains are fetched. Authentication, restricted pages and missing product versions require authorized vendor access/manual validation.

## Test
```bash
python -m unittest discover -s tests -v
python -m compileall -q .
```

## Deployment (Streamlit Community Cloud)
Commit all source files, `data/` CSV files, the Excel source workbook, `requirements.txt`, and `app.py` to GitHub. In Streamlit Cloud, choose `app.py` as the entry point. Do not commit `.venv`, SQLite database, or passwords. Cloud refreshes are manual unless an external scheduler can reach a persistent store.

## Important limitations
- This release is **not** a verified live scraper for all 29 vendors. It adds structured extraction and traceability only where public source content supports it.
- Vendor 403/login responses cannot be solved by retrying arbitrary routes or bypassing access controls. Use approved support credentials, vendor APIs, or authorized exported reports.
- An ID mentioned in source text does not prove its PTF is available, required for that exact installed release, or applied to the user's system.
- The offline test suite checks parser rules and regression behavior; it does not confirm the live contents or availability of external vendor websites.
