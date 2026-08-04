# AED System Field Round-Trip Audit v5

Build: `2026-08-04-FULL-REBUILD-v5-FIELD-ROUNDTRIP`

## Audit method

Every business input was traced through five stages:

1. Streamlit input or editable table cell
2. Normalisation and validation
3. Durable write target
4. Reload source used after rerun/redeployment
5. Page or record view where the value is shown

Search terms, filters, sorting choices and confirmation checkboxes are UI controls. They intentionally remain in session state and are not business records.

## Result summary

| Workflow | Durable write target | Main display targets | Result |
|---|---|---|---|
| AED Profile Edit | Official `IB_list_TEST.xlsx` | Unit Profile, Master Table, Map/location views | PASS |
| Master Table Direct Edit | Official `IB_list_TEST.xlsx` | Master Table, Unit Profile, Map/location views | PASS |
| Add AED | Official `IB_list_TEST.xlsx` | Master Table, Unit Profile, Map after coordinate/state processing | PASS |
| Deactivate AED | `data/aed_lifecycle_history.csv` | Active lists exclude unit; Lifecycle History shows reason | FIXED / PASS |
| PM Checklist | Excel + `pm_responses.csv` + optional Issues + PM Plan | Service Records, Unit Profile history, Issues, PM Planning, Map status | PASS |
| Unit Profile Add Service | `manual_service_records.csv` + optional Excel + PM Plan | Service Records and Unit Profile history | FIXED / PASS |
| Report Issue | Issue CSVs + photo files | Issues, Unit Profile Issues, Map workflow colour | FIXED / PASS |
| Issue Assignment / Work / Progress | Issue record + `issue_history.csv` | Issues Overview and Activity History | PASS |
| Resolution / Verification | Resolution + attachment + history files | Issues Resolution, Service Records, Unit Profile history | PASS |
| PM Planning | `pm_plan_records.csv` + optional Excel date update | PM Planning and Monthly PM Map | PASS |
| Map status definitions | `map_status_definitions.csv` | Status cards, marker legend, unit controls | PASS |
| Planning marker colour | plan/unit state CSV | AED Map | PASS; intentionally not written to company Excel |

## 1. Official AED master data

The following editable fields are all mapped to official Excel columns, written by the shared conflict-protected repository, reloaded into `aed_data.csv`, and displayed in Unit Profile and Master Table:

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
- Adult Pads Replacement Date, Expiry Date and Lot Number
- Pediatric Pads Replacement Date, Expiry Date and Lot Number
- Battery Replacement History and Battery Expiry Date
- PM Completed Date and Next PM Date
- Service Type / Job Type
- Last Done By
- Service Report / e-SR
- Repaired?
- Remarks

`Location` is derived again from Block / Locations and Street Name during Excel-to-cache synchronisation, so a location edit is reflected after the writeback refresh.

Profile Edit, Full Details and Direct Table Edit now treat `already_applied` and `no_changes` as completed safe outcomes. The edit/review state is cleared and the page reloads current Excel values instead of leaving the user trapped on the review screen.

## 2. Unit Profile Add Service

### Entered values and destinations

| Entered value | Saved in structured record | Optional Excel effect | Displayed in |
|---|---:|---|---|
| Service Date | Yes | PM date/battery history when selected and valid | Profile Service History; Service Records |
| Service Type | Yes | Job Type when update is selected | Profile; Master; Service Records |
| Technician | Yes | Last Done By when update is selected | Profile history; Service Records; Master |
| e-SR | Yes | Updates Excel only when nonblank | Profile history; Service Records; Master |
| Record Status | Yes | Pending records cannot replace latest completed values | Service Records and Profile history |
| Work notes | Yes | None | Service Records and Profile history |
| Update latest fields | Stored as actual result | Job Type/Technician/nonblank e-SR | Additional Saved Information |
| Update PM dates | Stored as actual result | PM Completed and Next PM | Additional Saved Information |
| PM interval months | Yes | Used to calculate Next PM | Service Records and Profile history |
| Battery replacement implied by completed battery service | Yes | Battery Replacement History | Service Records and Profile history |
| Same-month PM Plan link | Yes | Marks plan Completed | Service Records; Profile history; PM Planning |

### Defects corrected

- A blank optional e-SR no longer clears the existing Excel e-SR.
- Technician is required for a new service record.
- A Pending or Follow-up battery record no longer updates Battery Replacement History.
- `PM Interval Months Used` is now stored and displayed.
- Completed manual PM records can complete the matching same-month PM Plan.
- `Master Data Updated`, `PM Dates Updated`, and `Battery History Updated` reflect actual changed fields and a safe Excel result, not merely checkbox state.
- Legacy manual battery records still infer Battery Replaced only when the record status is Completed.

