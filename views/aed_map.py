from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from services.aed_repository import get_all_units
from ui.components import page_header
from utils.streamlit_utils import rerun_app
from utils.text_utils import clean_text

from views.map_modules.detail_panel import render_selected_aed_panel
from views.map_modules.filters import (
    MAP_FILTER_KEYS,
    _map_filter_selections_from_state,
    _mark_map_filter_changed,
    _normalise_map_filter_state,
    apply_status_filter,
    filter_without_status,
    linked_map_filter_options,
    reset_aed_map_filters,
)
from views.map_modules.helpers import safe_html
from views.map_modules.renderer import create_map, render_folium
from views.map_modules.status_service import (
    COLOR_EMOJI,
    COLOR_PALETTE,
    active_statuses,
    apply_status_renames,
    ensure_all_units_have_state,
    load_plan_records,
    load_status_definitions,
    load_unit_state,
    safe_int,
    save_plan_records,
    save_status_definitions,
    save_unit_state,
    validate_and_prepare_status_editor,
)
from views.map_modules.styles import apply_map_page_styles


# ---------------------------------------------------------------------------
# Files and columns
# ---------------------------------------------------------------------------

REQUIRED_AED_COLUMNS = {
    "Serial Number",
    "Location",
    "Postal Code",
    "Latitude",
    "Longitude",
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Page styling
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# AED and monthly plan loading
# ---------------------------------------------------------------------------

def load_aed_data(aed_csv_file: str | Path | None = None) -> pd.DataFrame:
    """Load AED master data through the shared repository."""

    del aed_csv_file  # The repository owns the configured source path.
    dataframe = get_all_units()

    missing = REQUIRED_AED_COLUMNS - set(dataframe.columns)
    if missing:
        raise ValueError(
            "AED master data is missing: " + ", ".join(sorted(missing))
        )

    dataframe = dataframe.copy()
    dataframe["Latitude"] = pd.to_numeric(
        dataframe["Latitude"], errors="coerce"
    )
    dataframe["Longitude"] = pd.to_numeric(
        dataframe["Longitude"], errors="coerce"
    )
    return dataframe


# ---------------------------------------------------------------------------
# Custom status definitions
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# All Units Map state
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Status editor
# ---------------------------------------------------------------------------


def render_status_editor_contents(
    status_file: str | Path,
    state_file: str | Path,
    plan_file: str | Path,
) -> None:
    definitions = load_status_definitions(status_file)
    unit_state = load_unit_state(state_file)
    plan_records = load_plan_records(plan_file)

    st.caption(
        "Add, rename, reorder or disable statuses and choose from the expanded colour palette. "
        "Pending, Completed, Issue and Pending Verification workflow roles remain protected."
    )

    editor_dataframe = definitions.copy()
    editor_dataframe["Active"] = (
        editor_dataframe["Active"]
        .str.casefold()
        .eq("yes")
    )
    editor_dataframe["Display Order"] = editor_dataframe[
        "Display Order"
    ].map(lambda value: safe_int(value, 999))

    edited = st.data_editor(
        editor_dataframe,
        width="stretch",
        hide_index=True,
        num_rows="dynamic",
        key="aed_map_status_editor",
        column_config={
            "Status ID": None,
            "Status Name": st.column_config.TextColumn(
                "Status Name",
                required=True,
            ),
            "Marker Color": st.column_config.SelectboxColumn(
                "Color",
                options=list(COLOR_PALETTE),
                required=True,
            ),
            "Active": st.column_config.CheckboxColumn(
                "Active",
                default=True,
            ),
            "Display Order": st.column_config.NumberColumn(
                "Order",
                min_value=1,
                step=1,
                required=True,
            ),
            "Workflow Role": st.column_config.SelectboxColumn(
                "Workflow Role",
                options=[
                    "None",
                    "Pending",
                    "Completed",
                    "Issue",
                    "Pending Verification",
                    "Out of Service",
                ],
                required=True,
            ),
        },
    )

    st.markdown(
        '<div class="status-editor-note">'
        "Order controls the status cards from left to right. "
        "A status already used by a unit cannot be deleted or disabled."
        "</div>",
        unsafe_allow_html=True,
    )

    cancel_column, save_column = st.columns([1, 1])

    with cancel_column:
        if st.button(
            "Cancel",
            width="stretch",
            key="cancel_status_editor",
        ):
            rerun_app()

    with save_column:
        if st.button(
            "Save Status Settings",
            type="primary",
            width="stretch",
            key="save_status_editor",
        ):
            try:
                prepared, rename_map = (
                    validate_and_prepare_status_editor(
                        original=definitions,
                        edited=edited,
                        unit_state=unit_state,
                        plan_records=plan_records,
                    )
                )

                updated_state, updated_plans = apply_status_renames(
                    unit_state=unit_state,
                    plan_records=plan_records,
                    rename_map=rename_map,
                )

                save_status_definitions(
                    prepared,
                    status_file,
                )
                save_unit_state(
                    updated_state,
                    state_file,
                )
                save_plan_records(
                    updated_plans,
                    plan_file,
                )

                st.session_state[
                    "aed_map_notice"
                ] = "Status settings saved."
                rerun_app()

            except (ValueError, OSError) as error:
                st.error(str(error))


if hasattr(st, "dialog"):
    @st.dialog("Manage Statuses", width="large")
    def open_status_dialog(
        status_file: str | Path,
        state_file: str | Path,
        plan_file: str | Path,
    ) -> None:
        render_status_editor_contents(
            status_file=status_file,
            state_file=state_file,
            plan_file=plan_file,
        )
else:
    def open_status_dialog(
        status_file: str | Path,
        state_file: str | Path,
        plan_file: str | Path,
    ) -> None:
        st.session_state[
            "show_inline_status_editor"
        ] = True


# ---------------------------------------------------------------------------
# Building the two map datasets
# ---------------------------------------------------------------------------

def build_all_units_map_data(
    aed_dataframe: pd.DataFrame,
    state_dataframe: pd.DataFrame,
) -> pd.DataFrame:
    working = aed_dataframe.copy()

    state = state_dataframe.rename(
        columns={
            "Status": "PM Status",
        }
    )

    working = working.merge(
        state[
            [
                "Serial Number",
                "PM Status",
                "Color Override",
            ]
        ],
        on="Serial Number",
        how="left",
    )

    working["Plan ID"] = "ALL"
    working["Plan Month"] = ""
    working["Planned Date"] = ""
    working["Completed Date"] = ""
    working["Assigned To"] = working.get(
        "Last Done By",
        "",
    )
    working["Is Loaner"] = "No"

    return working


def build_monthly_map_data(
    aed_dataframe: pd.DataFrame,
    plan_dataframe: pd.DataFrame,
    plan_id: str,
) -> pd.DataFrame:
    selected_plan = plan_dataframe[
        plan_dataframe["Plan ID"].eq(plan_id)
    ].copy()

    if selected_plan.empty:
        return pd.DataFrame()

    current_columns = [
        column
        for column in [
            "Serial Number",
            "Model",
            "Location",
            "Postal Code",
            "Lift Lobby",
            "PM Completed Date",
            "Next PM Date",
            "Latitude",
            "Longitude",
        ]
        if column in aed_dataframe.columns
    ]

    current = aed_dataframe[current_columns].copy()

    current = current.rename(
        columns={
            "Location": "Current Location",
            "Postal Code": "Current Postal Code",
            "Latitude": "Current Latitude",
            "Longitude": "Current Longitude",
        }
    )

    combined = selected_plan.merge(
        current,
        on="Serial Number",
        how="left",
    )

    def snapshot_or_current(
        row: pd.Series,
        snapshot_column: str,
        current_column: str,
    ) -> Any:
        snapshot = clean_text(
            row.get(snapshot_column, "")
        )

        return (
            snapshot
            if snapshot
            else row.get(current_column, "")
        )

    combined["Location"] = combined.apply(
        lambda row: snapshot_or_current(
            row,
            "Location Snapshot",
            "Current Location",
        ),
        axis=1,
    )
    combined["Postal Code"] = combined.apply(
        lambda row: snapshot_or_current(
            row,
            "Postal Code Snapshot",
            "Current Postal Code",
        ),
        axis=1,
    )
    combined["Latitude"] = combined.apply(
        lambda row: snapshot_or_current(
            row,
            "Latitude Snapshot",
            "Current Latitude",
        ),
        axis=1,
    )
    combined["Longitude"] = combined.apply(
        lambda row: snapshot_or_current(
            row,
            "Longitude Snapshot",
            "Current Longitude",
        ),
        axis=1,
    )

    combined["Latitude"] = pd.to_numeric(
        combined["Latitude"],
        errors="coerce",
    )
    combined["Longitude"] = pd.to_numeric(
        combined["Longitude"],
        errors="coerce",
    )

    return combined


# ---------------------------------------------------------------------------
# Filters and status cards
# ---------------------------------------------------------------------------


def render_status_cards(
    dataframe: pd.DataFrame,
    definitions: pd.DataFrame,
    status_file: str | Path,
    state_file: str | Path,
    plan_file: str | Path,
) -> None:
    statuses = active_statuses(definitions)
    status_filter = clean_text(
        st.session_state.get(
            "aed_map_status_filter",
            "",
        )
    )

    if statuses.empty:
        st.warning(
            "No active statuses are available."
        )
        return

    items = statuses.to_dict("records")
    items.append(
        {
            "_Manage Button": True,
        }
    )

    for start in range(0, len(items), 7):
        row_items = items[start:start + 7]
        columns = st.columns(
            [1] * len(row_items),
            gap="small",
        )

        for column, item in zip(columns, row_items):
            with column:
                if item.get("_Manage Button"):
                    clicked = st.button(
                        "＋ Manage Statuses",
                        width="stretch",
                        key=f"manage_statuses_{start}",
                    )

                    if clicked:
                        open_status_dialog(
                            status_file=status_file,
                            state_file=state_file,
                            plan_file=plan_file,
                        )
                    continue

                status_name = clean_text(
                    item["Status Name"]
                )
                color_name = clean_text(
                    item["Marker Color"]
                ).title()
                count = int(
                    dataframe["PM Status"]
                    .astype(str)
                    .str.casefold()
                    .eq(status_name.casefold())
                    .sum()
                )
                selected = (
                    status_filter.casefold()
                    == status_name.casefold()
                )
                emoji = COLOR_EMOJI.get(
                    color_name,
                    "⚪",
                )
                label = (
                    f"{'✓ ' if selected else ''}"
                    f"{emoji} {status_name}\n"
                    f"{count} unit{'s' if count != 1 else ''}"
                )

                if st.button(
                    label,
                    width="stretch",
                    type=(
                        "primary"
                        if selected
                        else "secondary"
                    ),
                    key=(
                        "status_card_"
                        + clean_text(item["Status ID"])
                    ),
                ):
                    st.session_state[
                        "aed_map_status_filter"
                    ] = (
                        ""
                        if selected
                        else status_name
                    )
                    rerun_app()


# ---------------------------------------------------------------------------
# Marker styling and map creation
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Saving selected marker status and color
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Selected AED panel
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

def render_aed_map_page(
    aed_csv_file: str | Path,
) -> None:
    apply_map_page_styles()

    base_directory = Path(
        aed_csv_file
    ).resolve().parent

    plan_file = base_directory / "pm_plan_records.csv"
    status_file = base_directory / "map_status_definitions.csv"
    state_file = base_directory / "map_unit_state.csv"

    page_header(
        "AED Map",
        "View all AED units or a monthly PM plan, manage operational statuses, and act directly from each marker.",
        eyebrow="ASSET CONTROL · LOCATION VIEW",
        chip="ALL UNITS + MONTHLY PM MAP",
        capabilities=[
            ("Locate and filter", "Move from the full fleet to the exact units, model or assignee you need."),
            ("Status control", "Use customizable workflow statuses and marker colors to show current action."),
            ("Direct action", "Open PM Checklist or Report Issue from the selected AED context."),
        ],
    )

    notice = st.session_state.pop(
        "aed_map_notice",
        "",
    )

    if notice:
        st.success(notice)

    try:
        aed_dataframe = load_aed_data(
            aed_csv_file
        )
        plan_records = load_plan_records(
            plan_file
        )
        definitions = load_status_definitions(
            status_file
        )
        unit_state = load_unit_state(
            state_file
        )
        unit_state = ensure_all_units_have_state(
            aed_dataframe=aed_dataframe,
            state_dataframe=unit_state,
            definitions=definitions,
            state_file=state_file,
        )
    except (
        FileNotFoundError,
        ValueError,
        OSError,
        pd.errors.ParserError,
    ) as error:
        st.error(
            f"Failed to load AED map data: {error}"
        )
        return

    # Top controls ----------------------------------------------------------
    control_columns = st.columns(
        [1.65, 1.65, 2.45, 1.1, 1.25, 0.8],
        gap="small",
    )

    with control_columns[0]:
        map_options = [
            "All Units Map",
            "Monthly PM Map",
        ]

        if hasattr(st, "segmented_control"):
            map_type = st.segmented_control(
                "Map Type",
                options=map_options,
                default=st.session_state.get(
                    "aed_map_type",
                    "All Units Map",
                ),
                key="aed_map_type",
                label_visibility="collapsed",
            )
        else:
            map_type = st.radio(
                "Map Type",
                options=map_options,
                horizontal=True,
                key="aed_map_type",
                label_visibility="collapsed",
            )

        map_type = map_type or "All Units Map"

    selected_plan_id = "ALL"
    selected_plan_label = "All current AED units"

    with control_columns[1]:
        if map_type == "Monthly PM Map":
            if plan_records.empty:
                st.selectbox(
                    "Plan Month",
                    options=["No saved plans"],
                    disabled=True,
                    label_visibility="collapsed",
                )
            else:
                plan_options = (
                    plan_records[
                        [
                            "Plan ID",
                            "Plan Month",
                        ]
                    ]
                    .drop_duplicates()
                    .sort_values(
                        by=[
                            "Plan Month",
                            "Plan ID",
                        ],
                        ascending=False,
                    )
                )

                plan_ids = plan_options[
                    "Plan ID"
                ].tolist()

                plan_label_lookup = {}

                for _, row in plan_options.iterrows():
                    plan_month = clean_text(
                        row["Plan Month"]
                    )

                    try:
                        readable = (
                            pd.Period(
                                plan_month,
                                freq="M",
                            )
                            .to_timestamp()
                            .strftime("%B %Y")
                        )
                    except Exception:
                        readable = (
                            plan_month
                            or "Unknown month"
                        )

                    plan_label_lookup[
                        row["Plan ID"]
                    ] = (
                        f"{readable} — "
                        f"{row['Plan ID']}"
                    )

                stored_plan_id = clean_text(
                    st.session_state.get(
                        "aed_map_plan_id",
                        "",
                    )
                )

                if stored_plan_id not in plan_ids:
                    st.session_state[
                        "aed_map_plan_id"
                    ] = plan_ids[0]

                selected_plan_id = st.selectbox(
                    "Plan Month",
                    options=plan_ids,
                    format_func=lambda value: (
                        plan_label_lookup.get(
                            value,
                            value,
                        )
                    ),
                    key="aed_map_plan_id",
                    label_visibility="collapsed",
                )
                selected_plan_label = (
                    plan_label_lookup.get(
                        selected_plan_id,
                        selected_plan_id,
                    )
                )
        else:
            st.selectbox(
                "Plan Month",
                options=["All current AED units"],
                disabled=True,
                label_visibility="collapsed",
            )

    with control_columns[2]:
        keyword = st.text_input(
            "Search",
            placeholder=(
                "Search location, building, serial no."
            ),
            key="aed_map_keyword",
            label_visibility="collapsed",
        )

    # Build base dataset before filter dropdowns.
    if map_type == "Monthly PM Map":
        if plan_records.empty:
            working_dataframe = pd.DataFrame()
        else:
            working_dataframe = build_monthly_map_data(
                aed_dataframe=aed_dataframe,
                plan_dataframe=plan_records,
                plan_id=selected_plan_id,
            )
    else:
        working_dataframe = build_all_units_map_data(
            aed_dataframe=aed_dataframe,
            state_dataframe=unit_state,
        )

    status_filter = clean_text(
        st.session_state.get(
            "aed_map_status_filter",
            "",
        )
    )

    _normalise_map_filter_state(
        dataframe=working_dataframe,
        keyword=keyword,
        status_name=status_filter,
    )
    map_filter_selections = _map_filter_selections_from_state()

    with control_columns[3]:
        model_options = linked_map_filter_options(
            dataframe=working_dataframe,
            target_filter="model",
            keyword=keyword,
            status_name=status_filter,
            selections=map_filter_selections,
        )
        selected_models = st.multiselect(
            "Model",
            options=model_options,
            placeholder="All Models",
            key=MAP_FILTER_KEYS["model"],
            label_visibility="collapsed",
            on_change=_mark_map_filter_changed,
            args=("model",),
        )
        map_filter_selections["model"] = selected_models

    with control_columns[4]:
        assigned_options = linked_map_filter_options(
            dataframe=working_dataframe,
            target_filter="assignee",
            keyword=keyword,
            status_name=status_filter,
            selections=map_filter_selections,
        )
        selected_assignees = st.multiselect(
            "Assigned To",
            options=assigned_options,
            placeholder="All Technicians",
            key=MAP_FILTER_KEYS["assignee"],
            label_visibility="collapsed",
            on_change=_mark_map_filter_changed,
            args=("assignee",),
        )
        map_filter_selections["assignee"] = selected_assignees

    with control_columns[5]:
        st.button(
            "↻ Reset",
            width="stretch",
            key="reset_aed_map_page",
            on_click=reset_aed_map_filters,
        )

    if map_type == "Monthly PM Map" and plan_records.empty:
        st.info(
            "No monthly PM plans were found. "
            "Create a plan in PM Planning first."
        )
        return

    if working_dataframe.empty:
        st.info(
            "There are no AED units available for this map."
        )
        return

    base_filtered = filter_without_status(
        dataframe=working_dataframe,
        keyword=keyword,
        selected_models=selected_models,
        selected_assignees=selected_assignees,
    )

    plan_unit_count = len(working_dataframe)

    st.markdown(
        '<div class="aed-plan-summary">'
        f"{safe_html(selected_plan_label)} · "
        f"{plan_unit_count} unit"
        f"{'s' if plan_unit_count != 1 else ''}"
        "</div>",
        unsafe_allow_html=True,
    )

    # Status cards ----------------------------------------------------------
    render_status_cards(
        dataframe=base_filtered,
        definitions=definitions,
        status_file=status_file,
        state_file=state_file,
        plan_file=plan_file,
    )

    if (
        not hasattr(st, "dialog")
        and st.session_state.get(
            "show_inline_status_editor",
            False,
        )
    ):
        with st.expander(
            "Manage Statuses",
            expanded=True,
        ):
            render_status_editor_contents(
                status_file=status_file,
                state_file=state_file,
                plan_file=plan_file,
            )

    st.markdown(
        '<div class="aed-helper-bar">'
        "ⓘ Statuses are customizable. Click a status card to filter "
        "the map; click the same card again to clear that status filter."
        "</div>",
        unsafe_allow_html=True,
    )

    # status_filter was read before the linked dropdowns so the selected
    # status also narrows their available Model and Assigned To options.
    status_filter = clean_text(
        st.session_state.get(
            "aed_map_status_filter",
            "",
        )
    )
    displayed = apply_status_filter(
        dataframe=base_filtered,
        status_name=status_filter,
    )

    valid_coordinates = displayed.dropna(
        subset=[
            "Latitude",
            "Longitude",
        ]
    ).copy()

    missing_coordinates = (
        len(displayed)
        - len(valid_coordinates)
    )

    if missing_coordinates > 0:
        st.warning(
            f"⚠ {missing_coordinates} matching unit(s) "
            "are hidden because their coordinates are missing."
        )

    if valid_coordinates.empty:
        st.info(
            "No AED markers match the current filters."
        )
        return

    # Current selection before map rendering.
    selected_serial = clean_text(
        st.session_state.get(
            "aed_map_selected_serial",
            "",
        )
    )

    displayed_serials = {
        clean_text(value).casefold()
        for value in valid_coordinates[
            "Serial Number"
        ]
    }

    if (
        not selected_serial
        or selected_serial.casefold()
        not in displayed_serials
    ):
        selected_serial = clean_text(
            valid_coordinates.iloc[0][
                "Serial Number"
            ]
        )
        st.session_state[
            "aed_map_selected_serial"
        ] = selected_serial

    map_column, details_column = st.columns(
        [2.65, 1.35],
        gap="medium",
    )

    with map_column:
        try:
            map_object = create_map(
                dataframe=valid_coordinates,
                definitions=definitions,
                selected_serial=selected_serial,
            )
            map_result = render_folium(
                map_object=map_object,
                map_key=(
                    "aed_map_"
                    + map_type.replace(" ", "_")
                    + "_"
                    + selected_plan_id
                    + "_"
                    + status_filter.replace(" ", "_")
                ),
            )
        except ValueError as error:
            st.warning(str(error))
            return

        clicked_serial = clean_text(
            map_result.get(
                "last_object_clicked_tooltip",
                "",
            )
        )

        if (
            clicked_serial
            and clicked_serial.casefold()
            in displayed_serials
        ):
            selected_serial = clicked_serial
            st.session_state[
                "aed_map_selected_serial"
            ] = clicked_serial

    selected_matches = valid_coordinates[
        valid_coordinates["Serial Number"]
        .astype(str)
        .str.casefold()
        .eq(selected_serial.casefold())
    ]

    selected_row = (
        selected_matches.iloc[0]
        if not selected_matches.empty
        else None
    )

    with details_column:
        render_selected_aed_panel(
            selected_row=selected_row,
            map_type=map_type,
            plan_id=selected_plan_id,
            definitions=definitions,
            state_file=state_file,
            plan_file=plan_file,
        )
