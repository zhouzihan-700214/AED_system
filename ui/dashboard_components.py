from __future__ import annotations

from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from services.dashboard_service import (
    DASHBOARD_VIEWS,
    apply_dashboard_filters,
    build_period_options,
    calculate_dashboard_kpis,
    find_selected_source,
    get_assignee_options,
)
from utils.streamlit_utils import rerun_app
from utils.text_utils import clean_text


DISPLAY_QUEUE_COLUMNS = [
    "Category",
    "Priority",
    "Item",
    "Location",
    "Due / Age",
    "Owner",
    "Status",
]


def _navigate(page_name: str) -> None:
    st.session_state["page"] = page_name
    rerun_app()


def _safe_key(value: Any) -> str:
    return "".join(
        character if character.isalnum() else "_"
        for character in clean_text(value)
    )[:80]


def _format_period(period: str) -> str:
    try:
        return pd.Period(period, freq="M").strftime("%B %Y")
    except Exception:
        return period


def render_control_header(snapshot: dict[str, Any]) -> None:
    as_of = snapshot["as_of"]
    warning_count = int(snapshot["data_health"].get("warning_count", 0))
    warning_text = (
        f"{warning_count} data warning(s)"
        if warning_count
        else "All configured data sources readable"
    )

    header_col, report_col, pm_col = st.columns([5.2, 1.25, 1.1], gap="small")
    with header_col:
        st.markdown(
            f"""
            <section class="ops-control-header">
                <div class="ops-control-eyebrow">AED OPERATIONS · CONTROL CENTRE</div>
                <h1>AED Operations Control Center</h1>
                <p>Monitor preventive maintenance, issue resolution and AED unit status.</p>
                <div class="ops-control-meta">
                    <span>Data refreshed {escape(as_of.strftime('%d %b %Y, %H:%M'))}</span>
                    <span class="ops-control-meta-divider">•</span>
                    <span>{escape(warning_text)}</span>
                </div>
            </section>
            """,
            unsafe_allow_html=True,
        )

    with report_col:
        st.markdown('<div class="ops-header-action-spacer"></div>', unsafe_allow_html=True)
        if st.button(
            "Report issue",
            key="dashboard_header_report_issue",
            width="stretch",
            type="secondary",
        ):
            _navigate("Report Issue")

    with pm_col:
        st.markdown('<div class="ops-header-action-spacer"></div>', unsafe_allow_html=True)
        if st.button(
            "Start PM",
            key="dashboard_header_start_pm",
            width="stretch",
            type="primary",
        ):
            _navigate("PM Checklist")


def render_global_toolbar(snapshot: dict[str, Any]) -> dict[str, str]:
    current_period = snapshot["period"]
    period_options = build_period_options(today=snapshot["today"])
    if current_period not in period_options:
        period_options.append(current_period)
        period_options.sort()

    st.session_state.setdefault("dashboard_view", "PM")
    st.session_state.setdefault("dashboard_period", current_period)
    st.session_state.setdefault("dashboard_assignee", "All")
    st.session_state.setdefault("dashboard_search", "")

    if st.session_state["dashboard_view"] not in DASHBOARD_VIEWS:
        st.session_state["dashboard_view"] = "PM"
    if st.session_state["dashboard_period"] not in period_options:
        st.session_state["dashboard_period"] = current_period

    assignee_options = get_assignee_options(snapshot["queue"])
    if st.session_state["dashboard_assignee"] not in assignee_options:
        st.session_state["dashboard_assignee"] = "All"

    st.markdown('<div class="ops-toolbar-label">CONTROL SCOPE</div>', unsafe_allow_html=True)
    view_col, period_col, owner_col, search_col = st.columns(
        [2.45, 1.25, 1.25, 2.1],
        gap="small",
    )

    with view_col:
        view = st.segmented_control(
            "Management view",
            DASHBOARD_VIEWS,
            key="dashboard_view",
            label_visibility="collapsed",
        ) or "PM"

    with period_col:
        period = st.selectbox(
            "Period",
            period_options,
            key="dashboard_period",
            format_func=_format_period,
            label_visibility="collapsed",
        )

    with owner_col:
        assignee = st.selectbox(
            "Assignee",
            assignee_options,
            key="dashboard_assignee",
            label_visibility="collapsed",
        )

    with search_col:
        search_placeholder = (
            "Serial, model, location or postal code"
            if view == "Unit Profiles"
            else "Serial, issue, location or status"
        )
        keyword = st.text_input(
            "Search work",
            key="dashboard_search",
            placeholder=search_placeholder,
            label_visibility="collapsed",
        )

    if view == "Unit Profiles":
        st.caption(
            "Search selects the AED profile list. Period and assignee remain available when you return to operational views."
        )
    else:
        st.caption(
            "View · Period · Assignee · Search. The work queue updates immediately when the scope changes."
        )

    return {
        "view": view,
        "period": period,
        "assignee": assignee,
        "keyword": keyword,
    }


