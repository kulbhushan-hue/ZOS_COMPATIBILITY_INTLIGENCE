# V13 — Start with two commands

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

On opening the dashboard, the approved-vendor scraper runs automatically without additional commands. See [V13_TWO_COMMAND_START_HERE.md](V13_TWO_COMMAND_START_HERE.md) for details. Docker is not required.

---

# V10 backend scraping update

Start with **V10_BACKEND_START_HERE.md** for the latest scraper instructions. The original dashboard is retained.

**Latest update:** See [MULTI_VENDOR_V2_START_HERE.md](MULTI_VENDOR_V2_START_HERE.md) and [MULTI_VENDOR_V2_CHANGELOG.md](MULTI_VENDOR_V2_CHANGELOG.md) for the 2026-11-09 source adapters, verification caveats, and instructions.

# IMPORTANT: See `START_HERE.md` for complete installation, running, deployment, and refresh/PTF verification instructions.

# z/OS Compatibility Intelligence

A nine-page Streamlit dashboard built on the **original project** with its six vendor compatibility CSVs, existing matching/Excel utilities, and optional watsonx.ai RAG assistant. Includes a new read-only Broadcom HTML crawler, linked maintenance evidence extraction, versioned SQLite snapshots, and change detection.

## Start locally

Requires Python **3.11–3.12**, outbound HTTPS access to authorized vendor websites, and normal filesystem write permissions.

```bash
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The dashboard opens at `http://localhost:8501`. It immediately displays the **original 240 CSV records and the supplied AMXT Excel assessment**, without network scraping. These sources can contain different naming and overlapping products; the combined count is a count of distinct source keys, not proof of distinct installed products.

## Nine working pages

1. **Overview** — counts, support status, vendor coverage, latest snapshot, source jobs.
2. **Comparative Matrix** — compares z/OS 3.1 to 3.2 without inventing missing 3.1 statements.
3. **Compatibility Matrix** — filters on all six vendor CSVs and any exactly matched Broadcom scraped rows; source provenance, Excel download.
4. **PTF Intelligence** — product/release selection, extracted PTF IDs, linked PTF and Additional Information text, OS comparison, exact source links, Excel download.
5. **Source Monitor** — manual Broadcom refresh, option to follow approved off-page references, extraction metrics, errors and source directory.
6. **Change History** — compare successive successful Broadcom snapshots; inspect before/after records and export to Excel.
7. **Inventory Readiness** — upload customer CSV/XLSX with `Vendor, Product, VRM`, or select entries; view compatibility and PTF caveats and export results. Installed SMP/E service cannot be inferred.
8. **AI Assistant** — TF-IDF matching from all compatibility records; optional Granite text generation when IBM watsonx credentials are configured.

9. **Workbook Explorer** — browse all Sheet1, Sheet2 and AMXT values, filter, export, and inspect PTF worklists.

## Using the real Broadcom crawler

Open **Source Monitor → Refresh Broadcom now**. The backend:

1. Downloads the official Broadcom z/OS compatibility HTML matrix over HTTPS.
2. Finds the product table using its *z/OS V3R2, V3R1, V2R5* headers rather than assuming a fixed table index.
3. Extracts vendor, product, release, target OS, compatibility, and every PTF/Additional Information link associated with that OS cell.
4. Resolves same-page `#anchor` targets in the downloaded HTML. If the optional **Follow approved external detail pages** toggle is enabled, requests supported off-page HTTPS vendor links; only allowlisted vendor domains may be contacted.
5. Extracts source text, PTF/APAR IDs, FIXCAT references and possible USERMOD/SYSMOD/FMID indicators. Keeps the raw extracted text and original URL for manual audit.
6. Rejects obviously incomplete results, then atomically saves a new SQLite snapshot. The previous successful snapshot stays available on failure.
7. Replaces a baseline support status **only when vendor + product + release + z/OS match exactly after normalization**; other existing CSV rows are preserved. New source releases appear separately.

