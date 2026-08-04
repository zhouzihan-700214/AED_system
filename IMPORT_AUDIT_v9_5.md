# Import Compatibility Audit — v9.5

The complete production codebase was audited after the v9.4 Issues workspace update.

## Checks performed

- Parsed every production Python file.
- Verified that every local module referenced by `import` exists.
- Verified that every function, class and constant referenced by `from ... import ...` exists.
- Checked the top-level local import graph for circular dependencies.
- Compiled all Python files.
- Imported every production module independently with Streamlit UI modules stubbed.
- Ran the complete pytest suite.
- Confirmed all third-party imports are represented in `requirements.txt`.

## Hardening changes

- Removed the accidental duplicate dead `user_is_editing()` blocks from both entrypoints.
- Kept `user_is_editing()` local to both entrypoints; neither imports it from `utils.streamlit_utils`.
- Routed all production uses of `MANUAL_SERVICE_RECORDS_FILE` through
  `services.manual_service_storage`, which supplies a fallback when an older
  `config.py` is temporarily loaded.
- Added `services/__init__.py` so `services` is an explicit package rather than
  relying on namespace-package behaviour.
- Added automated import-contract and production smoke-import tests.
