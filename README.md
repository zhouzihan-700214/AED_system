# AED Operations Control System

## Current release: v8 Service Record Scope

Build ID: `2026-08-04-FULL-REBUILD-v8-SERVICE-RECORD-SCOPE`

The Service Records page now provides a clickable scope for **All Records**, **Matched**, **Mismatch** and **Loaner**, with counts calculated against the current Master Table. A linked **Loaner Unit** filter is also available. Mismatch records are identified without adding duplicate Record Postal Code, Master Postal Code or mismatch-reason columns.

The AED Management and Unit Profile workspace now uses stable summary cards, one full-width search/filter area, full-text wrapping, responsive 2 x 2 profile statistics, non-cropping buttons and horizontal wrapping profile navigation. All v6 unified-management and v5 field round-trip workflows are preserved.


## v6 unified AED Management

The latest workspace merges the former AED Management and Master Table user journeys without removing the original capabilities. AED Management now contains one search, one linked-filter set and one AED table. In **Browse Units**, clicking a row opens the complete electronic Unit Profile. In **Direct Edit**, the same filtered result set retains reviewed multi-row editing, full-details editing, Add/Deactivate, OneDrive conflict protection and all audit histories. Old `AED Master Table` and `AED Master Data` routes remain as hidden compatibility redirects into AED Management Direct Edit mode.

The optimized Unit Profile retains Overview, Edit Details, Service History, Add Service and Issues, with shortcuts to PM Checklist, Report Issue, Service Records, AED Map and filtered table editing.

# AED Operations Control Center — Full Rebuild v5 Field Round-Trip Audited

Historical v5 build ID: `2026-08-04-FULL-REBUILD-v5-FIELD-ROUNDTRIP`

This package consolidates the preservation, workflow and record-integrity audits into one complete project. It is a complete project, not a partial patch. The original dark sidebar,
light workspace, page structure and dedicated Master Table remain in place.

## Main pages

- **Operations Control** — boss overview with `Overview / PM / Issues / Unit Profiles`.
- **AED Management** — four management KPIs followed immediately by a searchable Unit Profile workspace.
- **Master Table** — independent sidebar page with partial search, linked filters, Reset, direct table editing, review-before-save, conflict protection, Add/Deactivate and audit histories.
- **AED Map** — 15+ marker colours, editable status definitions and direct planning-colour auto-save.
- **PM Planning**
- **PM Checklist**
- **Report Issue**
- **Issues / Resolution / Verification**
- **Service Records**

## Unit Profile

Select an AED by Serial Number, model, location or postal code. Each profile has:

- **Overview** — every field in the current IB List cache, arranged by section.
- **Edit Details** — formal field editing with Before/After review, confirmation and the same protected Excel transaction used by Master Table.
- **Service History** — PM checklist records, issue resolutions, current master service fields, legacy Remarks and records added from the profile.
- **Add Service** — creates a separate structured service record. It does not append text to the company's Remarks. Completed records may optionally update the latest service fields and PM dates in Excel.
- **Issues** — all issue records linked to the unit.
- Quick actions to PM Checklist, Report Issue and Master Table.

Structured profile service records also appear on the separate **Service Records** page.

## OneDrive design

Two separate remote files are used:

1. `/AED System/IB_list_TEST.xlsx` — official IB List fields.
2. `/AED System/AED_System_State.zip` — system-only colours, issues, PM records,
   manual service records, histories and photos.

The official workbook cache is not included in the system-state archive. This avoids
loading a stale master-data copy from the wrong remote file.

The application checks OneDrive approximately every 10 seconds while the session is
active. Remote workbook/state downloads are paused while a write form or table editor
is open, so unsaved input is not replaced. Safe local system-state uploads may still
run. A manual **Refresh now** action remains available as a recovery tool.

## Deployment reliability

`streamlit_app.py` contains the full startup composition and does not rely on a thin
`from app import main` wrapper. This preserves the deployment pattern that was known
to work for this repository.

## Service Type order

The original `PM` and `Commissioning` positions are preserved. The final three options are:

- `PM+batt`
- `PM+glass`
- `PM +batt +glass`

## Validation

- Python compile check: passed for all runtime/test Python files.
- Automated test suite: **102 passed**.
- Import audit: all 53 runtime modules imported with dependency stubs.
- UI dry-render audit: all 9 visible pages and all 5 Unit Profile sections completed without an exception.
- Runtime source contains no `Asset readiness` label.
- Runtime source contains no deprecated `use_container_width` argument.

The dry-render audit is not a substitute for signing into the user's actual Microsoft
account. See `VALIDATION_REPORT.md`, `RECORD_AUDIT_v4.md` and `FULL_REBUILD_DEPLOY.md`.


## v5 field round-trip audit

See `FIELD_ROUNDTRIP_AUDIT_v5.md` for the field-by-field write, reload and display verification.