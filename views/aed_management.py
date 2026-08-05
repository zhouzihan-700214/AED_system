from __future__ import annotations

from pathlib import Path
from typing import Any
from datetime import date
from html import escape as html_escape
import uuid

import pandas as pd
import streamlit as st

from config import (
    AED_LIFECYCLE_FILE,
    AUDIT_HISTORY_FILE,
    CONFLICT_HISTORY_FILE,
    EXCEL_WRITE_HISTORY_FILE,
    ISSUE_RECORD_FILE,
    ISSUE_RESOLUTION_FILE,
    MAP_STATUS_FILE,
    MAP_UNIT_STATE_FILE,
    PM_PLAN_FILE,
    PM_RESPONSES_FILE,
    TRANSACTION_HISTORY_FILE,
)
from services.manual_service_storage import MANUAL_SERVICE_RECORDS_FILE
from services import aed_service
from services.aed_field_schema import (
    DATE_FIELDS,
    DETAIL_EDITABLE_COLUMNS,
    FIELD_LABELS,
    JOB_TYPE_OPTIONS,
    REPAIRED_OPTIONS,
    TABLE_EDITABLE_COLUMNS,
)
from services.aed_repository import (
    add_unit,
    batch_update_units,
    deactivate_unit,
    get_all_units,
    get_sync_status,
    update_unit,
)
from services.aed_table_edit_service import (
    build_cell_changes,
    group_changes_for_repository,
    normalize_value,
    prepare_editor_dataframe,
    validate_table_changes,
)
from services.excel_write_service import load_excel_write_history
from services.issue_service import load_issue_records
from services.pm_service import complete_matching_pm_plan
from services.unit_profile_service import (
    append_manual_service_record,
    build_manual_service_update_plan,
    build_service_history,
    filter_unit_profiles,
    generate_manual_service_record_id,
    load_unit_issues,
)
from ui.components import page_header, section_label
from utils.streamlit_utils import rerun_app
from utils.text_utils import clean_text
from views.map_modules.status_service import (
    COLOR_EMOJI,
    load_plan_records,
    load_status_definitions,
    load_unit_state,
    status_color_lookup,
)


MANAGEMENT_FILTER_KEYS = {
    "model": "management_model",
    "location": "management_location",
    "postal_code": "management_postal",
    "lift_lobby": "management_lift_lobby",
    "job_type": "management_job_type",
    "last_done_by": "management_last_done_by",
}

MANAGEMENT_DATE_FILTERS = [
    ("PM Completed Date", "pm_completed"),
    ("Next PM Date", "next_pm"),
    ("Battery Expiry Date", "battery_expiry"),
    ("Adult Pads Expiry Date", "adult_expiry"),
    ("Pediatric Pads Expiry Date", "pediatric_expiry"),
]

MIN_DATE = date(1900, 1, 1)
MAX_DATE = date(2100, 12, 31)

EDITOR_STATE_DEFAULTS = {
    "aed_editor_mode": "browse",
    "aed_editor_session_id": None,
    "aed_editor_base_df": None,
    "aed_editor_working_df": None,
    "aed_editor_base_signature": None,
    "aed_editor_changes": [],
    "aed_editor_errors": [],
    "aed_editor_warnings": [],
}


def initialise_table_editor_state() -> None:
    for key, value in EDITOR_STATE_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clear_table_editor_state() -> None:
    for key, value in EDITOR_STATE_DEFAULTS.items():
        st.session_state[key] = value


def initialise_management_workspace_state() -> None:
    """Initialise the single Management search/table/profile workspace."""
    st.session_state.setdefault("aed_management_view", "list")
    st.session_state.setdefault("management_table_mode", "Browse Units")
    st.session_state.setdefault("management_profile_serial", "")
    st.session_state.setdefault("management_browse_table_nonce", 0)


def _management_date_ranges_from_state() -> dict[str, tuple[Any, Any]]:
    return {
        column: (
            st.session_state.get(f"{key_prefix}_from"),
            st.session_state.get(f"{key_prefix}_to"),
        )
        for column, key_prefix in MANAGEMENT_DATE_FILTERS
    }


def _management_filter_selections_from_state() -> dict[str, list[Any]]:
    selections: dict[str, list[Any]] = {}
    for filter_name, session_key in MANAGEMENT_FILTER_KEYS.items():
        value = st.session_state.get(session_key, [])
        if isinstance(value, (list, tuple, set)):
            selections[filter_name] = list(value)
        elif value:
            selections[filter_name] = [value]
        else:
            selections[filter_name] = []
    return selections


def _mark_management_filter_changed(filter_name: str) -> None:
    st.session_state["management_last_changed_filter"] = filter_name


def _normalise_management_filter_state(
    dataframe: pd.DataFrame,
    keyword: str,
    date_ranges: dict[str, tuple[Any, Any]],
) -> None:
    selections = _management_filter_selections_from_state()
    last_changed = st.session_state.get("management_last_changed_filter")

    if last_changed in MANAGEMENT_FILTER_KEYS:
        base_options = aed_service.linked_filter_options(
            dataframe=dataframe,
            target_filter=last_changed,
            keyword=keyword,
            selections={name: [] for name in MANAGEMENT_FILTER_KEYS},
            date_ranges=date_ranges,
        )
        allowed = set(base_options)
        valid = [value for value in selections[last_changed] if value in allowed]
        if valid != selections[last_changed]:
            selections[last_changed] = valid
            st.session_state[MANAGEMENT_FILTER_KEYS[last_changed]] = valid

    order = [name for name in MANAGEMENT_FILTER_KEYS if name != last_changed]
    if last_changed in MANAGEMENT_FILTER_KEYS:
        order.append(last_changed)

    for _ in range(len(MANAGEMENT_FILTER_KEYS) + 1):
        changed = False
        for filter_name in order:
            options = aed_service.linked_filter_options(
                dataframe=dataframe,
                target_filter=filter_name,
                keyword=keyword,
                selections=selections,
                date_ranges=date_ranges,
            )
            allowed = set(options)
            valid = [value for value in selections[filter_name] if value in allowed]
            if valid != selections[filter_name]:
                selections[filter_name] = valid
                st.session_state[MANAGEMENT_FILTER_KEYS[filter_name]] = valid
                changed = True
        if not changed:
            break


def reset_management_filters() -> None:
    defaults: dict[str, Any] = {
        "management_keyword": "",
        "management_model": [],
        "management_location": [],
        "management_postal": [],
        "management_lift_lobby": [],
        "management_job_type": [],
        "management_last_done_by": [],
        "management_sort_by": "Serial Number",
        "management_sort_order": "Ascending",
        "management_last_changed_filter": None,
    }
    for _, key_prefix in MANAGEMENT_DATE_FILTERS:
        defaults[f"{key_prefix}_from"] = None
        defaults[f"{key_prefix}_to"] = None
    for key, value in defaults.items():
        st.session_state[key] = value


def render_filters(dataframe: pd.DataFrame) -> dict[str, Any]:
    """Render the single responsive search and linked-filter workspace."""
    filter_state: dict[str, Any] = {}
    keyword = st.session_state.get("management_keyword", "")
    date_ranges = _management_date_ranges_from_state()

    with st.container(border=True):
        st.markdown("#### Search and filter AED units")
        st.caption(
            "One search controls both Browse Units and Direct Edit. All linked filters "
            "continue to narrow each other automatically."
        )
        search_col, reset_col = st.columns([5.2, 1.15], gap="small")
        with search_col:
            filter_state["keyword"] = st.text_input(
                "Search AED units",
                placeholder=(
                    "Serial, model, location, postal code, lobby, PO, zone, "
                    "lot number, e-SR or remarks"
                ),
                key="management_keyword",
            )
        with reset_col:
            st.markdown('<div class="aed-control-top-spacer"></div>', unsafe_allow_html=True)
            st.button(
                "Reset all",
                width="stretch",
                key="reset_management_filters_button",
                on_click=reset_management_filters,
            )

        keyword = filter_state["keyword"]
        _normalise_management_filter_state(dataframe, keyword, date_ranges)
        selections = _management_filter_selections_from_state()
        tabs = st.tabs(["Linked Filters", "Date Filters", "Sorting"])

        labels = {
            "model": "Model",
            "location": "Location",
            "postal_code": "Postal Code",
            "lift_lobby": "Lift Lobby",
            "job_type": "Service Type",
            "last_done_by": "Last Done By",
        }
        with tabs[0]:
            filter_columns = st.columns(3, gap="small")
            for index, (filter_name, label) in enumerate(labels.items()):
                options = aed_service.linked_filter_options(
                    dataframe=dataframe,
                    target_filter=filter_name,
                    keyword=keyword,
                    selections=selections,
                    date_ranges=date_ranges,
                )
                with filter_columns[index % 3]:
                    filter_state[filter_name] = st.multiselect(
                        label,
                        options=options,
                        key=MANAGEMENT_FILTER_KEYS[filter_name],
                        on_change=_mark_management_filter_changed,
                        args=(filter_name,),
                    )
                selections[filter_name] = filter_state[filter_name]

        with tabs[1]:
            date_ranges = {}
            date_columns = st.columns(2, gap="medium")
            for index, (column, key_prefix) in enumerate(MANAGEMENT_DATE_FILTERS):
                with date_columns[index % 2]:
                    st.markdown(f"**{column}**")
                    from_col, to_col = st.columns(2, gap="small")
                    with from_col:
                        start_value = st.date_input(
                            "From",
                            value=None,
                            format="DD-MM-YYYY",
                            min_value=MIN_DATE,
                            max_value=MAX_DATE,
                            key=f"{key_prefix}_from",
                        )
                    with to_col:
                        end_value = st.date_input(
                            "To",
                            value=None,
                            format="DD-MM-YYYY",
                            min_value=MIN_DATE,
                            max_value=MAX_DATE,
                            key=f"{key_prefix}_to",
                        )
                    date_ranges[column] = (start_value, end_value)
            filter_state["date_ranges"] = date_ranges

        with tabs[2]:
            sort_col, order_col = st.columns(2, gap="medium")
            with sort_col:
                filter_state["sort_by"] = st.selectbox(
                    "Sort By",
                    options=aed_service.AED_COLUMNS,
                    index=0,
                    key="management_sort_by",
                )
            with order_col:
                filter_state["ascending"] = (
                    st.radio(
                        "Order",
                        options=["Ascending", "Descending"],
                        horizontal=True,
                        key="management_sort_order",
                    )
                    == "Ascending"
                )

    return filter_state


def _unit_option_label(dataframe: pd.DataFrame, row_index: Any) -> str:
    row = dataframe.loc[row_index]
    serial = aed_service.clean_text(row.get("Serial Number", "")) or "No serial"
    location = aed_service.clean_text(row.get("Location", "")) or "No location"
    postal = aed_service.clean_text(row.get("Postal Code", "")) or "No postal code"
    return f"{serial} | {location} | {postal}"


def _date_input_value(value: Any):
    parsed = aed_service.parse_date(value)
    return None if parsed is None else parsed.date()


