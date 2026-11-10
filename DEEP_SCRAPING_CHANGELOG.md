# Deep scraping backend — V7

- New standalone `deep_scraper.py` with all-link URL ingestion from AMXT, original vendor CSVs, curated official sources and V6 product worklist.
- Deep, bounded same-vendor link discovery and detailed HTML table/section, PDF and vendor-adapter extraction.
- Source-level evidence/identifier and compatibility CSV exports plus failures, timings, SHA256 and release-match review labels.
- Resumable checkpoint, fresh rescans, retry of failures, robots handling, rate limiting, URL safeguards and no authentication bypass.
- Authorized exported vendor document support for blocked web access.
- Dashboard and original data remain untouched.
- New offline tests added to the existing suite.

Live verification for every vendor remains environment-dependent; no claims of universal live success.
