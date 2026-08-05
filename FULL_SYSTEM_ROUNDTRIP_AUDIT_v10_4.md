# Full-System Round-Trip Audit v10.4

Build: `2026-08-04-v10.4-FULL-SYSTEM-ROUNDTRIP`

## Scope

This audit verifies the complete data path, not only the Issues module:

1. user-entered value;
2. validation and normalisation;
3. durable file or workbook write;
4. reload into the website cache;
5. display in the expected system page/table;
6. mocked OneDrive download/upload and eTag behaviour.

A real Microsoft account was not available in the offline test environment. Therefore,
actual Microsoft login and a live write to the user's personal OneDrive remain deployment
smoke tests. The production Graph request code, full `.xlsx` bytes, eTag checks and
round-trip behaviour were exercised with a mocked remote OneDrive endpoint.

## Result

- Python compilation: PASS
- Automated suite: **153 / 153 passed**
- Dedicated full-system integration tests: **8 / 8 passed**
- Overall measured test coverage: 70% of all source lines; core service and transaction
  paths are substantially more covered than Streamlit rendering code.
- Single entrypoint: PASS (`streamlit_app.py`; no `app.py`)

## One defect found and fixed

A real Excel date in `Battery Replacement History` could be read by openpyxl as a
`datetime` while the website cache stored the same date as `DD-MM-YYYY`. During a
`PM+batt` submission this could create a false same-field conflict, even though the
values represented the same date.

The write service now normalises a single battery-history Excel date before comparison,
while preserving free-text multi-date history strings. A full PM+battery integration test
now verifies this path against a copied real workbook.

## Official Excel master data

All official editable fields were written to a copied `IB_list_TEST.xlsx`, read back into
`aed_data.csv`, and checked in the reloaded row:

- Installation Date
- Model / Related Object
- Installed Phase / Month
- PO Number
- Zone
- Block / Locations
- Street Name
- Postal Code
- Level
- Lift Lobby
- Adult Pads replacement / expiry / lot
- Pediatric Pads replacement / expiry / lot
- Battery Replacement History
- Battery Expiry Date
- PM Completed Date
- Next PM Date
- Job Type
- Last Done By
- Service Report / e-SR
- Repaired?
- Remarks

`Location` was also re-derived from Block / Locations and Street Name after refresh.

Validated directions:

- System edit -> correct Excel serial row and official column -> cache -> Master Table / Unit Profile
- External Excel edit -> forced OneDrive download -> cache -> system readers
- Multi-row table changes remain all-or-nothing when a conflict is found
- Add AED appends a new official workbook row
- Deactivate AED keeps the official row and writes lifecycle state separately

## PM Checklist end-to-end result

A complete non-loaner `PM+batt` submission was committed against a real workbook copy.
The test checked the selected serial row, not merely whether any workbook cell changed.

### Values written to the official IB List

- Postal Code
- Lift Lobby
- Battery Expiry Date
- Adult Pads Expiry Date
- Adult Pads Lot Number
- Pediatric Pads Expiry Date
- Pediatric Pads Lot Number
- PM Completed On
- Next PM Due, using the AED's PM interval
- Job Type
- Last done by
- Service Report / e-SR, when nonblank
- Battery Replacement History, when batteries were replaced

### Full PM record stored outside the official IB List

The following checklist-specific values have no corresponding official IB List column.
They are intentionally stored in `pm_responses.csv`, displayed in Service Records and
Unit Profile history, and included in the separate OneDrive system-state archive:

- Customer / Location
- Loaner Unit
- Cabinet Inspection
- Cabinet Alarm
- AED Physical Condition
- Self Test Result
- AED Cover
- Adult/Pediatric pads within-expiry answers
- AED Signage
- Final Check
- Service Notes
- PM Response ID, operation ID and submission metadata
- failed checklist fields and linked Issue IDs
- linked PM Plan ID

This separation prevents the official company workbook from gaining unapproved columns.

### PM-linked updates verified

- `pm_responses.csv`: one idempotent committed row
- official Excel: correct row and columns
- `aed_data.csv`: refreshed master values
- Service Records: PM row visible with the same PM Response ID
- Unit Profile Service History: PM summary visible
- PM Planning: exact same-month plan marked Completed
- Issues: one Issue per failed checklist item, linked to PM Response ID and source field
- Map state: Issue / Pending Verification / Completed according to unresolved Issues
- OneDrive official workbook: mocked download -> update -> upload of the same file
- OneDrive State ZIP: PM response, plan and Issue records included

A loaner PM was also tested: the PM record is saved, but the official IB List is not
changed and `Excel Update Status = NOT_REQUIRED_LOANER`.

## Unit Profile Add Service

Verified inputs and destinations:

- date, type, technician, e-SR/reference, status and work notes -> structured manual record
- completed service with requested master update -> official Excel Job Type / Last Done By /
  nonblank e-SR
- requested PM-date update -> PM Completed Date and calculated Next PM Date
- completed battery service -> Battery Replacement History
- same-month plan -> Completed and linked to Service Record ID
- Service Records -> row visible
- Unit Profile Service History -> row visible

Pending/follow-up records cannot overwrite completed master service fields or append a
battery replacement date. A blank optional e-SR does not clear the workbook value.

## Issues and resolutions

Verified complete lifecycle:

- Reported -> Assigned -> In Progress -> Pending Verification -> Closed
- rejection -> Reopened -> second resolution attempt -> Closed
- actor, assignee, due date, progress, action, root cause, parts, test and notes
- initial and resolution evidence attachments
- all attempts retained
- Service Records resolution row
- Unit Profile Issue and Service History views
- Today’s Issues and people/type/status filters
- map workflow state for one or multiple Issues on the same AED

## PM Planning and map

Verified:

- plan month, planned date, serial, assignee, status and snapshots persist
- batch Next PM Date update uses the protected Excel transaction
- PM completion links only the exact serial and service month
- planning colour and workflow state save to system files and are intentionally not written
  into the official IB List

## OneDrive behaviour tested

### Official workbook

- remote metadata/eTag read
- latest full workbook download
- protected local Excel transaction
- upload to the same OneDrive item ID
- newer remote eTag stops overwrite
- uploaded workbook bytes contain the expected changed cells
- subsequent external workbook change downloads and updates the website cache

### Operational system records

`AED_System_State.zip` round-tripped:

- PM responses
- PM plans
- manual service records
- Issues and history
- resolution submissions
- attachments and photos
- map state and definitions
- transaction, conflict, audit and lifecycle history

The official workbook cache is deliberately excluded from this ZIP.

## Architecture boundary

The official Excel workbook and `AED_System_State.zip` are two separate OneDrive files.
Microsoft Graph cannot commit both files as one atomic transaction. The system uses
idempotent record IDs, local atomic writes, eTag conflict detection and recovery copies,
but a network interruption between the workbook upload and State ZIP upload can still
require a retry or reconciliation.

For production sign-off, complete one live account test after deployment:

1. submit a PM Checklist on a designated test AED;
2. open the OneDrive workbook and confirm the same serial row fields;
3. confirm the PM Response ID in Service Records and Unit Profile;
4. edit one harmless workbook field directly in Excel Online;
5. wait for automatic refresh and confirm the system displays the external value;
6. revert the test data.
