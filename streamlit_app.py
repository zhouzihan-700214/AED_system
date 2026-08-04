"""Single Streamlit entrypoint for the AED Operations Control Center.

This project intentionally has one executable entry file only:
``streamlit_app.py``.  Startup configuration, compatibility defaults, session
bootstrap, cloud synchronisation, navigation and page dispatch are composed
here.  Business logic remains in the existing ``services`` and ``views``
packages.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from collections.abc import Mapping
import os
import uuid

import streamlit as st

st.set_page_config(
    page_title="AED Operations Control Center",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Import the configuration module itself instead of importing individual names.
# This avoids startup-time ``cannot import name ... from config`` failures and
# lets the single entrypoint provide safe defaults before other modules load.
import config as config


def _apply_config_compatibility() -> None:
    """Complete older configuration modules before importing application code.

    A clean deployment uses the bundled ``config.py`` and does not need these
    fallbacks.  They are deliberately centralised here so a partially cached
    Streamlit process cannot fail one missing constant at a time.
    """

    project_root = Path(
        getattr(config, "PROJECT_ROOT", getattr(config, "BASE_DIR", Path(__file__).resolve().parent))
    )
    data_dir = Path(getattr(config, "DATA_DIR", project_root / "data"))
    temp_dir = Path(getattr(config, "TEMP_DIR", project_root / "temp"))
    external_data_dir = Path(getattr(config, "EXTERNAL_DATA_DIR", project_root / "external_data"))
    backups_dir = project_root / "backups"

    path_defaults: dict[str, Path] = {
        "PROJECT_ROOT": project_root,
        "BASE_DIR": project_root,
        "DATA_DIR": data_dir,
        "TEMP_DIR": temp_dir,
        "EXTERNAL_DATA_DIR": external_data_dir,
        "AED_CACHE_FILE": project_root / "aed_data.csv",
        "AED_DATA_FILE": project_root / "aed_data.csv",
        "AED_HISTORY_FILE": project_root / "aed_management_history.csv",
        "AED_LIFECYCLE_FILE": data_dir / "aed_lifecycle_history.csv",
        "AUDIT_HISTORY_FILE": data_dir / "audit_history.csv",
        "TRANSACTION_HISTORY_FILE": data_dir / "transaction_history.csv",
        "CONFLICT_HISTORY_FILE": data_dir / "conflict_history.csv",
        "ACTIVE_TRANSACTION_FILE": data_dir / "active_transaction.json",
        "SYNC_STATE_FILE": data_dir / "excel_sync_state.json",
        "EXCEL_OPERATION_LOCK_FILE": data_dir / "excel_operation.lock",
        "EXCEL_WRITE_HISTORY_FILE": data_dir / "excel_write_history.csv",
        "EXCEL_BACKUP_DIR": backups_dir / "excel",
        "CACHE_BACKUP_DIR": backups_dir / "aed_cache",
        "PM_RESPONSES_FILE": project_root / "pm_responses.csv",
        "PM_PLAN_FILE": project_root / "pm_plan_records.csv",
        "MANUAL_SERVICE_RECORDS_FILE": project_root / "manual_service_records.csv",
        "ISSUE_RECORD_FILE": project_root / "issue_records.csv",
        "ISSUE_HISTORY_FILE": project_root / "issue_history.csv",
        "ISSUE_ATTACHMENTS_FILE": project_root / "issue_attachments.csv",
        "ISSUE_RESOLUTION_FILE": project_root / "issue_resolution_submissions.csv",
        "ISSUE_PHOTO_DIR": project_root / "issue_photos",
        "MAP_STATUS_FILE": project_root / "map_status_definitions.csv",
        "MAP_UNIT_STATE_FILE": project_root / "map_unit_state.csv",
        "MAP_COLOR_SETTINGS_FILE": project_root / "map_color_settings.csv",
        "ONEDRIVE_CACHE_DIR": data_dir / "onedrive_workbook_cache",
        "ONEDRIVE_SYNC_STATE_FILE": data_dir / "onedrive_sync_state.json",
        "ONEDRIVE_PENDING_DIR": backups_dir / "onedrive_pending",
        "SYSTEM_STATE_SYNC_FILE": data_dir / "system_state_sync.json",
        "SYSTEM_STATE_PENDING_DIR": backups_dir / "system_state_pending",
    }
    for name, value in path_defaults.items():
        if not hasattr(config, name):
            setattr(config, name, value)

    if not hasattr(config, "MICROSOFT_CONFIG"):
        config.MICROSOFT_CONFIG = {
            "client_id": "",
            "client_secret": "",
            "authority": "https://login.microsoftonline.com/consumers",
            "redirect_uri": "",
            "onedrive_file_path": "/AED System/IB_list_TEST.xlsx",
            "system_state_path": "/AED System/AED_System_State.zip",
        }
    config.MICROSOFT_CONFIG.setdefault("onedrive_file_path", "/AED System/IB_list_TEST.xlsx")
    config.MICROSOFT_CONFIG.setdefault("system_state_path", "/AED System/AED_System_State.zip")

    scalar_defaults: dict[str, Any] = {
        "BUILD_ID": "2026-08-05-v10.8-DIRECT-SECRETS-READ",
        "AUDIT_USERS": ("Zihan", "Supervisor", "Technician 1", "Technician 2"),
        "ONEDRIVE_CLOUD_ENABLED": False,
        "ALLOW_LOCAL_DATA_MODE": False,
        "REQUIRE_ONEDRIVE_SIGN_IN": True,
        "EXCEL_FILE": external_data_dir / "IB_list_TEST.xlsx",
        "EXCEL_SHEET": "Sheet1",
        "EXCEL_HEADER_ROW": 1,
        "EXCEL_DATA_START_ROW": 3,
        "SERIAL_COLUMN": "Serial Number",
        "LOCK_WARNING_MINUTES": 5,
        "LOCK_STALE_MINUTES": 15,
        "MAX_CACHE_BACKUPS": 20,
        "MAX_EXCEL_BACKUPS": 20,
        "PRESERVE_CACHE_ONLY_UNITS": True,
        "STAGING_SHEET_NAME": "__STAGING_UPDATE__",
    }
    for name, value in scalar_defaults.items():
        if not hasattr(config, name):
            setattr(config, name, value)

    if not hasattr(config, "EXCEL_WRITE_LOCK_FILE"):
        config.EXCEL_WRITE_LOCK_FILE = config.EXCEL_OPERATION_LOCK_FILE
    if not hasattr(config, "SYNC_LOCK_FILE"):
        config.SYNC_LOCK_FILE = config.EXCEL_OPERATION_LOCK_FILE

    state_paths = tuple(getattr(config, "SYSTEM_STATE_PATHS", ()))
    required_state_paths = (
        config.AED_HISTORY_FILE,
        config.PM_RESPONSES_FILE,
        config.PM_PLAN_FILE,
        config.MANUAL_SERVICE_RECORDS_FILE,
        config.ISSUE_RECORD_FILE,
        config.ISSUE_HISTORY_FILE,
        config.ISSUE_ATTACHMENTS_FILE,
        config.ISSUE_RESOLUTION_FILE,
        config.MAP_STATUS_FILE,
        config.MAP_UNIT_STATE_FILE,
        config.MAP_COLOR_SETTINGS_FILE,
        config.AUDIT_HISTORY_FILE,
        config.TRANSACTION_HISTORY_FILE,
        config.CONFLICT_HISTORY_FILE,
        config.EXCEL_WRITE_HISTORY_FILE,
        config.AED_LIFECYCLE_FILE,
        config.ISSUE_PHOTO_DIR,
    )
    config.SYSTEM_STATE_PATHS = tuple(dict.fromkeys((*state_paths, *required_state_paths)))

    if not hasattr(config, "ensure_project_directories"):
        def ensure_project_directories() -> None:
            for directory in (
                config.EXTERNAL_DATA_DIR,
                config.DATA_DIR,
                config.TEMP_DIR,
                config.CACHE_BACKUP_DIR,
                config.EXCEL_BACKUP_DIR,
                config.ISSUE_PHOTO_DIR,
                config.ONEDRIVE_CACHE_DIR,
                config.ONEDRIVE_PENDING_DIR,
                config.SYSTEM_STATE_PENDING_DIR,
            ):
                Path(directory).mkdir(parents=True, exist_ok=True)

        config.ensure_project_directories = ensure_project_directories



# Microsoft settings are loaded from one runtime-only source.  No cloud
# service is imported until these values have been applied to the compatibility
# configuration module.
_apply_config_compatibility()

import services.cloud_runtime as cloud_runtime

CLOUD_SETTINGS = cloud_runtime.apply_to_config(config)


def _refresh_runtime_cloud_configuration() -> None:
    """Compatibility wrapper around the v10.7 runtime settings loader."""

    global CLOUD_SETTINGS
    secret_root = getattr(st, "secrets", {})
    CLOUD_SETTINGS = cloud_runtime.load_cloud_settings(secret_root)
    cloud_runtime.apply_to_config(config, CLOUD_SETTINGS)

# Import modules, not individual functions.  The entrypoint therefore has no
# fragile ``from module import newly_added_symbol`` dependencies.  A mixed or
# incomplete repository is converted into one clear deployment message rather
# than a chain of raw ImportError tracebacks.
try:
    import services.aed_repository as aed_repository
    import services.excel_lock_service as excel_lock_service
    import services.issue_service as issue_service
    import services.manual_service_storage as manual_service_storage
    import services.microsoft_auth_service as microsoft_auth_service
    import services.pm_service as pm_service
    import services.recovery_service as recovery_service
    import services.system_state_service as system_state_service
    import ui.navigation as navigation
    import ui.styles as styles
    import update_missing_coordinates as coordinate_service
    import views.registry as page_registry
except (ImportError, ModuleNotFoundError) as import_error:
    st.error("The deployed repository is incomplete or contains mixed versions.")
    st.write(
        "Delete the old repository contents, upload the complete ZIP root, "
        "and keep `streamlit_app.py` as the only Main file path."
    )
    st.code(f"{type(import_error).__name__}: {import_error}", language="text")
    st.stop()


AUTO_REFRESH_INTERVAL = "10s"
_WRITE_WORKSPACE_PAGES = {
    "PM Planning",
    "PM Checklist",
    "Report Issue",
    "Issues",
    "AED Map",
}


def _runtime_contract_errors() -> list[str]:
    """Return missing runtime functions as readable deployment errors."""

    required = {
        aed_repository: ("ensure_cache_current", "get_sync_status", "refresh_from_excel"),
        excel_lock_service: ("inspect_lock", "remove_confirmed_stale_lock"),
        issue_service: ("ensure_issue_storage",),
        manual_service_storage: ("ensure_manual_service_storage",),
        microsoft_auth_service: (
            "build_sign_in_url",
            "get_authentication_status",
            "handle_auth_callback",
            "sign_out",
        ),
        pm_service: ("ensure_aed_pm_fields", "ensure_pm_storage"),
        recovery_service: ("recover_incomplete_transaction",),
        system_state_service: ("bootstrap_system_state", "sync_system_state"),
        navigation: ("consume_map_navigation", "render_navigation"),
        styles: ("apply_global_styles",),
        coordinate_service: ("file_signature", "update_missing_coordinates"),
        page_registry: ("render_current_page",),
    }
    errors: list[str] = []
    for module, names in required.items():
        for name in names:
            if not callable(getattr(module, name, None)):
                errors.append(f"{module.__name__}.{name}")
    return errors


def _stop_for_incompatible_deployment() -> None:
    missing = _runtime_contract_errors()
    if not missing:
        return
    st.error("The deployed repository contains mixed application versions.")
    st.write("Replace the repository root with the complete ZIP contents, then reboot the app.")
    st.code("\n".join(missing), language="text")
    st.stop()


def _profile_editor_is_open() -> bool:
    for key, value in st.session_state.items():
        key_text = str(key)
        if key_text.startswith(("profile_edit_pending::", "profile_service_pending::")):
            return True
        if key_text.startswith("profile_section_") and value in {"Edit Details", "Add Service"}:
            return True
    return False


def user_is_editing() -> bool:
    """Prevent cloud downloads while a user has an active write workspace."""

    page = str(st.session_state.get("page", ""))
    if page in _WRITE_WORKSPACE_PAGES:
        return True
    if page == "AED Master Table":
        return str(st.session_state.get("aed_editor_mode", "browse")) != "browse"
    if page in {"AED Management", "Operations Dashboard"}:
        return _profile_editor_is_open()
    return False


def initialise_user_session() -> None:
    st.session_state.setdefault("session_id", str(uuid.uuid4()))
    users = tuple(getattr(config, "AUDIT_USERS", ()))
    st.session_state.setdefault("audit_user", users[0] if users else "")
    st.session_state.setdefault("page", "Operations Dashboard")


def render_microsoft_sign_in_gate() -> None:
    """Require a complete runtime configuration and a Microsoft session.

    Production never falls back to bundled Excel/CSV data.  The settings are
    read again here so a newly rebooted Streamlit process always uses the
    current App Settings > Secrets values.
    """

    global CLOUD_SETTINGS
    CLOUD_SETTINGS = cloud_runtime.load_cloud_settings(getattr(st, "secrets", {}))
    cloud_runtime.apply_to_config(config, CLOUD_SETTINGS)

    if not CLOUD_SETTINGS.configured:
        st.title("Microsoft OneDrive configuration required")
        st.error(
            "The application could not read all Microsoft settings from the "
            "current Streamlit runtime. It has stopped before loading any local "
            "or cached AED data and will not fall back to a bundled workbook."
        )
        st.write(f"Configuration source detected: `{CLOUD_SETTINGS.source}`")
        st.caption(f"Application build: {config.BUILD_ID}")
        labels = ("client_id", "client_secret", "redirect_uri")
        st.code(
            "\n".join(
                f"{'MISSING' if key in CLOUD_SETTINGS.missing_keys else 'CONFIGURED'}  {key}"
                for key in labels
            ),
            language="text",
        )
        st.caption(
            "Key matching is case-insensitive and accepts underscores, spaces or "
            "hyphens. Credential values are never displayed."
        )
        detected_keys = cloud_runtime.detected_secret_keys(getattr(st, "secrets", {}))
        if detected_keys:
            st.caption("Non-sensitive secret key names detected by this runtime:")
            st.code("\n".join(detected_keys), language="text")
        st.code(
            "[microsoft]\n"
            "client_id = \"...\"\n"
            "client_secret = \"...\"\n"
            "authority = \"https://login.microsoftonline.com/consumers\"\n"
            "redirect_uri = \"https://<your-app>.streamlit.app/\"\n"
            "onedrive_file_path = \"/AED System/IB_list_TEST.xlsx\"\n"
            "system_state_path = \"/AED System/AED_System_State.zip\"",
            language="toml",
        )
        notice = (
            "After saving Secrets, use Manage app → Reboot app. Removing or "
            "changing allow_local_data_mode is not required in this build."
        )
        renderer = getattr(st, "info", getattr(st, "caption", None))
        if renderer is not None:
            renderer(notice)
        st.stop()

    microsoft_auth_service.handle_auth_callback()
    status = microsoft_auth_service.get_authentication_status()
    if status.authenticated:
        return

    st.title("Connect Microsoft OneDrive")
    st.write(
        "Sign in with the Microsoft account that owns "
        f"`{CLOUD_SETTINGS.onedrive_file_path}`."
    )
    if status.message:
        st.error(status.message)
    try:
        sign_in_url = microsoft_auth_service.build_sign_in_url()
    except Exception as error:
        st.error(f"Could not prepare Microsoft sign-in: {error}")
        st.stop()
    st.link_button(
        "Sign in with Microsoft",
        sign_in_url,
        type="primary",
        width="content",
    )
    st.caption(
        "After sign-in, the official OneDrive workbook is downloaded before any "
        "AED page is opened."
    )
    st.stop()


def initialise_operational_storage(*, allow_remote_refresh: bool = True) -> None:
    """Initialise cloud state, recovery and every local application store.

    In the production OneDrive mode, remote data is authoritative. A failed
    workbook or state-archive bootstrap stops the page instead of silently
    opening a bundled workbook or an old CSV cache.
    """

    config.ensure_project_directories()

    if config.ONEDRIVE_CLOUD_ENABLED and not st.session_state.get("_system_state_bootstrapped", False):
        try:
            result = system_state_service.bootstrap_system_state()
        except Exception as error:
            raise RuntimeError(
                "Could not load the operational records from OneDrive: " + str(error)
            ) from error
        if not result.success:
            raise RuntimeError(result.message or "OneDrive system-state bootstrap failed.")
        st.session_state["_system_state_bootstrapped"] = True
        if result.changed:
            st.session_state["system_state_notice"] = result.message

    if not st.session_state.get("_recovery_checked", False):
        recovery = recovery_service.recover_incomplete_transaction()
        st.session_state["_recovery_checked"] = True
        if recovery.get("status") in {"recovered", "cleaned"}:
            st.session_state["recovery_notice"] = recovery.get("message", "")
        elif recovery.get("status") == "failed":
            st.session_state["recovery_error"] = recovery.get("message", "")

    first_cloud_load = (
        config.ONEDRIVE_CLOUD_ENABLED
        and not st.session_state.get("_onedrive_master_bootstrapped", False)
    )
    if first_cloud_load or allow_remote_refresh or not Path(config.AED_DATA_FILE).exists():
        sync_result = aed_repository.ensure_cache_current(force=first_cloud_load)
        if config.ONEDRIVE_CLOUD_ENABLED and sync_result.status not in {"synced", "up_to_date"}:
            raise RuntimeError(
                "Could not load the official OneDrive Excel workbook: "
                + (sync_result.message or "unknown synchronisation error")
            )
        if first_cloud_load:
            st.session_state["_onedrive_master_bootstrapped"] = True
            st.session_state["aed_sync_notice"] = (
                sync_result.message or "Official OneDrive Excel loaded."
            )
    pm_service.ensure_pm_storage()
    manual_service_storage.ensure_manual_service_storage()
    issue_service.ensure_issue_storage(config.ISSUE_RECORD_FILE)
    pm_service.ensure_aed_pm_fields(config.AED_DATA_FILE)


def sync_coordinates_after_csv_change() -> None:
    state_key = "_checked_aed_coordinate_file_signature"
    current_signature = coordinate_service.file_signature(config.AED_DATA_FILE)
    if current_signature is None or st.session_state.get(state_key) == current_signature:
        return

    try:
        summary = coordinate_service.update_missing_coordinates(config.AED_DATA_FILE, create_backup=False)
        st.session_state[state_key] = coordinate_service.file_signature(config.AED_DATA_FILE)
        if summary["updated"] > 0:
            st.toast(f"Added or refreshed coordinates for {summary['updated']} AED unit(s).")
        if summary["failed"] > 0:
            st.warning(
                f"{summary['failed']} AED unit(s) still have no valid coordinates. "
                "Check their Postal Code and OneMap credentials."
            )
    except Exception as error:
        st.session_state[state_key] = current_signature
        st.warning(f"Automatic coordinate update could not finish: {error}")


def render_identity_control() -> None:
    with st.sidebar.expander("Operator Identity", expanded=False):
        st.selectbox(
            "Audit user",
            options=list(config.AUDIT_USERS),
            key="audit_user",
            help="Used in audit records; this is separate from Microsoft sign-in.",
        )
        st.caption(f"Session: {st.session_state['session_id'][:8]}")


def render_microsoft_connection_control() -> None:
    if not config.ONEDRIVE_CLOUD_ENABLED:
        return
    status = microsoft_auth_service.get_authentication_status()
    with st.sidebar.expander("Microsoft OneDrive", expanded=True):
        if status.authenticated:
            st.success("Connected")
            st.caption(status.account_name)
            st.caption(config.MICROSOFT_CONFIG.get("onedrive_file_path", ""))
            st.caption(config.MICROSOFT_CONFIG.get("system_state_path", ""))
            if st.button("Sign out", width="stretch", key="microsoft_sign_out"):
                microsoft_auth_service.sign_out()
                st.rerun()
        else:
            st.warning("Not connected")
            st.link_button(
                "Sign in with Microsoft",
                microsoft_auth_service.build_sign_in_url(),
                width="stretch",
            )


def render_data_sync_control() -> None:
    status = aed_repository.get_sync_status()
    status_label = {
        "synced": "Synced",
        "up_to_date": "Up to date",
        "csv_fallback": "CSV fallback",
        "failed": "Needs attention",
        "not_checked": "Not checked",
    }.get(str(status.get("status", "")), str(status.get("status", "Unknown")))

    with st.sidebar.expander("Data Source", expanded=False):
        st.caption(f"Excel: {Path(config.EXCEL_FILE).name}")
        st.caption(f"Worksheet: {config.EXCEL_SHEET}")
        if status.get("onedrive_enabled", False):
            st.success("Browser OneDrive mode")
            st.caption(
                "Official workbook: "
                f"{status.get('onedrive_remote_path') or config.MICROSOFT_CONFIG.get('onedrive_file_path', '')}"
            )
            st.caption(
                "System records: "
                f"{config.MICROSOFT_CONFIG.get('system_state_path', '/AED System/AED_System_State.zip')}"
            )
        else:
            st.info("Local workbook mode")
            st.caption(str(config.EXCEL_FILE))
        st.caption(f"Status: {status_label}")

        lock_status = excel_lock_service.inspect_lock()
        if lock_status.get("exists"):
            payload = lock_status.get("payload", {})
            st.warning(
                "Excel operation in progress: "
                f"{payload.get('operation_type', 'Unknown')} by {payload.get('user', 'Unknown')}."
            )
            if lock_status.get("confirmed_stale") and st.button(
                "Remove confirmed stale lock", width="stretch"
            ):
                if excel_lock_service.remove_confirmed_stale_lock():
                    st.success("Confirmed stale lock removed.")
                    st.rerun()

        if st.button("Refresh now", width="stretch", key="refresh_external_aed_data"):
            result = aed_repository.refresh_from_excel()
            if result.status == "failed":
                st.error(result.message)
            else:
                state_result = None
                if config.ONEDRIVE_CLOUD_ENABLED:
                    try:
                        state_result = system_state_service.sync_system_state()
                    except Exception as error:
                        st.warning(f"System-record refresh needs attention: {error}")
                st.session_state["aed_sync_notice"] = result.message
                if state_result and state_result.message:
                    st.session_state["system_state_notice"] = state_result.message
                st.rerun()


@st.fragment(run_every=AUTO_REFRESH_INTERVAL)
def auto_refresh_cloud_data() -> None:
    """Pull cloud changes automatically unless a write workspace is active."""

    if (
        not config.ONEDRIVE_CLOUD_ENABLED
        or not microsoft_auth_service.get_authentication_status().authenticated
    ):
        return

    should_rerun = False
    editing = user_is_editing()

    if editing:
        st.session_state.pop("aed_auto_sync_error", None)
    else:
        excel_result = aed_repository.ensure_cache_current(force=False)
        if excel_result.status == "failed":
            st.session_state["aed_auto_sync_error"] = excel_result.message
        else:
            st.session_state.pop("aed_auto_sync_error", None)
            if excel_result.changed:
                st.session_state["aed_sync_notice"] = (
                    "A newer OneDrive Excel version was detected and loaded automatically."
                )
                should_rerun = True

    try:
        state_result = system_state_service.sync_system_state(allow_download=not editing)
        if state_result.status == "conflict":
            st.session_state["system_state_error"] = state_result.message
        elif state_result.status == "deferred":
            st.session_state.pop("system_state_error", None)
        else:
            st.session_state.pop("system_state_error", None)
            if state_result.downloaded:
                st.session_state["system_state_notice"] = state_result.message
                should_rerun = True
    except Exception as error:
        st.session_state["system_state_error"] = str(error)

    if should_rerun:
        st.rerun()


def flush_system_state_after_page() -> None:
    """Upload any records written by the rendered page in the same app cycle."""

    if (
        not config.ONEDRIVE_CLOUD_ENABLED
        or not microsoft_auth_service.get_authentication_status().authenticated
    ):
        return
    try:
        result = system_state_service.sync_system_state(allow_download=False)
    except Exception as error:
        st.session_state["system_state_error"] = (
            "The page data was saved locally, but the OneDrive system-record upload failed: "
            + str(error)
        )
        return
    if result.status == "conflict":
        st.session_state["system_state_error"] = result.message
    elif result.uploaded:
        st.session_state["system_state_notice"] = result.message
        st.session_state.pop("system_state_error", None)


def render_notices() -> None:
    transient = {
        "recovery_notice": st.success,
        "recovery_error": st.error,
        "aed_sync_notice": st.success,
        "system_state_notice": st.success,
    }
    persistent = {
        "system_state_error": st.error,
        "aed_auto_sync_error": st.warning,
    }

    for key, renderer in transient.items():
        value = st.session_state.pop(key, "")
        if value:
            renderer(value)
    for key, renderer in persistent.items():
        value = st.session_state.get(key, "")
        if value:
            renderer(value)
    for warning in st.session_state.pop("aed_sync_warnings", []):
        st.warning(warning)


def main() -> None:
    """Run the complete application from the single supported entrypoint."""

    styles.apply_global_styles()
    _stop_for_incompatible_deployment()
    initialise_user_session()
    render_microsoft_sign_in_gate()

    editing_at_start = user_is_editing()
    try:
        initialise_operational_storage(allow_remote_refresh=not editing_at_start)
    except Exception as error:
        st.error(f"Operational storage initialisation failed: {error}")
        st.stop()

    sync_coordinates_after_csv_change()
    navigation.consume_map_navigation()
    navigation.render_navigation(config.ISSUE_RECORD_FILE, build_id=config.BUILD_ID)
    render_microsoft_connection_control()
    render_identity_control()
    render_data_sync_control()
    auto_refresh_cloud_data()
    render_notices()
    page_registry.render_current_page(st.session_state["page"])
    flush_system_state_after_page()


if __name__ == "__main__":
    main()