def _render_metric_card(metric: dict[str, str]) -> None:
    tone = escape(metric.get("tone", "blue"))
    st.markdown(
        f"""
        <div class="ops-kpi ops-kpi-{tone}">
            <div class="ops-kpi-label">{escape(metric.get('label', ''))}</div>
            <div class="ops-kpi-value">{escape(metric.get('value', '0'))}</div>
            <div class="ops-kpi-note">{escape(metric.get('note', ''))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_row(snapshot: dict[str, Any], view: str) -> None:
    metrics = calculate_dashboard_kpis(
        view=view,
        queue=snapshot["queue"],
        pm_summary=snapshot["pm_summary"],
        issue_summary=snapshot["issue_summary"],
        readiness_summary=snapshot["readiness_summary"],
    )

    columns = st.columns(4, gap="small")
    for column, metric in zip(columns, metrics):
        with column:
            _render_metric_card(metric)


def _selection_rows(event: Any) -> list[int]:
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection", {})

    if selection is None:
        return []
    if isinstance(selection, dict):
        return list(selection.get("rows", []))
    return list(getattr(selection, "rows", []) or [])


def render_work_queue(queue: pd.DataFrame) -> pd.Series | None:
    st.markdown(
        f"""
        <div class="ops-section-heading">
            <div>
                <span>PRIORITY WORK</span>
                <h2>Work queue</h2>
            </div>
            <div class="ops-section-count">{len(queue)} item(s)</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if queue.empty:
        st.success("No work items match the current management scope.")
        st.session_state.pop("dashboard_selected_queue_id", None)
        return None

    display = queue[DISPLAY_QUEUE_COLUMNS].copy()
    event = st.dataframe(
        display,
        key="operations_priority_queue",
        hide_index=True,
        width="stretch",
        height=430,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Category": st.column_config.TextColumn("Category", width="small"),
            "Priority": st.column_config.TextColumn("Priority", width="small"),
            "Item": st.column_config.TextColumn("Item", width="medium"),
            "Location": st.column_config.TextColumn("Location", width="large"),
            "Due / Age": st.column_config.TextColumn("Due / Age", width="medium"),
            "Owner": st.column_config.TextColumn("Owner", width="small"),
            "Status": st.column_config.TextColumn("Status", width="medium"),
        },
    )

    selected_rows = _selection_rows(event)
    if selected_rows:
        selected_index = selected_rows[0]
        if 0 <= selected_index < len(queue):
            selected = queue.iloc[selected_index].copy()
            st.session_state["dashboard_selected_queue_id"] = clean_text(
                selected.get("Queue ID")
            )
            return selected

    saved_id = clean_text(st.session_state.get("dashboard_selected_queue_id"))
    if saved_id:
        matches = queue[queue["Queue ID"].astype(str).eq(saved_id)]
        if not matches.empty:
            return matches.iloc[0].copy()

    return None


def _detail_rows(items: list[tuple[str, Any]]) -> str:
    return "".join(
        (
            '<div class="ops-detail-row">'
            f'<span>{escape(label)}</span>'
            f'<strong>{escape(clean_text(value) or "—")}</strong>'
            "</div>"
        )
        for label, value in items
    )


