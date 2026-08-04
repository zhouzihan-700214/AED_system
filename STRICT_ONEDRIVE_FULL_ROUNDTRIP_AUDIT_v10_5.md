# Strict Signed-In OneDrive Full-System Round-Trip Audit v10.5

Build: `2026-08-05-v10.5-STRICT-ONEDRIVE-ROUNDTRIP`

## Purpose

This audit tests the production path after Microsoft sign-in. It verifies that the official OneDrive workbook is authoritative, that user-entered values reach the correct workbook row or operational record, and that every system view reloads the resulting data from its intended source.

## Result

- Python compilation: PASS
- Automated tests: **160 / 160 passed**
- Single entrypoint: PASS (`streamlit_app.py` only)
- Import-contract audit: PASS
- UI dry-render regression tests: PASS
- Official workbook field round-trip: PASS
- PM Checklist and mocked OneDrive upload: PASS
- Operational state archive round-trip: PASS
- eTag conflict protection: PASS
- Stale-local-data rejection: PASS

A real Microsoft account was not available in the offline runtime. Graph requests, workbook bytes, item IDs, eTags and upload/download sequences were tested with mocked Graph responses. A final live-account smoke test remains required after deployment.

## Production source-of-truth rules

### Official AED master data

`/AED System/IB_list_TEST.xlsx` is the only authoritative source in production.

After sign-in, the application:

1. forces a OneDrive workbook download on the first app load of the session;
2. stores the downloaded workbook in the private cache directory;
3. rebuilds `aed_data.csv` from that workbook;
4. removes cache-only AED rows that are not present in the official workbook;
5. stops the application if the workbook download or Excel-to-cache conversion fails.

The app no longer opens bundled Excel or stale CSV data after a failed signed-in refresh.

### Operational records

`/AED System/AED_System_State.zip` stores system-only records:

- PM responses and PM plans;
- manual service records;
- Issues, history, resolution attempts and attachments;
- map workflow state and colours;
- transaction, conflict, audit and lifecycle histories.

The archive is loaded at authenticated startup. Local record changes are checked and uploaded after page actions and by the periodic cloud synchroniser.

If the remote state archive does not yet exist, the app creates a clean archive. Bundled/demo Issue rows, map assignments and photos are backed up locally but are not uploaded into the new production archive.

## Destination matrix

| User action | Official OneDrive Excel | OneDrive state archive | System views updated |
|---|---|---|---|
| AED Management direct edit | Correct serial row and mapped official columns | Audit/transaction history | Master Table, Unit Profile, Map location data |
| Unit Profile Edit Details | Correct serial row and mapped official columns | Audit/transaction history | Unit Profile, Master Table |
| Add AED | New official workbook row | Audit/transaction history | Master Table, Unit Profile, PM selection, Map after coordinates |
| Deactivate AED | Official row retained | Lifecycle history | Active lists hide the unit |
| PM Checklist, non-loaner | PM/consumable/service fields on correct serial row | Complete checklist, plan linkage, generated Issues, map state | Service Records, Unit Profile, PM Planning, Issues, Map |
| PM Checklist, loaner | No official workbook change | Complete checklist record | Service Records and linked operational views |
| Unit Profile Add Service | Optional latest-service and PM fields | Structured service record and plan linkage | Service Records, Unit Profile |
| PM Planning | Optional batch Next PM Date write | Plan rows and colours | PM Planning and Map |
| Report Issue | No unapproved workbook columns | Issue, history and evidence | Issues, Unit Profile, Map |
| Issue workflow/resolution | No unapproved workbook columns | Assignment, progress, attempts, verification and evidence | Issues, Service Records, Unit Profile, Map |
| Map workflow status/colour | No official workbook change | Map state/configuration | AED Map and Operations views |

## PM Checklist fields written to the official workbook

For a non-loaner checklist, the selected serial row is updated with the applicable values:

- Postal Code;
- Lift Lobby;
- Battery Expiry Date;
- Adult Pads Expiry Date and Lot Number;
- Pediatric Pads Expiry Date and Lot Number;
- PM Completed On;
- Next PM Due;
- Job Type;
- Last done by;
- Service Report / e-SR when provided;
- Battery Replacement History when battery replacement is indicated.

Checklist-only values with no approved IB List column remain in the PM response record and state archive. They are displayed in Service Records and Unit Profile rather than adding unapproved columns to the company workbook.

## Signed-in round-trip tests

The integration suite simulated the following remote sequence:

1. download the latest workbook bytes and eTag;
2. rebuild the website cache from the workbook;
3. update the exact serial row through the protected Excel transaction;
4. request current remote metadata;
5. upload the modified workbook to the same OneDrive item ID;
6. save the returned new eTag;
7. modify the remote workbook externally;
8. download it again and confirm the new value appears in the website cache.

The PM cloud test confirms the uploaded workbook contains the entered technician, e-SR and PM date, and that the matching PM response has `Excel Update Status = UPDATED`.

## Defects found and corrected during this audit

1. A successful sign-in could still be followed by stale CSV display if the remote workbook refresh failed. Production now stops instead.
2. `PRESERVE_CACHE_ONLY_UNITS` could retain rows not present in the official OneDrive workbook. Cloud refresh now treats Excel as authoritative and removes those rows.
3. A missing Microsoft configuration previously enabled silent local mode. Production now blocks and shows a configuration error.
4. A new missing state archive could upload bundled/demo operational records. It now creates a clean remote archive and preserves bundled records only as a local recovery ZIP.
5. Operational records were primarily uploaded by the periodic synchroniser. The app now also flushes state after page actions.

## Remaining live verification

Offline tests cannot prove the actual Microsoft tenant, consent, redirect URI, file permissions or real OneDrive path. After deployment:

1. sign in from a new/private browser session;
2. confirm the Data Source panel shows Browser OneDrive mode and the expected remote path;
3. submit a PM Checklist for a designated test AED using a unique e-SR;
4. open Excel Online and verify the same serial row and fields;
5. confirm the same PM Response ID in Service Records and Unit Profile;
6. edit one harmless Excel field online and confirm the app reads it back;
7. revert the test values.

Do not treat the live OneDrive connection as production-signed-off until these seven steps pass.
