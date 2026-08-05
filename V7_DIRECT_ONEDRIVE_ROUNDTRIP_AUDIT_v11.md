# v11 V7 Direct OneDrive Core — Validation Report

## Purpose

The current feature set is preserved, but the Microsoft/OneDrive core is based on the uploaded v7 build that already used direct browser OAuth and Microsoft Graph file operations.

## Authoritative files

- AED master data: `/AED System/IB_list_TEST.xlsx`
- Operational records: `/AED System/AED_System_State.zip`

## Save transaction

1. Require Microsoft sign-in.
2. Download the newest workbook and its eTag.
3. Rebuild the local AED cache from that downloaded workbook.
4. Locate the target row by `Serial Number`.
5. Apply only validated changed fields.
6. Save the workbook transaction locally.
7. Upload bytes to the same OneDrive driveItem ID.
8. Send `If-Match` with the downloaded eTag.
9. Download the remote workbook again.
10. Rebuild Master Table, Unit Profile, PM Planning and other AED views from the remote read-back.

## Features using the same transaction

- AED Master Table direct edit
- Batch edit
- Unit Profile / Edit Full Details
- Add AED
- PM Checklist
- PM Planning date update
- Add Service fields that are mapped to the IB List

## Separate state archive

Complete PM responses, PM plans, Issues, resolutions, map state, service records, audit history and uploaded photos are synchronised to `AED_System_State.zip` because the official IB List does not contain matching columns for those records.

## Architecture changes

- Restored the v7 direct `[microsoft]` Secrets reader.
- Restored the v7 Microsoft OAuth service.
- Restored the v7 direct OneDrive workbook service.
- Removed `services/cloud_runtime.py` and all runtime proxy dependencies.
- Preserved v10.9 remote read-back and field-level Excel transaction behaviour.
- Added `If-Match` protection to the v7 upload implementation.

## Automated validation

- 170 tests collected and passed.
- All Python modules compiled.
- Tests cover standard `[microsoft]` Secrets, OAuth URL creation, Graph download/upload, eTag conflicts, PM Checklist Excel mapping, direct table editing, Add AED, PM Planning, external Excel changes, system-state archive, Issues and Unit Profile round trips.

## Real-account boundary

Automated tests emulate Microsoft Graph requests and real `.xlsx` bytes. A final deployment check still requires signing into the actual Microsoft account and updating one test AED row in the real OneDrive workbook.
