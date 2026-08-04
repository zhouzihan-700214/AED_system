# Runtime Microsoft Secrets Refresh v10.6

Build: `2026-08-05-v10.6-SECRETS-RUNTIME-REFRESH`

## Problem

The strict OneDrive build originally evaluated Microsoft settings when `config.py`
was first imported. A Streamlit process that had imported the module before Cloud
Secrets were saved could continue holding the empty values. The parser also only
recognised the exact lowercase `[microsoft]` section and snake_case keys.

## Fix

- Re-read `st.secrets` before any Microsoft/OneDrive service is imported.
- Recompute `MICROSOFT_CONFIG`, `ONEDRIVE_CLOUD_ENABLED`, deployment mode and the
  OneDrive workbook cache path from the current runtime values.
- Continue to recommend the canonical lowercase `[microsoft]` section.
- Accept prior section/key spellings for deployment compatibility.
- Show a safe diagnostic with `CONFIGURED` or `MISSING` for each required key.
- Never display client ID or client secret values.

## Required keys

- `client_id`
- `client_secret`
- `redirect_uri`
- `onedrive_file_path` (defaults to `/AED System/IB_list_TEST.xlsx`)

`authority` and `system_state_path` have defaults and are not the cause of the
configuration-required page.

## Validation

- Full automated test suite passed.
- Standard lowercase section passed.
- Legacy section/key aliases passed.
- Exact missing-key diagnostics passed.
- Python compilation passed.