This is a conservative HTML parser, **not** a universal web crawler. Vendors may change page layouts, use authenticated portals, or include JS-driven or unresolvable links. Those links are marked partial/unavailable rather than fabricated. A live crawl must run in a network-connected environment; it is not run by packaging or tests.

**Important:** PTF identification is not PTF installation verification. IDs extracted from unrestricted narrative text may include related PTFs; read the original source to establish whether every ID is required. Source data is not a replacement for product lifecycle or SMP/E checks.

## Data and persistence

- `ISV Compatibility assessment -Data.xlsx`: **new reference workbook**, included intact with all three sheets: Sheet1 (vendor sources), Sheet2 (241 historical inventory rows) and AMXT (384 spreadsheet data rows including one blank vendor/product entry; 383 usable vendor/product assessment records). AMXT covers **z/OS 3.2**, and its statuses, PTF text, message IDs, links, MFA notes and comments are retained.
- `workbook_data.py`: imports and normalizes the AMXT sheet; alias matching is conservative and original text is preserved. Statuses such as `No Info` and free-text comments are never interpreted as verified Yes/No without explicit values. The AMXT workbook does **not** assert z/OS 3.1 compatibility, so 3.1 is never copied from 3.2.
- `data/*_compat.csv`: original six baseline vendor datasets. No changes to source CSVs.
- `reference/zOS_3.2_filtered.xlsx`: the provided reference workbook.
- `state/compatibility.sqlite3`: created at first use and holds real crawled snapshots, per-OS maintenance evidence, change records and refresh job logs. It is **not** included in the distribution.
- `ZOS_DB_PATH` environment variable: overrides the SQLite path. E.g. `ZOS_DB_PATH=/data/compatibility.sqlite3` for a mounted persistent volume.

**Streamlit Community Cloud** and other ephemeral containers may erase local SQLite files during redeployment/restart. Use a persistent mounted volume or migrate the store layer to a managed database for long-lived production audit history. The app does **not** run recurring background polling by itself: click Refresh or schedule `refresh_once.py` with an external persistent job runner and appropriate vendor rate limits. The UI displays the last successful snapshot, not guaranteed instantaneous vendor updates.

## AI configuration (optional)

The original `rag_engine.py` is preserved. Set `WATSONX_APIKEY`, `WATSONX_PROJECT_ID` (or `WATSONX_SPACE_ID`) and optionally `WATSONX_URL`, `WATSONX_MODEL_ID` in private environment secrets. Install the optional `ibm-watsonx-ai` library to enable text generation. Without this configuration, the **AI Assistant page works as evidence retrieval**.

Never commit tokens or API keys to the ZIP or source repository.

## Run tests

```bash
python -m unittest discover -s tests -v
python -m compileall -q .
```

Offline fixture tests validate product/OS mapping, internal anchor PTF extraction, atomic snapshot versioning and failed-job preservation. They **do not validate vendor network connectivity or a full browser session**.

## Deployment

A maintained `Dockerfile` serves Streamlit on port 8080 for IBM Cloud Code Engine. `legacy_app.py` preserves the original application as a reference. Existing deployment and presentation notes are included in `reference/`.

Use HTTPS, keep external vendor traffic bounded, respect vendor access policies, and verify licensing/usage terms before scheduling repeated crawls. Separate source adapters are needed to extract *live* detail pages for IBM, BMC, Rocket, Precisely and ASG; the dashboard already displays their CSV baseline records.

## 2026-11-02 refresh / PTF display bug fix

This release fixes two dashboard defects encountered after the first Broadcom refresh:

