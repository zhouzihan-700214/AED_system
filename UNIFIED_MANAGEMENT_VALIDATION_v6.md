# AED Management v6 Validation

Build: `2026-08-04-FULL-REBUILD-v8-SERVICE-RECORD-SCOPE`

## Latest UI requirements implemented

1. AED Management and Master Table are one visible asset-control workspace.
2. The Management KPI, Attention Required and monthly PM progress remain available.
3. The directory has exactly one keyword search and one linked-filter set.
4. Browse Units and Direct Edit use the same filtered AED result set.
5. Clicking a Browse Units row opens the selected unit by Serial Number.
6. Returning from the profile preserves the search and filters.
7. The optimized profile keeps Overview, Edit Details, Service History, Add Service and Issues.
8. Profile shortcuts open PM Checklist, Report Issue, Service Records, AED Map and filtered Table Edit.
9. Direct Edit retains reviewed multi-cell editing, conflict-safe OneDrive Excel writeback, Full Details Editor, Add/Deactivate and all audit histories.
10. Old AED Master Table and AED Master Data routes remain hidden compatibility redirects.

## Data and workflow preservation

The v5 field round-trip implementation remains unchanged for:

- Profile and table edits to the official OneDrive workbook;
- Excel-to-system refresh;
- PM Checklist to Service Records and linked Issues;
- manual service records;
- Issue assignment, progress, resolution and verification;
- PM Planning completion linkage;
- map colour and status records;
- lifecycle and audit histories;
- OneDrive system-state persistence.

## Automated validation

- Python files compiled: 77
- Automated tests collected: 119
- Automated tests passed: 119
- Runtime code occurrences of `Asset readiness`: 0
- Runtime code occurrences of deprecated `use_container_width`: 0
- Secrets example contains placeholders only.

A live Microsoft/OneDrive login and browser interaction cannot be executed in the offline build environment. Deployment still requires a real-account smoke test.
