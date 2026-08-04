# Service Record Scope v8

Build: `2026-08-04-FULL-REBUILD-v8-SERVICE-RECORD-SCOPE`

## Added behaviour

The Service Records page now recalculates every record against the current AED Master Table and assigns one of three scope states:

- `Matched`: the recorded serial number is assigned to the recorded postal code in the current Master Table.
- `Mismatch`: the non-loaner record does not match that current postal-code-to-serial relationship, including missing or unrecognised identifiers.
- `Loaner`: the record is explicitly marked as a loaner and is kept outside the normal master matching decision.

The page provides a clickable scope for `All Records`, `Matched`, `Mismatch`, and `Loaner`, with live counts. It also provides a linked `Loaner Unit` filter with `Yes` and `No` values.

Mismatch rows only receive the concise `Record Match = Mismatch` status. The system does not add separate `Record Postal Code`, `Master Postal Code`, or `Mismatch Reason` columns.

Issue-resolution service records inherit the loaner status from their linked Issue. Unit Profile manual service records are treated as non-loaner because they are created from an AED unit in the Master Table.
