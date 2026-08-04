# Single Entry Rewrite v10

## Runtime structure

- Removed `app.py` from the repository.
- `streamlit_app.py` is the only executable entrypoint.
- Startup configuration, compatibility defaults, session initialisation, Microsoft
  sign-in, storage bootstrap, coordinate refresh, navigation, auto-refresh and page
  dispatch are composed in that file.
- Business services and page renderers remain modular; they are imported as modules
  instead of importing individual newly-added symbols.

## Changed startup logic

1. Configure the Streamlit page.
2. Import `config` as a module and fill missing compatibility values once.
3. Import service/UI/view modules only after configuration is complete.
4. Validate all runtime functions before initialising data.
5. Initialise user session and authentication.
6. Initialise cloud/local storage with write-workspace protection.
7. Render navigation, sync controls, notices and the selected page.

## Validation

- `app.py` does not exist in the package.
- All Python files compile.
- 137 automated tests pass.
- Local import symbol and cycle audits pass.
- The supported Streamlit Cloud entry path is `streamlit_app.py`.
