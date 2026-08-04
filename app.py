"""Application composition for the full AED Operations rebuild.

The entrypoint is deliberately small and deterministic. All pages use the same
configuration, OneDrive connection, navigation and refresh lifecycle.
"""
from __future__ import annotations

import uuid

import streamlit as st

from config import (
    AED_DATA_FILE,
    AUDIT_USERS,
    BUILD_ID,
    EXCEL_FILE,
    EXCEL_SHEET,
    ISSUE_RECORD_FILE,
    MICROSOFT_CONFIG,
    ONEDRIVE_CLOUD_ENABLED,
    ensure_project_directories,
)
from services.manual_service_storage import ensure_manual_service_storage
from services.aed_repository import ensure_cache_current, get_sync_status, refresh_from_excel
from services.excel_lock_service import inspect_lock, remove_confirmed_stale_lock
from services.issue_service import ensure_issue_storage
from services.microsoft_auth_service import (
    build_sign_in_url,
    get_authentication_status,
    handle_auth_callback,
    sign_out,
)
from services.pm_service import ensure_aed_pm_fields, ensure_pm_storage
from services.recovery_service import recover_incomplete_transaction
from services.system_state_service import bootstrap_system_state, sync_system_state
from ui.navigation import consume_map_navigation, render_navigation
from ui.styles import apply_global_styles
# Kept local on purpose. The entrypoints must not depend on a newly added
# helper symbol in ``utils.streamlit_utils`` because Streamlit Cloud can keep
# an older utility module during a partial deployment.
_WRITE_WORKSPACE_PAGES = {
    "PM Planning",
    "PM Checklist",
    "Report Issue",
    "Issues",
    "AED Map",
}


def _profile_editor_is_open() -> bool:
    for key, value in st.session_state.items():
        key_text = str(key)
        if key_text.startswith(("profile_edit_pending::", "profile_service_pending::")):
            return True
        if key_text.startswith("profile_section_") and value in {"Edit Details", "Add Service"}:
            return True
    return False


def user_is_editing() -> bool:
    page = str(st.session_state.get("page", ""))
    if page in _WRITE_WORKSPACE_PAGES:
        return True
    if page == "AED Master Table":
        return str(st.session_state.get("aed_editor_mode", "browse")) != "browse"
    if page in {"AED Management", "Operations Dashboard"}:
        return _profile_editor_is_open()
    return False

from update_missing_coordinates import file_signature, update_missing_coordinates
from views.registry import render_current_page

AUTO_REFRESH_INTERVAL = "10s"


def initialise_user_session() -> None:
    st.session_state.setdefault("session_id", str(uuid.uuid4()))
    st.session_state.setdefault("audit_user", AUDIT_USERS[0] if AUDIT_USERS else "")
    st.session_state.setdefault("page", "Operations Dashboard")


def render_microsoft_sign_in_gate() -> None:
    if not ONEDRIVE_CLOUD_ENABLED:
        return

    handle_auth_callback()
    status = get_authentication_status()
    if status.authenticated:
        return

    st.title("Connect Microsoft OneDrive")
    st.write(
        "Sign in with the Microsoft account that owns "
        f"`{MICROSOFT_CONFIG.get('onedrive_file_path', '/AED System/IB_list_TEST.xlsx')}`."
    )
    if status.message:
        st.error(status.message)
    st.link_button(
        "Sign in with Microsoft",
        build_sign_in_url(),
        type="primary",
        width="content",
    )
    st.caption(
        "The system uses delegated Files.ReadWrite permission to read and update "
        "the selected workbook and a separate system-state archive."
    )
    st.stop()


def initialise_operational_storage(*, allow_remote_refresh: bool = True) -> None:
    """Load cloud state first, then validate all local working files.

    A cached workbook is never replaced while a form or table editor is open.
    The first startup still creates the cache when no local copy exists.
    """
    ensure_project_directories()

    if ONEDRIVE_CLOUD_ENABLED and not st.session_state.get("_system_state_bootstrapped", False):
        try:
            result = bootstrap_system_state()
            st.session_state["_system_state_bootstrapped"] = True
            if result.changed:
                st.session_state["system_state_notice"] = result.message
        except Exception as error:
            st.session_state["system_state_error"] = str(error)

    if not st.session_state.get("_recovery_checked", False):
        recovery = recover_incomplete_transaction()
        st.session_state["_recovery_checked"] = True
        if recovery.get("status") in {"recovered", "cleaned"}:
            st.session_state["recovery_notice"] = recovery.get("message", "")
        elif recovery.get("status") == "failed":
            st.session_state["recovery_error"] = recovery.get("message", "")

    if allow_remote_refresh or not AED_DATA_FILE.exists():
        ensure_cache_current(force=False)
    ensure_pm_storage()
    ensure_manual_service_storage()
    ensure_issue_storage(ISSUE_RECORD_FILE)
    ensure_aed_pm_fields(AED_DATA_FILE)


