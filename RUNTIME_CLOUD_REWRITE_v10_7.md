# Runtime Cloud Rewrite v10.7

## Purpose

The previous implementation refreshed `config.MICROSOFT_CONFIG` at runtime, but several cloud services imported and copied those values earlier. A process that first saw empty Secrets could therefore continue using stale empty values.

## New design

- `services/cloud_runtime.py` is the single runtime source for Microsoft settings.
- Secrets are read directly from the current Streamlit runtime.
- Key matching is case-insensitive and ignores spaces, hyphens and underscores.
- Standard `[microsoft]`, legacy section names, nested mappings and flat keys are supported.
- Microsoft auth, OneDrive workbook and system-state services request runtime settings when used.
- Production always requires OneDrive sign-in. The old `allow_local_data_mode` flag is ignored.
- No AED page is opened until configuration is complete, sign-in succeeds, the official workbook downloads and system state loads.

## Required settings

```toml
[microsoft]
client_id = "APPLICATION_CLIENT_ID"
client_secret = "CLIENT_SECRET_VALUE"
authority = "https://login.microsoftonline.com/consumers"
redirect_uri = "https://YOUR_APP.streamlit.app/"
onedrive_file_path = "/AED System/IB_list_TEST.xlsx"
system_state_path = "/AED System/AED_System_State.zip"
```

`client_secret` must be the secret **Value**, not its Secret ID.

## Diagnostics

The configuration screen displays only:

- detected section/source;
- build ID;
- which required keys are configured or missing.

Credential values are never shown.
