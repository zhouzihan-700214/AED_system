# Import compatibility fix v9.1

## Fixed

- `app.py` and `streamlit_app.py` no longer import
  `ensure_manual_service_storage` from `services.unit_profile_service`.
- Startup now imports the bootstrap function from the independent
  `services.manual_service_storage` module.
- This prevents startup failure when Streamlit Cloud has a stale or mismatched
  copy of `unit_profile_service.py`.

## Deployment

Replace the complete project contents, including the new file:

- `services/manual_service_storage.py`

Do not update only `streamlit_app.py`, because that would preserve the mixed
project version that caused the original error.
