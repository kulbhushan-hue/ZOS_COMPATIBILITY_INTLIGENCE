# z/OS Compatibility Intelligence — V4 installation and validation

## What V4 does

Retains the original nine-page Streamlit interface and working Broadcom PTF crawler. Fixes repeated vendor observations in Source Monitor by taking the newest **successful** source observation per vendor and URL, while retaining a separate history of every check. Adds **review-only** candidate matching between `MFX for z/OS` and `Syncsort MFX` when the exact version matches. Adds explicit `Unknown / Not verified` for previously blank PTF availability in the Compatibility Matrix and PTF worklist. Makes source-check time and PTF verification status distinct in the observations export. Improves regression coverage for IBM requirement tables and explicit Rocket release tables.

**V4 does not claim full live scraping for all 29 vendors**. Some official pages still return HTTP 403, require login, serve browser-rendered tables, or provide only product-level announcements. No 403 bypass and no invented PTF or compatibility status are implemented. No vendor audit observation silently overwrites the baseline.

## Requirements

Python 3.11 or 3.12, network access for clicking vendor refresh, and write access to the database directory. Installing Python is a prerequisite. For Streamlit Community Cloud, persistent SQLite storage is not guaranteed across restarts.

## Windows PowerShell

```powershell
cd path\to\zos_compatibility_intelligence
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m streamlit run app.py
```

If the PowerShell activation is blocked, call `.venv\Scripts\python.exe` directly rather than changing system-wide execution policy.

## Linux / macOS

```bash
cd /path/to/zos_compatibility_intelligence
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m streamlit run app.py
```

Open `http://localhost:8501`.

## Validation sequence

1. In **Source Monitor**, click **Refresh Broadcom now**. Check the log and download `broadcom_scraped_ptfs.csv` after a successful request. An extracted identifier does not mean the PTF is installed.
2. Select IBM/BMC/Rocket/Precisely/ASG in Source Monitor. Use **Check selected vendor sources**; start with 2 or 3 URLs each and adjust the timeout when needed. A 401/403 is recorded as a blocked source, not incompatibility.
3. Download **vendor source audit** to see every checked URL, including failed checks. Download **structured source observations** to see only the newest successful observation for each URL (no duplicates from repeated refreshes).
4. Check `review_candidate` and `matrix_promotion`. A review candidate is only a possible name match; it never changes a vendor compatibility cell automatically.
5. Open **Compatibility Matrix** and export Excel. Blank PTF availability is shown as **Unknown / Not verified**. Broadcom linked PTF identifiers remain distinct from historical AMXT-mentioned IDs.
6. Inspect actual vendor documents and installed SMP/E data before making a production migration decision.

## Streamlit Community Cloud

Push the **contents** of this folder to a GitHub repository. Choose `app.py` as the entrypoint. Put `requirements.txt`, all Python modules, `data/` CSVs and `ISV Compatibility assessment -Data.xlsx` in the same repository. Set `ZOS_DB_PATH` to a writable location if necessary; use an external durable store for long-term audit history. Enable network connectivity to approved vendor domains. Do not store credentials in repository source files.

## Automation

`refresh_all_vendors.py` can be invoked from an external scheduler. Read its CLI help/flags before using. Running the dashboard alone does **not** activate background scheduling. Avoid high-frequency crawling; respect vendor terms, rate limits and access restrictions.

## Troubleshooting

- **403 / 401**: source access is restricted; use authorized vendor access or a publicly available official alternative.
- **No IBM PTF rows**: IBM publishes minimum-level requirements and many PTFs through HOLDDATA/`REPORT MISSINGFIX`; generic web pages are not complete install-level inventories.
- **No Rocket/ASG observations**: an official HTML table must explicitly contain product, release and target z/OS status; brochures and home pages are not sufficient.
- **No observations despite readable URL**: the source may be JavaScript-rendered, a non-table narrative, or lack an exact product/release assertion. Consult URL audit notes.
- **Missing prior results after Cloud restart**: use persistent storage; local SQLite is ephemeral in Community Cloud.

## Restricted-site document fallback

In **Source Monitor → Import an authorized vendor HTML/PDF reference**, select the vendor, upload an officially obtained `.html`, `.htm` or `.pdf` file (up to 2 MB), and optionally include its official URL. Click **Extract evidence from document**. Product-level observations will appear in the review worklist when the document has a supported structured table. This does not automatically certify an installed release, bypass a portal login, or count as a live web scrape.
