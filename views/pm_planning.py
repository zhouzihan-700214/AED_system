from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from services.aed_repository import batch_update_units, get_all_units
from services.csv_storage import atomic_write_csv
from services.pm_service import (
    DEFAULT_PM_INTERVAL_MONTHS,
    PM_INTERVAL_COLUMN,
    PM_PLAN_COLUMNS,
)
from ui.components import page_header
from utils.text_utils import clean_text
from utils.streamlit_utils import rerun_app


DISPLAY_COLUMNS = [
    "Serial Number",
    "Model",
    "Location",
    "Postal Code",
    "Lift Lobby",
    "PM Completed Date",
    "Next PM Date",
    PM_INTERVAL_COLUMN,
]

REQUIRED_COLUMNS = DISPLAY_COLUMNS.copy()
PLAN_COLUMNS = PM_PLAN_COLUMNS


def load_aed_data(aed_csv_file: str | Path | None = None) -> pd.DataFrame:
    """Load and prepare AED planning fields through the shared repository."""

    del aed_csv_file
    dataframe = get_all_units().copy()

    for column in REQUIRED_COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = ""

        dataframe[column] = (
            dataframe[column]
            .astype(str)
            .str.strip()
        )

    dataframe["_PM Completed Parsed"] = pd.to_datetime(
        dataframe["PM Completed Date"],
        format="%d-%m-%Y",
        errors="coerce",
    )
    dataframe["_Next PM Parsed"] = pd.to_datetime(
        dataframe["Next PM Date"],
        format="%d-%m-%Y",
        errors="coerce",
    )

    intervals = pd.to_numeric(
        dataframe[PM_INTERVAL_COLUMN],
        errors="coerce",
    ).fillna(DEFAULT_PM_INTERVAL_MONTHS).clip(lower=1).astype(int)
    dataframe[PM_INTERVAL_COLUMN] = intervals.astype(str)

    fallback_due_dates = pd.Series(pd.NaT, index=dataframe.index, dtype="datetime64[ns]")
    for interval_months in sorted(intervals.unique()):
        mask = intervals.eq(interval_months)
        fallback_due_dates.loc[mask] = (
            dataframe.loc[mask, "_PM Completed Parsed"]
            + pd.DateOffset(months=int(interval_months))
        )

    # Next PM Date is the single operational source of truth. Only when it is
    # missing do we derive a temporary planning date from PM Completed Date
    # and the unit's PM Interval Months.
    dataframe["_PM Due Date"] = dataframe["_Next PM Parsed"].fillna(fallback_due_dates)

    dataframe["_Original Row Index"] = dataframe.index

    return dataframe


def build_year_options(
    dataframe: pd.DataFrame,
) -> list[int]:
    current_year = date.today().year

    due_years = (
        dataframe["_PM Due Date"]
        .dropna()
        .dt.year
        .astype(int)
        .tolist()
    )

    years = set(due_years)
    years.update(
        range(current_year - 1, current_year + 4)
    )

    return sorted(years)


def apply_planning_rules(
    dataframe: pd.DataFrame,
    selected_year: int,
    selected_month: int,
    planning_scope: str,
    include_without_pm_date: bool,
) -> pd.DataFrame:
    selected_period = pd.Period(
        year=selected_year,
        month=selected_month,
        freq="M",
    )

    due_periods = dataframe[
        "_PM Due Date"
    ].dt.to_period("M")

    if planning_scope == "Due in selected month":
        due_mask = due_periods.eq(selected_period)
    else:
        due_mask = due_periods.le(selected_period)

    due_mask = due_mask.fillna(False)

    if include_without_pm_date:
        no_pm_date_mask = dataframe["_PM Due Date"].isna()
        final_mask = due_mask | no_pm_date_mask
    else:
        final_mask = due_mask

    planned = dataframe.loc[final_mask].copy()

    planned["_No PM Date"] = planned["_PM Due Date"].isna()

    planned = planned.sort_values(
        by=[
            "_No PM Date",
            "_PM Due Date",
            "Postal Code",
            "Location",
            "Serial Number",
        ],
        ascending=[True, True, True, True, True],
        na_position="last",
    )

    return planned


def export_planning_csv(
    dataframe: pd.DataFrame,
) -> bytes:
    return dataframe[
        DISPLAY_COLUMNS
    ].to_csv(
        index=False,
        encoding="utf-8-sig",
    ).encode("utf-8-sig")


