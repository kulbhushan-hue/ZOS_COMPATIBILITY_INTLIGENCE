# Multi-vendor 2026-11-09 update

- Kept the existing nine-page Streamlit dashboard and complete Broadcom matrix extraction.
- Added structured source observations from IBM z/OS 3.2 minimum software level tables. These identify requirements, NOT verified compatibility of an installed VRM.
- Prioritized the public BMC AMI Capacity support matrix over blocked dynamic BMC PAC links during default checks. BMC matrix parser retained; product version stays `Not stated` where appropriate.
- Added Precisely MFX release/minimum-OS observations; Ironstream z/OS 3.2 announcement observations; vendor-specific alphanumeric Ironstream maintenance excerpts.
- Removed a stale Rocket link from the curated directory. Rocket/ASG still require official accessible product-release evidence.
- Enhanced Source Monitor with counts of saved structured observations and exports of source-level evidence.
- Explicitly separated `Not installed` from `Not available` for AMXT PTF status; added an installation-status column in the combined PTF worklist.
- Added regression tests for new parsers and status semantics. No credentials, bypasses or non-vendor links are used.

Not implemented: automatic full compatibility/maintenance extraction for all 29 vendors, authenticated PAC/SPCR portal automation, installation checks against real SMP/E inventory, reliable scheduled refresh without an external scheduler. These remain gated by accessible source documents and authorized access.
