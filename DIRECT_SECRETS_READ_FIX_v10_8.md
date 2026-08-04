# Direct Streamlit Secrets Read Fix v10.8

## Root cause addressed

The previous runtime loader first converted `st.secrets` and nested sections to
plain dictionaries. Streamlit officially guarantees direct dict-like access,
but the live secrets object can be a lazy proxy. In a runtime where eager
conversion does not materialise nested sections, the app reports `client_id`
and `client_secret` as missing even though they exist.

## New behaviour

- Reads `st.secrets` and `[microsoft]` through direct item access.
- Does not require `dict(st.secrets)` to succeed.
- Supports underscore, hyphen, space and case variations.
- Displays only detected key names when configuration is incomplete; values are
  never shown.
- Keeps strict OneDrive-only startup behaviour.
