# Workflow Verification v3

Build: `2026-08-03-FULL-REBUILD-v3-WORKFLOW-VERIFIED`

## 1. Website ↔ OneDrive Excel

### Website to Excel
All official AED changes use `services.aed_repository`.

`Master Table / Unit Profile / PM Checklist`
→ download the latest OneDrive workbook
→ refresh the local cache
→ execute the protected Excel transaction
→ compare the OneDrive eTag
→ upload the same `IB_list_TEST.xlsx`

A newer remote eTag stops the upload instead of overwriting another user's changes.

### Excel to website
The app checks OneDrive approximately every 10 seconds when no write workspace is open.
A changed eTag downloads the newest workbook and rebuilds `aed_data.csv`.
The sidebar also provides **Refresh now**.

## 2. PM Checklist and Issue workflow

A confirmed PM Checklist submission:

1. safely updates the official Excel master fields (unless it is a loaner),
2. appends a committed row to `pm_responses.csv`,
3. appears in **Service Records** and the unit's **Service History**,
4. creates one Issue per failed checklist field,
5. provides direct buttons to open the saved Service Record or created Issues.

A confirmed Report Issue submission:

1. writes to `issue_records.csv`,
2. appears immediately in **Issues** and the unit's Profile,
3. provides a direct **Open this Issue for processing** button,
4. supports Reported → Assigned → In Progress → Pending Verification → Closed,
5. requires resolution details, a functional test and completion evidence before verification.

## 3. AED Management Unit Profile search

`AED Management` now contains a visible **Search AED unit** field above the selector.
Partial, case-insensitive search covers:

- Serial Number
- Model
- Location
- Block / Locations
- Street Name
- Postal Code

Selecting a matching unit opens:

- Overview
- Edit Details
- Service History
- Add Service
- Issues

Profile save feedback is displayed on the AED Management page after rerun.

## Automated verification

- Python compilation: passed
- Automated tests: 96 passed
- Dedicated end-to-end workflow tests cover:
  - website update → OneDrive upload gateway
  - external OneDrive Excel → website refresh gateway
  - PM response → Service Records
  - failed PM field → Issues
  - Report Issue → assignment → work → resolution → verification → closure
  - AED Management search across all required fields

Live Microsoft Graph authentication and the user's actual OneDrive workbook still require one deployment test using the configured Microsoft account.
