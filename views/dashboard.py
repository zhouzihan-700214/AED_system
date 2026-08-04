from __future__ import annotations

from pathlib import Path

import streamlit as st

from services.aed_repository import get_all_units
from services.dashboard_service import DashboardPaths, build_dashboard_snapshot
from ui.dashboard_components import (
    build_filtered_queue,
    render_activity_feed,
    render_control_header,
    render_global_toolbar,
    render_kpi_row,
    render_operational_summaries,
    render_quick_actions,
    render_selected_item_panel,
    render_source_health,
    render_work_queue,
)
from views.aed_management import render_dashboard_unit_profiles


def render_dashboard(
    *,
    aed_data_file: str | Path,
    issue_record_file: str | Path,
    pm_response_file: str | Path,
    pm_plan_file: str | Path,
    aed_history_file: str | Path,
    issue_history_file: str | Path,
) -> None:
    """Boss-facing operations page with a direct Unit Profiles scope."""
    paths = DashboardPaths(
        aed_data=Path(aed_data_file),
        issue_records=Path(issue_record_file),
        pm_responses=Path(pm_response_file),
        pm_plan=Path(pm_plan_file),
        aed_history=Path(aed_history_file),
        issue_history=Path(issue_history_file),
    )

    selected_period = st.session_state.get("dashboard_period")
    try:
        master_data = get_all_units()
        snapshot = build_dashboard_snapshot(
            paths=paths,
            selected_period=selected_period,
            aed_data=master_data,
        )
    except Exception as error:
        st.error(f"The Operations Control Center could not load its data: {error}")
        return

    render_control_header(snapshot)
    filters = render_global_toolbar(snapshot)

    if filters["period"] != snapshot["period"]:
        snapshot = build_dashboard_snapshot(
            paths=paths,
            selected_period=filters["period"],
            aed_data=master_data,
        )

    if filters["view"] == "Unit Profiles":
        render_dashboard_unit_profiles(
            snapshot["aed_data"],
            keyword=filters["keyword"],
            context_key="dashboard",
        )
        with st.expander("Recent operational activity", expanded=False):
            render_activity_feed(snapshot["recent_activity"])
        render_quick_actions()
        return

    filtered_queue = build_filtered_queue(snapshot, filters)
    render_kpi_row(snapshot, filters["view"])

    queue_col, detail_col = st.columns([2.1, 1], gap="medium")
    with queue_col:
        selected_item = render_work_queue(filtered_queue)
    with detail_col:
        render_selected_item_panel(selected_item, snapshot)

    render_operational_summaries(snapshot, filters["period"])

    with st.expander("Recent operational activity", expanded=False):
        render_activity_feed(snapshot["recent_activity"])
    render_source_health(snapshot)
    render_quick_actions()
