# Validation Report — Full Rebuild v4 Records Audited

Build: `2026-08-03-FULL-REBUILD-v4-RECORDS-AUDITED`

## Defects found in v1

1. The dashboard placed an expander inside another expander, which could fail at runtime.
2. Unit Profile Add Service appended text into official Excel Remarks rather than creating
   a true service record; the entry did not appear in Service Records.
3. Automatic OneDrive downloads were not paused while users edited forms/tables.
4. The Streamlit entrypoint regressed to a thin `from app import main` wrapper despite
   this repository's earlier deployment problem with that structure.
5. The separate system-state archive included the official `aed_data.csv` workbook cache,
   creating a stale-master-data risk.

All five were corrected in v2.

## Completed checks

- Python compile: all 72 Python files passed.
- Automated tests: **102 passed**.
- Runtime import audit: **53 of 53 modules imported** using local dependency stubs.
- UI dry-render audit:
  - Operations Dashboard
  - AED Management
  - AED Master Table
  - AED Map
  - PM Planning
  - PM Checklist
  - Service Records
  - Report Issue
  - Issues
- Unit Profile dry-render audit:
  - Overview
  - Edit Details
  - Service History
  - Add Service
  - Issues
- Structured manual service record write/read/history tests passed.
- Master Table remains a separate sidebar route.
- Unit Profiles replace the old homepage scope and appear before secondary AED Management summaries.
- Runtime Python contains no `Asset readiness` label.
- Service Type order verified.
- Map colour and Issue workflow tests passed.
- OneDrive file path encoding, upload and ETag conflict tests passed.
- System-state archive scope and extraction tests passed.
- Official workbook cache is excluded from system-state archive.
- Secret example contains placeholders only.

## Validation boundary

The checks above validate code paths, data services, imports and a dependency-stubbed UI
render. They do not claim a successful login to the user's Microsoft account, a real
OneDrive write, a real OneMap request or a completed Streamlit Cloud browser session.
Those require the user's private deployment and credentials. The build marker and first
functional checks in `FULL_REBUILD_DEPLOY.md` are provided for that final verification.

## v3 workflow verification addendum

Build `2026-08-03-FULL-REBUILD-v3-WORKFLOW-VERIFIED` adds explicit end-to-end tests for Excel round-trip gateways, PM-to-Service-Records linkage, PM-failure-to-Issues linkage, the complete Issue processing lifecycle, and AED Management Unit Profile search. Total automated tests: 96 passed.

## v4 record-integrity addendum

Build `2026-08-03-FULL-REBUILD-v4-RECORDS-AUDITED` adds end-to-end checks for PM reference/notes/model snapshots, battery-history updates, PM Plan completion, durable PM-to-Issue linkage and retry deduplication, manual service snapshots, structured Issue resolution records/evidence, and mixed legacy record dates. Total automated tests: **102 passed**. See `RECORD_AUDIT_v4.md` for corrected defects and remaining architecture boundaries.