## 3. PM Checklist

All checklist inputs are saved in `pm_responses.csv`:

- Service Date, Technician, Service Type
- Service Report / e-SR and Service Notes
- Customer / Location, Postal Code and Lift Lobby
- Loaner status
- Cabinet Inspection and Cabinet Alarm
- Serial Number and AED snapshots
- Physical Condition and Self Test
- Battery Expiry Date
- Cover condition
- Adult and Pediatric pad dates, lot numbers and validity answers
- Signage and Final Check

After confirmation:

- the selected non-loaner AED is safely updated in Excel;
- the full response appears in Service Records;
- a summary appears in Unit Profile Service History;
- each failed checklist field creates a linked Issue;
- the Issue stores PM Response ID, failed field and failed value;
- the matching PM Plan month is marked Completed;
- the unit workflow colour follows open Issue / verification / completion state.

A safe Excel result of `no_changes` is now accepted. The PM record is still saved, instead of losing the completed checklist merely because the official values already matched.

Service Records now also exposes Submission Status, Excel Update Status, Submitted By and Operation ID in Additional Saved Information.

## 4. Report Issue and Issue processing

### Report Issue values

Source, Reported By, unit snapshot, loaner status, issue types, priority, description and initial photos are saved. They appear in Issues. Source, loaner status and PM linkage values are also visible in the Unit Profile Issue table.

The Issues Overview now includes a dedicated **Source and Record Linkage** block showing:

- Source
- Loaner Unit
- Source Record ID
- Source Field
- Source Value

This corrects the prior condition where those values were durable but hidden.

### Processing values

- Review/assignment actor, assignee, due date, review notes and instructions are visible in Overview/history.
- Started By and starting notes are visible in Overview/history.
- Progress actor and notes are append-only history entries.
- Action Taken, Root Cause, Parts Replaced, Test Performed, Test Result, Resolution Notes and completion photos are visible in Resolution and Service Records.
- Verification decision, verifier, time and notes are visible in Resolution, Service Records and Activity History.
- Rejected attempts remain preserved and do not overwrite earlier resolution attempts.

## 5. PM Planning and Map

Monthly plan rows persist Plan Month, Planned Date, Serial Number, Assigned To, Loaner status, status, completion linkage and coordinate/location snapshots. They reload in Saved Monthly Plan and Monthly PM Map.

Batch Next PM Date changes use the same Excel conflict protection as Master Table and become visible in Profile/Master after cache refresh.

Map status name, marker colour, active flag, display order and workflow role persist in the status definition file. Planning colour overrides save immediately and display on the map. Operational colours remain controlled by PM/Issue workflow. These colour records intentionally do not modify company Excel.

## 6. Deactivation and audit records

The deactivation reason was already written to `data/aed_lifecycle_history.csv`, but no page displayed it. A new **AED Lifecycle History** expander now shows:

- timestamp
- serial number
- inactive status
- reason
- user
- source page
- operation ID

## 7. Data persistence

Official master fields use `/AED System/IB_list_TEST.xlsx`.

Operational records use `/AED System/AED_System_State.zip`, including PM, plans, manual services, Issues, resolution attempts, attachments/photos, map definitions/state, transaction/audit/conflict and lifecycle history.

## Remaining architecture limits

- Real Microsoft authentication and the user's actual OneDrive file cannot be fully exercised in an offline test container. The Graph/Excel code path and mocked end-to-end tests pass, but one deployed online write/read test is still required.
- Excel and the separate State ZIP cannot form one cloud-atomic transaction. Recovery and idempotent IDs reduce risk, but a network interruption between the two uploads can require retry/review.
- Simultaneous edits to the State ZIP are conflict-detected and recoverable, but not automatically merged like database transactions.
- Historical records are append-only. A formal Void/Correction workflow is still needed if the company requires controlled corrections rather than new explanatory records.

## Validation

- Automated tests: 111 passed
- Python source compilation: passed
- Official profile/add fields all have Excel mappings: passed
- PM, Issue, Resolution and Planning input schema coverage: passed
- Manual service full-field record-to-display round trip: passed
- Blank e-SR preservation: passed
- Pending battery protection: passed
- PM `no_changes` record preservation: passed
- Issue source/linkage visibility: passed
- Lifecycle reason visibility: passed
