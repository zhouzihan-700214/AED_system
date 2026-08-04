from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from services.csv_storage import atomic_write_csv
from utils.text_utils import clean_text
from .geocoding_service import geocode_postal_code


AED_COLUMNS = [
    "Serial Number",
    "Installation Date",
    "Model",
    "Installed Phase / Month",
    "PO Number",
    "Zone",
    "Block / Locations",
    "Street Name",
    "Location",
    "Postal Code",
    "Level",
    "Lift Lobby",
    "Adult Pads Replacement Date",
    "Adult Pads Expiry Date",
    "Adult Pads Lot Number",
    "Pediatric Pads Replacement Date",
    "Pediatric Pads Expiry Date",
    "Pediatric Pads Lot Number",
    "Battery Replacement History",
    "Battery Expiry Date",
    "PM Completed Date",
    "Next PM Date",
    "PM Interval Months",
    "Job Type",
    "Last Done By",
    "Service Report e-SR",
    "Remarks",
    "Patrol Schedule",
    "PM Schedule (H1)",
    "PM Schedule (H2)",
    "Repaired?",
]

# These columns are maintained automatically and are not shown in the
# editable AED Management table.
SYSTEM_COLUMNS = [
    "Latitude",
    "Longitude",
    "OneMap Address",
    "Geocoding Status",
]

MASTER_COLUMNS = AED_COLUMNS + SYSTEM_COLUMNS

DATE_COLUMNS = [
    "Installation Date",
    "Adult Pads Replacement Date",
    "Adult Pads Expiry Date",
    "Pediatric Pads Replacement Date",
    "Pediatric Pads Expiry Date",
    "Battery Expiry Date",
    "PM Completed Date",
    "Next PM Date",
]

SEARCH_COLUMNS = [
    "Serial Number",
    "Model",
    "Installed Phase / Month",
    "PO Number",
    "Zone",
    "Block / Locations",
    "Street Name",
    "Location",
    "Postal Code",
    "Level",
    "Lift Lobby",
    "Adult Pads Lot Number",
    "Pediatric Pads Lot Number",
    "Service Report e-SR",
    "Remarks",
]

LINKED_FILTER_COLUMNS = {
    "model": "Model",
    "location": "Location",
    "postal_code": "Postal Code",
    "lift_lobby": "Lift Lobby",
    "job_type": "Job Type",
    "last_done_by": "Last Done By",
}

HISTORY_COLUMNS = [
    "Source",
    "Action",
    "Changed At",
    "Serial Number Before",
    "Serial Number After",
    "Field Name",
    "Old Value",
    "New Value",
]


def parse_date(value: Any) -> pd.Timestamp | None:
    text = clean_text(value)
    if not text:
        return None

    parsed = pd.to_datetime(text, format="%d-%m-%Y", errors="coerce")
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed)


def format_date(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""

    if isinstance(value, str):
        parsed = parse_date(value)
    else:
        parsed = pd.to_datetime(value, errors="coerce")

    if pd.isna(parsed):
        return ""
    return pd.Timestamp(parsed).strftime("%d-%m-%Y")


def calculate_next_pm_date(
    pm_completed_value: Any,
    interval_months: Any = 12,
) -> str:
    completed = parse_date(pm_completed_value)
    if completed is None or pd.isna(completed):
        return ""

    try:
        months = int(clean_text(interval_months))
    except (TypeError, ValueError):
        months = 12
    if months <= 0:
        months = 12

    return (
        pd.Timestamp(completed) + pd.DateOffset(months=months)
    ).strftime("%d-%m-%Y")


def ensure_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy()

    for column in MASTER_COLUMNS:
        if column not in result.columns:
            result[column] = ""

    # Preserve the user-facing AED columns plus the automatically maintained
    # coordinate columns required by the map.
    result = result[MASTER_COLUMNS]

    for column in MASTER_COLUMNS:
        result[column] = result[column].map(
            lambda value: "" if pd.isna(value) else str(value).strip()
        )

    return result


def load_aed_data(csv_file: str | Path) -> pd.DataFrame:
    path = Path(csv_file)

    if not path.exists():
        empty = pd.DataFrame(columns=MASTER_COLUMNS)
        atomic_write_csv(empty, path, preferred_columns=MASTER_COLUMNS)
        return empty

    dataframe = pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    ).fillna("")

    return ensure_columns(dataframe)


def save_aed_data(dataframe: pd.DataFrame, csv_file: str | Path) -> None:
    output = ensure_columns(dataframe)

    for column in DATE_COLUMNS:
        output[column] = output[column].map(format_date)

    atomic_write_csv(output, csv_file, preferred_columns=MASTER_COLUMNS)


