# Multi-vendor z/OS Compatibility Intelligence — Start Here

This version **keeps the nine-page Streamlit dashboard** and the existing Broadcom deep-link/PTF crawler. It adds a controlled **all-vendor public-source audit** on the Source Monitor page.

## 1. Installation

Requirements: Python 3.11 or 3.12; Internet access from the machine running Streamlit; permission to read public vendor documentation.

Windows PowerShell:

```powershell
cd zos_compatibility_intelligence
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m streamlit run app.py
```

Linux/macOS:

```bash
cd zos_compatibility_intelligence
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open http://localhost:8501 . Source data is present immediately from the CSVs and original three-sheet workbook; live source checks require a refresh.

## 2. Scrape Broadcom

On **Source Monitor**, click **Refresh Broadcom now**. This extracts Broadcom's compatibility matrix and follows its PTF/Additional Information references. A successful snapshot appears in the main Compatibility Matrix and PTF Intelligence pages. If a refresh fails, the last successful snapshot remains available.

## 3. Check other vendors — new feature

Open **Source Monitor → All-vendor source audit**. Select vendors, select up to two approved source URLs per vendor, then click **Check selected vendor sources**.

The audit reads official public HTML or PDF (up to 2 MB), looks for matching product names and z/OS references, extracts PTF identifier *mentions*, and stores the source URL, checked timestamp, excerpts, and errors. Explicit table-based observations are also shown where a supported parser is available (BMC published support matrix and Action Software release history).

**Important:** Source mentions are not proof of compatibility or maintenance applicability. They are not silently overwritten into the version-specific compatibility matrix. IBM's SPCR is a dynamic interactive system; many other sources may be blocked by login/MFA or may not provide structured compatibility tables. Broadcom is the only fully integrated deep-link and version-specific compatibility crawler in this build. This release does not falsely claim complete deep scraping for all 29 vendors.

The original AMXT workbook has 29 vendors, but public product-specific verification links for relatively few vendors. Curated official pages are available for several more. Any vendor without an approved source shows `No approved source URL`, not `Success`.

## 4. Unattended schedule (external scheduler)

Run one-shot commands from the project folder:

```bash
python refresh_once.py
python refresh_all_vendors.py --vendors IBM BMC Rocket Precisely ASG --per-vendor 2
python refresh_all_vendors.py --all --per-vendor 2
```

On a Linux server, a cron example for daily 02:00 (server local time):

```cron
0 2 * * * cd /srv/zos_compatibility_intelligence && /srv/zos_compatibility_intelligence/.venv/bin/python refresh_once.py >> /var/log/zos_broadcom.log 2>&1
30 2 * * * cd /srv/zos_compatibility_intelligence && /srv/zos_compatibility_intelligence/.venv/bin/python refresh_all_vendors.py --all --per-vendor 2 >> /var/log/zos_vendors.log 2>&1
```

Only install scheduler entries when you actually want automatic checks. Streamlit Community Cloud by itself does **not** provide a reliable persistent scheduler or durable local SQLite files. For production, configure a separate scheduled worker and persistent database volume via `ZOS_DB_PATH` that is accessible to both dashboard and worker. **Never schedule large all-vendor batches inside Streamlit page rendering.**

## 5. Logs, audit trail, export

- Download **vendor_source_audit.csv** from Source Monitor.
- Expand **Inspect exact source excerpts and mentioned PTF IDs**.
- When supported tables yield explicit assertions, use **vendor_published_observations.csv**.
- Download the **Compatibility Matrix** export separately. It continues to preserve workbook/Broadcom values with their provenance.
- `state/compatibility.sqlite3` stores local audit and Broadcom history; back up or mount persistent storage for production.

## 6. Verify on your computer

```bash
python -m unittest discover -s tests -v
python -m compileall -q .
```

All tests are offline: they check HTML/PDF parser behavior, source URL restrictions, source status labels and database migrations. They cannot establish that a vendor's public website will be reachable on your specific network.

## 7. Streamlit Cloud

Push the complete extracted folder's **contents** (including `app.py`, `multi_vendor.py`, `store.py`, `requirements.txt`, workbook, `data/`, and `tests/`) to GitHub. Set `app.py` as the entry point. The vendor audit requires outbound HTTPS; Cloud IP blocks and vendor rate limits may prevent some sources from being read. To preserve history between restarts use persistent external storage, not the default ephemeral filesystem.

## 8. Security / verification notes

- No login or MFA bypass; do not add passwords to source URLs.
- Do not equate a source-mentioned PTF with a verified required/available/installed PTF.
- Public-source audits are capped and use timeouts; do not scrape prohibited or restricted content.
- Carefully verify compatibility per product **and release** against the vendor's authoritative document before upgrade planning.

### Add official source URLs for the 18 vendors that currently lack URLs

Prepare a UTF-8 CSV such as:

```csv
Vendor,URL
21CS,https://21cs.com/
Chicago-Soft Ltd,https://chicago-soft.com/
```

Use vendor names matching the Workbook Explorer and include authoritative compatibility/documentation pages where possible (product-specific pages are better than home pages). Upload this CSV in **Source Monitor** before clicking **Check selected vendor sources**; these URLs apply to the current audit run, and the resulting evidence is saved. For unattended jobs, use:

```bash
python refresh_all_vendors.py --all --sources vendor_sources.csv
```

Public URL validation blocks private/internal addresses, login endpoints, and non-vendor hosts for known vendor domain mappings. The app never uses this mechanism to bypass authentication. A URL being accepted does not imply it publishes the necessary compatibility information.
