from __future__ import annotations

from typing import Any

import streamlit as st


WRITE_WORKSPACE_PAGES = {
    "PM Planning",
    "PM Checklist",
    "Report Issue",
    "Issues",
    "AED Map",
}


def rerun_app() -> None:
    """Rerun the current Streamlit application."""
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def _profile_editor_open(session_state: Any) -> bool:
    for key, value in session_state.items():
        key_text = str(key)
        if key_text.startswith(("profile_edit_pending::", "profile_service_pending::")):
            return True
        if key_text.startswith("profile_section_") and value in {"Edit Details", "Add Service"}:
            return True
    return False


def user_is_editing() -> bool:
    """Return True when an automatic data download could erase active input.

    System-state uploads may still run while this is true, but remote downloads
    and official-workbook refreshes are deferred until the user leaves the
    write workspace.
    """
    page = str(st.session_state.get("page", ""))
    if page in WRITE_WORKSPACE_PAGES:
        return True
    if page == "AED Master Table":
        return str(st.session_state.get("aed_editor_mode", "browse")) != "browse"
    if page in {"AED Management", "Operations Dashboard"} and _profile_editor_open(st.session_state):
        return True
    return False