def prepare_editor_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    # Coordinates are system-managed, so only the agreed user-editable
    # columns are sent to st.data_editor.
    editor_df = dataframe[AED_COLUMNS].copy()
    editor_df["PM Interval Months"] = pd.to_numeric(
        editor_df["PM Interval Months"],
        errors="coerce",
    ).fillna(12).astype(int)

    for column in DATE_COLUMNS:
        editor_df[column] = editor_df[column].map(parse_date)

    editor_df.insert(0, "_Row Index", editor_df.index.astype(int))
    return editor_df.reset_index(drop=True)


def _text_contains(series: pd.Series, keyword: str) -> pd.Series:
    return (
        series.astype(str)
        .str.casefold()
        .str.contains(keyword.casefold(), na=False, regex=False)
    )


def apply_filters(
    dataframe: pd.DataFrame,
    keyword: str = "",
    model: list[str] | None = None,
    location: list[str] | None = None,
    postal_code: list[str] | None = None,
    lift_lobby: list[str] | None = None,
    job_type: list[str] | None = None,
    last_done_by: list[str] | None = None,
    date_ranges: dict[str, tuple[Any, Any]] | None = None,
    sort_by: str = "Serial Number",
    ascending: bool = True,
) -> pd.DataFrame:
    result = dataframe.copy()

    if clean_text(keyword):
        mask = pd.Series(False, index=result.index)
        for column in SEARCH_COLUMNS:
            mask |= _text_contains(result[column], clean_text(keyword))
        result = result.loc[mask]

    selections = {
        "Model": model,
        "Location": location,
        "Postal Code": postal_code,
        "Lift Lobby": lift_lobby,
        "Job Type": job_type,
        "Last Done By": last_done_by,
    }

    for column, selected_values in selections.items():
        if selected_values:
            result = result[result[column].isin(selected_values)]

    for column, bounds in (date_ranges or {}).items():
        start_value, end_value = bounds
        parsed_series = result[column].map(parse_date)

        if start_value is not None:
            result = result.loc[parsed_series >= pd.Timestamp(start_value)]
            parsed_series = result[column].map(parse_date)

        if end_value is not None:
            result = result.loc[parsed_series <= pd.Timestamp(end_value)]

    if sort_by in result.columns:
        if sort_by in DATE_COLUMNS:
            sort_values = result[sort_by].map(parse_date)
            result = result.assign(_sort_value=sort_values).sort_values(
                "_sort_value",
                ascending=ascending,
                na_position="last",
            ).drop(columns="_sort_value")
        else:
            result = result.sort_values(
                sort_by,
                ascending=ascending,
                na_position="last",
                key=lambda s: s.astype(str).str.casefold(),
            )

    return result


def linked_filter_options(
    dataframe: pd.DataFrame,
    target_filter: str,
    keyword: str = "",
    selections: dict[str, list[str]] | None = None,
    date_ranges: dict[str, tuple[Any, Any]] | None = None,
) -> list[str]:
    """Return options for one filter after applying every other filter."""

    if target_filter not in LINKED_FILTER_COLUMNS:
        valid_names = ", ".join(LINKED_FILTER_COLUMNS)
        raise ValueError(
            f"Unknown linked filter '{target_filter}'. "
            f"Expected one of: {valid_names}."
        )

    active = {
        name: list(values or [])
        for name, values in (selections or {}).items()
        if name in LINKED_FILTER_COLUMNS
    }
    for name in LINKED_FILTER_COLUMNS:
        active.setdefault(name, [])

    # Ignore the target filter itself so that its options are controlled by
    # all the other active facets. This supports proper multi-select behavior.
    active[target_filter] = []

    filtered = apply_filters(
        dataframe=dataframe,
        keyword=keyword,
        model=active["model"],
        location=active["location"],
        postal_code=active["postal_code"],
        lift_lobby=active["lift_lobby"],
        job_type=active["job_type"],
        last_done_by=active["last_done_by"],
        date_ranges=date_ranges,
        sort_by="Serial Number",
        ascending=True,
    )

    return unique_values(
        filtered,
        LINKED_FILTER_COLUMNS[target_filter],
    )


def unique_values(dataframe: pd.DataFrame, column: str) -> list[str]:
    return sorted(
        {
            clean_text(value)
            for value in dataframe[column].tolist()
            if clean_text(value)
        },
        key=str.casefold,
    )


def validate_date_fields(record: pd.Series) -> list[str]:
    errors: list[str] = []

    for column in DATE_COLUMNS:
        value = record.get(column, "")
        if clean_text(value) and pd.isna(parse_date(value)):
            errors.append(
                f"{column} must be a real date in DD-MM-YYYY format."
            )

    interval_text = clean_text(record.get("PM Interval Months", "")) or "12"
    try:
        interval = int(interval_text)
    except ValueError:
        interval = 0
    if interval < 1 or interval > 60:
        errors.append("PM Interval Months must be a whole number from 1 to 60.")

    return errors