def render_batch_due_date_update(candidates: pd.DataFrame, plan_csv_file: str | Path) -> None:
    with st.expander("Batch Update Next PM Date", expanded=False):
        st.caption(
            "All selected date changes are checked and written in one Excel transaction. "
            "If any selected unit has a conflict, the entire batch is stopped."
        )
        if candidates.empty:
            st.info("No current candidates are available for batch rescheduling.")
            return

        editor = candidates[["Serial Number", "Location", "Next PM Date"]].copy()
        editor.insert(0, "Include", False)
        editor["Current Next PM Date"] = pd.to_datetime(
            editor["Next PM Date"], format="%d-%m-%Y", errors="coerce"
        )
        editor["New Next PM Date"] = editor["Current Next PM Date"]
        editor = editor.drop(columns=["Next PM Date"])
        edited = st.data_editor(
            editor, width="stretch", hide_index=True, num_rows="fixed",
            key="stage4_batch_pm_due_editor",
            disabled=["Serial Number", "Location", "Current Next PM Date"],
            column_config={
                "Include": st.column_config.CheckboxColumn("Include"),
                "Current Next PM Date": st.column_config.DateColumn("Current Next PM Date", format="DD-MM-YYYY"),
                "New Next PM Date": st.column_config.DateColumn("New Next PM Date", format="DD-MM-YYYY", required=True),
            },
        )
        save_clicked = st.button(
            "Save Selected PM Dates to Excel", type="primary", width="stretch",
            key="stage4_batch_pm_due_save",
        )
        if not save_clicked:
            return

        selected = edited[edited["Include"].fillna(False).astype(bool)].copy()
        updates = []
        history_rows = []
        for _, row in selected.iterrows():
            current = row.get("Current Next PM Date")
            new = row.get("New Next PM Date")
            if pd.isna(new):
                continue
            current_text = "" if pd.isna(current) else pd.Timestamp(current).strftime("%d-%m-%Y")
            new_text = pd.Timestamp(new).strftime("%d-%m-%Y")
            if new_text == current_text:
                continue
            serial = clean_text(row.get("Serial Number", ""))
            updates.append({
                "serial_number": serial,
                "original_values": {"Next PM Date": current_text},
                "desired_values": {"Next PM Date": new_text},
            })
            source = candidates[candidates["Serial Number"].astype(str).str.strip().eq(serial)]
            source_row = source.iloc[0] if not source.empty else pd.Series(dtype=object)
            history_rows.append({
                "Serial Number": serial,
                "Old Date": current_text,
                "New Date": new_text,
                "Location Snapshot": clean_text(source_row.get("Location", "")),
                "Postal Code Snapshot": clean_text(source_row.get("Postal Code", "")),
                "Latitude Snapshot": clean_text(source_row.get("Latitude", "")),
                "Longitude Snapshot": clean_text(source_row.get("Longitude", "")),
            })
        if not updates:
            st.info("No selected date changes were detected.")
            return

        result = batch_update_units(
            updates=updates,
            user=st.session_state.get("audit_user", ""),
            session_id=st.session_state.get("session_id", ""),
            source_page="PM Planning",
        )
        if result.success:
            existing = load_plan_records(plan_csv_file)
            created_at = datetime.now().astimezone().strftime("%d-%m-%Y %H:%M:%S")
            batch_rows = []
            for item in history_rows:
                new_date = datetime.strptime(item["New Date"], "%d-%m-%Y")
                batch_rows.append({
                    "Operation ID": result.operation_id,
                    "Plan ID": f"RESCHEDULE-{result.operation_id[:8]}",
                    "Plan Month": new_date.strftime("%Y-%m"),
                    "Planned Date": item["New Date"],
                    "Serial Number": item["Serial Number"],
                    "Assigned To": st.session_state.get("audit_user", ""),
                    "PM Status": "Rescheduled",
                    "Completed Date": "",
                    "Is Loaner": "No",
                    "Color Override": "",
                    "Location Snapshot": item["Location Snapshot"],
                    "Postal Code Snapshot": item["Postal Code Snapshot"],
                    "Latitude Snapshot": item["Latitude Snapshot"],
                    "Longitude Snapshot": item["Longitude Snapshot"],
                    "Created At": created_at,
                })
            combined = pd.concat([existing, pd.DataFrame(batch_rows)], ignore_index=True)
            save_plan_records(combined, plan_csv_file)
            st.session_state["pm_plan_save_message"] = (
                f"{result.message} Operation ID: {result.operation_id}"
            )
            st.session_state["pm_plan_save_message_type"] = "success"
            rerun_app()
        elif result.status == "conflict":
            st.error(result.message)
            conflict_rows = []
            for serial, fields in result.conflicts.items():
                for field, values in fields.items():
                    conflict_rows.append({
                        "Serial Number": serial, "Field": field,
                        "Opened Value": values.get("original", ""),
                        "Current Excel": values.get("current", ""),
                        "Planned Value": values.get("desired", ""),
                    })
            st.dataframe(pd.DataFrame(conflict_rows), width="stretch", hide_index=True)
        elif result.status == "already_applied":
            st.info(result.message)
        else:
            st.error(result.message)