def sync_coordinates_after_csv_change() -> None:
    state_key = "_checked_aed_coordinate_file_signature"
    current_signature = file_signature(AED_DATA_FILE)
    if current_signature is None or st.session_state.get(state_key) == current_signature:
        return

    try:
        summary = update_missing_coordinates(AED_DATA_FILE, create_backup=False)
        st.session_state[state_key] = file_signature(AED_DATA_FILE)
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
            options=list(AUDIT_USERS),
            key="audit_user",
            help="Used in audit records; this is separate from Microsoft sign-in.",
        )
        st.caption(f"Session: {st.session_state['session_id'][:8]}")


def render_microsoft_connection_control() -> None:
    if not ONEDRIVE_CLOUD_ENABLED:
        return
    status = get_authentication_status()
    with st.sidebar.expander("Microsoft OneDrive", expanded=True):
        if status.authenticated:
            st.success("Connected")
            st.caption(status.account_name)
            st.caption(MICROSOFT_CONFIG.get("onedrive_file_path", ""))
            st.caption(MICROSOFT_CONFIG.get("system_state_path", ""))
            if st.button("Sign out", width="stretch", key="microsoft_sign_out"):
                sign_out()
                st.rerun()
        else:
            st.warning("Not connected")
            st.link_button("Sign in with Microsoft", build_sign_in_url(), width="stretch")


def render_data_sync_control() -> None:
    status = get_sync_status()
    status_label = {
        "synced": "Synced",
        "up_to_date": "Up to date",
        "csv_fallback": "CSV fallback",
        "failed": "Needs attention",
        "not_checked": "Not checked",
    }.get(str(status.get("status", "")), str(status.get("status", "Unknown")))

    with st.sidebar.expander("Data Source", expanded=False):
        st.caption(f"Excel: {EXCEL_FILE.name}")
        st.caption(f"Worksheet: {EXCEL_SHEET}")
        if status.get("onedrive_enabled", False):
            st.success("Browser OneDrive mode")
            st.caption(
                f"Official workbook: {status.get('onedrive_remote_path') or MICROSOFT_CONFIG.get('onedrive_file_path', '')}"
            )
            st.caption(
                f"System records: {MICROSOFT_CONFIG.get('system_state_path', '/AED System/AED_System_State.zip')}"
            )
        else:
            st.info("Local workbook mode")
            st.caption(str(EXCEL_FILE))
        st.caption(f"Status: {status_label}")

        lock_status = inspect_lock()
        if lock_status.get("exists"):
            payload = lock_status.get("payload", {})
            st.warning(
                "Excel operation in progress: "
                f"{payload.get('operation_type', 'Unknown')} by {payload.get('user', 'Unknown')}."
            )
            if lock_status.get("confirmed_stale") and st.button(
                "Remove confirmed stale lock", width="stretch"
            ):
                if remove_confirmed_stale_lock():
                    st.success("Confirmed stale lock removed.")
                    st.rerun()

        if st.button("Refresh now", width="stretch", key="refresh_external_aed_data"):
            result = refresh_from_excel()
            if result.status == "failed":
                st.error(result.message)
            else:
                state_result = None
                if ONEDRIVE_CLOUD_ENABLED:
                    try:
                        state_result = sync_system_state()
                    except Exception as error:
                        st.warning(f"System-record refresh needs attention: {error}")
                st.session_state["aed_sync_notice"] = result.message
                if state_result and state_result.message:
                    st.session_state["system_state_notice"] = state_result.message
                st.rerun()


@st.fragment(run_every=AUTO_REFRESH_INTERVAL)
def auto_refresh_cloud_data() -> None:
    """Automatically pull official Excel changes and sync system-only records."""
    if not ONEDRIVE_CLOUD_ENABLED or not get_authentication_status().authenticated:
        return

    should_rerun = False
    editing = user_is_editing()

    if editing:
        st.session_state.pop("aed_auto_sync_error", None)
    else:
        excel_result = ensure_cache_current(force=False)
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
        state_result = sync_system_state(allow_download=not editing)
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


def render_notices() -> None:
    for key, renderer in [
        ("recovery_notice", st.success),
        ("recovery_error", st.error),
        ("aed_sync_notice", st.success),
        ("system_state_notice", st.success),
        ("system_state_error", st.error),
        ("aed_auto_sync_error", st.warning),
    ]:
        value = st.session_state.pop(key, "") if key not in {"system_state_error", "aed_auto_sync_error"} else st.session_state.get(key, "")
        if value:
            renderer(value)

    for warning in st.session_state.pop("aed_sync_warnings", []):
        st.warning(warning)


def main() -> None:
    apply_global_styles()
    initialise_user_session()
    render_microsoft_sign_in_gate()

    editing_at_start = user_is_editing()
    try:
        initialise_operational_storage(allow_remote_refresh=not editing_at_start)
    except Exception as error:
        st.error(f"Operational storage initialisation failed: {error}")
        st.stop()

    sync_coordinates_after_csv_change()
    consume_map_navigation()
    render_navigation(ISSUE_RECORD_FILE, build_id=BUILD_ID)
    render_microsoft_connection_control()
    render_identity_control()
    render_data_sync_control()
    auto_refresh_cloud_data()
    render_notices()
    render_current_page(st.session_state["page"])


if __name__ == "__main__":
    main()