def _column_config(editor_df: pd.DataFrame | None = None) -> dict[str, Any]:
    job_options = list(JOB_TYPE_OPTIONS)
    repaired_options = list(REPAIRED_OPTIONS)
    if editor_df is not None:
        for value in editor_df.get("Job Type", pd.Series(dtype=str)).astype(str).str.strip().unique():
            if value and value not in job_options:
                job_options.append(value)
        for value in editor_df.get("Repaired?", pd.Series(dtype=str)).astype(str).str.strip().unique():
            if value and value not in repaired_options:
                repaired_options.append(value)
    return {
        "Serial Number": st.column_config.TextColumn(
            "Serial Number", help="Unique identifier; cannot be edited."
        ),
        "Model": st.column_config.TextColumn("Model / Related Object"),
        "Postal Code": st.column_config.TextColumn(
            "Postal Code", help="Six-digit postal code", max_chars=6
        ),
        "Adult Pads Expiry Date": st.column_config.DateColumn(
            "Adult Pads Expiry Date", format="DD/MM/YYYY"
        ),
        "Pediatric Pads Expiry Date": st.column_config.DateColumn(
            "Pediatric Pads Expiry Date", format="DD/MM/YYYY"
        ),
        "Battery Expiry Date": st.column_config.DateColumn(
            "Battery Expiry Date", format="DD/MM/YYYY"
        ),
        "PM Completed Date": st.column_config.DateColumn(
            "PM Completed Date", format="DD/MM/YYYY"
        ),
        "Next PM Date": st.column_config.DateColumn(
            "Next PM Date", format="DD/MM/YYYY", required=True
        ),
        "Job Type": st.column_config.SelectboxColumn(
            "Service Type", options=job_options
        ),
        "Repaired?": st.column_config.SelectboxColumn(
            "Repaired?", options=repaired_options
        ),
        "Service Report e-SR": st.column_config.TextColumn(
            "Service Report / e-SR"
        ),
    }


def render_browse_table(filtered: pd.DataFrame) -> None:
    """Render the current filtered rows before starting a direct-edit session."""
    display_columns = [
        column for column in aed_service.AED_COLUMNS if column in filtered.columns
    ]
    st.dataframe(
        filtered[display_columns],
        width="stretch",
        height=500,
        hide_index=True,
    )

    count = len(filtered)
    if count == 0:
        st.info("No AED units match the current filters.")
        return
    if count > 100:
        st.warning(
            "Narrow the filters to 100 AED units or fewer before entering table edit mode."
        )
        return

    if st.button(
        "Edit Current Results",
        type="primary",
        width="stretch",
        key="start_aed_table_edit",
    ):
        try:
            editor_df = prepare_editor_dataframe(filtered)
        except ValueError as error:
            st.error(str(error))
            return
        st.session_state.aed_editor_mode = "edit"
        st.session_state.aed_editor_session_id = uuid.uuid4().hex
        st.session_state.aed_editor_base_df = editor_df.copy()
        st.session_state.aed_editor_working_df = editor_df.copy()
        st.session_state.aed_editor_base_signature = get_sync_status().get("signature")
        st.session_state.aed_editor_changes = []
        st.session_state.aed_editor_errors = []
        st.session_state.aed_editor_warnings = []
        rerun_app()


def _browse_table_display(filtered: pd.DataFrame) -> pd.DataFrame:
    """Build the compact clickable table without changing the master dataframe."""
    rows = filtered.copy().reset_index(drop=True)
    if rows.empty:
        return pd.DataFrame(
            columns=[
                "Serial Number",
                "Model",
                "Location",
                "Postal Code",
                "Next PM Date",
                "Service Type",
                "Open Issues",
                "Marker",
            ]
        )

    issues = load_issue_records(ISSUE_RECORD_FILE)
    if not issues.empty and {"Serial Number", "Status"}.issubset(issues.columns):
        active = issues[
            ~issues["Status"].astype(str).str.casefold().isin({"closed", "resolved"})
        ].copy()
        counts = active.groupby(
            active["Serial Number"].astype(str).str.strip()
        ).size()
        rows["Open Issues"] = (
            rows["Serial Number"].astype(str).str.strip().map(counts).fillna(0).astype(int)
        )
    else:
        rows["Open Issues"] = 0

    state = load_unit_state(MAP_UNIT_STATE_FILE)
    definitions = load_status_definitions(MAP_STATUS_FILE)
    colour_lookup = status_color_lookup(definitions)
    state_lookup: dict[str, tuple[str, str]] = {}
    if not state.empty and "Serial Number" in state.columns:
        for _, row in state.iterrows():
            serial = clean_text(row.get("Serial Number"))
            if serial:
                state_lookup[serial] = (
                    clean_text(row.get("Status")),
                    clean_text(row.get("Color Override")).title(),
                )

    def marker_for(serial: Any) -> str:
        status, override = state_lookup.get(clean_text(serial), ("", ""))
        colour = override or colour_lookup.get(status.casefold(), "Gray")
        label = override or status or "Pending"
        return f"{COLOR_EMOJI.get(colour, '●')} {label}"

    rows["Marker"] = rows["Serial Number"].map(marker_for)
    rows["Service Type"] = rows.get("Job Type", "")
    display_columns = [
        "Serial Number",
        "Model",
        "Location",
        "Postal Code",
        "Next PM Date",
        "Service Type",
        "Open Issues",
        "Marker",
    ]
    return rows.reindex(columns=display_columns)


def render_selectable_browse_table(filtered: pd.DataFrame) -> None:
    """Open a unit profile by clicking its row in the single AED table."""
    display = _browse_table_display(filtered)
    if display.empty:
        st.info("No AED units match the current search and filters.")
        return

    st.caption(
        "Click any AED row to open its complete profile. Search and filter selections "
        "are preserved when you return to this list."
    )
    nonce = int(st.session_state.get("management_browse_table_nonce", 0))
    event = st.dataframe(
        display,
        width="stretch",
        height=min(620, 48 + 36 * len(display)),
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"aed_management_browse_table_{nonce}",
        column_config={
            "Open Issues": st.column_config.NumberColumn("Open Issues", format="%d"),
        },
    )
    selected_rows = _selection_rows(event)
    if not selected_rows:
        return
    selected_index = selected_rows[0]
    if not 0 <= selected_index < len(display):
        return
    serial = clean_text(display.iloc[selected_index].get("Serial Number"))
    if not serial:
        return
    st.session_state["management_profile_serial"] = serial
    st.session_state["aed_management_view"] = "profile"
    rerun_app()


def render_edit_mode() -> None:
    base_df = st.session_state.aed_editor_base_df
    working_df = st.session_state.aed_editor_working_df
    editor_id = st.session_state.aed_editor_session_id
    if base_df is None or working_df is None or not editor_id:
        clear_table_editor_state()
        st.error("The edit session was incomplete and has been reset.")
        return

    st.subheader(f"Editing {len(base_df)} AED unit(s)")
    st.info(
        "Filters and automatic Excel refresh are paused. Edit the cells, then review before saving."
    )
    with st.form(f"aed_table_form_{editor_id}"):
        edited_df = st.data_editor(
            working_df,
            width="stretch",
            height=650,
            hide_index=True,
            num_rows="fixed",
            disabled=["Serial Number"],
            column_config=_column_config(working_df),
            key=f"aed_table_editor_{editor_id}",
        )
        left, right = st.columns(2)
        review_clicked = left.form_submit_button(
            "Review Changes", type="primary", width="stretch"
        )
        cancel_clicked = right.form_submit_button(
            "Cancel Editing", width="stretch"
        )

    if cancel_clicked:
        clear_table_editor_state()
        rerun_app()
    if not review_clicked:
        return

    try:
        changes = build_cell_changes(base_df, edited_df)
        errors, warnings = validate_table_changes(base_df, changes)
    except ValueError as error:
        st.error(str(error))
        return
    if not changes:
        st.info("No changes were detected.")
        return

    st.session_state.aed_editor_working_df = edited_df.copy()
    st.session_state.aed_editor_changes = changes
    st.session_state.aed_editor_errors = errors
    st.session_state.aed_editor_warnings = warnings
    st.session_state.aed_editor_mode = "review"
    rerun_app()


def _changes_dataframe(changes: list[dict[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Serial Number": change["serial_number"],
                "Field": FIELD_LABELS.get(change["field"], change["field"]),
                "Old Value": change["original_value"],
                "New Value": change["desired_value"],
            }
            for change in changes
        ]
    )