def get_plan_file_path(
    aed_csv_file: str | Path,
) -> Path:
    return Path(aed_csv_file).resolve().parent / "pm_plan_records.csv"


def ensure_plan_columns(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    result = dataframe.copy()

    for column in PLAN_COLUMNS:
        if column not in result.columns:
            result[column] = ""

    result = result[PLAN_COLUMNS]

    for column in PLAN_COLUMNS:
        result[column] = (
            result[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    return result


def load_plan_records(
    plan_csv_file: str | Path,
) -> pd.DataFrame:
    path = Path(plan_csv_file)

    if not path.exists():
        return pd.DataFrame(columns=PLAN_COLUMNS)

    try:
        dataframe = pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        ).fillna("")
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=PLAN_COLUMNS)

    return ensure_plan_columns(dataframe)


def save_plan_records(
    dataframe: pd.DataFrame,
    plan_csv_file: str | Path,
) -> None:
    atomic_write_csv(
        ensure_plan_columns(dataframe),
        plan_csv_file,
        preferred_columns=PLAN_COLUMNS,
    )


def build_plan_selection_table(
    planned: pd.DataFrame,
) -> pd.DataFrame:
    selection = planned[
        [
            "_Original Row Index",
            *DISPLAY_COLUMNS,
        ]
    ].copy()

    selection.insert(0, "Include", True)
    selection["Assigned To"] = ""
    selection["Is Loaner"] = False

    return selection.reset_index(drop=True)


def create_monthly_plan_records(
    master_dataframe: pd.DataFrame,
    selected_rows: pd.DataFrame,
    selected_year: int,
    selected_month: int,
    planned_date: date,
    plan_csv_file: str | Path,
) -> tuple[pd.DataFrame, int, int]:
    existing = load_plan_records(plan_csv_file)

    plan_id = f"PM-{selected_year}-{selected_month:02d}"
    plan_month = f"{selected_year}-{selected_month:02d}"
    planned_date_text = planned_date.strftime("%d-%m-%Y")
    created_at = (
        datetime.now()
        .astimezone()
        .strftime("%d-%m-%Y %H:%M:%S")
    )

    existing_pairs = {
        (
            clean_text(row["Plan ID"]).casefold(),
            clean_text(row["Serial Number"]).casefold(),
        )
        for _, row in existing.iterrows()
    }

    new_rows: list[dict[str, str]] = []
    skipped_count = 0

    for _, selected_row in selected_rows.iterrows():
        include_value = selected_row.get("Include", False)

        if not bool(include_value):
            continue

        row_index = int(selected_row["_Original Row Index"])

        if row_index not in master_dataframe.index:
            continue

        source_row = master_dataframe.loc[row_index]
        serial_number = clean_text(
            source_row.get("Serial Number", "")
        )

        if not serial_number:
            skipped_count += 1
            continue

        pair = (
            plan_id.casefold(),
            serial_number.casefold(),
        )

        if pair in existing_pairs:
            skipped_count += 1
            continue

        is_loaner = bool(
            selected_row.get("Is Loaner", False)
        )

        new_rows.append(
            {
                "Plan ID": plan_id,
                "Plan Month": plan_month,
                "Planned Date": planned_date_text,
                "Serial Number": serial_number,
                "Assigned To": clean_text(
                    selected_row.get("Assigned To", "")
                ),
                "PM Status": "Pending",
                "Completed Date": "",
                "Is Loaner": "Yes" if is_loaner else "No",
                "Color Override": "",
                "Location Snapshot": clean_text(
                    source_row.get("Location", "")
                ),
                "Postal Code Snapshot": clean_text(
                    source_row.get("Postal Code", "")
                ),
                "Latitude Snapshot": clean_text(
                    source_row.get("Latitude", "")
                ),
                "Longitude Snapshot": clean_text(
                    source_row.get("Longitude", "")
                ),
                "Created At": created_at,
            }
        )

        existing_pairs.add(pair)

    if new_rows:
        new_dataframe = pd.DataFrame(
            new_rows,
            columns=PLAN_COLUMNS,
        )
        combined = pd.concat(
            [existing, new_dataframe],
            ignore_index=True,
        )
    else:
        combined = existing

    save_plan_records(combined, plan_csv_file)

    return combined, len(new_rows), skipped_count


def render_saved_plan(
    plan_records: pd.DataFrame,
    plan_id: str,
) -> None:
    current_plan = plan_records[
        plan_records["Plan ID"].eq(plan_id)
    ].copy()

    st.markdown("### Saved Monthly Plan")

    if current_plan.empty:
        st.info(
            "No saved records exist for this month yet."
        )
        return

    pending_count = int(
        current_plan["PM Status"]
        .str.casefold()
        .eq("pending")
        .sum()
    )
    completed_count = int(
        current_plan["PM Status"]
        .str.casefold()
        .eq("completed")
        .sum()
    )

    metric_1, metric_2, metric_3 = st.columns(3)
    metric_1.metric("Saved Units", len(current_plan))
    metric_2.metric("Pending", pending_count)
    metric_3.metric("Completed", completed_count)

    visible_columns = [
        "Plan ID",
        "Planned Date",
        "Serial Number",
        "Assigned To",
        "PM Status",
        "Completed Date",
        "Completed By",
        "Completion Record ID",
        "Is Loaner",
        "Location Snapshot",
        "Postal Code Snapshot",
    ]

    st.dataframe(
        current_plan[visible_columns],
        width="stretch",
        hide_index=True,
    )


def render_pm_planning_page(
    aed_csv_file: str | Path = "aed_data.csv",
) -> None:
    page_header(
        "PM Planning",
        "Identify AED units due for preventive maintenance and save a persistent monthly execution plan.",
        eyebrow="MAINTENANCE · PLAN",
        chip="MONTHLY SCHEDULING",
        capabilities=[
            ("Due-date scope", "Plan units due in one month or include everything already overdue."),
            ("Assignment ready", "Choose units, planned dates and technicians before field work begins."),
            ("Persistent plan", "Save the plan for later review, map display and completion tracking."),
        ],
    )

    plan_csv_file = get_plan_file_path(aed_csv_file)

    try:
        dataframe = load_aed_data(aed_csv_file)
        plan_records = load_plan_records(plan_csv_file)
    except FileNotFoundError as error:
        st.error(str(error))
        return
    except pd.errors.EmptyDataError:
        st.error("AED master data is empty.")
        return
    except Exception as error:
        st.error(f"Failed to load PM planning data: {error}")
        return

    if dataframe.empty:
        st.info("There are no AED units in the master table.")
        return

    month_names = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]

    controls_left, controls_middle, controls_right = st.columns(
        [1, 1, 2.2]
    )

    with controls_left:
        selected_month_name = st.selectbox(
            "Planning Month",
            options=month_names,
            index=date.today().month - 1,
            key="planning_month",
        )
        selected_month = (
            month_names.index(selected_month_name) + 1
        )

    with controls_middle:
        year_options = build_year_options(dataframe)
        current_year = date.today().year

        default_year_index = (
            year_options.index(current_year)
            if current_year in year_options
            else 0
        )

        selected_year = st.selectbox(
            "Planning Year",
            options=year_options,
            index=default_year_index,
            key="planning_year",
        )

    with controls_right:
        planning_scope = st.radio(
            "Planning Scope",
            options=[
                "Due in selected month",
                "Due by selected month (includes overdue)",
            ],
            horizontal=True,
            key="planning_scope",
        )

    include_without_pm_date = st.checkbox(
        "Include AED units without a usable PM due date",
        value=False,
        key="planning_include_blank_pm",
        help=(
            "These units do not have a usable Next PM Date and cannot be "
            "derived from PM Completed Date, so they are included separately."
        ),
    )

    selected_period_text = (
        f"{selected_month_name} {selected_year}"
    )
    plan_id = f"PM-{selected_year}-{selected_month:02d}"

    planned = apply_planning_rules(
        dataframe=dataframe,
        selected_year=selected_year,
        selected_month=selected_month,
        planning_scope=planning_scope,
        include_without_pm_date=include_without_pm_date,
    )

    valid_pm_count = int(
        dataframe["_PM Due Date"].notna().sum()
    )
    missing_or_invalid_count = len(dataframe) - valid_pm_count

    metric_1, metric_2, metric_3 = st.columns(3)

    metric_1.metric(
        "Total AED Units",
        len(dataframe),
    )
    metric_2.metric(
        f"Due for {selected_period_text}",
        len(planned),
    )
    metric_3.metric(
        "Without Usable PM Due Date",
        missing_or_invalid_count,
    )

    if missing_or_invalid_count:
        st.warning(
            f"{missing_or_invalid_count} AED unit(s) have no usable Next PM Date "
            "and no derivable PM due date. They are excluded unless the "
            "checkbox above is selected."
        )

    st.markdown(f"### PM Candidates — {selected_period_text}")

    if planned.empty:
        st.info(
            "No AED units match the current planning rules."
        )
        edited_selection = pd.DataFrame()
    else:
        selection_table = build_plan_selection_table(planned)

        scope_key = (
            "month"
            if planning_scope == "Due in selected month"
            else "overdue"
        )
        editor_key = (
            f"pm_plan_editor_{selected_year}_{selected_month}_"
            f"{scope_key}_{int(include_without_pm_date)}"
        )

        edited_selection = st.data_editor(
            selection_table,
            width="stretch",
            hide_index=True,
            height=500,
            num_rows="fixed",
            key=editor_key,
            disabled=[
                "_Original Row Index",
                *DISPLAY_COLUMNS,
            ],
            column_config={
                "Include": st.column_config.CheckboxColumn(
                    "Include",
                    help="Select this AED for the saved monthly plan.",
                    default=True,
                ),
                "_Original Row Index": None,
                "Assigned To": st.column_config.TextColumn(
                    "Assigned To",
                    help="Technician or intern assigned to this AED.",
                ),
                "Is Loaner": st.column_config.CheckboxColumn(
                    "Is Loaner",
                    help=(
                        "Loaner units can still be completed on the "
                        "monthly PM map."
                    ),
                    default=False,
                ),
            },
        )

    render_batch_due_date_update(planned, plan_csv_file)

    planned_date = st.date_input(
        "Planned Date",
        value=date(
            selected_year,
            selected_month,
            1,
        ),
        format="DD-MM-YYYY",
        key=f"planned_date_{selected_year}_{selected_month}",
    )

    create_clicked = st.button(
        "Create / Add to Monthly Plan",
        type="primary",
        width="stretch",
        disabled=planned.empty,
        key=f"create_pm_plan_{selected_year}_{selected_month}",
    )

    if create_clicked:
        selected_count = 0

        if not edited_selection.empty:
            selected_count = int(
                edited_selection["Include"]
                .fillna(False)
                .astype(bool)
                .sum()
            )

        if selected_count == 0:
            st.warning(
                "Select at least one AED unit before creating the plan."
            )
        else:
            try:
                updated_records, added_count, skipped_count = (
                    create_monthly_plan_records(
                        master_dataframe=dataframe,
                        selected_rows=edited_selection,
                        selected_year=selected_year,
                        selected_month=selected_month,
                        planned_date=planned_date,
                        plan_csv_file=plan_csv_file,
                    )
                )

                st.session_state[
                    "pm_plan_save_message"
                ] = (
                    f"{added_count} AED unit(s) added to {plan_id}. "
                    f"{skipped_count} duplicate or invalid unit(s) skipped."
                )
                st.session_state[
                    "pm_plan_save_message_type"
                ] = (
                    "success"
                    if added_count > 0
                    else "info"
                )

                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()

            except (OSError, ValueError) as error:
                st.error(
                    f"Failed to save the monthly PM plan: {error}"
                )

    save_message = st.session_state.pop(
        "pm_plan_save_message",
        "",
    )
    save_message_type = st.session_state.pop(
        "pm_plan_save_message_type",
        "",
    )

    if save_message:
        if save_message_type == "success":
            st.success(save_message)
        else:
            st.info(save_message)

    plan_records = load_plan_records(plan_csv_file)
    render_saved_plan(plan_records, plan_id)

    export_filename = (
        "pm_candidates_"
        f"{selected_year}_{selected_month:02d}.csv"
    )

    st.download_button(
        "Export Current Candidate List",
        data=export_planning_csv(planned),
        file_name=export_filename,
        mime="text/csv",
        disabled=planned.empty,
    )

    with st.expander("Planning Rule and Saved Data"):
        st.markdown(
            """
            - `Next PM Date` is the single operational due-date source.
            - If it is blank, the preview derives a temporary due date from
              `PM Completed Date + PM Interval Months`.
            - The default interval is 12 months and can be maintained per AED.
            - The candidate table is only a preview until
              **Create / Add to Monthly Plan** is clicked.
            - Saved plans are written to `pm_plan_records.csv`.
            - Each saved unit begins with `PM Status = Pending`.
            - The same Serial Number may appear in different months.
            - The same Serial Number cannot be duplicated within the
              same monthly Plan ID.
            - Location, postal code and coordinates are copied as
              snapshots when the plan is created.
            """
        )
