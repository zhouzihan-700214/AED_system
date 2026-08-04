# Runtime Cloud Validation v10.7

## Result

- Runtime Microsoft settings are read from one source: `services/cloud_runtime.py`.
- Standard `[microsoft]` Secrets format is recognised.
- Legacy case, flat keys, nested sections, hyphens, spaces and underscores are recognised.
- Stale empty values previously imported into `config.py` are replaced.
- Authentication, workbook sync and system-state sync no longer rely on copied import-time settings.
- The old `allow_local_data_mode` setting cannot bypass production sign-in.
- OneDrive workbook remains the authoritative AED master-data source after sign-in.
- Local bundled workbook and stale CSV are not opened when cloud configuration or bootstrap fails.

## Validation performed

- 166 automated tests passed.
- 91 Python files compiled successfully.
- Official workbook opens successfully with openpyxl.
- Final package contains `streamlit_app.py` and no `app.py`.
- Secrets example contains placeholders only.

## Required live verification

A real Microsoft OAuth exchange cannot be completed without the deployed app's Streamlit Secrets and Microsoft account. After deployment, the expected first page is **Connect Microsoft OneDrive**, followed by the Microsoft account selector.
