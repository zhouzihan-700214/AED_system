# Config compatibility fix v9.2

- `services/manual_service_storage.py` no longer requires `MANUAL_SERVICE_RECORDS_FILE` to already exist in `config.py`.
- When paired with an older cached config, it falls back to `<project root>/manual_service_records.csv`.
- The fallback is injected into the loaded `config` module before other services and views import it.
- The manual service file is also appended to legacy `SYSTEM_STATE_PATHS` when available.
- Both `app.py` and `streamlit_app.py` load this compatibility bootstrap immediately after the central config import.
