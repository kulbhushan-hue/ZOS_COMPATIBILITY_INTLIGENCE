# V5 – Product-specific vendor-source discovery and evidence review

## What changed

- Preserves the nine-page Streamlit dashboard, Broadcom PTF extraction, six CSV baselines and AMXT workbook.
- The source audit now follows **at most two** explicitly labelled compatibility/requirements documents discovered on approved IBM, BMC, Rocket, ASG and Precisely pages. Follow-up links must be same-vendor official public HTTP(S) URLs. Every follow-up has its own audit record, URL, outcome and timestamp.
- A BMC hub page can now lead to a separate matrix, if a valid link exists in the fetched HTML; access-restricted links are recorded as blocked instead of creating empty or false compatibility entries.
- Source Monitor now shows the distinct number of checked URLs, currently readable URLs, blocked URLs and exact-release assertions that require review.
- Product-level / minimum-level vendor requirements **never** automatically overwrite product-and-release compatibility. Extracted PTF IDs do **not** prove applicability, publication availability or installation.
- The full historical log is retained; the published observations export retains latest distinct evidence rather than duplicating each refresh.

## Local installation – Windows / Linux / macOS

1. Install Python 3.11 or 3.12.
2. Extract the entire ZIP, including `data/`, `reference/`, the `.xlsx` workbook and all `.py` modules.
3. Open a terminal in the folder containing `app.py`.
4. Create a virtual environment and activate it:

   **Windows PowerShell**
   ```powershell
   py -3.11 -m venv .venv
   .venv\\Scripts\\Activate.ps1
   ```
   **Linux / macOS**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
5. Install dependencies: `python -m pip install -r requirements.txt`
6. Start: `python -m streamlit run app.py`
7. Open `http://localhost:8501`.

## Run a vendor refresh

1. Go to **Source Monitor**.
2. For Broadcom, click **Refresh Broadcom now** to update actual linked PTF data.
3. For other vendors, select IBM/BMC/Rocket/Precisely/ASG, set initial URLs per vendor to 2–5 and click **Check selected vendor sources**. Explicit related compatibility documents may also be requested, subject to the per-vendor follow-up limit.
4. Review both the source-audit table and published-observations table. HTTP 401/403 means blocked: it does **not** mean a product is incompatible.
5. Download `vendor_source_audit.csv` and `vendor_published_observations.csv`; confirm exact vendor, product, release, target OS, document URL and evidence wording.
6. For blocked official sources, import an **authorized** HTML/PDF export in Source Monitor. It is labelled operator supplied rather than live verified.

## Run tests

`python -m unittest discover -s tests -q`

## Schedule externally (optional)

`python refresh_all_vendors.py --vendors IBM BMC Rocket Precisely ASG --per-vendor 3`

Run from an external scheduler such as cron, Windows Task Scheduler or a CI job. Streamlit itself does not guarantee background jobs or persistent storage. Set `ZOS_DB_PATH` to a path on durable storage for retention.

## Known limitations / honest coverage

- Broadcom supports a dedicated table-and-PTF crawler. Other vendors use conservative official-source document readers and limited structured adapters. **Full automatic product/release/PTF certification for all 29 vendors has not been demonstrated.**
- Some official vendor pages require login or block cloud scraping, including previously reported BMC and IBM URLs. This update does not bypass those restrictions.
- Public documents may omit exact releases, PTF applicability or installed status; such rows remain unverified or review-only.
- The new source-discovery mechanism has been tested with representative offline HTML, not a full production network crawl. Verify with your next Source Monitor exports.
