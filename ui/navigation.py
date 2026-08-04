from __future__ import annotations

from pathlib import Path

import streamlit as st

from services.issue_service import get_open_issue_count
from utils.streamlit_utils import rerun_app


PAGE_NAMES = {
    "Operations Dashboard",
    "AED Management",
    "AED Master Table",
    "AED Master Data",  # Backward-compatible hidden route.
    "AED Map",
    "PM Planning",
    "PM Checklist",
    "Service Records",
    "Report Issue",
    "Issues",
}


def query_value(name: str) -> str:
    try:
        value = st.query_params.get(name, "")
    except Exception:
        value = ""
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value).strip()


def consume_map_navigation() -> None:
    requested_page = query_value("page")
    if requested_page not in {"PM Checklist", "Report Issue"}:
        return

    target = {
        "Serial Number": query_value("serial"),
        "Postal Code": query_value("postal_code"),
    }
    if requested_page == "PM Checklist":
        st.session_state["map_pm_target"] = target
    else:
        st.session_state["map_report_target"] = target
    st.session_state["page"] = requested_page
    try:
        st.query_params.clear()
    except Exception:
        pass


def _render_page_button(page_name: str, label: str) -> None:
    if st.button(
        label,
        width="stretch",
        type="primary" if st.session_state["page"] == page_name else "secondary",
        key=f"nav_{page_name}",
    ):
        st.session_state["page"] = page_name
        rerun_app()


def render_navigation(issue_record_file: str | Path, *, build_id: str = "") -> None:
    if st.session_state.get("page") not in PAGE_NAMES:
        st.session_state["page"] = "Operations Dashboard"

    open_issue_count = get_open_issue_count(issue_record_file)
    issue_label = f"●  Issues ({open_issue_count})" if open_issue_count else "○  Issues"

    groups = [
        ("OVERVIEW", [("Operations Dashboard", "◉  Operations Control")]),
        (
            "WORK MANAGEMENT",
            [
                ("PM Planning", "◫  PM Planning"),
                ("PM Checklist", "▤  PM Checklist"),
                ("Report Issue", "⚠  Report Issue"),
                ("Issues", issue_label),
            ],
        ),
        (
            "ASSET CONTROL",
            [
                ("AED Management", "▣  AED Management"),
                ("AED Map", "⌖  AED Map"),
            ],
        ),
        ("RECORDS", [("Service Records", "≡  Service Records")]),
    ]

    with st.sidebar:
        st.markdown(
            """
            <div class="aed-brand">
                <div class="aed-brand-icon"><span>⚡</span></div>
                <div class="aed-brand-name">AED Operations</div>
            </div>
            <div class="aed-brand-subtitle">CONTROL · SERVICE · TRACE</div>
            """,
            unsafe_allow_html=True,
        )
        for section, pages in groups:
            st.markdown(f'<div class="aed-nav-section">{section}</div>', unsafe_allow_html=True)
            for page_name, label in pages:
                _render_page_button(page_name, label)

        st.markdown(
            f"""
            <div class="aed-sidebar-summary">
                <strong>Work requiring attention</strong>
                <span>{open_issue_count} open issue(s). Open Operations Control for PM, issues and unit profiles.</span>
            </div>
            <div class="aed-version">AED Operations · {build_id or 'Full rebuild'}</div>
            """,
            unsafe_allow_html=True,
        )
