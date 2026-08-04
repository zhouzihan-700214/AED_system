from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from config import ISSUE_RECORD_FILE, ISSUE_RESOLUTION_FILE
from services.manual_service_storage import MANUAL_SERVICE_RECORDS_FILE
from services.aed_repository import get_all_units
from services.unit_profile_service import load_manual_service_records
from services.service_record_service import (
    load_service_records as load_service_records_data,
    service_record_scope_counts,
)
from ui.components import page_header
from utils.text_utils import clean_text


PRIORITY_COLUMNS = [
    "Service Date",
    "Technician",
    "Service Type",
    "Record Source",
    "Record Status",
    "Record Match",
    "Loaner Unit",
    "AED Serial Number",
    "AED Model",
    "AED Location",
    "Postal Code",
    "Lift Lobby",
    "Battery Replaced",
    "Submitted At",
]

CHECKLIST_FIELDS = [
    (1, "Service Date", "Service Date"),
    (2, "Technician", "Technician"),
    (3, "Service Type", "Service Type"),
    (4, "Customer / Location", "Customer / Location"),
    (5, "Postal Code", "Postal Code"),
    (6, "Lift Lobby", "Lift Lobby"),
    (7, "Is this a loaner unit?", "Loaner Unit"),
    (8, "Cabinet Inspection", "Cabinet Inspection"),
    (9, "Cabinet Alarm", "Cabinet Alarm"),
    (10, "AED Serial Number", "AED Serial Number"),
    (11, "AED Physical Condition", "AED Physical Condition"),
    (12, "Self Test Result", "Self Test Result"),
    (13, "Battery Expiry Date", "Battery Expiry Date"),
    (14, "AED Cover", "AED Cover"),
    (15, "Adult Pads Expiry Date", "Adult Pads Expiry Date"),
    (16, "Adult Pads Lot Number", "Adult Pads Lot Number"),
    (
        17,
        "Adult Pads Within Expiry Date",
        "Adult Pads Within Expiry Date",
    ),
    (18, "Pediatric Pads Expiry Date", "Pediatric Pads Expiry Date"),
    (19, "Pediatric Pads Lot Number", "Pediatric Pads Lot Number"),
    (
        20,
        "Pediatric Pads Within Expiry Date",
        "Pediatric Pads Within Expiry Date",
    ),
    (21, "AED Signage", "AED Signage"),
    (22, "Final Check", "Final Check"),
]

SUPPLEMENTARY_FIELDS = [
    "Record Source",
    "Record Match",
    "Loaner Unit",
    "Submission Status",
    "Excel Update Status",
    "Submitted By",
    "Operation ID",
    "Record Status",
    "Service Record ID",
    "Service Report e-SR",
    "Service Notes",
    "Linked Plan ID",
    "Failed Checklist Fields",
    "Created Issue IDs",
    "Issue ID",
    "Issue Type",
    "Resolution Submission ID",
    "Resolution Attempt Number",
    "Action Taken",
    "Root Cause",
    "Parts Replaced",
    "Test Performed",
    "Test Result",
    "Resolution Notes",
    "Verification Result",
    "Verification Notes",
    "Verified By",
    "Verified At",
    "Attachment Count",
    "Attachment Paths",
    "Postal Code",
    "Lift Lobby",
    "Master Operation ID",
    "PM Dates Updated",
    "Battery History Updated",
    "PM Interval Months Used",
    "PM Response ID",
    "Original Serial Number",
    "AED Model",
    "AED Location",
    "Battery Replaced",
    "Master Data Updated",
    "Submitted At",
]


SERVICE_RECORD_FILTER_KEYS = {
    "month": "service_records_month",
    "technician": "service_records_technician",
    "service_type": "service_records_service_type",
    "battery_replaced": "service_records_battery",
    "model": "service_records_model",
    "record_source": "service_records_source",
    "record_status": "service_records_status",
    "loaner": "service_records_loaner",
}

SERVICE_RECORD_FILTER_COLUMNS = {
    "technician": "Technician",
    "service_type": "Service Type",
    "battery_replaced": "Battery Replaced",
    "model": "AED Model",
    "record_source": "Record Source",
    "record_status": "Record Status",
    "loaner": "Loaner Unit",
}