- Previously persisted SQLite observations lacked `ptf_links_present`, causing `KeyError` on app.py refresh. `store.py` now persists this flag, automatically migrates older SQLite schemas, and reconstructs the flag from saved link evidence. `app.py` also safely handles older records without this field.
- The data merge previously accessed `Series.product` as an attribute; Pandas interprets it as a method, preventing existing rows from matching by product name. The merge now uses bracket-based column access and populates the existing product row instead of creating an unnecessary duplicate.
- The PTF column shows extracted PTF IDs when available, and explicitly identifies links whose PTF IDs were **not** extracted, without inventing numbers. No PTF link alone proves no maintenance is needed.
- Added `test_refresh_regression.py` to verify saved snapshots, missing legacy fields, and schema migration; all seven offline tests pass.

**After deploying:** Update `app.py`, `store.py` and tests (or deploy the complete ZIP), restart the app and inspect the Compatibility Matrix and PTF Intelligence pages. You should not need to delete your existing SQLite database. A successful live refresh is still dependent on the vendor site's HTML format and outbound network access, and has not been exercised from this environment.


## 2026-11-02 workbook integration (latest)

The attached **ISV Compatibility assessment -Data.xlsx** has been fully integrated without replacing the earlier application. It includes 29 vendor labels in AMXT (some refer to the same corporate vendor under alternative names), beyond the earlier six-vendor CSV baseline. No credentials or account-bypassing behavior are included.

- Added **Comparative Matrix** and **Workbook Explorer** pages to preserve the useful three-tab AMXT dashboard behavior from the latest attached ZIP, while retaining the previous seven pages.
- Added workbook-derived PTF/USERMOD worklist to the PTF Intelligence page, visible even before a live Broadcom refresh. Displays original cells *and* parsed identifiers separately.
- Added AMXT source row, original compatibility text, maintenance text, verification URLs, message IDs and MFA/access notes to the merged dataset. The original workbook remains unchanged and available in the ZIP.
- Added `refresh_once.py` for running a real Broadcom scrape under a separate external scheduler. For example, on an always-on Linux host with a **persistent mounted database**, configure a daily cron entry: `0 5 * * * cd /your/project && ZOS_DB_PATH=/persistent/compatibility.sqlite3 /your/venv/bin/python refresh_once.py`. This does **not** schedule itself when deployed.
- The UI PTF worklist shows the source's assertions such as “PTFs not installed” strictly as **human-entered notes**, not evidence from an installed mainframe or an authoritative current maintenance record.

### Deployment checklist

1. Copy all files from this ZIP, not just the new `app.py`; the Excel and `workbook_data.py` must both be at the project root.
2. Keep `requirements.txt` and install dependencies. For Streamlit Community Cloud set entrypoint `app.py` with the project's root working directory.
3. Open **Workbook Explorer → AMXT**, check the original PTF IDs and reference URLs, then open **PTF Intelligence**.
4. Open **Source Monitor → Refresh Broadcom now** to perform a real scrape (requires vendor network access). Verify new PTF IDs before relying on them for a migration.
5. If you need long-lived automated history, configure persistent storage and an external scheduler.

### Validation

Twelve offline regression tests were run successfully including workbook loading, real source cell preservation, the exact AMXT LU17113/LU19858 example, dashboard merge and the earlier `ptf_links_present` migration fix. **No full Streamlit browser execution or live Broadcom network crawl was performed in the build environment**, so external-site changes or Cloud deployment differences may still require validation.

## V7: Full-link backend deep scraping

For backend-only multi-vendor source extraction, see **[DEEP_SCRAPING_START_HERE.md](DEEP_SCRAPING_START_HERE.md)**. Run `python deep_scraper.py --max-pages 200 --depth 2`; no dashboard changes are required. Results are saved to `exports/deep/` with original URLs, PTF IDs, excerpts, crawl audit and retry checkpoint. Live vendor access requires the deployment environment to reach and be authorized by each source.

## V11: inspect actual vendor response content

See `V11_SOURCE_CONTENT_START_HERE.md`. The new source-content cache, offline replay,
and page diagnostics are backend-only; the dashboard is not modified.
