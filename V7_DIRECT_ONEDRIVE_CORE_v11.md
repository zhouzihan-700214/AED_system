# v11 — v7 Direct OneDrive Core

This build keeps the latest AED, PM, Issues, Service Records and Unit Profile features,
but restores the proven v7 Microsoft/OneDrive architecture.

Data flow:

1. `config.py` reads `[microsoft]` from Streamlit Secrets.
2. The v7 OAuth service signs the browser user into Microsoft.
3. The latest `/AED System/IB_list_TEST.xlsx` is downloaded.
4. Existing field-level Excel transactions update the target Serial Number row.
5. The same OneDrive driveItem is replaced, with eTag and If-Match protection.
6. The remote workbook is downloaded again and every AED table is rebuilt from it.
7. PM/Issue/system-only records are synchronized through `/AED System/AED_System_State.zip`.

No `cloud_runtime.py` proxy is used.