def _parse_mixed_datetime(series: pd.Series) -> pd.Series:
    values = series.astype(str).str.strip()
    try:
        return pd.to_datetime(
            values,
            format="mixed",
            dayfirst=True,
            errors="coerce",
        )
    except (TypeError, ValueError):
        return pd.to_datetime(values, dayfirst=True, errors="coerce")


def parse_service_date_series(series: pd.Series) -> pd.Series:
    return _parse_mixed_datetime(series)


def parse_submitted_at_series(series: pd.Series) -> pd.Series:
    return _parse_mixed_datetime(series)


def load_aed_lookup(aed_csv_file: str | Path | None = None) -> pd.DataFrame:
    del aed_csv_file
    dataframe = get_all_units().copy()

    for column in ["Serial Number", "Model", "Location"]:
        if column not in dataframe.columns:
            dataframe[column] = ""

        dataframe[column] = (
            dataframe[column]
            .astype(str)
            .str.strip()
        )

    return dataframe[
        ["Serial Number", "Model", "Location"]
    ].copy()


def create_lookup_map(
    dataframe: pd.DataFrame,
    value_column: str,
) -> dict[str, str]:
    lookup: dict[str, str] = {}

    for _, row in dataframe.iterrows():
        serial = clean_text(row.get("Serial Number", ""))
        value = clean_text(row.get(value_column, ""))

        if serial and serial.casefold() not in lookup:
            lookup[serial.casefold()] = value

    return lookup


def _manual_records_for_service_page(
    manual_service_file: str | Path,
) -> pd.DataFrame:
    manual = load_manual_service_records(manual_service_file)
    if manual.empty:
        return pd.DataFrame()

    result = pd.DataFrame(index=manual.index)
    result["PM Response ID"] = manual["Service Record ID"]
    result["Service Record ID"] = manual["Service Record ID"]
    result["Service Date"] = manual["Service Date"]
    result["Technician"] = manual["Technician"]
    result["Service Type"] = manual["Service Type"]
    result["AED Serial Number"] = manual["AED Serial Number"]
    result["Original Serial Number"] = manual["AED Serial Number"]
    result["Submitted At"] = manual["Created At"]
    result["Submitted By"] = manual["Created By"]
    result["Record Source"] = manual["Source"].replace("", "Unit Profile")
    result["Record Status"] = manual["Status"]
    result["Service Notes"] = manual["Details"]
    result["Service Report e-SR"] = manual["Reference"]
    result["Master Data Updated"] = manual["Master Data Updated"]
    result["PM Dates Updated"] = manual["PM Dates Updated"]
    result["Battery Replaced"] = manual["Service Type"].astype(str).str.contains(
        "batt|battery", case=False, regex=True, na=False
    ).map({True: "Yes", False: "No"})
    return result.fillna("")


def load_service_records(
    response_csv_file: str | Path,
    aed_csv_file: str | Path,
    manual_service_file: str | Path = MANUAL_SERVICE_RECORDS_FILE,
    issue_record_file: str | Path = ISSUE_RECORD_FILE,
    resolution_file: str | Path = ISSUE_RESOLUTION_FILE,
) -> pd.DataFrame:
    """Load the exact dataset used by the Service Records page."""
    return load_service_records_data(
        response_csv_file=response_csv_file,
        aed_csv_file=aed_csv_file,
        manual_service_file=manual_service_file,
        issue_record_file=issue_record_file,
        resolution_file=resolution_file,
    )

def unique_values(
    dataframe: pd.DataFrame,
    column: str,
) -> list[str]:
    if column not in dataframe.columns:
        return []

    values = {
        clean_text(value)
        for value in dataframe[column].tolist()
        if clean_text(value)
    }

    return sorted(values, key=str.casefold)


def available_months(
    dataframe: pd.DataFrame,
) -> list[tuple[str, str]]:
    if "_Service Date Parsed" not in dataframe.columns:
        return []

    valid_dates = dataframe["_Service Date Parsed"].dropna()

    month_values = sorted(
        {
            timestamp.strftime("%Y-%m")
            for timestamp in valid_dates
        },
        reverse=True,
    )

    return [
        (
            month_value,
            pd.Timestamp(
                f"{month_value}-01"
            ).strftime("%B %Y"),
        )
        for month_value in month_values
    ]


