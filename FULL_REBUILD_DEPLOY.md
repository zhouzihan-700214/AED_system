# Deploy v10.5 Strict Signed-In OneDrive Round-Trip Build

## Use a clean repository-root replacement

Do not layer this version on top of earlier patches.

1. Download or clone a backup of the current repository.
2. Delete the old application files/folders from the GitHub repository root.
3. Upload the **contents of this ZIP root**. GitHub must directly show:

```text
streamlit_app.py
config.py
requirements.txt
services/
views/
ui/
utils/
.streamlit/
```

There must not be an extra outer folder containing these files.

The repository root must **not** contain `app.py`. `streamlit_app.py` is the only
Streamlit entrypoint and the Streamlit Cloud Main file path must point to it.

4. Commit to the exact branch used by Streamlit, normally `main`.
5. In Streamlit App settings confirm:
   - Repository: the repository just replaced
   - Branch: `main`
   - Main file path: `streamlit_app.py`
6. Reboot the app.
7. Confirm the sidebar footer displays:

```text
AED Operations · 2026-08-05-v10.5-STRICT-ONEDRIVE-ROUNDTRIP
```

If that exact marker is absent, the open webpage is not running this package.

## First functional checks

After Microsoft sign-in, check these in order:

1. Operations Control → `Unit Profiles` appears in CONTROL SCOPE.
2. AED Management → Unit Profiles appears directly below the four KPI cards.
3. Select an AED → open each profile section: Overview, Edit Details, Service History, Add Service, Issues.
4. Add one harmless test service record without selecting Excel updates → confirm it appears in both Unit Profile Service History and Service Records.
5. Master Table → verify filters, direct edit review and Cancel without saving.
6. AED Map → change one planning colour and confirm it saves without a Save button.
7. Submit a harmless PM Checklist with an e-SR and note → confirm the same PM Response ID appears in Service Records.
8. Use one failed test item in a test unit → confirm the created Issue shows the PM Response ID and failed field.
9. Complete one test Issue resolution → confirm the resolution attempt and evidence appear in Service Records.

## Secrets

Keep one `[onemap]` section and one `[microsoft]` section. The optional
`system_state_path` may be omitted because the code has a default.

Never commit a completed `.streamlit/secrets.toml` file.

The Microsoft `redirect_uri` in Streamlit Secrets must exactly match the Web redirect
URI registered in Microsoft Entra, including the final `/`.

## Security action

An older repository version contained real-looking credentials in
`.streamlit/secrets.toml.example`. Rotate the OneMap password and Microsoft Client
Secret, then update Streamlit Secrets. This package contains placeholders only.

## Strict production data-source rule

Production defaults to `allow_local_data_mode = false`. Every new Streamlit session must complete Microsoft sign-in before any page is rendered. The first authenticated startup forces a fresh OneDrive workbook download and loads `AED_System_State.zip`. If either remote source cannot be loaded, the application stops instead of opening the bundled workbook or a stale `aed_data.csv`.

Local/offline mode is available only when explicitly enabled for development:

```toml
[deployment]
allow_local_data_mode = true
```

Do not enable local mode in the deployed production app.

## Required live OneDrive sign-off

The automated suite uses a real workbook copy and mocked Microsoft Graph responses.
After deployment, perform one live account round-trip before production use:

1. Select a designated test AED and note its current IB List values.
2. Submit one PM Checklist with a unique e-SR reference.
3. In Excel Online, confirm the exact serial row received PM Completed On, Next PM Due,
   Job Type, Last done by, e-SR and the entered consumable fields.
4. Confirm the same PM Response ID appears in Service Records and Unit Profile history.
5. Change one harmless field directly in Excel Online, wait for automatic refresh, and
   confirm the system table/profile shows it.
6. Revert the test changes.

Do not declare the personal OneDrive connection production-verified until this live test
is complete.
