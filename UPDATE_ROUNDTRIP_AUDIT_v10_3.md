# Update Roundtrip Audit v10.3

## Scope

The Issue workflow was tested as a real cross-file roundtrip rather than only by source inspection.

## Verified workflow

1. Report an Issue.
2. Review and assign it.
3. Start work.
4. Add a progress update.
5. Submit a resolution with evidence.
6. Approve and close the resolution.
7. Reject a resolution, reopen the Issue, submit a second attempt, and approve it.
8. Keep the correct map state when one AED has more than one Issue.

## Verified destinations

- `issue_records.csv`
- `issue_history.csv`
- `issue_resolution_submissions.csv`
- `issue_attachments.csv` and saved evidence files
- `map_unit_state.csv`
- Issues: All Issues and Today's Issues
- Issue type, status and person filters
- AED Management: Unit Profile Issues
- AED Management: Unit Profile Service History
- Service Records: Issue Resolution rows

## Corrections made

- Multi-select Issue Types are now split into individual filter options. An Issue saved as `Cabinet Issue; Battery Issue` is returned by either filter.
- Resolution Submitted By filtering now includes every resolution attempt, not only the latest submitter.
- Verified / Closed By continues to include all verification attempts.
- Issue timestamps and Today's Issues use the configurable business timezone. Default: `Asia/Singapore`; override with `AED_TIMEZONE`.
- A blank or malformed zero-column PM response CSV no longer prevents Issue Resolution records from loading in Service Records.

## Result

- Python compilation: passed.
- Automated tests: 145 passed.
- Full Issue roundtrip: passed.
- Reopen and second-resolution roundtrip: passed.
- Multiple-Issue map synchronization: passed.