def apply_filters(
    dataframe: pd.DataFrame,
    keyword: str,
    start_date: date | None,
    end_date: date | None,
    selected_month: str,
    technicians: list[str],
    service_types: list[str],
    battery_replaced_values: list[str],
    models: list[str],
    record_sources: list[str] | None = None,
    record_statuses: list[str] | None = None,
    loaner_values: list[str] | None = None,
    record_scope: str = "All Records",
) -> pd.DataFrame:
    filtered = dataframe.copy()

    scope = clean_text(record_scope) or "All Records"
    if scope in {"Matched", "Mismatch", "Loaner"}:
        match_series = filtered.get(
            "Record Match",
            pd.Series("", index=filtered.index, dtype=str),
        ).astype(str)
        filtered = filtered.loc[match_series.eq(scope)]

    keyword_text = clean_text(keyword).casefold()

    if keyword_text:
        keyword_columns = [
            "AED Serial Number",
            "AED Location",
            "Postal Code",
            "Lift Lobby",
            "Adult Pads Lot Number",
            "Pediatric Pads Lot Number",
            "AED Model",
            "PM Response ID",
            "Service Record ID",
            "Service Report e-SR",
            "Service Notes",
            "Issue ID",
            "Resolution Submission ID",
            "Created Issue IDs",
            "Issue Type",
            "Action Taken",
            "Root Cause",
            "Parts Replaced",
            "Test Performed",
            "Test Result",
            "Resolution Notes",
            "Verification Notes",
        ]

        keyword_mask = pd.Series(
            False,
            index=filtered.index,
        )

        for column in keyword_columns:
            if column not in filtered.columns:
                continue

            keyword_mask |= (
                filtered[column]
                .astype(str)
                .str.casefold()
                .str.contains(
                    keyword_text,
                    regex=False,
                    na=False,
                )
            )

        filtered = filtered.loc[keyword_mask]

    if start_date is not None:
        filtered = filtered.loc[
            filtered["_Service Date Parsed"]
            >= pd.Timestamp(start_date)
        ]

    if end_date is not None:
        filtered = filtered.loc[
            filtered["_Service Date Parsed"]
            <= pd.Timestamp(end_date)
        ]

    if selected_month:
        filtered = filtered.loc[
            filtered["_Service Date Parsed"]
            .dt.strftime("%Y-%m")
            .eq(selected_month)
        ]

    filter_pairs = [
        ("Technician", technicians),
        ("Service Type", service_types),
        ("Battery Replaced", battery_replaced_values),
        ("AED Model", models),
        ("Record Source", record_sources or []),
        ("Record Status", record_statuses or []),
        ("Loaner Unit", loaner_values or []),
    ]

    for column, selected_values in filter_pairs:
        if selected_values:
            filtered = filtered.loc[
                filtered[column]
                .astype(str)
                .isin(selected_values)
            ]

    filtered = filtered.sort_values(
        by=[
            "_Service Date Parsed",
            "_Submitted At Parsed",
        ],
        ascending=[False, False],
        na_position="last",
    )

    return filtered


def _service_record_filter_selections_from_state() -> dict[str, list[str]]:
    """Return the current Service Records filter selections as lists."""

    selections: dict[str, list[str]] = {}

    for filter_name, session_key in SERVICE_RECORD_FILTER_KEYS.items():
        value = st.session_state.get(session_key, "" if filter_name == "month" else [])

        if isinstance(value, (list, tuple, set)):
            selections[filter_name] = [
                clean_text(item)
                for item in value
                if clean_text(item)
            ]
        elif clean_text(value):
            selections[filter_name] = [clean_text(value)]
        else:
            selections[filter_name] = []

    return selections


def _set_service_record_filter_state(
    filter_name: str,
    values: list[str],
) -> None:
    """Write a normalised filter value back to Streamlit session state."""

    session_key = SERVICE_RECORD_FILTER_KEYS[filter_name]

    if filter_name == "month":
        st.session_state[session_key] = values[0] if values else ""
    else:
        st.session_state[session_key] = values


def _mark_service_record_filter_changed(filter_name: str) -> None:
    """Remember the newest choice so it wins over incompatible older choices."""

    st.session_state["service_records_last_changed_filter"] = filter_name


