# z/OS Compatibility Intelligence — Multi-vendor evidence update (9 Nov 2026)

## Important distinction

The app **does not claim to automatically validate all 29 vendors**. It shows all vendor baseline records from the supplied workbook; public sources can be checked for structured *observations* by vendor. Broadcom is the only fully integrated matrix + linked-PTF crawler. Other vendor source observations are separately visible in Source Monitor, not silently merged into a release's compatibility cell. This avoids inaccurate migration advice.

## Setup (Windows)

1. Install Python 3.11 or 3.12 from python.org and enable *Add Python to PATH*.
2. Extract the ZIP. Open a terminal in the extracted directory (the one containing `app.py`).
3. Run:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m streamlit run app.py
```

If PowerShell activation is blocked, invoke `.venv\Scripts\python.exe -m streamlit run app.py` directly.

## Setup (Linux/macOS)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open http://localhost:8501.

## Refresh and verify

1. Open **Source Monitor**.
2. Run **Refresh Broadcom now** for its full matrix and linked PTF details.
3. Select **IBM, BMC, Precisely, Rocket, ASG** in the multi-vendor source-check area. Increase **Maximum source URLs per vendor** to 3 or 4 if needed; 2 prioritizes high-value sources.
4. Click **Check selected vendor sources**. Results are saved in SQLite. Check `Structured observations`, `Result`, `Details`, then expand/download **Published vendor observations**.
5. Confirm any BMC product version explicitly. A generic table `X` is not a product-VRM certification. IBM minimum-product-level tables do not demonstrate that the installed version is ready. Precisely MFX *minimum* OS is not a certification for every newer release.
6. Review **PTF Intelligence** and **Compatibility Matrix**. Separate historical AMXT comments from vendor source evidence. When a PTF is 'not installed' in AMXT, do not treat it as 'not available' from the vendor.

## Scheduled checks (external scheduler)

```bash
python refresh_once.py
python refresh_all_vendors.py --vendors IBM BMC Precisely Rocket ASG --per-vendor 3
python -m unittest discover -s tests -v
```

Schedule these commands externally using cron, Windows Task Scheduler, or a cloud job on persistent storage. Merely running Streamlit does not create a background daily job. `ZOS_DB_PATH` can point to a persistent SQLite file in a single-writer deployment. Community Cloud local storage is ephemeral; use a persistent-volume deployment for historical audit records.

## Source coverage / limitations

- **Broadcom**: structured HTML matrix and linked maintenance; published PTF data still needs applicability and installed-maintenance verification.
- **IBM**: public z/OS installation requirements tables, plus SPCR report links. Interactive product-specific SPCR queries may require additional authorized workflows; no automatic inferred compatibility.
- **BMC**: public AMI Capacity Management support table; private PAC/compatibility portals may return HTTP 403 and are not bypassed. Some table assertions omit product VRM.
- **Precisely**: MFX minimum-OS lifecycle table, Ironstream z/OS 3.2 announcements, and selected alphanumeric maintenance references. Product release is often unspecified.
- **Rocket / ASG**: currently auditable public sources only; no fabricated certifications. Add legitimate, accessible product-specific URLs to Source Monitor's `Vendor,URL` CSV.
- **Remaining AMXT vendors**: source checking when a valid official URL is configured; without accessible product-release-specific sources, status stays workbook-based/unverified.

## Tests

Run `python -m unittest discover -s tests -v`. The tests use local HTML fixtures and do not require vendor internet access. A successful offline test cannot certify that today's vendor site will remain reachable or that current product releases are supported.

## Project files

`app.py` (dashboard), `crawler.py` (Broadcom), `multi_vendor.py` (controlled source-check layer), `vendor_assertions.py` (IBM/Precisely structured parsers), `quality.py` (availability versus installation labels), `store.py` (SQLite snapshots/audits), `refresh_all_vendors.py` (external batch run), `data/` (baseline vendor CSVs), `ISV Compatibility assessment -Data.xlsx` (original reference workbook), `tests/` (regression suite).
