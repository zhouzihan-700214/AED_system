# Requirements Matrix — v4 Records Audited

## Layout and navigation

- Original visual style and grouped sidebar retained.
- Visible pages: Operations Control, PM Planning, PM Checklist, Report Issue, Issues,
  AED Management, Master Table, AED Map and Service Records.
- Every visible sidebar route has a registered renderer.
- AED Management remains boss-focused.
- Master Table remains an independent sidebar page.
- `Asset readiness` is absent from runtime code and replaced by `Unit Profiles`.

## Master Table

- Partial-text search across Serial, model, location, postal and other business fields.
- Linked filters and Reset that clears filter selections.
- Direct cell editing.
- Before/After review and explicit confirmation.
- Same-field conflict detection, operation lock, backup, transaction and audit history.
- Full-details editor.
- Add AED and Deactivate AED.

## Unit Profile

- Direct searchable selector on Operations Control and AED Management.
- Overview covers all current IB List/cache columns.
- Formal field editing uses the protected Excel repository transaction.
- Before/After review and confirmation.
- Structured Add Service record with review and confirmation.
- Add Service does not rewrite Remarks.
- Completed service may optionally update latest service fields and PM dates.
- Pending/follow-up service cannot replace completed master fields.
- Manual service records appear in both Unit Profile history and Service Records.
- Combined PM, resolution, current IB List, legacy Remarks and manual service history.
- Linked Issue history.
- Quick actions for PM Checklist, Report Issue and Master Table.

## Service Type

- Existing PM and Commissioning positions unchanged.
- `PM+batt`, `PM+glass`, `PM +batt +glass` appended at the end.
- PM Checklist maps its selected Service Type back to the official Job Type field.

## Colours and map

- At least 15 marker colours.
- Status names, definitions, workflow roles and colours remain editable.
- Planning colour changes directly and auto-saves without Save/Confirm.
- Planning colour remains outside the official IB List.
- Open Issue controls red; pending verification controls yellow; a unit returns to
  green only after no unresolved Issue remains.

## Confirmed workflows

- PM Checklist: review/confirmation before formal submit.
- PM Checklist records retain e-SR, notes, model/location snapshots and the linked PM Plan.
- Failed PM items create separate Issue records after confirmation.
- PM-created Issues retain the PM Response ID, failed field and failed value.
- PM Checklist, Unit Profile service and Issue resolution attempts all appear in Service Records.
- Resolution records retain attempt, action, root cause, parts, tests, verification and evidence links.
- Report Issue: confirmation before creation.
- Submit Resolution: confirmation.
- Verify/Close: confirmation and remaining-Issue check.
- Formal master/profile field changes: review before Excel save.

## OneDrive and refresh safety

- Browser Microsoft sign-in and personal OneDrive Graph file operations.
- Official workbook full-file download/upload with ETag conflict detection.
- Separate system-state ZIP for internal records and photos.
- Official workbook cache excluded from the system-state archive.
- Approximate 10-second sync.
- Remote downloads paused in active write workspaces and profile editors.
- Existing OneMap support and local-workbook fallback retained.
- Self-contained Streamlit Cloud entrypoint retained.