def linked_service_record_options(
    dataframe: pd.DataFrame,
    target_filter: str,
    keyword: str,
    start_date: date | None,
    end_date: date | None,
    selections: dict[str, list[str]] | None = None,
    record_scope: str = "All Records",
) -> list[str]:
    """Return one filter's options after applying every other active filter."""

    if target_filter not in SERVICE_RECORD_FILTER_KEYS:
        valid_names = ", ".join(SERVICE_RECORD_FILTER_KEYS)
        raise ValueError(
            f"Unknown Service Records filter '{target_filter}'. "
            f"Expected one of: {valid_names}."
        )

    active = {
        name: list(values or [])
        for name, values in (selections or {}).items()
        if name in SERVICE_RECORD_FILTER_KEYS
    }

    for name in SERVICE_RECORD_FILTER_KEYS:
        active.setdefault(name, [])

    # Exclude the target itself. This keeps all values that are compatible
    # with the other filters and allows a multiselect to retain several values.
    active[target_filter] = []

    selected_month = active["month"][0] if active["month"] else ""

    filtered = apply_filters(
        dataframe=dataframe,
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
        selected_month=selected_month,
        technicians=active["technician"],
        service_types=active["service_type"],
        battery_replaced_values=active["battery_replaced"],
        models=active["model"],
        record_sources=active["record_source"],
        record_statuses=active["record_status"],
        loaner_values=active["loaner"],
        record_scope=record_scope,
    )

    if target_filter == "month":
        return [
            month_value
            for month_value, _ in available_months(filtered)
        ]

    return unique_values(
        filtered,
        SERVICE_RECORD_FILTER_COLUMNS[target_filter],
    )


def _normalise_service_record_filter_state(
    dataframe: pd.DataFrame,
    keyword: str,
    start_date: date | None,
    end_date: date | None,
    record_scope: str = "All Records",
) -> None:
    """Clear choices that no longer match the other Service Records filters."""

    selections = _service_record_filter_selections_from_state()
    last_changed = st.session_state.get(
        "service_records_last_changed_filter"
    )

    # First validate the newest choice against the keyword/date scope alone.
    # This preserves the user's newest action and clears incompatible older
    # choices from other filters instead of immediately undoing the new choice.
    if last_changed in SERVICE_RECORD_FILTER_KEYS:
        empty_selections = {
            name: []
            for name in SERVICE_RECORD_FILTER_KEYS
        }
        base_options = linked_service_record_options(
            dataframe=dataframe,
            target_filter=last_changed,
            keyword=keyword,
            start_date=start_date,
            end_date=end_date,
            selections=empty_selections,
            record_scope=record_scope,
        )
        allowed = set(base_options)
        valid = [
            value
            for value in selections[last_changed]
            if value in allowed
        ]

        if valid != selections[last_changed]:
            selections[last_changed] = valid
            _set_service_record_filter_state(last_changed, valid)

    order = [
        name
        for name in SERVICE_RECORD_FILTER_KEYS
        if name != last_changed
    ]

    if last_changed in SERVICE_RECORD_FILTER_KEYS:
        order.append(last_changed)

    # Several passes settle chains such as Model -> Technician -> Month.
    for _ in range(len(SERVICE_RECORD_FILTER_KEYS) + 1):
        changed = False

        for filter_name in order:
            options = linked_service_record_options(
                dataframe=dataframe,
                target_filter=filter_name,
                keyword=keyword,
                start_date=start_date,
                end_date=end_date,
                selections=selections,
                record_scope=record_scope,
            )
            allowed = set(options)
            valid = [
                value
                for value in selections[filter_name]
                if value in allowed
            ]

            # Service Month is a single-select filter.
            if filter_name == "month":
                valid = valid[:1]

            if valid != selections[filter_name]:
                selections[filter_name] = valid
                _set_service_record_filter_state(filter_name, valid)
                changed = True

        if not changed:
            break


def reset_service_record_filters() -> None:
    """Restore every Service Records filter to its initial value."""

    defaults: dict[str, Any] = {
        "service_records_keyword": "",
        "service_records_date_from": None,
        "service_records_date_to": None,
        "service_records_month": "",
        "service_records_technician": [],
        "service_records_service_type": [],
        "service_records_battery": [],
        "service_records_model": [],
        "service_records_source": [],
        "service_records_status": [],
        "service_records_loaner": [],
        "service_records_scope": "All Records",
        "service_records_last_changed_filter": None,
    }

    for key, value in defaults.items():
        st.session_state[key] = value

    # The old selected detail record may not exist after the filters reset.
    st.session_state.pop("selected_service_record", None)


