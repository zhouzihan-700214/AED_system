# Direct OneDrive Round-Trip Audit — v10.9

## Reference reviewed

The uploaded `AED_System_Operations_Control_Center_v3_Stage5_Direct_Table_Editing` project uses a local Excel workbook. Its useful transaction pattern was retained:

- stable Serial Number identity;
- direct multi-cell table editing;
- review before save;
- field-level conflict detection;
- only changed cells written;
- one protected Excel transaction;
- workbook validation and backup;
- Excel-to-website refresh after save.

## Cloud transaction used in v10.9

```text
Microsoft sign-in
→ force-download the latest official OneDrive workbook
→ rebuild aed_data.csv from that workbook
→ run the protected Stage 5 Excel transaction
→ upload to the same OneDrive driveItem
→ enforce the opened eTag with If-Match
→ force-download the uploaded remote workbook
→ rebuild aed_data.csv again from the remote read-back
→ render every AED table from that refreshed cache
```

The upload still performs an early metadata/eTag comparison. `If-Match` protects the later race window between metadata lookup and upload.

## Master-data write entry points

The following entry points use `services.aed_repository`, which applies the direct OneDrive transaction:

- AED Management direct table edit;
- AED Management full-details edit;
- Add AED;
- PM Checklist master-field update;
- PM Planning batch Next PM update;
- manual service updates configured to change approved IB List fields.

## Operational records

Records without approved official workbook columns are not forced into the IB List. They are written to their structured CSV stores and synchronised to OneDrive through `AED_System_State.zip`, including full PM responses, Issue workflow records, resolution submissions, map state and photos.

## Conflict and failure behaviour

- If the remote eTag differs before upload, the save is rejected.
- The upload request sends `If-Match` so a remote edit during the final race window returns a conflict rather than being overwritten.
- If upload fails, a pending recovery workbook is preserved and the official remote workbook is restored locally.
- After a successful upload, the same remote file is read back. If another edit appears immediately, the newest remote version becomes the website source and a warning is shown.
- Cloud mode does not preserve cache-only AED rows.

## Automated verification

- Full project test suite: 172 tests passed.
- Python compile-all: passed.
- Dedicated v10.9 order test confirms:
  1. download latest;
  2. rebuild cache;
  3. protected cell transaction;
  4. upload same item;
  5. read back remote;
  6. rebuild all tables.
- Upload test confirms the original eTag is sent as `If-Match`.
- Existing full-system tests verify PM Checklist, direct AED edits, Add AED, external Excel edits, Service Records, Unit Profile, PM Planning, Issues and map state round trips.

## Real-account boundary

Automated tests use a real workbook copy and a simulated Microsoft Graph endpoint. A final production acceptance test must still be performed with the signed-in Microsoft account and the real OneDrive workbook item.
