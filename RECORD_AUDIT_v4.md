# Record Integrity Audit v4

Build: `2026-08-03-FULL-REBUILD-v4-RECORDS-AUDITED`

This audit followed each record from its entry form through storage, cross-page display,
workflow linkage, OneDrive system-state inclusion and retry behaviour.

## Record sources covered

- PM Checklist submissions
- Unit Profile manual service records
- Reported Issues
- Issue assignment, work, resolution and verification history
- Resolution evidence attachments
- PM Planning completion links
- Master/Excel transaction and field audit history
- Map status and operational state records

## Defects corrected after v3

1. PM Checklist now stores `Service Report e-SR`, service notes and the AED model snapshot.
2. PM service types containing battery replacement automatically store
   `Battery Replaced = Yes` and append the service date to Battery Replacement History.
3. A completed PM Checklist links to and completes the matching same-month PM Plan.
4. PM-created Issues store the PM Response ID, failed checklist field and failed value.
   Repeating the same commit reuses the existing Issue instead of creating a duplicate.
5. PM Response rows store the linked Plan ID, failed fields and created Issue IDs.
6. Unit Profile manual records store model, location, postal code and lift-lobby snapshots,
   so older records do not silently change when the AED master location changes later.
7. Issue resolution submissions now appear in Service Records as structured records,
   including attempt number, action, root cause, parts, tests, verification and evidence.
8. Service Records now accepts current and common legacy date formats instead of hiding
   records whose date is not exactly `DD-MM-YYYY`.
9. Record Source and Record Status filters are fully linked and Reset Filters clears them.
10. Service Records selection labels and detail panels now expose source, status,
    reference/e-SR, location snapshot and resolution evidence more clearly.
11. Empty packaged CSV files were migrated to the current schemas without deleting
    existing issue/history/attachment rows.

## Persistence coverage

The OneDrive system-state archive includes PM records, PM plans, manual service records,
Issues, Issue history, resolution submissions, attachments, photos, map state and audit
histories. The official IB List workbook remains separate.

## Remaining architecture boundaries

### Concurrent system-record edits

`AED_System_State.zip` uses eTag conflict detection and creates a recovery ZIP when both
local and remote state changed. It does not automatically merge two users' simultaneous
CSV changes. Atomic local writes prevent partial files, but they do not provide a true
multi-user database transaction across all record files.

### Cross-file transaction boundary

A PM submission updates the official workbook and several system record files. Retries
are idempotent for the PM response, PM-generated Issues and PM Plan link, but Microsoft
Excel and the separate system-state archive cannot be committed as one atomic remote
transaction. A network failure between those operations may require retry/reconciliation.

### Record corrections

Saved service and resolution records are treated as audit records. The current UI does
not provide a formal `Void / Superseded by / Correction reason` workflow. Incorrect
records should not be silently edited or deleted; a production deployment should add a
controlled correction record if this is required by company policy.

### Live cloud boundary

Automated tests use local files and mocked OneDrive gateways. Real Microsoft sign-in,
actual Excel Online propagation, Streamlit Cloud restart behaviour and concurrent-user
conflict recovery must still be tested in the deployed account.