def record_label(
    dataframe: pd.DataFrame,
    row_index: int,
) -> str:
    row = dataframe.loc[row_index]

    service_date = (
        clean_text(row.get("Service Date", ""))
        or "No service date"
    )
    serial = (
        clean_text(row.get("AED Serial Number", ""))
        or "No serial"
    )
    location = (
        clean_text(row.get("AED Location", ""))
        or "No location"
    )
    technician = (
        clean_text(row.get("Technician", ""))
        or "No technician"
    )

    source = clean_text(row.get("Record Source", "")) or "Service"
    service_type = clean_text(row.get("Service Type", "")) or "—"

    return (
        f"{service_date} | {serial} | {source} | {service_type} | "
        f"{location} | {technician}"
    )


def export_dataframe(
    dataframe: pd.DataFrame,
) -> bytes:
    helper_columns = [
        "_Service Date Parsed",
        "_Submitted At Parsed",
        "_Original Row Index",
    ]

    export_columns = [
        column
        for column in dataframe.columns
        if column not in helper_columns
    ]

    return dataframe[
        export_columns
    ].to_csv(
        index=False,
        encoding="utf-8-sig",
    ).encode("utf-8-sig")


def render_record_details(
    row: pd.Series,
    *,
    issue_record_file: str | Path = ISSUE_RECORD_FILE,
) -> None:
    st.subheader("Service Record Details")
    st.caption(
        "This is a view-only record. The source is shown below."
    )

    general_left, general_right = st.columns(2)

    with general_left:
        record_id = (
            clean_text(row.get("Service Record ID", ""))
            or clean_text(row.get("PM Response ID", ""))
            or clean_text(row.get("Resolution Submission ID", ""))
        )
        st.markdown(f"**Record ID:** {record_id or '—'}")
        st.markdown(
            f"**Record Source:** "
            f"{clean_text(row.get('Record Source', '')) or '—'}"
        )
        st.markdown(
            f"**Service Date:** "
            f"{clean_text(row.get('Service Date', '')) or '—'}"
        )
        st.markdown(
            f"**Technician:** "
            f"{clean_text(row.get('Technician', '')) or '—'}"
        )
        st.markdown(
            f"**Service Type:** "
            f"{clean_text(row.get('Service Type', '')) or '—'}"
        )
        st.markdown(
            f"**Record Status:** "
            f"{clean_text(row.get('Record Status', '')) or '—'}"
        )
        st.markdown(
            f"**Reference / e-SR:** "
            f"{clean_text(row.get('Service Report e-SR', '')) or '—'}"
        )
        st.markdown(
            f"**Submitted At:** "
            f"{clean_text(row.get('Submitted At', '')) or '—'}"
        )

    with general_right:
        st.markdown(
            f"**AED Serial Number:** "
            f"{clean_text(row.get('AED Serial Number', '')) or '—'}"
        )
        st.markdown(
            f"**AED Model:** "
            f"{clean_text(row.get('AED Model', '')) or '—'}"
        )
        st.markdown(
            f"**AED Location:** "
            f"{clean_text(row.get('AED Location', '')) or '—'}"
        )
        st.markdown(
            f"**Postal Code / Lift Lobby:** "
            f"{clean_text(row.get('Postal Code', '')) or '—'} / "
            f"{clean_text(row.get('Lift Lobby', '')) or '—'}"
        )
        st.markdown(
            f"**Loaner Unit:** "
            f"{clean_text(row.get('Loaner Unit', '')) or 'No'}"
        )
        st.markdown(
            f"**Postal / Serial Check:** "
            f"{clean_text(row.get('Record Match', '')) or '—'}"
        )
        st.markdown(
            f"**Battery Replaced:** "
            f"{clean_text(row.get('Battery Replaced', '')) or '—'}"
        )
        st.markdown(
            f"**Master Data Updated:** "
            f"{clean_text(row.get('Master Data Updated', '')) or '—'}"
        )

    record_source = clean_text(row.get("Record Source", "")) or "PM Checklist"
    if record_source.casefold() == "pm checklist":
        checklist_rows = []
        for item_number, label, column in CHECKLIST_FIELDS:
            checklist_rows.append(
                {
                    "Item": item_number,
                    "Checklist Field": label,
                    "Recorded Response": clean_text(row.get(column, "")) or "—",
                }
            )
        st.markdown("#### Full Checklist")
        st.dataframe(pd.DataFrame(checklist_rows), width="stretch", hide_index=True)
    else:
        st.markdown("#### Service Notes")
        st.write(clean_text(row.get("Service Notes", "")) or "No additional notes were recorded.")

    attachment_paths = [
        clean_text(value)
        for value in clean_text(row.get("Attachment Paths", "")).split(";")
        if clean_text(value)
    ]
    if attachment_paths:
        st.markdown("#### Resolution Evidence")
        image_columns = st.columns(min(3, len(attachment_paths)))
        for index, saved_path in enumerate(attachment_paths):
            resolved = Path(issue_record_file).resolve().parent / saved_path
            with image_columns[index % len(image_columns)]:
                if resolved.exists():
                    st.image(str(resolved), caption=Path(saved_path).name, width="stretch")
                else:
                    st.warning(f"Evidence file is unavailable: {saved_path}")

    with st.expander("Additional Saved Information"):
        additional_rows = []

        for field in SUPPLEMENTARY_FIELDS:
            additional_rows.append(
                {
                    "Field": field,
                    "Value": (
                        clean_text(row.get(field, ""))
                        or "—"
                    ),
                }
            )

        st.dataframe(
            pd.DataFrame(additional_rows),
            width="stretch",
            hide_index=True,
        )