def duplicate_serial_exists(
    dataframe: pd.DataFrame,
    serial_number: str,
    exclude_index: int | None = None,
) -> bool:
    serial = clean_text(serial_number).casefold()
    if not serial:
        return False

    candidates = dataframe.copy()
    if exclude_index is not None and exclude_index in candidates.index:
        candidates = candidates.drop(index=exclude_index)

    return (
        candidates["Serial Number"]
        .astype(str)
        .str.strip()
        .str.casefold()
        .eq(serial)
        .any()
    )


def append_history_rows(
    history_rows: list[dict[str, str]],
    history_file: str | Path,
) -> None:
    if not history_rows:
        return

    path = Path(history_file)
    new_history = pd.DataFrame(history_rows, columns=HISTORY_COLUMNS)

    if path.exists():
        existing = pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        ).fillna("")

        for column in HISTORY_COLUMNS:
            if column not in existing.columns:
                existing[column] = ""

        existing = existing[HISTORY_COLUMNS]
        combined = pd.concat([new_history, existing], ignore_index=True)
    else:
        combined = new_history

    atomic_write_csv(combined, path, preferred_columns=HISTORY_COLUMNS)


def save_editor_changes(
    master_dataframe: pd.DataFrame,
    edited_dataframe: pd.DataFrame,
    csv_file: str | Path,
    history_file: str | Path,
) -> tuple[pd.DataFrame, int]:
    updated = ensure_columns(master_dataframe)
    history_rows: list[dict[str, str]] = []
    changed_at = datetime.now().astimezone().strftime("%d-%m-%Y %H:%M:%S")
    changed_fields = 0

    def record_change(
        row_index: int,
        column: str,
        old_value: str,
        new_value: str,
        serial_before: str,
        serial_after: str,
        action: str = "Table Edit",
    ) -> None:
        if old_value == new_value:
            return

        updated.at[row_index, column] = new_value
        history_rows.append(
            {
                "Source": "AED Management",
                "Action": action,
                "Changed At": changed_at,
                "Serial Number Before": serial_before,
                "Serial Number After": serial_after,
                "Field Name": column,
                "Old Value": old_value,
                "New Value": new_value,
            }
        )

    for _, edited_row in edited_dataframe.iterrows():
        row_index = int(edited_row["_Row Index"])

        if row_index not in updated.index:
            continue

        original_row = updated.loc[row_index].copy()
        serial_before = clean_text(original_row.get("Serial Number", ""))

        normalized_values: dict[str, str] = {}
        for column in AED_COLUMNS:
            value = edited_row.get(column, "")
            normalized_values[column] = (
                format_date(value) if column in DATE_COLUMNS else clean_text(value)
            )

        errors = validate_date_fields(pd.Series(normalized_values))
        if errors:
            raise ValueError(" ".join(errors))

        new_serial = normalized_values["Serial Number"]
        if duplicate_serial_exists(updated, new_serial, exclude_index=row_index):
            raise ValueError(
                f"Serial Number '{new_serial}' already exists. "
                "A non-empty Serial Number must be unique."
            )

        original_pm_date = clean_text(original_row.get("PM Completed Date", ""))
        new_pm_date = normalized_values["PM Completed Date"]
        original_interval = clean_text(original_row.get("PM Interval Months", "")) or "12"
        new_interval = normalized_values.get("PM Interval Months", "") or "12"
        normalized_values["PM Interval Months"] = new_interval

        if new_pm_date != original_pm_date or new_interval != original_interval:
            normalized_values["Next PM Date"] = calculate_next_pm_date(
                new_pm_date,
                new_interval,
            )

        serial_after = normalized_values["Serial Number"]

        for column in AED_COLUMNS:
            old_value = clean_text(original_row.get(column, ""))
            new_value = normalized_values[column]

            if old_value == new_value:
                continue

            record_change(
                row_index=row_index,
                column=column,
                old_value=old_value,
                new_value=new_value,
                serial_before=serial_before,
                serial_after=serial_after,
            )
            changed_fields += 1

        old_postal_code = clean_text(original_row.get("Postal Code", ""))
        new_postal_code = normalized_values["Postal Code"]

        # Only a Postal Code change triggers another OneMap lookup.
        if new_postal_code != old_postal_code:
            geocoding_result = geocode_postal_code(new_postal_code)

            coordinate_values = {
                "Latitude": geocoding_result.latitude,
                "Longitude": geocoding_result.longitude,
                "OneMap Address": geocoding_result.address,
                "Geocoding Status": geocoding_result.status,
            }

            for column, new_value in coordinate_values.items():
                old_value = clean_text(original_row.get(column, ""))

                record_change(
                    row_index=row_index,
                    column=column,
                    old_value=old_value,
                    new_value=clean_text(new_value),
                    serial_before=serial_before,
                    serial_after=serial_after,
                    action="Automatic Coordinate Update",
                )

    save_aed_data(updated, csv_file)
    append_history_rows(history_rows, history_file)
    return updated, changed_fields


