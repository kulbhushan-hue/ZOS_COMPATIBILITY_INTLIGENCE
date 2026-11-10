# V6 changes (2026-11-09)

- Added `vendor_coverage.py`: one product-level acquisition gap row per baseline inventory record, with source approval, URL audit status, workbook PTF identifiers, and explicit release-evidence counts.
- Added Source Monitor worklist with filtering and CSV export, plus on-demand checking of one selected product reference.
- Added `extract_official_document_tables` for explicitly delimited IBM minimum-level and BMC support-matrix evidence in authorized PDF/text exports. These do not automatically certify an installed release.
- Added 5 offline tests covering coverage, failed source labeling, IBM/BMC document tables, and the rule against inferring support from prose.
- Retained original nine pages and dedicated Broadcom crawler; did not modify historical workbook content.

## Limitations

- IBM SPCR interactive reports, BMC authenticated portals and vendor JavaScript apps may require authorized exports or provider APIs.
- Other vendor source adapters are not equivalent to verified all-vendor PTF scraping.
- Product/source worklist identifies evidence gaps; it does not fill those gaps by guessing.