def render_service_records_page(
    response_csv_file: str | Path = "pm_responses.csv",
    aed_csv_file: str | Path = "aed_data.csv",
    manual_service_file: str | Path = MANUAL_SERVICE_RECORDS_FILE,
    issue_record_file: str | Path = ISSUE_RECORD_FILE,
    resolution_file: str | Path = ISSUE_RESOLUTION_FILE,
) -> None:
    page_header(
        "Service Records",
        "Search, filter, review and export PM Checklist, Unit Profile service and Issue resolution records.",
        eyebrow="MAINTENANCE · TRACE",
        chip="SUBMISSION HISTORY",
        capabilities=[
            ("Linked filters", "Narrow records by service date, technician, model and checklist result."),
            ("Record detail", "Open one submission and review every captured inspection field."),
            ("Export view", "Download the currently filtered result for reporting or follow-up."),
        ],
    )

    try:
        records = load_service_records(
            response_csv_file=response_csv_file,
            aed_csv_file=aed_csv_file,
            manual_service_file=manual_service_file,
            issue_record_file=issue_record_file,
            resolution_file=resolution_file,
        )
    except pd.errors.EmptyDataError:
        st.info("pm_responses.csv is currently empty.")
        return
    except Exception as error:
        st.error(f"Failed to load Service Records: {error}")
        return

    if records.empty:
        st.info(
            "No Service Records have been saved yet. A record appears after a PM "
            "Checklist submission, Add Service in a Unit Profile, or an Issue resolution submission."
        )
        return

    scope_counts = service_record_scope_counts(records)
    scope_options = ["All Records", "Matched", "Mismatch", "Loaner"]
    current_scope = clean_text(st.session_state.get("service_records_scope", "All Records"))
    if current_scope not in scope_options:
        st.session_state["service_records_scope"] = "All Records"

    st.markdown("### Record Scope")
    if hasattr(st, "segmented_control"):
        record_scope = st.segmented_control(
            "Record Scope",
            options=scope_options,
            key="service_records_scope",
            label_visibility="collapsed",
        ) or "All Records"
    else:
        record_scope = st.radio(
            "Record Scope",
            options=scope_options,
            key="service_records_scope",
            horizontal=True,
            label_visibility="collapsed",
        )
    scope_columns = st.columns(4, gap="small")
    for column, scope_name in zip(scope_columns, scope_options):
        column.metric(scope_name, scope_counts[scope_name])
    st.caption(
        "Matched means the record serial number belongs to the recorded postal code "
        "in the current Master Table. Mismatch records are grouped for follow-up; "
        "the page does not add duplicate postal-code fields or a mismatch-reason column."
    )

    table_column, filter_column = st.columns(
        [4.35, 1.45],
        gap="large",
    )

    with filter_column:
        st.markdown("### Filters")

        keyword = st.text_input(
            "Keyword Search",
            placeholder=(
                "Serial, location, postal code, "
                "lift lobby or pads lot number"
            ),
            key="service_records_keyword",
        )

        with st.expander("Custom Date Range", expanded=False):
            start_column, end_column = st.columns(2)

            with start_column:
                start_date = st.date_input(
                    "From",
                    value=None,
                    format="DD-MM-YYYY",
                    key="service_records_date_from",
                )

            with end_column:
                end_date = st.date_input(
                    "To",
                    value=None,
                    format="DD-MM-YYYY",
                    key="service_records_date_to",
                )

        _normalise_service_record_filter_state(
            dataframe=records,
            keyword=keyword,
            start_date=start_date,
            end_date=end_date,
            record_scope=record_scope,
        )
        selections = _service_record_filter_selections_from_state()

        dynamic_month_values = linked_service_record_options(
            dataframe=records,
            target_filter="month",
            keyword=keyword,
            start_date=start_date,
            end_date=end_date,
            selections=selections,
            record_scope=record_scope,
        )
        all_month_labels = dict(available_months(records))
        month_labels = {
            "": "All months",
            **{
                month_value: all_month_labels.get(
                    month_value,
                    month_value,
                )
                for month_value in dynamic_month_values
            },
        }

        selected_month = st.selectbox(
            "Filter by Month",
            options=list(month_labels.keys()),
            format_func=lambda value: month_labels[value],
            key="service_records_month",
            on_change=_mark_service_record_filter_changed,
            args=("month",),
            help="Show records whose Service Date falls within the selected month.",
        )
        selections["month"] = (
            [selected_month]
            if selected_month
            else []
        )

        with st.expander("Record Filters", expanded=True):
            selected_filters: dict[str, list[str]] = {}
            filter_labels = {
                "technician": "Technician",
                "service_type": "Service Type",
                "battery_replaced": "Battery Replaced",
                "model": "Model",
                "record_source": "Record Source",
                "record_status": "Record Status",
                "loaner": "Loaner Unit",
            }

            for filter_name, label in filter_labels.items():
                options = linked_service_record_options(
                    dataframe=records,
                    target_filter=filter_name,
                    keyword=keyword,
                    start_date=start_date,
                    end_date=end_date,
                    selections=selections,
                    record_scope=record_scope,
                )

                selected_filters[filter_name] = st.multiselect(
                    label,
                    options=options,
                    key=SERVICE_RECORD_FILTER_KEYS[filter_name],
                    on_change=_mark_service_record_filter_changed,
                    args=(filter_name,),
                )
                selections[filter_name] = selected_filters[filter_name]

            technicians = selected_filters["technician"]
            service_types = selected_filters["service_type"]
            battery_replaced_values = selected_filters[
                "battery_replaced"
            ]
            models = selected_filters["model"]
            record_sources = selected_filters["record_source"]
            record_statuses = selected_filters["record_status"]
            loaner_values = selected_filters["loaner"]

        st.button(
            "Reset Filters",
            width="stretch",
            key="reset_service_record_filters_button",
            on_click=reset_service_record_filters,
        )

    filtered = apply_filters(
        dataframe=records,
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
        selected_month=selected_month,
        technicians=technicians,
        service_types=service_types,
        battery_replaced_values=battery_replaced_values,
        models=models,
        record_sources=record_sources,
        record_statuses=record_statuses,
        loaner_values=loaner_values,
        record_scope=record_scope,
    )

    with table_column:
        metric_left, metric_right, metric_space = st.columns(
            [1, 1, 3]
        )
        metric_left.metric(
            "Total Records",
            len(records),
        )
        metric_right.metric(
            "Visible Records",
            len(filtered),
        )

        display_columns = [
            column
            for column in PRIORITY_COLUMNS
            if column in filtered.columns
        ]

        st.dataframe(
            filtered[display_columns],
            width="stretch",
            hide_index=True,
            height=430,
        )

        export_name = (
            f"service_records_"
            f"{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )

        st.download_button(
            "Export Filtered Records",
            data=export_dataframe(filtered),
            file_name=export_name,
            mime="text/csv",
            disabled=filtered.empty,
            width="content",
        )

    st.divider()

    if filtered.empty:
        st.info(
            "No Service Records match the current filters."
        )
        return

    valid_record_indices = filtered.index.tolist()
    if st.session_state.get("selected_service_record") not in valid_record_indices:
        st.session_state.pop("selected_service_record", None)

    selected_index = st.selectbox(
        "Select a Service Record",
        options=valid_record_indices,
        format_func=lambda row_index: record_label(
            filtered,
            row_index,
        ),
        key="selected_service_record",
    )

    render_record_details(
        filtered.loc[selected_index],
        issue_record_file=issue_record_file,
    )
