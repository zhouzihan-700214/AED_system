"""Helpers for safe cell-level editing of filtered AED results."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from services.aed_field_schema import (
    DATE_FIELDS,
    JOB_TYPE_OPTIONS,
    REPAIRED_OPTIONS,
    REQUIRED_FIELDS,
    TABLE_EDITABLE_COLUMNS,
)


def is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip().casefold() in {"", "nan", "nat", "none"}


def normalize_date(value: Any) -> str:
    """Convert a supported date-like value to DD-MM-YYYY for project storage."""
    if is_empty_value(value):
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d-%m-%Y")
    if isinstance(value, date):
        return value.strftime("%d-%m-%Y")

    text = str(value).strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        raise ValueError(f"Invalid date value: {value}")
    return pd.Timestamp(parsed).strftime("%d-%m-%Y")


def normalize_postal_code(value: Any) -> str:
    if is_empty_value(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    else:
        text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    text = text.replace(" ", "")
    if not text.isdigit():
        raise ValueError("Postal Code must contain digits only.")
    if len(text) > 6:
        raise ValueError("Postal Code must contain no more than six digits.")
    return text.zfill(6)


def normalize_value(field: str, value: Any) -> str:
    if field in DATE_FIELDS:
        return normalize_date(value)
    if field == "Postal Code":
        return normalize_postal_code(value)
    if is_empty_value(value):
        return ""
    return str(value).strip()


def _editor_date(value: Any) -> date | None:
    normalized = normalize_date(value)
    if not normalized:
        return None
    return datetime.strptime(normalized, "%d-%m-%Y").date()


def prepare_editor_dataframe(source_df: pd.DataFrame) -> pd.DataFrame:
    required_columns = ["Serial Number", *TABLE_EDITABLE_COLUMNS]
    editor_df = source_df.copy()
    for column in required_columns:
        if column not in editor_df.columns:
            editor_df[column] = ""
    editor_df = editor_df[required_columns].copy()
    editor_df["Serial Number"] = (
        editor_df["Serial Number"].astype(str).str.strip().str.upper()
    )
    if editor_df["Serial Number"].eq("").any():
        raise ValueError("The editor contains an empty Serial Number.")
    duplicates = editor_df.loc[
        editor_df["Serial Number"].duplicated(keep=False), "Serial Number"
    ].unique()
    if len(duplicates):
        raise ValueError(
            "Duplicate Serial Numbers found: " + ", ".join(map(str, duplicates))
        )

    for field in DATE_FIELDS:
        if field in editor_df.columns:
            editor_df[field] = editor_df[field].map(_editor_date)
    if "Postal Code" in editor_df.columns:
        editor_df["Postal Code"] = editor_df["Postal Code"].map(normalize_postal_code)

    editor_df = editor_df.sort_values("Serial Number", kind="stable")
    editor_df = editor_df.set_index("Serial Number", drop=False)
    return editor_df


def build_cell_changes(
    original_df: pd.DataFrame,
    edited_df: pd.DataFrame,
) -> list[dict[str, str]]:
    original = original_df.copy()
    edited = edited_df.copy()
    for name, frame in (("Original", original), ("Edited", edited)):
        if "Serial Number" not in frame.columns:
            raise ValueError(f"{name} data has no Serial Number column.")
        frame["Serial Number"] = frame["Serial Number"].astype(str).str.strip().str.upper()
        frame.set_index("Serial Number", drop=False, inplace=True)

    original_serials = set(original.index)
    edited_serials = set(edited.index)
    if original_serials != edited_serials:
        raise ValueError(
            "Rows were unexpectedly added or removed in the editor. "
            f"Missing: {sorted(original_serials - edited_serials)}; "
            f"Unexpected: {sorted(edited_serials - original_serials)}"
        )

    changes: list[dict[str, str]] = []
    for serial in edited.index:
        for field in TABLE_EDITABLE_COLUMNS:
            if field not in original.columns or field not in edited.columns:
                continue
            old_value = normalize_value(field, original.at[serial, field])
            new_value = normalize_value(field, edited.at[serial, field])
            if old_value == new_value:
                continue
            changes.append(
                {
                    "serial_number": serial,
                    "field": field,
                    "original_value": old_value,
                    "desired_value": new_value,
                }
            )
    return changes


def build_final_rows(
    original_df: pd.DataFrame,
    changes: list[dict[str, str]],
) -> dict[str, dict[str, str]]:
    original = original_df.copy()
    original["Serial Number"] = original["Serial Number"].astype(str).str.strip().str.upper()
    original = original.set_index("Serial Number", drop=False)
    affected = {change["serial_number"] for change in changes}
    final_rows: dict[str, dict[str, str]] = {}
    for serial in affected:
        if serial not in original.index:
            raise ValueError(f"Unknown Serial Number in changes: {serial}")
        final_rows[serial] = {
            field: normalize_value(field, original.at[serial, field])
            for field in original.columns
            if field != "Serial Number"
        }
    for change in changes:
        final_rows[change["serial_number"]][change["field"]] = change["desired_value"]
    return final_rows


def validate_table_changes(
    original_df: pd.DataFrame,
    changes: list[dict[str, str]],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    final_rows = build_final_rows(original_df, changes)
    changed_by_serial: dict[str, set[str]] = {}
    for change in changes:
        changed_by_serial.setdefault(change["serial_number"], set()).add(change["field"])

    for serial, row in final_rows.items():
        changed_fields = changed_by_serial.get(serial, set())
        for field in REQUIRED_FIELDS - {"Serial Number"}:
            if field in changed_fields and is_empty_value(row.get(field, "")):
                errors.append(f"{serial}: {field} is required.")

        postal = row.get("Postal Code", "")
        if postal and (not postal.isdigit() or len(postal) != 6):
            errors.append(f"{serial}: Postal Code must be exactly six digits.")

        if "Job Type" in changed_fields:
            job_type = row.get("Job Type", "")
            if job_type and job_type not in JOB_TYPE_OPTIONS:
                errors.append(f"{serial}: Invalid Job Type.")
        if "Repaired?" in changed_fields:
            repaired = row.get("Repaired?", "")
            if repaired and repaired not in REPAIRED_OPTIONS:
                errors.append(f"{serial}: Invalid Repaired? value.")

        completed = row.get("PM Completed Date", "")
        next_pm = row.get("Next PM Date", "")
        if completed and next_pm:
            completed_date = datetime.strptime(completed, "%d-%m-%Y").date()
            next_date = datetime.strptime(next_pm, "%d-%m-%Y").date()
            if next_date < completed_date:
                errors.append(
                    f"{serial}: Next PM Date cannot be before PM Completed Date."
                )

        for field in (
            "Adult Pads Expiry Date",
            "Pediatric Pads Expiry Date",
            "Battery Expiry Date",
        ):
            expiry = row.get(field, "")
            if expiry and datetime.strptime(expiry, "%d-%m-%Y").date() < date.today():
                warnings.append(f"{serial}: {field} is already past.")

    return errors, warnings


def group_changes_for_repository(changes: list[dict[str, str]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for change in changes:
        serial = change["serial_number"]
        item = grouped.setdefault(
            serial,
            {
                "serial_number": serial,
                "original_values": {},
                "desired_values": {},
            },
        )
        item["original_values"][change["field"]] = change["original_value"]
        item["desired_values"][change["field"]] = change["desired_value"]
    return list(grouped.values())