def _flatten_conflicts(conflicts: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for serial, field_conflicts in conflicts.items():
        for field, values in field_conflicts.items():
            rows.append(
                {
                    "Serial Number": serial,
                    "Field": FIELD_LABELS.get(field, field),
                    "Opened Value": values.get("original", ""),
                    "Current Excel": values.get("current", ""),
                    "Your Value": values.get("desired", ""),
                }
            )
    return pd.DataFrame(rows)


def render_review_mode() -> None:
    changes = list(st.session_state.aed_editor_changes)
    errors = list(st.session_state.aed_editor_errors)
    warnings = list(st.session_state.aed_editor_warnings)
    affected = {change["serial_number"] for change in changes}

    st.subheader("Review Changes")
    st.write(f"{len(changes)} cell change(s) across {len(affected)} AED unit(s).")
    st.dataframe(_changes_dataframe(changes), width="stretch", hide_index=True)
    for warning in warnings:
        st.warning(warning)
    for error in errors:
        st.error(error)
    if errors:
        st.info("Return to editing and correct the errors before saving.")

    col1, col2, col3 = st.columns(3)
    confirm = col1.button(
        "Confirm Save to Excel",
        type="primary",
        disabled=bool(errors),
        width="stretch",
    )
    back = col2.button("Back to Editing", width="stretch")
    discard = col3.button("Discard Changes", width="stretch")

    if back:
        st.session_state.aed_editor_mode = "edit"
        rerun_app()
    if discard:
        clear_table_editor_state()
        rerun_app()
    if not confirm:
        return

    updates = group_changes_for_repository(changes)
    with st.spinner("Checking conflicts and updating Excel..."):
        result = batch_update_units(
            updates=updates,
            user=st.session_state.get("audit_user", ""),
            session_id=st.session_state.get("session_id", ""),
            source_page="AED Management Table",
        )
    if result.success or result.status in {"already_applied", "no_changes"}:
        clear_table_editor_state()
        st.session_state["aed_writeback_notice"] = result.message
        st.session_state["aed_writeback_warnings"] = list(result.warnings)
        rerun_app()
    if result.status == "conflict":
        st.error(result.message)
        st.dataframe(
            _flatten_conflicts(result.conflicts),
            width="stretch",
            hide_index=True,
        )
        st.info("No part of this edit batch was saved.")
    elif result.status in {"already_applied", "no_changes"}:
        st.info(result.message)
    elif result.excel_updated:
        st.warning(result.message)
    else:
        st.error(result.message)


def _snapshot_value(field: str, value: Any) -> str:
    try:
        return normalize_value(field, value)
    except ValueError:
        return aed_service.clean_text(value)


def _select_options_with_current(options: list[str], current: str) -> list[str]:
    result = list(options)
    if current and current not in result:
        result.append(current)
    return result


def render_full_details_editor(filtered: pd.DataFrame) -> None:
    with st.expander("Edit Full Details", expanded=False):
        st.caption(
            "Use this form for fields that are too wide for the main table, including replacement history and Remarks."
        )
        if filtered.empty:
            st.info("No AED matches the current filters.")
            return
        indices = filtered.index.tolist()
        selected_index = st.selectbox(
            "Select an AED",
            options=indices,
            index=None,
            placeholder="Choose one matching AED",
            format_func=lambda index: _unit_option_label(filtered, index),
            key="full_detail_selected_index",
        )
        if selected_index is None:
            return
        selected = filtered.loc[selected_index]
        serial = aed_service.clean_text(selected.get("Serial Number", ""))
        snapshot_key = "full_detail_snapshot"
        if st.session_state.get("full_detail_snapshot_serial") != serial:
            st.session_state.full_detail_snapshot_serial = serial
            st.session_state[snapshot_key] = {
                field: _snapshot_value(field, selected.get(field, ""))
                for field in DETAIL_EDITABLE_COLUMNS
            }
        snapshot = dict(st.session_state.get(snapshot_key, {}))

        with st.form(f"full_detail_form_{serial}"):
            st.markdown("#### Basic Information")
            c1, c2 = st.columns(2)
            c1.text_input("Serial Number", value=serial, disabled=True)
            c2.text_input(
                "Audit User",
                value=st.session_state.get("audit_user", ""),
                disabled=True,
            )
            installation = c1.date_input(
                "Installation Date",
                value=_date_input_value(snapshot.get("Installation Date", "")),
                format="DD-MM-YYYY", min_value=MIN_DATE, max_value=MAX_DATE,
            )
            model = c2.text_input(
                "Model / Related Object", value=snapshot.get("Model", "")
            )
            phase = c1.text_input(
                "Installed Phase / Month",
                value=snapshot.get("Installed Phase / Month", ""),
            )
            po_number = c2.text_input("PO Number", value=snapshot.get("PO Number", ""))
            zone = c1.text_input("Zone", value=snapshot.get("Zone", ""))
            block = c2.text_input(
                "Block / Locations", value=snapshot.get("Block / Locations", "")
            )
            street = c1.text_input("Street Name", value=snapshot.get("Street Name", ""))
            postal = c2.text_input(
                "Postal Code", value=snapshot.get("Postal Code", ""), max_chars=6
            )
            level = c1.text_input("Level", value=snapshot.get("Level", ""))
            lobby = c2.text_input("Lift Lobby", value=snapshot.get("Lift Lobby", ""))

            st.markdown("#### Adult Pads")
            c1, c2, c3 = st.columns(3)
            adult_replacement = c1.date_input(
                "Adult Pads Replacement Date",
                value=_date_input_value(snapshot.get("Adult Pads Replacement Date", "")),
                format="DD-MM-YYYY", min_value=MIN_DATE, max_value=MAX_DATE,
            )
            adult_expiry = c2.date_input(
                "Adult Pads Expiry Date",
                value=_date_input_value(snapshot.get("Adult Pads Expiry Date", "")),
                format="DD-MM-YYYY", min_value=MIN_DATE, max_value=MAX_DATE,
            )
            adult_lot = c3.text_input(
                "Adult Pads Lot Number", value=snapshot.get("Adult Pads Lot Number", "")
            )

            st.markdown("#### Pediatric Pads")
            c1, c2, c3 = st.columns(3)
            pediatric_replacement = c1.date_input(
                "Pediatric Pads Replacement Date",
                value=_date_input_value(snapshot.get("Pediatric Pads Replacement Date", "")),
                format="DD-MM-YYYY", min_value=MIN_DATE, max_value=MAX_DATE,
            )
            pediatric_expiry = c2.date_input(
                "Pediatric Pads Expiry Date",
                value=_date_input_value(snapshot.get("Pediatric Pads Expiry Date", "")),
                format="DD-MM-YYYY", min_value=MIN_DATE, max_value=MAX_DATE,
            )
            pediatric_lot = c3.text_input(
                "Pediatric Pads Lot Number",
                value=snapshot.get("Pediatric Pads Lot Number", ""),
            )

            st.markdown("#### Battery")
            c1, c2 = st.columns(2)
            battery_expiry = c1.date_input(
                "Battery Expiry Date",
                value=_date_input_value(snapshot.get("Battery Expiry Date", "")),
                format="DD-MM-YYYY", min_value=MIN_DATE, max_value=MAX_DATE,
            )
            battery_history = c2.text_area(
                "Battery Replacement History",
                value=snapshot.get("Battery Replacement History", ""),
                height=90,
            )

            st.markdown("#### PM and Service")
            c1, c2 = st.columns(2)
            completed = c1.date_input(
                "PM Completed Date",
                value=_date_input_value(snapshot.get("PM Completed Date", "")),
                format="DD-MM-YYYY", min_value=MIN_DATE, max_value=MAX_DATE,
            )
            next_pm = c2.date_input(
                "Next PM Date",
                value=_date_input_value(snapshot.get("Next PM Date", "")),
                format="DD-MM-YYYY", min_value=MIN_DATE, max_value=MAX_DATE,
            )
            job_options = _select_options_with_current(
                JOB_TYPE_OPTIONS, snapshot.get("Job Type", "")
            )
            job_type = c1.selectbox(
                "Job Type",
                options=job_options,
                index=job_options.index(snapshot.get("Job Type", ""))
                if snapshot.get("Job Type", "") in job_options
                else 0,
            )
            last_done = c2.text_input(
                "Last Done By", value=snapshot.get("Last Done By", "")
            )
            report = c1.text_input(
                "Service Report / e-SR",
                value=snapshot.get("Service Report e-SR", ""),
            )
            repaired_options = _select_options_with_current(
                REPAIRED_OPTIONS, snapshot.get("Repaired?", "")
            )
            repaired = c2.selectbox(
                "Repaired?",
                options=repaired_options,
                index=repaired_options.index(snapshot.get("Repaired?", ""))
                if snapshot.get("Repaired?", "") in repaired_options
                else 0,
            )
            remarks = st.text_area(
                "Remarks",
                value=snapshot.get("Remarks", ""),
                height=150,
                help=(
                    "When saved, existing Remarks continuation text is consolidated into the main AED row."
                ),
            )
            submitted = st.form_submit_button(
                "Save Full Details to Excel",
                type="primary",
                width="stretch",
            )

        if not submitted:
            return
        entered: dict[str, Any] = {
            "Installation Date": aed_service.format_date(installation),
            "Model": model,
            "Installed Phase / Month": phase,
            "PO Number": po_number,
            "Zone": zone,
            "Block / Locations": block,
            "Street Name": street,
            "Postal Code": postal,
            "Level": level,
            "Lift Lobby": lobby,
            "Adult Pads Replacement Date": aed_service.format_date(adult_replacement),
            "Adult Pads Expiry Date": aed_service.format_date(adult_expiry),
            "Adult Pads Lot Number": adult_lot,
            "Pediatric Pads Replacement Date": aed_service.format_date(pediatric_replacement),
            "Pediatric Pads Expiry Date": aed_service.format_date(pediatric_expiry),
            "Pediatric Pads Lot Number": pediatric_lot,
            "Battery Replacement History": battery_history,
            "Battery Expiry Date": aed_service.format_date(battery_expiry),
            "PM Completed Date": aed_service.format_date(completed),
            "Next PM Date": aed_service.format_date(next_pm),
            "Job Type": job_type,
            "Last Done By": last_done,
            "Service Report e-SR": report,
            "Repaired?": repaired,
            "Remarks": remarks,
        }
        changes: dict[str, Any] = {}
        original_values: dict[str, Any] = {}
        try:
            for field, raw_value in entered.items():
                new_value = normalize_value(field, raw_value)
                old_value = snapshot.get(field, "")
                if new_value != old_value:
                    changes[field] = new_value
                    original_values[field] = old_value
        except ValueError as error:
            st.error(str(error))
            return
        if not changes:
            st.info("No changes were detected.")
            return
        result = update_unit(
            serial_number=serial,
            changes=changes,
            original_values=original_values,
            user=st.session_state.get("audit_user", ""),
            session_id=st.session_state.get("session_id", ""),
            source_page="AED Management Full Details",
        )
        if result.success or result.status in {"already_applied", "no_changes"}:
            st.session_state.pop("full_detail_snapshot_serial", None)
            st.session_state.pop(snapshot_key, None)
            st.session_state["aed_writeback_notice"] = result.message
            st.session_state["aed_writeback_warnings"] = list(result.warnings)
            rerun_app()
        elif result.status == "conflict":
            st.error(result.message)
            rows = [
                {
                    "Field": FIELD_LABELS.get(field, field),
                    "Opened Value": values.get("original", ""),
                    "Current Excel": values.get("current", ""),
                    "Your Value": values.get("desired", ""),
                }
                for field, values in result.conflicts.items()
            ]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        elif result.status in {"no_changes", "already_applied"}:
            st.info(result.message)
        elif result.excel_updated:
            st.warning(result.message)
        else:
            st.error(result.message)


def _optional_date(label: str, key: str):
    return st.date_input(label, value=None, format="DD-MM-YYYY", min_value=MIN_DATE, max_value=MAX_DATE, key=key)


def render_add_and_deactivate(dataframe: pd.DataFrame) -> None:
    with st.expander("Add or Deactivate AED", expanded=False):
        add_tab, deactivate_tab = st.tabs(["Add AED", "Deactivate AED"])
        with add_tab:
            st.caption("Fields marked * are required; the remaining fields may be completed later.")
            with st.form("stage5_full_add_aed_form"):
                st.markdown("#### Basic Information")
                c1, c2 = st.columns(2)
                serial = c1.text_input("Serial Number*")
                model = c2.text_input("Model / Related Object*")
                installation = c1.date_input(
                    "Installation Date", value=None, format="DD-MM-YYYY", min_value=MIN_DATE, max_value=MAX_DATE
                )
                phase = c2.text_input("Installed Phase / Month")
                po_number = c1.text_input("PO Number")
                zone = c2.text_input("Zone")
                block = c1.text_input("Block / Locations*")
                street = c2.text_input("Street Name*")
                postal = c1.text_input("Postal Code*", max_chars=6)
                level = c2.text_input("Level")
                lobby = c1.text_input("Lift Lobby")

                st.markdown("#### Adult Pads")
                c1, c2, c3 = st.columns(3)
                adult_replacement = c1.date_input(
                    "Adult Pads Replacement Date", value=None, format="DD-MM-YYYY", min_value=MIN_DATE, max_value=MAX_DATE
                )
                adult_expiry = c2.date_input(
                    "Adult Pads Expiry Date", value=None, format="DD-MM-YYYY", min_value=MIN_DATE, max_value=MAX_DATE
                )
                adult_lot = c3.text_input("Adult Pads Lot Number")

                st.markdown("#### Pediatric Pads")
                c1, c2, c3 = st.columns(3)
                pediatric_replacement = c1.date_input(
                    "Pediatric Pads Replacement Date", value=None, format="DD-MM-YYYY", min_value=MIN_DATE, max_value=MAX_DATE
                )
                pediatric_expiry = c2.date_input(
                    "Pediatric Pads Expiry Date", value=None, format="DD-MM-YYYY", min_value=MIN_DATE, max_value=MAX_DATE
                )
                pediatric_lot = c3.text_input("Pediatric Pads Lot Number")

                st.markdown("#### Battery")
                c1, c2 = st.columns(2)
                battery_expiry = c1.date_input(
                    "Battery Expiry Date", value=None, format="DD-MM-YYYY", min_value=MIN_DATE, max_value=MAX_DATE
                )
                battery_history = c2.text_area("Battery Replacement History", height=90)

                st.markdown("#### PM and Service")
                c1, c2 = st.columns(2)
                completed = c1.date_input(
                    "PM Completed Date", value=None, format="DD-MM-YYYY", min_value=MIN_DATE, max_value=MAX_DATE
                )
                next_pm = c2.date_input(
                    "Next PM Date*", value=None, format="DD-MM-YYYY", min_value=MIN_DATE, max_value=MAX_DATE
                )
                job_type = c1.selectbox("Service Type", options=JOB_TYPE_OPTIONS)
                last_done = c2.text_input("Last Done By")
                report = c1.text_input("Service Report / e-SR")
                repaired = c2.selectbox("Repaired?", options=REPAIRED_OPTIONS)
                remarks = st.text_area("Remarks", height=140)
                add_clicked = st.form_submit_button(
                    "Add AED to Excel", type="primary", width="stretch"
                )

            if add_clicked:
                values = {
                    "Serial Number": serial,
                    "Installation Date": aed_service.format_date(installation),
                    "Model": model,
                    "Installed Phase / Month": phase,
                    "PO Number": po_number,
                    "Zone": zone,
                    "Block / Locations": block,
                    "Street Name": street,
                    "Postal Code": postal,
                    "Level": level,
                    "Lift Lobby": lobby,
                    "Adult Pads Replacement Date": aed_service.format_date(adult_replacement),
                    "Adult Pads Expiry Date": aed_service.format_date(adult_expiry),
                    "Adult Pads Lot Number": adult_lot,
                    "Pediatric Pads Replacement Date": aed_service.format_date(pediatric_replacement),
                    "Pediatric Pads Expiry Date": aed_service.format_date(pediatric_expiry),
                    "Pediatric Pads Lot Number": pediatric_lot,
                    "Battery Replacement History": battery_history,
                    "Battery Expiry Date": aed_service.format_date(battery_expiry),
                    "PM Completed Date": aed_service.format_date(completed),
                    "Next PM Date": aed_service.format_date(next_pm),
                    "Job Type": job_type,
                    "Last Done By": last_done,
                    "Service Report e-SR": report,
                    "Repaired?": repaired,
                    "Remarks": remarks,
                }
                result = add_unit(
                    values=values,
                    user=st.session_state.get("audit_user", ""),
                    session_id=st.session_state.get("session_id", ""),
                    source_page="AED Management Add",
                )
                if result.success:
                    st.session_state["aed_writeback_notice"] = result.message
                    st.session_state["aed_writeback_warnings"] = list(result.warnings)
                    rerun_app()
                else:
                    st.error(result.message)

        with deactivate_tab:
            options = dataframe.index.tolist()
            selected_index = st.selectbox(
                "Select active AED",
                options=options,
                index=None,
                format_func=lambda index: _unit_option_label(dataframe, index),
                key="deactivate_aed_index",
            )
            reason = st.text_input("Reason", key="deactivate_reason")
            confirm = st.checkbox(
                "I confirm this unit should be hidden from active operational pages."
            )
            if st.button(
                "Deactivate AED",
                disabled=selected_index is None or not confirm,
                width="stretch",
            ):
                serial_value = aed_service.clean_text(
                    dataframe.loc[selected_index].get("Serial Number", "")
                )
                result = deactivate_unit(
                    serial_number=serial_value,
                    user=st.session_state.get("audit_user", ""),
                    session_id=st.session_state.get("session_id", ""),
                    reason=reason,
                    source_page="AED Management",
                )
                if result.success:
                    st.session_state["aed_writeback_notice"] = result.message
                    rerun_app()
                else:
                    st.error(result.message)


def _read_optional_csv(path: str | Path) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(
            csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig"
        )
    except (OSError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def render_audit_log(history_file: str | Path) -> None:
    with st.expander("Transaction History", expanded=False):
        history = _read_optional_csv(TRANSACTION_HISTORY_FILE)
        if history.empty:
            st.info("No transactions have been recorded yet.")
        else:
            st.dataframe(
                history.tail(50).iloc[::-1], width="stretch", hide_index=True
            )

    with st.expander("Field Audit and Conflict History", expanded=False):
        audit = _read_optional_csv(AUDIT_HISTORY_FILE)
        conflicts = _read_optional_csv(CONFLICT_HISTORY_FILE)
        audit_tab, conflict_tab = st.tabs(["All field results", "Conflicts"])
        with audit_tab:
            if audit.empty:
                st.info("No field-level audit records are available.")
            else:
                st.dataframe(
                    audit.tail(100).iloc[::-1],
                    width="stretch",
                    hide_index=True,
                )
        with conflict_tab:
            if conflicts.empty:
                st.info("No edit conflicts have been recorded.")
            else:
                st.dataframe(
                    conflicts.tail(100).iloc[::-1],
                    width="stretch",
                    hide_index=True,
                )

    with st.expander("Earlier Excel Write History", expanded=False):
        rows = load_excel_write_history(EXCEL_WRITE_HISTORY_FILE)
        if not rows:
            st.info("No earlier website-to-Excel updates were recorded.")
        else:
            st.dataframe(
                pd.DataFrame(rows).tail(30).iloc[::-1],
                width="stretch",
                hide_index=True,
            )

    with st.expander("AED Lifecycle History", expanded=False):
        lifecycle = _read_optional_csv(AED_LIFECYCLE_FILE)
        if lifecycle.empty:
            st.info("No AED lifecycle changes have been recorded.")
        else:
            display_columns = [
                "Timestamp",
                "Serial Number",
                "Status",
                "Reason",
                "User",
                "Source Page",
                "Operation ID",
            ]
            display_columns = [
                column for column in display_columns if column in lifecycle.columns
            ]
            st.dataframe(
                lifecycle.reindex(columns=display_columns).tail(100).iloc[::-1],
                width="stretch",
                hide_index=True,
            )

    with st.expander("Legacy CSV Audit Log", expanded=False):
        history = aed_service.load_history(history_file)
        if history.empty:
            st.info("No earlier CSV master-data changes were recorded.")
        else:
            st.dataframe(history.head(20), width="stretch", hide_index=True)


def _navigate_management(page_name: str) -> None:
    st.session_state["page"] = page_name
    rerun_app()


def _open_master_table(serial: str = "") -> None:
    """Open the unified AED Management table in Direct Edit mode."""
    reset_management_filters()
    if clean_text(serial):
        st.session_state["management_keyword"] = clean_text(serial)
    st.session_state["management_table_mode"] = "Direct Edit"
    st.session_state["aed_management_view"] = "list"
    st.session_state["page"] = "AED Management"


def _selection_rows(event: Any) -> list[int]:
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection", {})
    if selection is None:
        return []
    if isinstance(selection, dict):
        return list(selection.get("rows", []))
    return list(getattr(selection, "rows", []) or [])


def _management_snapshot(dataframe: pd.DataFrame) -> dict[str, Any]:
    try:
        issues = load_issue_records(ISSUE_RECORD_FILE)
    except Exception:
        issues = pd.DataFrame()

    if not issues.empty and "Status" in issues.columns:
        open_issues = issues[
            ~issues["Status"].astype(str).str.casefold().isin({"closed", "resolved"})
        ].copy()
        pending_verification = open_issues[
            open_issues["Status"].astype(str).str.casefold().eq("pending verification")
        ].copy()
    else:
        open_issues = pd.DataFrame()
        pending_verification = pd.DataFrame()

    plans = load_plan_records(PM_PLAN_FILE)
    current_month = date.today().strftime("%Y-%m")
    current_plan = (
        plans[plans["Plan Month"].astype(str).eq(current_month)].copy()
        if not plans.empty and "Plan Month" in plans.columns
        else pd.DataFrame()
    )
    if current_plan.empty:
        completed_count = 0
        outstanding_count = 0
    else:
        completed_mask = current_plan["Completed Date"].astype(str).str.strip().ne("")
        completed_count = int(completed_mask.sum())
        outstanding_count = int((~completed_mask).sum())

    return {
        "issues": issues,
        "open_issues": open_issues,
        "pending_verification": pending_verification,
        "current_plan": current_plan,
        "completed_count": completed_count,
        "outstanding_count": outstanding_count,
        "total_units": len(dataframe),
        "current_month": current_month,
    }


def _render_management_kpis(snapshot: dict[str, Any]) -> None:
    """Render four stable 2×2 summary cards without multiline button clipping."""
    cards = [
        {
            "label": "All AED Units",
            "value": snapshot["total_units"],
            "note": "Active units currently available in the unified Master data.",
            "button": "Open all units",
            "key": "management_open_all_units",
            "tone": "blue",
            "action": _open_master_table,
        },
        {
            "label": "PM Outstanding",
            "value": snapshot["outstanding_count"],
            "note": "Units still pending in the current monthly PM plan.",
            "button": "Open PM plan",
            "key": "management_open_pm",
            "tone": "amber",
            "action": lambda: st.session_state.__setitem__("page", "PM Planning"),
        },
        {
            "label": "Open Issues",
            "value": len(snapshot["open_issues"]),
            "note": "Unresolved operational risks that still require action.",
            "button": "Review open issues",
            "key": "management_open_issues",
            "tone": "coral",
            "action": lambda: st.session_state.__setitem__("page", "Issues"),
        },
        {
            "label": "Pending Verification",
            "value": len(snapshot["pending_verification"]),
            "note": "Submitted resolutions waiting for management verification.",
            "button": "Review verification",
            "key": "management_open_pending",
            "tone": "green",
            "action": lambda: st.session_state.__setitem__("page", "Issues"),
        },
    ]

    for row_start in (0, 2):
        columns = st.columns(2, gap="medium")
        for column, card in zip(columns, cards[row_start:row_start + 2]):
            with column:
                st.markdown(
                    f"""
                    <section class="management-kpi-card management-kpi-{card['tone']}">
                        <div class="management-kpi-label">{html_escape(str(card['label']))}</div>
                        <div class="management-kpi-value">{html_escape(str(card['value']))}</div>
                        <div class="management-kpi-note">{html_escape(str(card['note']))}</div>
                    </section>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(
                    card["button"],
                    width="stretch",
                    key=card["key"],
                    type="secondary",
                ):
                    card["action"]()
                    rerun_app()


def _render_attention_required(snapshot: dict[str, Any]) -> None:
    section_label("ATTENTION REQUIRED")
    open_issues = snapshot["open_issues"].copy()
    if open_issues.empty:
        st.success("No unresolved Issues require management attention.")
        return

    priority_order = {"Urgent": 0, "High": 1, "Medium": 2, "Low": 3}
    open_issues["_priority"] = open_issues.get(
        "Priority", pd.Series(index=open_issues.index, dtype=str)
    ).map(priority_order).fillna(9)
    open_issues["_reported"] = pd.to_datetime(
        open_issues.get("Reported At", ""),
        format="%d-%m-%Y %H:%M:%S",
        errors="coerce",
    )
    open_issues = open_issues.sort_values(
        ["_priority", "_reported"], ascending=[True, True]
    ).head(5)

    display = open_issues.reindex(
        columns=[
            "Priority",
            "Issue ID",
            "Serial Number",
            "Location",
            "Issue Type",
            "Status",
            "Due Date",
        ]
    ).copy()
    event = st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        height=min(250, 48 + 36 * len(display)),
        on_select="rerun",
        selection_mode="single-row",
        key="aed_management_attention_table",
    )
    selected_rows = _selection_rows(event)
    if selected_rows:
        selected_index = selected_rows[0]
        if 0 <= selected_index < len(open_issues):
            st.session_state["selected_issue_id"] = clean_text(
                open_issues.iloc[selected_index].get("Issue ID")
            )

    action_col, _ = st.columns([1.25, 4])
    with action_col:
        if st.button("Open Issue Management", width="stretch"):
            _navigate_management("Issues")


def _render_pm_progress(snapshot: dict[str, Any]) -> None:
    section_label("THIS MONTH PM PROGRESS")
    planned = len(snapshot["current_plan"])
    completed = snapshot["completed_count"]
    outstanding = snapshot["outstanding_count"]
    ratio = completed / planned if planned else 0.0

    with st.container(border=True):
        metric_col, progress_col, action_col = st.columns([1.15, 3.8, 1.15])
        with metric_col:
            st.metric("Completed", f"{completed} / {planned}")
        with progress_col:
            st.progress(ratio, text=f"{ratio:.0%} complete · {outstanding} outstanding")
            st.caption(
                "The progress bar uses the current month's saved PM plan. "
                "Planning details remain in PM Planning."
            )
        with action_col:
            if st.button("View PM Plan", width="stretch"):
                _navigate_management("PM Planning")


def _unit_profile_field_groups() -> list[tuple[str, list[str]]]:
    return [
        (
            "Basic Information",
            [
                "Serial Number",
                "Model",
                "Installation Date",
                "Installed Phase / Month",
                "PO Number",
                "Zone",
                "Repaired?",
            ],
        ),
        (
            "Location",
            [
                "Block / Locations",
                "Street Name",
                "Location",
                "Postal Code",
                "Level",
                "Lift Lobby",
                "OneMap Address",
                "Latitude",
                "Longitude",
                "Geocoding Status",
            ],
        ),
        (
            "Pads and Battery",
            [
                "Adult Pads Replacement Date",
                "Adult Pads Expiry Date",
                "Adult Pads Lot Number",
                "Pediatric Pads Replacement Date",
                "Pediatric Pads Expiry Date",
                "Pediatric Pads Lot Number",
                "Battery Replacement History",
                "Battery Expiry Date",
            ],
        ),
        (
            "PM and Service",
            [
                "PM Completed Date",
                "Next PM Date",
                "PM Interval Months",
                "Job Type",
                "Last Done By",
                "Service Report e-SR",
                "Patrol Schedule",
                "PM Schedule (H1)",
                "PM Schedule (H2)",
            ],
        ),
        ("Remarks", ["Remarks"]),
    ]


def _profile_value(master_row: pd.Series, field: str) -> str:
    return clean_text(master_row.get(field)) or "—"


def _build_profile_section_html(
    section_name: str,
    fields: list[str],
    master_row: pd.Series,
) -> str:
    """Build one uninterrupted HTML block so Markdown cannot expose raw tags."""
    field_cards: list[str] = []
    for field in fields:
        label = FIELD_LABELS.get(field, field)
        value = _profile_value(master_row, field)
        wide_class = " aed-profile-field-wide" if field == "Remarks" else ""
        field_cards.append(
            f'<div class="aed-profile-field{wide_class}">'
            f'<span>{html_escape(str(label))}</span>'
            f'<strong>{html_escape(str(value))}</strong>'
            '</div>'
        )

    return (
        '<section class="aed-profile-section-card">'
        f'<h4>{html_escape(section_name)}</h4>'
        f'<div class="aed-profile-fields-grid">{"".join(field_cards)}</div>'
        '</section>'
    )


def _render_profile_information(master_row: pd.Series) -> None:
    """Show every unit field in responsive cards with full text wrapping."""
    for section_name, fields in _unit_profile_field_groups():
        available = [field for field in fields if field in master_row.index]
        if not available:
            continue
        st.markdown(
            _build_profile_section_html(section_name, available, master_row),
            unsafe_allow_html=True,
        )


def _profile_review_table(changes: dict[str, str], originals: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Field": FIELD_LABELS.get(field, field),
                "Current": originals.get(field, ""),
                "New": value,
            }
            for field, value in changes.items()
        ]
    )


def _profile_operation_feedback(result: Any) -> None:
    if result.status == "conflict":
        st.error(result.message)
        rows = [
            {
                "Field": FIELD_LABELS.get(field, field),
                "Opened Value": values.get("original", ""),
                "Current Excel": values.get("current", ""),
                "Your Value": values.get("desired", ""),
            }
            for field, values in result.conflicts.items()
        ]
        if rows:
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    elif result.status in {"no_changes", "already_applied"}:
        st.info(result.message)
    elif result.excel_updated:
        st.warning(result.message)
    else:
        st.error(result.message)


def _profile_edit_pending_key(serial: str) -> str:
    return f"profile_edit_pending::{serial}"


def _service_add_pending_key(serial: str) -> str:
    return f"profile_service_pending::{serial}"


def _render_profile_edit(master_row: pd.Series, serial: str) -> None:
    """Edit the official IB List fields directly from the unit profile."""
    pending_key = _profile_edit_pending_key(serial)
    pending = st.session_state.get(pending_key)

    st.caption(
        "Edit the official unit record here. Changes are reviewed before they are "
        "written to the same OneDrive Excel file used by Master Table."
    )

    if pending:
        st.markdown("#### Review profile changes")
        st.dataframe(
            _profile_review_table(pending["changes"], pending["originals"]),
            width="stretch",
            hide_index=True,
        )
        for warning in pending.get("warnings", []):
            st.warning(warning)
        confirm_col, cancel_col, _ = st.columns([1.3, 1.1, 3])
        if confirm_col.button(
            "Confirm and update Excel",
            type="primary",
            width="stretch",
            key=f"profile_edit_confirm_{serial}",
        ):
            with st.spinner("Checking the latest OneDrive file and saving..."):
                result = update_unit(
                    serial_number=serial,
                    changes=pending["changes"],
                    original_values=pending["originals"],
                    user=st.session_state.get("audit_user", ""),
                    session_id=st.session_state.get("session_id", ""),
                    source_page="AED Management Unit Profile",
                )
            if result.success or result.status in {"already_applied", "no_changes"}:
                st.session_state.pop(pending_key, None)
                st.session_state["aed_writeback_notice"] = result.message
                st.session_state["aed_writeback_warnings"] = list(result.warnings)
                rerun_app()
            _profile_operation_feedback(result)
        if cancel_col.button(
            "Cancel",
            width="stretch",
            key=f"profile_edit_cancel_{serial}",
        ):
            st.session_state.pop(pending_key, None)
            rerun_app()
        return

    current = {
        field: _snapshot_value(field, master_row.get(field, ""))
        for field in DETAIL_EDITABLE_COLUMNS
    }

    with st.form(f"profile_edit_form_{serial}", clear_on_submit=False):
        with st.container(border=True):
            st.markdown("#### Basic and location information")
            c1, c2 = st.columns(2, gap="large")
            c1.text_input("Serial Number", value=serial, disabled=True)
            model = c2.text_input("Model / Related Object", value=current.get("Model", ""))
            installation = c1.date_input(
                "Installation Date",
                value=_date_input_value(current.get("Installation Date", "")),
                format="DD-MM-YYYY",
                min_value=MIN_DATE,
                max_value=MAX_DATE,
            )
            phase = c2.text_input(
                "Installed Phase / Month",
                value=current.get("Installed Phase / Month", ""),
            )
            po_number = c1.text_input("PO Number", value=current.get("PO Number", ""))
            zone = c2.text_input("Zone", value=current.get("Zone", ""))
            block = c1.text_input(
                "Block / Locations", value=current.get("Block / Locations", "")
            )
            street = c2.text_input("Street Name", value=current.get("Street Name", ""))
            postal = c1.text_input(
                "Postal Code", value=current.get("Postal Code", ""), max_chars=6
            )
            level = c2.text_input("Level", value=current.get("Level", ""))
            lobby = c1.text_input("Lift Lobby", value=current.get("Lift Lobby", ""))

        with st.container(border=True):
            st.markdown("#### Pads and battery")
            st.caption("Adult pads")
            c1, c2, c3 = st.columns(3, gap="small")
            adult_replacement = c1.date_input(
                "Replacement Date",
                value=_date_input_value(current.get("Adult Pads Replacement Date", "")),
                format="DD-MM-YYYY",
                min_value=MIN_DATE,
                max_value=MAX_DATE,
                key=f"profile_adult_replace_{serial}",
            )
            adult_expiry = c2.date_input(
                "Expiry Date",
                value=_date_input_value(current.get("Adult Pads Expiry Date", "")),
                format="DD-MM-YYYY",
                min_value=MIN_DATE,
                max_value=MAX_DATE,
                key=f"profile_adult_expiry_{serial}",
            )
            adult_lot = c3.text_input(
                "Lot Number",
                value=current.get("Adult Pads Lot Number", ""),
                key=f"profile_adult_lot_{serial}",
            )

            st.caption("Pediatric pads")
            c1, c2, c3 = st.columns(3, gap="small")
            pediatric_replacement = c1.date_input(
                "Replacement Date",
                value=_date_input_value(current.get("Pediatric Pads Replacement Date", "")),
                format="DD-MM-YYYY",
                min_value=MIN_DATE,
                max_value=MAX_DATE,
                key=f"profile_pedi_replace_{serial}",
            )
            pediatric_expiry = c2.date_input(
                "Expiry Date",
                value=_date_input_value(current.get("Pediatric Pads Expiry Date", "")),
                format="DD-MM-YYYY",
                min_value=MIN_DATE,
                max_value=MAX_DATE,
                key=f"profile_pedi_expiry_{serial}",
            )
            pediatric_lot = c3.text_input(
                "Lot Number",
                value=current.get("Pediatric Pads Lot Number", ""),
                key=f"profile_pedi_lot_{serial}",
            )

            c1, c2 = st.columns(2, gap="large")
            battery_expiry = c1.date_input(
                "Battery Expiry Date",
                value=_date_input_value(current.get("Battery Expiry Date", "")),
                format="DD-MM-YYYY",
                min_value=MIN_DATE,
                max_value=MAX_DATE,
            )
            battery_history = c2.text_area(
                "Battery Replacement History",
                value=current.get("Battery Replacement History", ""),
                height=96,
            )

        with st.container(border=True):
            st.markdown("#### PM and service")
            c1, c2 = st.columns(2, gap="large")
            completed = c1.date_input(
                "PM Completed Date",
                value=_date_input_value(current.get("PM Completed Date", "")),
                format="DD-MM-YYYY",
                min_value=MIN_DATE,
                max_value=MAX_DATE,
            )
            next_pm = c2.date_input(
                "Next PM Date",
                value=_date_input_value(current.get("Next PM Date", "")),
                format="DD-MM-YYYY",
                min_value=MIN_DATE,
                max_value=MAX_DATE,
            )
            job_options = _select_options_with_current(
                JOB_TYPE_OPTIONS, current.get("Job Type", "")
            )
            job_type = c1.selectbox(
                "Service Type",
                options=job_options,
                index=job_options.index(current.get("Job Type", "")),
            )
            last_done = c2.text_input(
                "Last Done By", value=current.get("Last Done By", "")
            )
            report = c1.text_input(
                "Service Report / e-SR",
                value=current.get("Service Report e-SR", ""),
            )
            repaired_options = _select_options_with_current(
                REPAIRED_OPTIONS, current.get("Repaired?", "")
            )
            repaired = c2.selectbox(
                "Repaired?",
                options=repaired_options,
                index=repaired_options.index(current.get("Repaired?", "")),
            )
            remarks = st.text_area(
                "Remarks",
                value=current.get("Remarks", ""),
                height=140,
                help="Existing service-history lines are preserved unless you edit them here.",
            )

        submitted = st.form_submit_button(
            "Review profile changes", type="primary", width="stretch"
        )

    if not submitted:
        return

    entered: dict[str, Any] = {
        "Installation Date": aed_service.format_date(installation),
        "Model": model,
        "Installed Phase / Month": phase,
        "PO Number": po_number,
        "Zone": zone,
        "Block / Locations": block,
        "Street Name": street,
        "Postal Code": postal,
        "Level": level,
        "Lift Lobby": lobby,
        "Adult Pads Replacement Date": aed_service.format_date(adult_replacement),
        "Adult Pads Expiry Date": aed_service.format_date(adult_expiry),
        "Adult Pads Lot Number": adult_lot,
        "Pediatric Pads Replacement Date": aed_service.format_date(pediatric_replacement),
        "Pediatric Pads Expiry Date": aed_service.format_date(pediatric_expiry),
        "Pediatric Pads Lot Number": pediatric_lot,
        "Battery Replacement History": battery_history,
        "Battery Expiry Date": aed_service.format_date(battery_expiry),
        "PM Completed Date": aed_service.format_date(completed),
        "Next PM Date": aed_service.format_date(next_pm),
        "Job Type": job_type,
        "Last Done By": last_done,
        "Service Report e-SR": report,
        "Repaired?": repaired,
        "Remarks": remarks,
    }

    changes: dict[str, str] = {}
    originals: dict[str, str] = {}
    try:
        for field, raw_value in entered.items():
            new_value = normalize_value(field, raw_value)
            old_value = current.get(field, "")
            if new_value != old_value:
                changes[field] = new_value
                originals[field] = old_value
    except ValueError as error:
        st.error(str(error))
        return

    if not changes:
        st.info("No changes were detected.")
        return

    change_rows = [
        {
            "serial_number": serial.upper(),
            "field": field,
            "original_value": originals[field],
            "desired_value": value,
        }
        for field, value in changes.items()
    ]
    errors, warnings = validate_table_changes(
        pd.DataFrame([master_row.to_dict()]), change_rows
    )
    if errors:
        for error in errors:
            st.error(error)
        return

    st.session_state[pending_key] = {
        "changes": changes,
        "originals": originals,
        "warnings": warnings,
    }
    rerun_app()


def _render_add_service_record(master_row: pd.Series, serial: str) -> None:
    """Add a durable service-history entry through the unit profile."""
    pending_key = _service_add_pending_key(serial)
    pending = st.session_state.get(pending_key)

    st.caption(
        "Add an individual service event without opening the full PM checklist. "
        "The event is saved as its own structured record, appears in Service History "
        "and Service Records, and does not rewrite the company's existing Remarks."
    )

    if pending:
        record = pending["record"]
        with st.container(border=True):
            st.markdown("#### Review new service record")
            summary = st.columns(3, gap="small")
            summary[0].metric("Date", record["Service Date"])
            summary[1].metric("Service Type", record["Service Type"])
            summary[2].metric("Status", record["Status"])
            st.caption(
                f"Technician: {record['Technician'] or '—'} · "
                f"Reference: {record['Reference'] or '—'} · "
                f"Record ID: {record['Service Record ID']}"
            )
            st.write(record["Details"] or "No additional details.")
            if record.get("PM Interval Months Used"):
                st.caption(
                    "PM interval used: "
                    f"{record['PM Interval Months Used']} month(s). "
                    "A matching PM plan in the same month will be completed when available."
                )
            if record.get("Battery Replaced") == "Yes":
                st.caption(
                    "This completed battery service will also update Battery Replacement History."
                )

        if pending["changes"]:
            st.markdown("**IB List fields that will also be updated**")
            st.dataframe(
                _profile_review_table(pending["changes"], pending["originals"]),
                width="stretch",
                hide_index=True,
            )
        else:
            st.info(
                "This service record will be saved without changing the current IB List values."
            )

        confirm_col, cancel_col, _ = st.columns([1.35, 1, 3])
        if confirm_col.button(
            "Confirm add record",
            type="primary",
            width="stretch",
            key=f"profile_service_confirm_{serial}",
        ):
            result = None
            if pending["changes"]:
                with st.spinner("Checking and updating the latest OneDrive Excel..."):
                    result = update_unit(
                        serial_number=serial,
                        changes=pending["changes"],
                        original_values=pending["originals"],
                        user=st.session_state.get("audit_user", ""),
                        session_id=st.session_state.get("session_id", ""),
                        source_page="AED Management Add Service Record",
                    )
                if not result.success and result.status not in {"no_changes", "already_applied"}:
                    _profile_operation_feedback(result)
                    return

            excel_values_confirmed = bool(
                pending["changes"]
                and result is not None
                and (result.success or result.status == "already_applied")
            )
            linked_plan_id = ""
            if pending.get("complete_pm_plan"):
                linked_plan_id = complete_matching_pm_plan(
                    serial,
                    record["Service Date"],
                    operation_id=(
                        clean_text(getattr(result, "operation_id", ""))
                        if result is not None
                        else ""
                    ),
                    response_id=record["Service Record ID"],
                    completed_by=st.session_state.get("audit_user", ""),
                    plan_file=PM_PLAN_FILE,
                )

            durable_record = {
                **record,
                "AED Serial Number": serial,
                "Created By": st.session_state.get("audit_user", ""),
                "Master Data Updated": "Yes" if excel_values_confirmed else "No",
                "PM Dates Updated": (
                    "Yes"
                    if excel_values_confirmed and bool(pending.get("pm_fields_changed"))
                    else "No"
                ),
                "Battery History Updated": (
                    "Yes"
                    if excel_values_confirmed and pending.get("battery_history_changed")
                    else "No"
                ),
                "Linked Plan ID": linked_plan_id,
                "Master Operation ID": (
                    clean_text(getattr(result, "operation_id", ""))
                    if result is not None
                    else ""
                ),
                "Source": "Unit Profile",
            }
            try:
                saved = append_manual_service_record(
                    durable_record,
                    path=MANUAL_SERVICE_RECORDS_FILE,
                )
            except Exception as error:
                st.error(
                    "The Excel update was safe, but the service record could not be saved: "
                    f"{error}"
                )
                return

            st.session_state.pop(pending_key, None)
            message = f"Service record {saved['Service Record ID']} was saved."
            if result is not None and result.message:
                message += f" {result.message}"
            if linked_plan_id:
                message += f" PM plan {linked_plan_id} was marked Completed."
            elif pending.get("complete_pm_plan"):
                message += " No pending PM plan was found for the same unit and month."
            st.session_state["aed_writeback_notice"] = message
            st.session_state["aed_writeback_warnings"] = (
                list(result.warnings) if result is not None else []
            )
            rerun_app()
        if cancel_col.button(
            "Cancel",
            width="stretch",
            key=f"profile_service_cancel_{serial}",
        ):
            st.session_state.pop(pending_key, None)
            rerun_app()
        return

    service_options = [option for option in JOB_TYPE_OPTIONS if clean_text(option)]
    default_technician = clean_text(st.session_state.get("audit_user"))
    default_interval = clean_text(master_row.get("PM Interval Months"))
    try:
        interval_value = max(1, int(default_interval or 12))
    except ValueError:
        interval_value = 12

    with st.form(f"profile_add_service_form_{serial}", clear_on_submit=False):
        with st.container(border=True):
            st.markdown("#### Service details")
            c1, c2 = st.columns(2, gap="large")
            service_date = c1.date_input(
                "Service Date", value=date.today(), format="DD-MM-YYYY"
            )
            service_type = c2.selectbox("Service Type", options=service_options)
            technician = c1.text_input("Technician*", value=default_technician)
            reference = c2.text_input(
                "Service Report / e-SR",
                placeholder="Optional reference number",
                help=(
                    "Leaving this blank keeps the existing e-SR in the IB List; "
                    "it will not erase it."
                ),
            )
            status = c1.selectbox(
                "Record Status",
                options=["Completed", "Pending", "Follow-up Required"],
            )
            update_latest = c2.checkbox(
                "Update latest service fields",
                value=True,
                help=(
                    "Updates Service Type and Technician in the IB List. e-SR is "
                    "updated only when a value is entered."
                ),
            )
            update_pm_dates = c1.checkbox(
                "Update PM Completed and Next PM dates",
                value=False,
                help=(
                    "Use this only for a completed PM. A matching same-month PM "
                    "plan will also be marked Completed."
                ),
            )
            interval_months = c2.number_input(
                "Next PM interval (months)",
                min_value=1,
                max_value=60,
                value=interval_value,
                step=1,
            )
            details = st.text_area(
                "Work performed / notes*",
                placeholder=(
                    "Describe the service, replacement, test result or follow-up needed."
                ),
                height=140,
            )

        submitted = st.form_submit_button(
            "Review new service record", type="primary", width="stretch"
        )

    if not submitted:
        return
    if not clean_text(technician):
        st.error("Technician is required.")
        return
    if not clean_text(details):
        st.error("Work performed / notes is required.")
        return

    try:
        update_plan = build_manual_service_update_plan(
            master_row,
            service_date=service_date,
            service_type=service_type,
            technician=technician,
            reference=reference,
            status=status,
            update_latest=update_latest,
            update_pm_dates=update_pm_dates,
            interval_months=int(interval_months),
        )
    except ValueError as error:
        st.error(str(error))
        return

    st.session_state[pending_key] = {
        "record": {
            "Service Record ID": generate_manual_service_record_id(),
            "AED Model": clean_text(master_row.get("Model", "")),
            "AED Location": clean_text(master_row.get("Location", ""))
            or clean_text(master_row.get("Block / Locations", "")),
            "Postal Code": clean_text(master_row.get("Postal Code", "")),
            "Lift Lobby": clean_text(master_row.get("Lift Lobby", "")),
            "Service Date": update_plan["service_date_text"],
            "Service Type": clean_text(service_type),
            "Technician": clean_text(technician),
            "Reference": clean_text(reference),
            "Status": clean_text(status),
            "Details": clean_text(details),
            "Battery Replaced": "Yes" if update_plan["battery_replaced"] else "No",
            "PM Interval Months Used": update_plan["interval_months_used"],
        },
        "changes": update_plan["changes"],
        "originals": update_plan["originals"],
        "master_fields_changed": update_plan["master_fields_changed"],
        "pm_fields_changed": update_plan["pm_fields_changed"],
        "battery_history_changed": update_plan["battery_history_changed"],
        "complete_pm_plan": update_plan["complete_pm_plan"],
    }
    rerun_app()

def _render_service_history(master_row: pd.Series, serial: str) -> None:
    history = build_service_history(
        master_row,
        serial,
        pm_responses_file=PM_RESPONSES_FILE,
        issue_record_file=ISSUE_RECORD_FILE,
        resolution_file=ISSUE_RESOLUTION_FILE,
        manual_service_file=MANUAL_SERVICE_RECORDS_FILE,
    )
    if history.empty:
        st.info(
            "No service record has been saved for this unit yet. Use Add Service "
            "to create the first record."
        )
        return

    st.caption(
        "Newest first. Records combine PM checklists, issue resolutions, current IB "
        "List fields, older Remarks and records added directly from this profile."
    )
    for row_index, (_, row) in enumerate(history.head(20).iterrows()):
        with st.container(border=True):
            top = st.columns([1.1, 1.8, 1.1], gap="small")
            top[0].markdown(f"**{clean_text(row.get('Service Date')) or 'Date not recorded'}**")
            top[1].markdown(f"**{clean_text(row.get('Service Type')) or 'Service'}**")
            top[2].caption(clean_text(row.get("Status")) or "Recorded")
            meta = []
            if clean_text(row.get("Technician")):
                meta.append(f"Technician: {clean_text(row.get('Technician'))}")
            if clean_text(row.get("Reference")):
                meta.append(f"Reference: {clean_text(row.get('Reference'))}")
            if clean_text(row.get("Source")):
                meta.append(f"Source: {clean_text(row.get('Source'))}")
            if meta:
                st.caption(" · ".join(meta))
            if clean_text(row.get("Details")):
                st.write(clean_text(row.get("Details")))

    if len(history) > 20:
        st.caption(f"Showing the newest 20 of {len(history)} records.")
    with st.expander("Open service history as a table"):
        st.dataframe(history, width="stretch", hide_index=True)


def _render_issue_history(serial: str) -> None:
    issues = load_unit_issues(serial, issue_record_file=ISSUE_RECORD_FILE)
    if issues.empty:
        st.success("No Issue record has been linked to this unit.")
        return

    display_columns = [
        "Issue ID",
        "Reported At",
        "Source",
        "Source Record ID",
        "Source Field",
        "Is Loaner",
        "Issue Type",
        "Priority",
        "Status",
        "Current Assignee",
        "Resolution Submitted At",
        "Closed At",
        "Resolution Notes",
    ]
    display_columns = [column for column in display_columns if column in issues.columns]
    st.dataframe(
        issues.reindex(columns=display_columns),
        hide_index=True,
        width="stretch",
        height=min(480, 48 + 37 * len(issues)),
        key=f"unit_issue_history_{serial}",
    )
    if st.button(
        "Open Issue Management",
        width="content",
        key=f"profile_open_issues_{serial}",
    ):
        _navigate_management("Issues")


def _render_profile_overview(
    master_row: pd.Series,
    serial: str,
    issues: pd.DataFrame,
) -> None:
    """Render the clean electronic-record overview with responsive detail cards."""
    open_count = 0
    issue_status_rows = ""
    if not issues.empty and "Status" in issues.columns:
        status_counts = issues["Status"].astype(str).replace("", "Unknown").value_counts()
        open_count = int(
            (~issues["Status"].astype(str).str.casefold().isin({"closed", "resolved"})).sum()
        )
        issue_status_rows = "".join(
            f'<div class="aed-snapshot-row"><span>{html_escape(str(status))}</span><strong>{int(count)}</strong></div>'
            for status, count in status_counts.items()
        )
    else:
        issue_status_rows = (
            '<div class="aed-profile-empty-state">No Issue has been linked to this AED.</div>'
        )

    pm_rows = [
        ("Last PM", _profile_value(master_row, "PM Completed Date")),
        ("Next PM", _profile_value(master_row, "Next PM Date")),
        ("Service Type", _profile_value(master_row, "Job Type")),
        ("Technician", _profile_value(master_row, "Last Done By")),
        ("Service Report", _profile_value(master_row, "Service Report e-SR")),
    ]
    pm_html = "".join(
        f'<div class="aed-snapshot-row"><span>{html_escape(label)}</span><strong>{html_escape(str(value))}</strong></div>'
        for label, value in pm_rows
    )

    pm_col, issue_col = st.columns(2, gap="medium")
    with pm_col:
        st.markdown(
            f"""
            <section class="aed-profile-overview-card">
                <div class="aed-profile-card-title">PM &amp; Service Snapshot</div>
                <div class="aed-snapshot-list">{pm_html}</div>
            </section>
            """,
            unsafe_allow_html=True,
        )
    with issue_col:
        st.markdown(
            f"""
            <section class="aed-profile-overview-card">
                <div class="aed-profile-card-title">Issue Summary</div>
                <div class="aed-issue-count-grid">
                    <div><span>All Issues</span><strong>{len(issues)}</strong></div>
                    <div><span>Open</span><strong>{open_count}</strong></div>
                </div>
                <div class="aed-snapshot-list">{issue_status_rows}</div>
            </section>
            """,
            unsafe_allow_html=True,
        )

    _render_profile_information(master_row)

    history = build_service_history(
        master_row,
        serial,
        pm_responses_file=PM_RESPONSES_FILE,
        issue_record_file=ISSUE_RECORD_FILE,
        resolution_file=ISSUE_RESOLUTION_FILE,
        manual_service_file=MANUAL_SERVICE_RECORDS_FILE,
    )
    st.markdown("#### Recent Activity")
    if history.empty:
        st.info("No service activity has been recorded for this AED yet.")
    else:
        recent_columns = [
            column
            for column in [
                "Service Date",
                "Service Type",
                "Technician",
                "Reference",
                "Source",
                "Status",
            ]
            if column in history.columns
        ]
        st.dataframe(
            history.reindex(columns=recent_columns).head(5),
            hide_index=True,
            width="stretch",
        )


def _render_unit_profile(master_row: pd.Series, marker_text: str) -> None:
    """Render the responsive electronic profile without clipped cards or labels."""
    serial = clean_text(master_row.get("Serial Number"))
    if not serial:
        return

    model = clean_text(master_row.get("Model")) or "Model not recorded"
    location = clean_text(master_row.get("Location")) or clean_text(
        master_row.get("Block / Locations")
    )
    postal = clean_text(master_row.get("Postal Code")) or "—"
    service_type = clean_text(master_row.get("Job Type")) or "—"
    next_pm = clean_text(master_row.get("Next PM Date")) or "—"
    issues = load_unit_issues(serial, issue_record_file=ISSUE_RECORD_FILE)
    open_issue_count = 0
    if not issues.empty and "Status" in issues.columns:
        open_issue_count = int(
            (~issues["Status"].astype(str).str.casefold().isin({"closed", "resolved"})).sum()
        )

    section_key = f"profile_section_{serial}"
    st.session_state.setdefault(section_key, "Overview")

    st.markdown('<div class="aed-profile-top-gap"></div>', unsafe_allow_html=True)
    with st.container(border=True):
        identity_col, action_col = st.columns([3.4, 1.35], gap="large")
        with identity_col:
            stat_items = [
                ("Unit Status", marker_text or "Pending"),
                ("Service Type", service_type),
                ("Next PM", next_pm),
                ("Open Issues", str(open_issue_count)),
            ]
            stat_html = "".join(
                f"""
                <div class="aed-profile-stat">
                    <span>{html_escape(label)}</span>
                    <strong>{html_escape(str(value))}</strong>
                </div>
                """
                for label, value in stat_items
            )
            st.markdown(
                f"""
                <section class="aed-profile-identity">
                    <div class="aed-profile-eyebrow">AED UNIT PROFILE</div>
                    <h2>{html_escape(serial)}</h2>
                    <div class="aed-profile-model">{html_escape(model)}</div>
                    <div class="aed-profile-location">{html_escape(location or 'Location not recorded')}</div>
                    <div class="aed-profile-postal">Postal Code · {html_escape(postal)}</div>
                    <div class="aed-profile-stat-grid">{stat_html}</div>
                </section>
                """,
                unsafe_allow_html=True,
            )
        with action_col:
            st.markdown(
                '<div class="aed-profile-actions-title">PRIMARY ACTIONS</div>',
                unsafe_allow_html=True,
            )
            if st.button(
                "Edit Details",
                type="primary",
                width="stretch",
                key=f"profile_edit_shortcut_{serial}",
            ):
                st.session_state[section_key] = "Edit Details"
                rerun_app()
            if st.button(
                "Add Service",
                width="stretch",
                key=f"profile_add_service_shortcut_{serial}",
            ):
                st.session_state[section_key] = "Add Service"
                rerun_app()
            if st.button(
                "Report Issue",
                width="stretch",
                key=f"profile_issue_{serial}",
            ):
                st.session_state["map_report_target"] = {
                    "Serial Number": serial,
                    "Postal Code": clean_text(master_row.get("Postal Code")),
                }
                _navigate_management("Report Issue")

        st.markdown(
            '<div class="aed-profile-actions-title aed-profile-actions-title-spaced">QUICK ACTIONS</div>',
            unsafe_allow_html=True,
        )
        quick_row_one = st.columns(2, gap="small")
        quick_row_two = st.columns(2, gap="small")
        if quick_row_one[0].button(
            "Fill PM Checklist", width="stretch", key=f"profile_pm_{serial}"
        ):
            st.session_state["map_pm_target"] = {
                "Serial Number": serial,
                "Postal Code": clean_text(master_row.get("Postal Code")),
            }
            _navigate_management("PM Checklist")
        if quick_row_one[1].button(
            "Open in Table Edit", width="stretch", key=f"profile_master_{serial}"
        ):
            _open_master_table(serial)
            rerun_app()
        if quick_row_two[0].button(
            "View Service Records", width="stretch", key=f"profile_records_{serial}"
        ):
            st.session_state["service_records_keyword"] = serial
            _navigate_management("Service Records")
        if quick_row_two[1].button(
            "Open AED Map", width="stretch", key=f"profile_map_{serial}"
        ):
            st.session_state["map_focus_serial"] = serial
            _navigate_management("AED Map")

        st.markdown('<div class="aed-profile-tab-divider"></div>', unsafe_allow_html=True)
        section = st.segmented_control(
            "Unit profile section",
            options=[
                "Overview",
                "Edit Details",
                "Service History",
                "Add Service",
                "Issues",
            ],
            label_visibility="collapsed",
            key=section_key,
        ) or "Overview"

        if section == "Overview":
            _render_profile_overview(master_row, serial, issues)
        elif section == "Edit Details":
            _render_profile_edit(master_row, serial)
        elif section == "Service History":
            _render_service_history(master_row, serial)
        elif section == "Add Service":
            _render_add_service_record(master_row, serial)
        else:
            _render_issue_history(serial)


def _render_writeback_messages() -> None:
    writeback_notice = st.session_state.pop("aed_writeback_notice", "")
    if writeback_notice:
        st.success(writeback_notice)
    for warning in st.session_state.pop("aed_writeback_warnings", []):
        st.warning(warning)


def _load_management_dataframe() -> pd.DataFrame | None:
    try:
        return get_all_units()
    except Exception as error:
        st.error(f"Failed to load AED data: {error}")
        return None


def _profile_selector_label(row: pd.Series) -> str:
    serial = clean_text(row.get("Serial Number"))
    model = clean_text(row.get("Model"))
    location = clean_text(row.get("Location")) or clean_text(row.get("Block / Locations"))
    postal = clean_text(row.get("Postal Code"))
    detail = " · ".join(value for value in [model, location, postal] if value)
    return f"{serial} — {detail}" if detail else serial


def render_dashboard_unit_profiles(
    dataframe: pd.DataFrame,
    *,
    keyword: str = "",
    show_search: bool = False,
    context_key: str = "dashboard",
) -> None:
    """Clean, direct unit-profile workspace used by both main home pages."""
    section_label("AED UNIT PROFILES")
    st.caption(
        "Search and select one AED. Its full electronic profile opens immediately below, "
        "including direct editing, service history, Add Service and Issue history."
    )

    search_key = f"{context_key}_unit_profile_search"
    selector_key = f"{context_key}_unit_profile_selector"
    selected_key = f"{context_key}_profile_serial"

    effective_keyword = clean_text(keyword)
    if show_search:
        effective_keyword = st.text_input(
            "Search AED unit",
            value=clean_text(st.session_state.get(search_key, "")),
            placeholder="Search Serial Number, model, location, street or postal code",
            key=search_key,
        )

    filtered = filter_unit_profiles(dataframe, effective_keyword)
    if filtered.empty:
        st.info("No AED unit matches the current search.")
        return

    options = filtered["Serial Number"].astype(str).tolist()
    label_lookup = {
        clean_text(row.get("Serial Number")): _profile_selector_label(row)
        for _, row in filtered.iterrows()
    }

    selected_serial = clean_text(st.session_state.get(selected_key))
    if selected_serial not in options:
        selected_serial = ""
    if clean_text(st.session_state.get(selector_key)) not in options:
        st.session_state.pop(selector_key, None)

    select_col, master_col = st.columns([5.2, 1.25], gap="small")
    with select_col:
        selected = st.selectbox(
            "Select AED unit",
            options=options,
            index=options.index(selected_serial) if selected_serial in options else None,
            format_func=lambda serial: label_lookup.get(serial, serial),
            placeholder="Choose one of the matching AED units",
            key=selector_key,
        )
    with master_col:
        st.markdown("<div style='height:1.72rem'></div>", unsafe_allow_html=True)
        if st.button(
            "Open Table Edit",
            width="stretch",
            key=f"{context_key}_profiles_open_master",
        ):
            _open_master_table()
            rerun_app()

    if not selected:
        st.info("Select one AED above to open its profile.")
        return

    selected_serial = clean_text(selected)
    st.session_state[selected_key] = selected_serial
    master_matches = dataframe[
        dataframe["Serial Number"].astype(str).str.strip().eq(selected_serial)
    ]
    if master_matches.empty:
        st.warning("The selected AED is no longer available in the current Master data.")
        return

    state = load_unit_state(MAP_UNIT_STATE_FILE)
    definitions = load_status_definitions(MAP_STATUS_FILE)
    marker_text = "Pending"
    if not state.empty:
        state_match = state[
            state["Serial Number"].astype(str).str.strip().eq(selected_serial)
        ]
        if not state_match.empty:
            state_row = state_match.iloc[0]
            override = clean_text(state_row.get("Color Override")).title()
            status = clean_text(state_row.get("Status"))
            colour_lookup = status_color_lookup(definitions)
            colour = override or colour_lookup.get(status.casefold(), "Gray")
            marker_text = f"{COLOR_EMOJI.get(colour, '●')} {override or status or 'Pending'}"

    _render_unit_profile(master_matches.iloc[0], marker_text)

def _render_unified_directory(
    dataframe: pd.DataFrame,
    history_file: str | Path,
) -> None:
    """Render one full-width search/filter/table workspace."""
    section_label("AED DIRECTORY")
    st.caption(
        "Use the single search and linked filters below. Browse Units opens a profile "
        "by row click; Direct Edit keeps the complete Master Table workflow."
    )

    filters = render_filters(dataframe)
    filtered = aed_service.apply_filters(
        dataframe=dataframe,
        keyword=filters["keyword"],
        model=filters["model"],
        location=filters["location"],
        postal_code=filters["postal_code"],
        lift_lobby=filters["lift_lobby"],
        job_type=filters["job_type"],
        last_done_by=filters["last_done_by"],
        date_ranges=filters["date_ranges"],
        sort_by=filters["sort_by"],
        ascending=filters["ascending"],
    )

    mode_col, count_col = st.columns([2.2, 1], gap="medium")
    with mode_col:
        mode = st.segmented_control(
            "Table mode",
            options=["Browse Units", "Direct Edit"],
            key="management_table_mode",
            label_visibility="collapsed",
        ) or "Browse Units"
    with count_col:
        st.markdown(
            f"""
            <div class="aed-directory-count">
                <span>Matching units</span>
                <strong>{len(filtered)} / {len(dataframe)}</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if mode == "Browse Units":
        st.info("Click any AED row to open its complete electronic profile.")
        render_selectable_browse_table(filtered)
    else:
        st.info("Edit the filtered results, then review every change before writing to Excel.")
        render_browse_table(filtered)
        with st.expander("Full Details Editor", expanded=False):
            render_full_details_editor(filtered)
        with st.expander("Add or Deactivate AED", expanded=False):
            render_add_and_deactivate(dataframe)
        with st.expander("Audit and Change History", expanded=False):
            render_audit_log(history_file)


def _render_selected_management_profile(dataframe: pd.DataFrame) -> None:
    serial = clean_text(st.session_state.get("management_profile_serial"))
    if not serial:
        st.session_state["aed_management_view"] = "list"
        rerun_app()
        return

    top_col, _ = st.columns([1.3, 5])
    if top_col.button("← Back to AED list", width="stretch"):
        st.session_state["aed_management_view"] = "list"
        st.session_state["management_browse_table_nonce"] = (
            int(st.session_state.get("management_browse_table_nonce", 0)) + 1
        )
        rerun_app()

    matches = dataframe[
        dataframe["Serial Number"].astype(str).str.strip().eq(serial)
    ]
    if matches.empty:
        st.warning("This AED is no longer available in the current Master data.")
        st.session_state["aed_management_view"] = "list"
        st.session_state["management_profile_serial"] = ""
        return

    state = load_unit_state(MAP_UNIT_STATE_FILE)
    definitions = load_status_definitions(MAP_STATUS_FILE)
    marker_text = "Pending"
    if not state.empty:
        state_match = state[
            state["Serial Number"].astype(str).str.strip().eq(serial)
        ]
        if not state_match.empty:
            state_row = state_match.iloc[0]
            override = clean_text(state_row.get("Color Override")).title()
            status = clean_text(state_row.get("Status"))
            colour = override or status_color_lookup(definitions).get(
                status.casefold(), "Gray"
            )
            marker_text = (
                f"{COLOR_EMOJI.get(colour, '●')} {override or status or 'Pending'}"
            )
    _render_unit_profile(matches.iloc[0], marker_text)


def render_aed_management(
    aed_data_file: str | Path,
    history_file: str | Path,
) -> None:
    """Unified Management, Master Table and clickable Unit Profile workspace."""
    del aed_data_file
    initialise_table_editor_state()
    initialise_management_workspace_state()

    page_header(
        "AED Management",
        "One search, one linked-filter set and one AED table for overview, direct editing and complete unit profiles.",
        eyebrow="ASSET CONTROL · UNIFIED AED WORKSPACE",
        chip="SEARCH · TABLE · PROFILE",
        capabilities=[
            ("Browse and open", "Click any filtered AED row to open its electronic profile."),
            ("Direct edit", "Use the same filtered results for reviewed multi-row Excel updates."),
            ("Full traceability", "Service, Issue and audit records stay connected to the unit."),
        ],
    )
    _render_writeback_messages()

    mode = st.session_state.aed_editor_mode
    if mode == "edit":
        render_edit_mode()
        return
    if mode == "review":
        render_review_mode()
        return
    if mode != "browse":
        clear_table_editor_state()
        st.error("Unknown editor state. The page was reset.")
        return

    dataframe = _load_management_dataframe()
    if dataframe is None:
        return

    if st.session_state.get("aed_management_view") == "profile":
        _render_selected_management_profile(dataframe)
        return

    snapshot = _management_snapshot(dataframe)
    _render_management_kpis(snapshot)
    with st.expander("Management overview · attention and PM progress", expanded=False):
        overview_left, overview_right = st.columns([1.45, 1], gap="large")
        with overview_left:
            _render_attention_required(snapshot)
        with overview_right:
            _render_pm_progress(snapshot)

    _render_unified_directory(dataframe, history_file)


def render_aed_master_table(
    aed_data_file: str | Path,
    history_file: str | Path,
) -> None:
    """Backward-compatible route into AED Management Direct Edit mode."""
    del aed_data_file, history_file
    initialise_management_workspace_state()
    st.session_state["management_table_mode"] = "Direct Edit"
    st.session_state["aed_management_view"] = "list"
    st.session_state["page"] = "AED Management"
    rerun_app()

