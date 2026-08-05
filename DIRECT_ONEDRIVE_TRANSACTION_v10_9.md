# v10.9 Direct OneDrive Transaction

The Stage 5 direct-table-editing workflow is retained, but the official workbook now brackets every write transaction:

```text
Microsoft sign-in
→ download the latest official OneDrive workbook
→ rebuild the AED cache from that workbook
→ apply the Stage 5 field-level Excel transaction
→ upload to the same OneDrive item with eTag/If-Match protection
→ download that same remote item again
→ rebuild all AED tables from the read-back workbook
```

This path is used by direct table editing, full-details editing, Add AED, PM Checklist master-field updates, PM Planning date updates and manual service updates that are configured to change the IB List. Operational records without approved IB List columns continue to sync through `AED_System_State.zip`.

The post-upload read-back makes the OneDrive workbook the final authority. A concurrent remote change is loaded into the website rather than silently replaced.