def _render_management_summary(snapshot: dict[str, Any]) -> None:
    queue = snapshot["queue"]
    overdue = int(
        queue["Due / Age"].astype(str).str.contains("overdue", case=False, na=False).sum()
    ) if not queue.empty else 0
    unassigned = int(queue["Owner"].eq("Unassigned").sum()) if not queue.empty else 0
    issue_summary = snapshot["issue_summary"]
    readiness = snapshot["readiness_summary"]

    st.markdown(
        f"""
        <div class="ops-detail-panel">
            <div class="ops-detail-kicker">MANAGEMENT SUMMARY</div>
            <h3>Select a work item</h3>
            <p>Choose one row from the queue to review its source record and open the correct workflow.</p>
            <div class="ops-summary-list">
                {_detail_rows([
                    ('Overdue work', overdue),
                    ('Open issues', issue_summary['open']),
                    ('Unassigned items', unassigned),
                    ('Consumables due', readiness['expiring_total']),
                    ('Registered AEDs', snapshot['data_health']['total_units']),
                ])}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _set_aed_target(source_row: pd.Series, *, state_key: str) -> None:
    st.session_state[state_key] = {
        "Serial Number": clean_text(source_row.get("Serial Number")),
        "Postal Code": clean_text(source_row.get("Postal Code")),
    }


def _render_aed_actions(
    selected_item: pd.Series,
    source_row: pd.Series,
    *,
    key_prefix: str,
) -> None:
    category = clean_text(selected_item.get("Category"))
    serial = clean_text(source_row.get("Serial Number"))

    if category == "PM":
        if st.button(
            "Start PM checklist",
            key=f"{key_prefix}_start_pm",
            type="primary",
            width="stretch",
        ):
            _set_aed_target(source_row, state_key="map_pm_target")
            _navigate("PM Checklist")
        if st.button(
            "Open PM planning",
            key=f"{key_prefix}_planning",
            width="stretch",
        ):
            _navigate("PM Planning")
    else:
        if st.button(
            "Open AED master record",
            key=f"{key_prefix}_master",
            type="primary",
            width="stretch",
        ):
            st.session_state["management_keyword"] = serial
            _navigate("AED Master Table")
        if st.button(
            "Report issue for this AED",
            key=f"{key_prefix}_report",
            width="stretch",
        ):
            st.session_state["report_issue_prefill"] = {
                "Source": "Operations Control",
                "Serial Number": serial,
                "Model": clean_text(source_row.get("Model")),
                "Location": clean_text(source_row.get("Location")),
                "Postal Code": clean_text(source_row.get("Postal Code")),
                "Lift Lobby": clean_text(source_row.get("Lift Lobby")),
                "Technician": "",
            }
            _navigate("Report Issue")


def _render_issue_actions(
    selected_item: pd.Series,
    *,
    key_prefix: str,
) -> None:
    issue_id = clean_text(selected_item.get("Item"))
    if st.button(
        "Open issue workflow",
        key=f"{key_prefix}_open_issue",
        type="primary",
        width="stretch",
    ):
        st.session_state["selected_issue_id"] = issue_id
        _navigate("Issues")


def render_selected_item_panel(
    selected_item: pd.Series | None,
    snapshot: dict[str, Any],
) -> None:
    st.markdown(
        """
        <div class="ops-section-heading ops-section-heading-compact">
            <div><span>DECISION PANEL</span><h2>Selected item</h2></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if selected_item is None:
        _render_management_summary(snapshot)
        return

    source_row = find_selected_source(snapshot, selected_item)
    if source_row is None:
        st.warning("The source record for this work item is no longer available.")
        return

    category = clean_text(selected_item.get("Category"))
    item = clean_text(selected_item.get("Item"))
    key_prefix = f"dashboard_detail_{_safe_key(selected_item.get('Queue ID'))}"

    if category in {"Issue", "Verification"}:
        title = clean_text(source_row.get("Issue Type")) or "Issue"
        detail_items = [
            ("Issue ID", source_row.get("Issue ID")),
            ("Serial Number", source_row.get("Serial Number")),
            ("Location", source_row.get("Location")),
            ("Priority", source_row.get("Priority")),
            ("Status", source_row.get("Status")),
            ("Assigned to", source_row.get("Current Assignee")),
            ("Reported by", source_row.get("Reported By")),
            ("Reported at", source_row.get("Reported At")),
            ("Due date", source_row.get("Due Date")),
            ("Next action", selected_item.get("Next Action")),
        ]
        description = clean_text(source_row.get("Detailed Description")) or "No description recorded."
    else:
        title = clean_text(source_row.get("Serial Number")) or item
        detail_items = [
            ("Location", source_row.get("Location")),
            ("Model", source_row.get("Model")),
            ("Next PM", source_row.get("Next PM Date")),
            ("PM completed", source_row.get("PM Completed Date")),
            ("Last done by", source_row.get("Last Done By")),
            ("Adult pads", source_row.get("Adult Pads Expiry Date")),
            ("Pediatric pads", source_row.get("Pediatric Pads Expiry Date")),
            ("Battery", source_row.get("Battery Expiry Date")),
            ("Current status", selected_item.get("Status")),
            ("Next action", selected_item.get("Next Action")),
        ]
        description = clean_text(selected_item.get("Title"))

    st.markdown(
        f"""
        <div class="ops-detail-panel">
            <div class="ops-detail-kicker">{escape(category.upper())}</div>
            <h3>{escape(title)}</h3>
            <p>{escape(description)}</p>
            <div class="ops-detail-list">{_detail_rows(detail_items)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if category in {"Issue", "Verification"}:
        _render_issue_actions(selected_item, key_prefix=key_prefix)
    else:
        _render_aed_actions(
            selected_item,
            source_row,
            key_prefix=key_prefix,
        )


def render_pm_progress(summary: dict[str, int], period: str) -> None:
    with st.container(border=True):
        st.markdown(
            f"**{_format_period(period)} PM completion**  \n"
            f"{summary['completed']} of {summary['planned']} saved plan item(s) completed"
        )
        st.progress(summary["completion_percent"] / 100 if summary["planned"] else 0)
        st.markdown(
            _detail_rows(
                [
                    ("Due this month", summary["due_this_period"]),
                    ("Planned", summary["planned"]),
                    ("Completed", summary["completed"]),
                    ("In progress", summary["in_progress"]),
                    ("Pending", summary["pending"]),
                    ("Unassigned", summary["unassigned"]),
                ]
            ),
            unsafe_allow_html=True,
        )


def render_issue_pipeline(summary: dict[str, int]) -> None:
    st.markdown(
        f"""
        <div class="ops-summary-card">
            <strong>Issue pipeline</strong>
            <div class="ops-summary-list">
                {_detail_rows([
                    ('Reported', summary['reported']),
                    ('Assigned', summary['assigned']),
                    ('In progress', summary['in_progress']),
                    ('Pending verification', summary['pending_verification']),
                    ('Reopened', summary['reopened']),
                    ('Unassigned', summary['unassigned']),
                ])}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_readiness_summary(summary: dict[str, int]) -> None:
    """Backward-compatible alias; the homepage now presents Unit Profiles."""
    st.markdown("**AED Unit Profiles**")
    st.caption("Open any AED electronic record from the Unit Profiles panel.")


def _profile_option_label(row: pd.Series) -> str:
    serial = clean_text(row.get("Serial Number"))
    model = clean_text(row.get("Model"))
    location = clean_text(row.get("Location")) or clean_text(row.get("Block / Locations"))
    detail = " · ".join(value for value in [model, location] if value)
    return f"{serial} — {detail}" if detail else serial


def render_unit_profile_entry(snapshot: dict[str, Any]) -> None:
    """Direct AED selector replacing the old third summary panel."""
    with st.container(border=True):
        st.markdown("**AED Unit Profiles**")
        st.caption(
            "Select an AED to open all information, edit details, review service history, "
            "add a service record or inspect Issues."
        )
        aed_data = snapshot.get("aed_data", pd.DataFrame()).copy()
        if aed_data.empty or "Serial Number" not in aed_data.columns:
            st.info("No AED unit is available yet.")
            return

        rows = aed_data[aed_data["Serial Number"].astype(str).str.strip().ne("")].copy()
        rows = rows.sort_values("Serial Number", kind="stable").reset_index(drop=True)
        serials = rows["Serial Number"].astype(str).tolist()
        label_lookup = {
            str(row.get("Serial Number", "")): _profile_option_label(row)
            for _, row in rows.iterrows()
        }
        selected = st.selectbox(
            "Select AED unit",
            options=serials,
            format_func=lambda serial: label_lookup.get(serial, serial),
            index=None,
            placeholder="Search Serial Number, model or location",
            key="dashboard_profile_entry_serial",
        )
        open_col, browse_col = st.columns(2, gap="small")
        if open_col.button(
            "Open selected profile",
            type="primary",
            width="stretch",
            disabled=selected is None,
            key="dashboard_open_selected_profile",
        ):
            st.session_state["dashboard_profile_serial"] = clean_text(
                selected
            )
            st.session_state["dashboard_view"] = "Unit Profiles"
            rerun_app()
        if browse_col.button(
            "Browse all profiles",
            width="stretch",
            key="dashboard_browse_all_profiles",
        ):
            st.session_state.pop("dashboard_profile_serial", None)
            st.session_state["dashboard_view"] = "Unit Profiles"
            rerun_app()


def render_operational_summaries(snapshot: dict[str, Any], period: str) -> None:
    st.markdown(
        '<div class="ops-section-heading"><div><span>CONTROL SUMMARY</span><h2>Progress, issues and unit profiles</h2></div></div>',
        unsafe_allow_html=True,
    )
    pm_col, issue_col, profile_col = st.columns([1, 1, 1.25], gap="small")
    with pm_col:
        render_pm_progress(snapshot["pm_summary"], period)
    with issue_col:
        render_issue_pipeline(snapshot["issue_summary"])
    with profile_col:
        render_unit_profile_entry(snapshot)

def render_activity_feed(activity: pd.DataFrame) -> None:
    st.markdown(
        '<div class="ops-section-heading"><div><span>RECENT ACTIVITY</span><h2>Operational changes</h2></div></div>',
        unsafe_allow_html=True,
    )
    if activity.empty:
        st.info("No PM, issue, planning or AED-change activity has been recorded yet.")
        return

    items = []
    for _, row in activity.iterrows():
        timestamp = clean_text(row.get("Activity At")) or "Time unavailable"
        actor = clean_text(row.get("Actor")) or "System"
        summary = clean_text(row.get("Summary"))
        activity_type = clean_text(row.get("Activity Type")) or "Update"
        items.append(
            f"""
            <div class="ops-activity-item">
                <div class="ops-activity-marker">{escape(activity_type[:1].upper())}</div>
                <div class="ops-activity-body">
                    <strong>{escape(summary)}</strong>
                    <span>{escape(timestamp)} · {escape(actor)}</span>
                </div>
            </div>
            """
        )

    st.markdown(
        '<div class="ops-activity-feed">' + "".join(items) + "</div>",
        unsafe_allow_html=True,
    )


def render_source_health(snapshot: dict[str, Any]) -> None:
    source_status = snapshot["source_status"]
    with st.expander("Data source health"):
        rows = []
        for status in source_status.values():
            modified_at = status.get("modified_at")
            rows.append(
                {
                    "Source": status.get("label", ""),
                    "Records": status.get("record_count", 0),
                    "Status": "Ready" if status.get("healthy") else "Needs attention",
                    "Last modified": (
                        modified_at.strftime("%d-%m-%Y %H:%M")
                        if modified_at is not None
                        else "—"
                    ),
                    "Detail": status.get("message", ""),
                }
            )
        st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            width="stretch",
        )


def render_quick_actions() -> None:
    st.markdown(
        '<div class="ops-section-heading"><div><span>QUICK ACTIONS</span><h2>Open another workspace</h2></div></div>',
        unsafe_allow_html=True,
    )
    labels = [
        ("Add / edit AED", "AED Master Table"),
        ("Open map", "AED Map"),
        ("PM planning", "PM Planning"),
        ("Service records", "Service Records"),
    ]
    columns = st.columns(len(labels), gap="small")
    for column, (label, page_name) in zip(columns, labels):
        with column:
            if st.button(
                label,
                key=f"dashboard_quick_{_safe_key(page_name)}",
                width="stretch",
            ):
                _navigate(page_name)


def build_filtered_queue(snapshot: dict[str, Any], filters: dict[str, str]) -> pd.DataFrame:
    return apply_dashboard_filters(
        snapshot["queue"],
        view=filters["view"],
        assignee=filters["assignee"],
        keyword=filters["keyword"],
    )
