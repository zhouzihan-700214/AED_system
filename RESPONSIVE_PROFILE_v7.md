# Responsive AED Management and Unit Profile v7

Build: `2026-08-04-FULL-REBUILD-v8-SERVICE-RECORD-SCOPE`

## UI changes

- Management summary cards use a stable 2 x 2 layout with separate action buttons.
- One full-width search and linked-filter workspace controls Browse Units and Direct Edit.
- Browse-table row selection still opens the selected Unit Profile.
- Unit Profile identity, location, postal code and status values wrap instead of truncating.
- Profile summary values use a responsive 2 x 2 grid instead of four narrow Streamlit metrics.
- Primary actions are full-width; quick actions use a stable 2 x 2 layout.
- Profile navigation uses a horizontal segmented control that can wrap on narrow screens.
- Overview and all unit fields use responsive cards with `height: auto` and word wrapping.
- Global button labels are never cropped; long labels may wrap to another line.

## Preserved workflows

OneDrive Excel write-back and refresh, direct table editing, review/confirmation, conflict protection, Add/Deactivate AED, PM records, Issues, Resolution/Verification, Service Records, Map status and all v5 field round-trip fixes remain unchanged.
