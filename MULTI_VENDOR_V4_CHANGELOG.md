# Multi-vendor V4 changes (9 November 2026)

- Kept the nine-page dashboard, Broadcom scraper, AMXT workbook and legacy project files.
- Latest **successful** source observation per vendor+URL now drives the published-observations report; full audit/check history remains accessible.
- Prevented duplicate Precisely findings from accumulating after repeated refreshes.
- Added review-only exact-version naming candidate: `MFX for z/OS` → `Syncsort MFX`, never automatic promotion.
- Added an explicit provenance field (`source_checked_at`) to exported observations, distinct from `ptf_verified_at` (unknown unless actually verified).
- Filled blank PTF availability with `Unknown / Not verified` in export and UI worklists.
- Retained authorization barriers: neither 403s nor marketing pages turn into compatibility assertions.
- Added seven offline regression tests for deduplication, matching, minimum-level evidence, and PTF status semantics.
- No live vendor crawler execution or Streamlit Cloud browser validation performed in the packaging environment.
- Added an authorized HTML/PDF upload path in Source Monitor for sources inaccessible to server-side scrapers (2 MB limit); operator-supplied evidence is never labelled live verification.
