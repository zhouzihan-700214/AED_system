# Responsive Unit Profile Validation v7

Build: `2026-08-04-FULL-REBUILD-v8-SERVICE-RECORD-SCOPE`

## Verified layout corrections

1. Management summary modules use a stable 2 x 2 structure. Their metric content is no longer embedded inside multiline Streamlit buttons.
2. Each summary card has consistent spacing and a separate full-width action button.
3. AED Directory uses one full-width search/filter workspace above the table. The old narrow right-hand filter column is not used by the active Management page.
4. Browse Units still opens a Profile by clicking the selected table row. Direct Edit uses the same filtered dataset.
5. Profile identity text, Model, Location, Postal Code, dates, status values and references use wrapping and automatic height.
6. Unit Status, Service Type, Next PM and Open Issues use a responsive 2 x 2 grid, preventing values such as dates from being reduced to partial text.
7. Primary actions are full-width. Quick actions use two rows of two buttons to preserve complete labels.
8. Profile navigation uses a horizontal segmented control and may wrap instead of overflowing.
9. All Overview fields use responsive cards. Remarks spans the full content width and preserves line breaks.
10. Global Streamlit button labels use automatic height, normal whitespace and overflow wrapping.
11. Narrow-screen CSS changes field grids and summary rows to one column and left-aligns values.

## Preserved business capabilities

- OneDrive Excel two-way update and eTag conflict protection.
- One search and one linked-filter set.
- Browse-table row click to Profile.
- Direct table editing, review, confirmation, Add AED, Deactivate AED, Full Details Editor and audit histories.
- Unit Profile Edit Details, Add Service, Service History and Issues.
- PM Checklist to Service Records and failed checks to linked Issues.
- Report Issue, assignment, resolution, verification and Issue Resolution service records.
- Field round-trip and system-state persistence fixes from v5/v6.

## Static validation

- Python files compiled: 78
- Automated tests passed: 123
- Runtime `use_container_width` usage: 0
- Active AED Management old side-by-side table/filter layout: removed

The environment does not contain Streamlit itself, so browser rendering cannot be executed here. The Python, CSS, workflow tests and static layout checks pass; final visual verification remains a deployment-browser check.
