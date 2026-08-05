# AED Management System v11 — V7 Direct OneDrive Core

This build uses the same direct Microsoft OAuth and OneDrive Graph architecture as the uploaded v7 reference, while retaining all later system features. The official master workbook is `/AED System/IB_list_TEST.xlsx`; operational records are stored in `/AED System/AED_System_State.zip`.

# AED Operations Control System

## Current release: v10.6 Runtime Secrets Refresh

Build ID: `2026-08-05-v10.6-SECRETS-RUNTIME-REFRESH`

This build keeps the strict signed-in OneDrive data path and refreshes Microsoft settings directly from current Streamlit runtime Secrets before service imports. It also provides safe missing-key diagnostics. See `RUNTIME_SECRETS_FIX_v10_6.md`.

## Historical v8 Service Record Scope

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

`streamlit_app.py` is the only executable application entrypoint. The repository
does not contain `app.py`, and no runtime file imports it. Configuration compatibility,
session bootstrap, OneDrive synchronisation, navigation and page dispatch are composed
directly in `streamlit_app.py`. Business logic remains separated in `services/`,
`views/`, `ui/` and `utils/`.

The entrypoint imports runtime modules rather than newly added function symbols and
validates the required runtime contract before the first page is rendered. This makes
mixed deployments easier to diagnose and removes the previous dual-entrypoint risk.

## Service Type order

The original `PM` and `Commissioning` positions are preserved. The final three options are:

- `PM+batt`
- `PM+glass`
- `PM +batt +glass`

## Validation

- Python compile check: passed for all runtime/test Python files.
- Automated test suite: **160 passed**.
- Import audit: all production modules imported with dependency stubs.
- UI dry-render audit: all 9 visible pages and all 5 Unit Profile sections completed without an exception.
- Runtime source contains no `Asset readiness` label.
- Runtime source contains no deprecated `use_container_width` argument.

The dry-render audit is not a substitute for signing into the user's actual Microsoft
account. See `VALIDATION_REPORT.md`, `RECORD_AUDIT_v4.md` and `FULL_REBUILD_DEPLOY.md`.


## v5 field round-trip audit

See `FIELD_ROUNDTRIP_AUDIT_v5.md` for the field-by-field write, reload and display verification.

## v10.2 Today’s Issues view

The Issues workspace now provides an **All Issues / Today’s Issues** switch.
Today’s Issues contains records whose `Reported At` date matches the application
host’s current local date. The complete search, type, lifecycle status, responsibility
and custom date filters remain available inside the Today view. Reset Filters clears
only the filters in the current view and does not force the user back to All Issues.