def add_aed_record(
    dataframe: pd.DataFrame,
    values: dict[str, Any],
    csv_file: str | Path,
    history_file: str | Path,
) -> tuple[pd.DataFrame, str]:
    row = {column: "" for column in MASTER_COLUMNS}

    for column in AED_COLUMNS:
        value = values.get(column, "")
        row[column] = format_date(value) if column in DATE_COLUMNS else clean_text(value)

    errors = validate_date_fields(pd.Series(row))
    if errors:
        raise ValueError(" ".join(errors))

    if duplicate_serial_exists(dataframe, row["Serial Number"]):
        raise ValueError(
            f"Serial Number '{row['Serial Number']}' already exists. "
            "A non-empty Serial Number must be unique."
        )

    row["PM Interval Months"] = row.get("PM Interval Months", "") or "12"
    if row["PM Completed Date"]:
        row["Next PM Date"] = calculate_next_pm_date(
            row["PM Completed Date"],
            row["PM Interval Months"],
        )

    # The user enters only Postal Code. Coordinates are obtained automatically.
    geocoding_result = geocode_postal_code(row["Postal Code"])
    row["Latitude"] = geocoding_result.latitude
    row["Longitude"] = geocoding_result.longitude
    row["OneMap Address"] = geocoding_result.address
    row["Geocoding Status"] = geocoding_result.status

    updated = pd.concat(
        [ensure_columns(dataframe), pd.DataFrame([row], columns=MASTER_COLUMNS)],
        ignore_index=True,
    )

    save_aed_data(updated, csv_file)

    changed_at = datetime.now().astimezone().strftime("%d-%m-%Y %H:%M:%S")
    history_rows = []

    for column, value in row.items():
        if value == "":
            continue

        history_rows.append(
            {
                "Source": "AED Management",
                "Action": "Add AED",
                "Changed At": changed_at,
                "Serial Number Before": "",
                "Serial Number After": row["Serial Number"],
                "Field Name": column,
                "Old Value": "",
                "New Value": value,
            }
        )

    append_history_rows(history_rows, history_file)

    if geocoding_result.success:
        message = "AED record added successfully with map coordinates."
    else:
        message = (
            "AED record added, but coordinates were not obtained: "
            f"{geocoding_result.status}"
        )

    return updated, message



def delete_aed_record(
    dataframe: pd.DataFrame,
    row_index: int,
    csv_file: str | Path,
    history_file: str | Path,
) -> pd.DataFrame:
    """Delete one AED row and preserve its previous values in the audit log."""
    if row_index not in dataframe.index:
        raise IndexError("The selected AED record no longer exists.")

    deleted_row = dataframe.loc[row_index].copy()
    serial_before = clean_text(
        deleted_row.get("Serial Number", "")
    )
    changed_at = datetime.now().astimezone().strftime(
        "%d-%m-%Y %H:%M:%S"
    )

    history_rows: list[dict[str, str]] = []

    for column in MASTER_COLUMNS:
        old_value = clean_text(deleted_row.get(column, ""))

        if not old_value:
            continue

        history_rows.append(
            {
                "Source": "AED Management",
                "Action": "Delete AED",
                "Changed At": changed_at,
                "Serial Number Before": serial_before,
                "Serial Number After": "",
                "Field Name": column,
                "Old Value": old_value,
                "New Value": "",
            }
        )

    # Even a completely blank row still receives one deletion record.
    if not history_rows:
        history_rows.append(
            {
                "Source": "AED Management",
                "Action": "Delete AED",
                "Changed At": changed_at,
                "Serial Number Before": "",
                "Serial Number After": "",
                "Field Name": "Record",
                "Old Value": "Blank AED row",
                "New Value": "",
            }
        )

    updated = dataframe.drop(index=row_index).reset_index(drop=True)

    save_aed_data(updated, csv_file)
    append_history_rows(history_rows, history_file)

    return updated

def load_history(history_file: str | Path) -> pd.DataFrame:
    path = Path(history_file)

    if not path.exists():
        return pd.DataFrame(columns=HISTORY_COLUMNS)

    history = pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    ).fillna("")

    for column in HISTORY_COLUMNS:
        if column not in history.columns:
            history[column] = ""

    return history[HISTORY_COLUMNS]
