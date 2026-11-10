# Multi-Vendor V3 — 2026-11-09

- IBM: prioritize official z/OS 3.2 product-level requirement sources and record PTF identifiers mentioned in the requirement table.
- BMC: retain explicit table observations and published support-started version when available; label HTTP 401/403 as access restrictions.
- Rocket/ASG: add narrowly scoped explicit HTML compatibility table extraction requiring product, release and z/OS-version columns. General source text does not certify compatibility.
- Audit: distinguish blocked public sources from negative compatibility; do not overwrite the AMXT and baseline matrix from unreviewed evidence.
- Reconciliation: append exact-vendor/product/release baseline match indicators to Source Monitor observations and exported CSV.
- Remove previously broken Rocket `node/56111` directory entry.
- Added 5 new regression cases; 37 offline unit tests passing.

**Status:** Works in offline parser tests. Live IBM/BMC/Rocket/ASG results remain dependent on actual public source access and the content vendors publish.
