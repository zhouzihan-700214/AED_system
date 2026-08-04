# Startup Import Removal v9.4

The application entrypoints no longer import `user_is_editing` from
`utils.streamlit_utils`. The equivalent helper is defined locally in both
`app.py` and `streamlit_app.py`, so an older cached utility module cannot cause
startup failure.
