# V5 changelog – 9 November 2026

- Added bounded, one-hop discovery of up to two explicit compatibility/requirements links per vendor from permitted public HTML source pages (IBM, BMC, Rocket, ASG, Precisely).
- Each discovered page is separately fetched with the existing vendor domain, public IP, response type, size, timeout, and redirect protections. HTTP 401/403/404 remain recorded as restrictions, not negative compatibility determinations.
- Prioritized workbook product-specific and operator-supplied references after known curated matrices rather than allowing generic home pages to crowd out the requested evidence.
- Added Source Monitor latest-by-URL metrics and release-specific observation count (for review only).
- Preserved nine-page UI, existing Broadcom deep PTF scraper, historic inventory and Excel, existing PTF availability and installation distinctions.
- Four regression tests cover authorized link discovery, cross-vendor blocking, one-hop execution, and optional no-follow behavior. All 50 offline tests pass.
- **Limit:** no live end-to-end vendor crawl was run inside this build environment. No additional validated IBM/BMC/Rocket/ASG product release identifiers are claimed. Some sources require authorized document exports.
