# Startup import compatibility v9.3

## Problem

Some Streamlit Cloud deployments loaded a newer entrypoint together with an
older cached `utils/streamlit_utils.py`. That older helper did not export
`user_is_editing`, so the application stopped during module import.

## Fix

Both supported entrypoints now attempt the normal helper import and contain an
equivalent local fallback for stale deployments:

- `app.py`
- `streamlit_app.py`

The fallback preserves the automatic-refresh safety behaviour for PM Planning,
PM Checklist, Report Issue, Issues, AED Map, AED Master Table and profile edit
workspaces.

## Validation

- Python compile check passed.
- All repository tests passed.
- A regression test confirms both entrypoints retain the guarded import and
  fallback implementation.
