# PTF evidence and data-quality update — 2026-11-09

Retains the previous nine-page dashboard and successful Broadcom nested-anchor crawler.

- Compatibility Matrix Excel: explicit source-linked PTF ID, PTF availability,
  workbook-mentioned IDs (separate), evidence provenance, timestamp and verification.
- PTF Intelligence: enriched combined worklist and AMXT original worklist.
- Source Monitor: clearer identifier status and retained deep-link evidence.
- Joins constrained to vendor + product + release + operating system.
- No fallback that treats unavailable/superseded PTFs as installed or ready.
- Existing SQLite schema remains compatible; no database reset required.
- Existing six vendor CSVs and original three-sheet ISV workbook preserved.

See START_HERE.md for installation, tests and limitations.

---

# Release: PTF display + Source Monitor refresh fix

## Fixed

- Legacy `ptf_links_present` database schema migration is retained and verified.
- Broadcom PTF anchor extraction now handles both semantic sections and anchor-in-table-row layouts without pulling PTFs from subsequent products.
- PTF identifiers and PTF-link-presence are separate concepts; the Source Monitor reports exact extract coverage.
- The Compatibility Matrix includes **Extracted PTF IDs** and **PTF evidence** columns.
- PTF Intelligence includes the **AMXT source worklist** and a **combined vendor worklist** with identifiers, usermod details, comments and verification hyperlinks.
- Partial/unreadable vendor detail pages **do not overwrite** maintenance already supplied by the AMXT workbook or historic CSV data.
- Previous snapshot preservation and migration behavior remain tested.
- Source Monitor refresh exceptions remain visible even if error-log recording fails.
- Vendor-sourced PTF tokens are kept distinct from APAR token prefixes.

## Preserved

- Nine-page dashboard, original six vendor CSVs, all three Excel workbook sheets,
  z/OS 3.1 comparison (no false inference from 3.2), AI retrieval, inventory,
  snapshot change tracking, Excel export and manual Broadcom crawl.

## Validation

- 15 offline unit/regression tests pass on supplied code and realistic HTML fixtures.
- All application Python source files compile.
- No live Streamlit/third-party website end-to-end smoke test in this environment.
- Testing Streamlit reference link requires authentication and is not directly inspectable.


## 2026-11-09 — Broadcom anchor PTF fix
- Fixed detail extraction to traverse nested content after each named PTF anchor,
  stopping at the next detail anchor (instead of the next ordinary element ID / table row).
- Added realistic multi-version/multi-product regression fixtures and missing-anchor test.
- Preserved existing nine-page UI, data sources, exports and snapshot database.
- Note: successful live vendor connectivity must still be confirmed post-deployment.
