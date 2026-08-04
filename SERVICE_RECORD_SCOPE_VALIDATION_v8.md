# Service Record Scope v8 Validation

Build: `2026-08-04-FULL-REBUILD-v8-SERVICE-RECORD-SCOPE`

Validated behaviours:

- Postal-code-to-serial matching supports more than one legitimate AED at the same postal code.
- A non-loaner record with the wrong serial for its recorded postal code is classified `Mismatch`.
- Missing or unrecognised non-loaner identifiers remain visible as `Mismatch` for follow-up.
- Loaner records are classified `Loaner` and can be filtered with `Loaner Unit = Yes`.
- Issue Resolution records inherit `Is Loaner` from their Issue.
- Reset Filters also resets the Record Scope and Loaner filter.
- No separate master postal-code or mismatch-reason fields are introduced.
