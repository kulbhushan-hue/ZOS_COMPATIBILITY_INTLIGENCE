# 2026-11-09 Multi-vendor source-audit update

- Preserves original nine-page dashboard and original Broadcom PTF deep-link parser.
- Adds `multi_vendor.py`, official-source discovery, URL validation, HTML/PDF extraction, controlled public-source checks, and per-source evidence/failed-check audit trail.
- Adds `refresh_all_vendors.py` as a CLI for an external scheduler.
- Adds Source Monitor controls for all workbook vendors, per-vendor audit table, downloadable source results, source excerpts, and supported explicit product/OS support-table assertions.
- Adds parsing for BMC public mainframe support matrix and Action Software release history. These observations are separate from the main matrix unless exact release-specific compatibility can be proven and intentionally integrated later.
- Adds official-source URLs for 21CS, Action Software, Chicago-Soft, NewEra, and Vanguard where verified publicly.
- Adds test cases for unsafe URLs, evidence handling, store persistence, and source parser behavior.

**Limitations:** A full live multi-vendor compatibility/PTF extractor across all 29 vendors is not demonstrated. Vendor portals vary, with dynamic SPCR, authentication/MFA, and missing structured product-level URLs. The audit distinguishes `Read`, `Blocked / failed`, and `No approved source URL` rather than fabricating verified coverage.
