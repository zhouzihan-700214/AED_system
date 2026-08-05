"""Pure data service for the Service Records page.

This module intentionally contains no Streamlit calls. It combines committed
PM Checklist submissions and structured records added from Unit Profiles, so
both the UI and automated workflow tests read the same source of truth.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import ISSUE_RECORD_FILE, ISSUE_RESOLUTION_FILE
from services.manual_service_storage import MANUAL_SERVICE_RECORDS_FILE
from services.aed_repository import get_all_units
from services.csv_storage import read_csv_safe
from services.unit_profile_service import load_manual_service_records
from utils.text_utils import clean_text


def _parse_mixed_datetime(series: pd.Series) -> pd.Series:
    """Parse current and legacy record dates without silently hiding rows."""

    values = series.astype(str).str.strip()
    try:
        return pd.to_datetime(
            values,
            format="mixed",
            dayfirst=True,
            errors="coerce",
        )
    except (TypeError, ValueError):
        # Compatibility fallback for older pandas versions.
        return pd.to_datetime(values, dayfirst=True, errors="coerce")


def parse_service_date_series(series: pd.Series) -> pd.Series:
    return _parse_mixed_datetime(series)


def parse_submitted_at_series(series: pd.Series) -> pd.Series:
    return _parse_mixed_datetime(series)


def load_aed_lookup(
    aed_csv_file: str | Path | None = None,
    *,
    aed_dataframe: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return the Serial/Model/Location lookup used to enrich service rows.

    ``aed_csv_file`` remains accepted for backward compatibility. Runtime data
    is loaded through the shared AED repository unless a dataframe is supplied
    explicitly by a test or another service.
    """
    del aed_csv_file
    dataframe = (
        aed_dataframe.copy()
        if aed_dataframe is not None
        else get_all_units().copy()
    )

    for column in ["Serial Number", "Model", "Location", "Postal Code"]:
        if column not in dataframe.columns:
            dataframe[column] = ""
        dataframe[column] = dataframe[column].astype(str).str.strip()

    return dataframe[["Serial Number", "Model", "Location", "Postal Code"]].copy()


def create_lookup_map(dataframe: pd.DataFrame, value_column: str) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for _, row in dataframe.iterrows():
        serial = clean_text(row.get("Serial Number", ""))
        value = clean_text(row.get(value_column, ""))
        if serial and serial.casefold() not in lookup:
            lookup[serial.casefold()] = value
    return lookup


def _normalise_serial(value: object) -> str:
    """Normalise serial numbers for comparison without changing saved values."""

    return "".join(clean_text(value).casefold().split())


def _normalise_postal_code(value: object) -> str:
    """Normalise postal codes for comparison while preserving non-numeric data."""

    text = clean_text(value)
    digits = "".join(character for character in text if character.isdigit())
    if digits:
        return digits
    return "".join(text.casefold().split())


def normalise_loaner_value(value: object) -> str:
    """Return the stable Yes/No value used by Service Records filters."""

    text = clean_text(value).casefold()
    return "Yes" if text in {"yes", "y", "true", "1", "loaner"} else "No"


def add_record_match_status(
    records: pd.DataFrame,
    aed_lookup: pd.DataFrame,
) -> pd.DataFrame:
    """Classify each record as Matched, Mismatch, or Loaner.

    A non-loaner record is Matched only when its recorded serial number is one
    of the serial numbers assigned to its recorded postal code in the current
    Master Table. Missing or unrecognised identifiers are deliberately marked
    Mismatch so they remain visible for follow-up. No comparison reason or
    duplicate postal-code fields are added to the record.
    """

    checked = records.copy()
    for column in ["AED Serial Number", "Original Serial Number", "Postal Code", "Loaner Unit"]:
        if column not in checked.columns:
            checked[column] = ""

    serials_by_postal: dict[str, set[str]] = {}
    for _, row in aed_lookup.iterrows():
        serial = _normalise_serial(row.get("Serial Number", ""))
        postal = _normalise_postal_code(row.get("Postal Code", ""))
        if serial and postal:
            serials_by_postal.setdefault(postal, set()).add(serial)

    statuses: list[str] = []
    normalised_loaner: list[str] = []
    for _, row in checked.iterrows():
        loaner = normalise_loaner_value(row.get("Loaner Unit", ""))
        normalised_loaner.append(loaner)
        if loaner == "Yes":
            statuses.append("Loaner")
            continue

        serial = _normalise_serial(row.get("AED Serial Number", ""))
        if not serial:
            serial = _normalise_serial(row.get("Original Serial Number", ""))
        postal = _normalise_postal_code(row.get("Postal Code", ""))
        allowed_serials = serials_by_postal.get(postal, set()) if postal else set()
        statuses.append("Matched" if serial and serial in allowed_serials else "Mismatch")

    checked["Loaner Unit"] = normalised_loaner
    checked["Record Match"] = statuses
    return checked


def service_record_scope_counts(records: pd.DataFrame) -> dict[str, int]:
    """Return counts displayed in the clickable Service Records scope."""

    status = records.get("Record Match", pd.Series("", index=records.index)).astype(str)
    return {
        "All Records": int(len(records)),
        "Matched": int(status.eq("Matched").sum()),
        "Mismatch": int(status.eq("Mismatch").sum()),
        "Loaner": int(status.eq("Loaner").sum()),
    }


def manual_records_for_service_page(
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
    result["AED Model"] = manual["AED Model"]
    result["AED Location"] = manual["AED Location"]
    result["Postal Code"] = manual["Postal Code"]
    result["Lift Lobby"] = manual["Lift Lobby"]
    result["Submitted At"] = manual["Created At"]
    result["Submitted By"] = manual["Created By"]
    result["Record Source"] = manual["Source"].replace("", "Unit Profile")
    result["Record Status"] = manual["Status"]
    result["Service Notes"] = manual["Details"]
    result["Service Report e-SR"] = manual["Reference"]
    result["Master Data Updated"] = manual["Master Data Updated"]
    result["PM Dates Updated"] = manual["PM Dates Updated"]
    battery_replaced = manual["Battery Replaced"].astype(str).str.strip()
    legacy_battery = (
        manual["Service Type"].astype(str).str.contains(
            "batt|battery", case=False, regex=True, na=False
        )
        & manual["Status"].astype(str).str.strip().str.casefold().eq("completed")
    ).map({True: "Yes", False: "No"})
    result["Battery Replaced"] = battery_replaced.where(
        battery_replaced.ne(""), legacy_battery
    )
    result["Battery History Updated"] = manual["Battery History Updated"]
    result["PM Interval Months Used"] = manual["PM Interval Months Used"]
    result["Linked Plan ID"] = manual["Linked Plan ID"]
    result["Master Operation ID"] = manual["Master Operation ID"]
    result["Loaner Unit"] = "No"
    return result.fillna("")


def issue_resolution_records_for_service_page(
    issue_record_file: str | Path = ISSUE_RECORD_FILE,
    resolution_file: str | Path = ISSUE_RESOLUTION_FILE,
) -> pd.DataFrame:
    """Normalise Issue resolution attempts into the shared Service Records ledger."""

    issues = read_csv_safe(issue_record_file)
    resolutions = read_csv_safe(resolution_file)
    if issues.empty or resolutions.empty or "Issue ID" not in resolutions.columns:
        return pd.DataFrame()

    issue_columns = [
        "Issue ID", "Serial Number", "Model", "Location", "Postal Code",
        "Lift Lobby", "Is Loaner", "Issue Type", "Status",
    ]
    for column in issue_columns:
        if column not in issues.columns:
            issues[column] = ""
    merged = resolutions.merge(
        issues[issue_columns],
        on="Issue ID",
        how="left",
        suffixes=("", "_Issue"),
    ).fillna("")
    if merged.empty:
        return pd.DataFrame()

    attachment_path = Path(issue_record_file).resolve().parent / "issue_attachments.csv"
    attachments = read_csv_safe(attachment_path)
    attachment_map: dict[str, list[str]] = {}
    if not attachments.empty and "Submission ID" in attachments.columns:
        for submission_id, group in attachments.groupby(
            attachments["Submission ID"].astype(str).str.strip(), dropna=False
        ):
            key = clean_text(submission_id)
            if not key:
                continue
            attachment_map[key] = [
                clean_text(value)
                for value in group.get("File Path", pd.Series(dtype=str)).tolist()
                if clean_text(value)
            ]

    result = pd.DataFrame(index=merged.index)
    result["PM Response ID"] = merged.get("Submission ID", "")
    result["Service Record ID"] = merged.get("Submission ID", "")
    result["Resolution Submission ID"] = merged.get("Submission ID", "")
    result["Issue ID"] = merged.get("Issue ID", "")
    result["Issue Type"] = merged.get("Issue Type", "")
    result["Resolution Attempt Number"] = merged.get("Attempt Number", "")
    result["Action Taken"] = merged.get("Action Taken", "")
    result["Root Cause"] = merged.get("Root Cause", "")
    result["Parts Replaced"] = merged.get("Parts Replaced", "")
    result["Test Performed"] = merged.get("Test Performed", "")
    result["Test Result"] = merged.get("Test Result", "")
    result["Resolution Notes"] = merged.get("Resolution Notes", "")
    result["Verification Notes"] = merged.get("Verification Notes", "")
    submitted_at = merged.get("Submitted At", pd.Series("", index=merged.index)).astype(str)
    result["Service Date"] = submitted_at.str.slice(0, 10)
    result["Technician"] = merged.get("Submitted By", "")
    result["Service Type"] = "Issue Resolution"
    result["AED Serial Number"] = merged.get("Serial Number", "")
    result["Original Serial Number"] = merged.get("Serial Number", "")
    result["AED Model"] = merged.get("Model", "")
    result["AED Location"] = merged.get("Location", "")
    result["Postal Code"] = merged.get("Postal Code", "")
    result["Lift Lobby"] = merged.get("Lift Lobby", "")
    result["Loaner Unit"] = merged.get("Is Loaner", "No")
    result["Submitted At"] = submitted_at
    result["Submitted By"] = merged.get("Submitted By", "")
    result["Record Source"] = "Issue Resolution"
    verification = merged.get("Verification Result", pd.Series("", index=merged.index)).astype(str)
    issue_status = merged.get("Status", pd.Series("", index=merged.index)).astype(str)
    result["Record Status"] = verification.where(verification.str.strip().ne(""), issue_status)
    result["Verification Result"] = verification
    result["Verified By"] = merged.get("Verified By", "")
    result["Verified At"] = merged.get("Verified At", "")
    submission_ids = merged.get("Submission ID", pd.Series("", index=merged.index)).astype(str)
    result["Attachment Paths"] = submission_ids.map(
        lambda value: "; ".join(attachment_map.get(clean_text(value), []))
    )
    result["Attachment Count"] = submission_ids.map(
        lambda value: str(len(attachment_map.get(clean_text(value), [])))
    )

    detail_columns = [
        ("Issue", "Issue Type"),
        ("Action", "Action Taken"),
        ("Root cause", "Root Cause"),
        ("Parts", "Parts Replaced"),
        ("Test", "Test Performed"),
        ("Test result", "Test Result"),
        ("Resolution", "Resolution Notes"),
        ("Verification", "Verification Notes"),
    ]
    details: list[str] = []
    for _, row in merged.iterrows():
        parts = []
        for label, column in detail_columns:
            value = clean_text(row.get(column, ""))
            if value:
                parts.append(f"{label}: {value}")
        details.append(" · ".join(parts))
    result["Service Notes"] = details
    result["Service Report e-SR"] = ""
    result["Master Data Updated"] = "No"
    result["PM Dates Updated"] = "No"
    combined_text = (
        merged.get("Action Taken", pd.Series("", index=merged.index)).astype(str) + " "
        + merged.get("Parts Replaced", pd.Series("", index=merged.index)).astype(str)
    )
    result["Battery Replaced"] = combined_text.str.contains(
        "battery|batt", case=False, regex=True, na=False
    ).map({True: "Yes", False: "No"})
    return result.fillna("")


def load_service_records(
    response_csv_file: str | Path,
    aed_csv_file: str | Path | None = None,
    manual_service_file: str | Path = MANUAL_SERVICE_RECORDS_FILE,
    issue_record_file: str | Path = ISSUE_RECORD_FILE,
    resolution_file: str | Path = ISSUE_RESOLUTION_FILE,
    *,
    aed_dataframe: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Combine every service source shown on the Service Records page."""
    response_path = Path(response_csv_file)

    if response_path.exists() and response_path.stat().st_size > 0:
        try:
            records = pd.read_csv(
                response_path,
                dtype=str,
                keep_default_na=False,
                encoding="utf-8-sig",
            ).fillna("")
        except pd.errors.EmptyDataError:
            records = pd.DataFrame()

        if not records.empty:
            records["Record Source"] = records.get("Record Source", "PM Checklist")
            if isinstance(records["Record Source"], pd.Series):
                records["Record Source"] = records["Record Source"].replace(
                    "", "PM Checklist"
                )
            if "Record Status" not in records.columns:
                records["Record Status"] = records.get("Submission Status", "")
            else:
                blank_status = records["Record Status"].astype(str).str.strip().eq("")
                records.loc[blank_status, "Record Status"] = records.loc[
                    blank_status, "Submission Status"
                ] if "Submission Status" in records.columns else ""
            if "Service Record ID" not in records.columns:
                records["Service Record ID"] = records.get("PM Response ID", "")
    else:
        records = pd.DataFrame()

    manual = manual_records_for_service_page(manual_service_file)
    resolutions = issue_resolution_records_for_service_page(
        issue_record_file=issue_record_file,
        resolution_file=resolution_file,
    )
    sources = [frame for frame in [records, manual, resolutions] if not frame.empty]
    if not sources:
        return pd.DataFrame()
    records = pd.concat(sources, ignore_index=True, sort=False).fillna("")

    required_columns = {
        "Service Date",
        "Technician",
        "Service Type",
        "Postal Code",
        "Lift Lobby",
        "Loaner Unit",
        "Record Match",
        "AED Serial Number",
        "Battery Replaced",
        "Adult Pads Lot Number",
        "Pediatric Pads Lot Number",
        "AED Location",
        "Submitted At",
        "PM Response ID",
        "Original Serial Number",
        "Record Source",
        "Record Status",
        "Submission Status",
        "Excel Update Status",
        "Submitted By",
        "Operation ID",
        "Service Notes",
        "Service Report e-SR",
        "PM Dates Updated",
        "Battery History Updated",
        "PM Interval Months Used",
        "Master Operation ID",
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
    }
    for column in required_columns:
        if column not in records.columns:
            records[column] = ""
    if "AED Model" not in records.columns:
        records["AED Model"] = ""

    aed_lookup = load_aed_lookup(
        aed_csv_file,
        aed_dataframe=aed_dataframe,
    )
    model_lookup = create_lookup_map(aed_lookup, "Model")
    location_lookup = create_lookup_map(aed_lookup, "Location")

    for row_index, row in records.iterrows():
        current_serial = clean_text(row.get("AED Serial Number", ""))
        original_serial = clean_text(row.get("Original Serial Number", ""))
        serial_keys = [
            serial.casefold()
            for serial in [current_serial, original_serial]
            if serial
        ]

        if not clean_text(row.get("AED Model", "")):
            for serial_key in serial_keys:
                model = model_lookup.get(serial_key, "")
                if model:
                    records.at[row_index, "AED Model"] = model
                    break

        if not clean_text(row.get("AED Location", "")):
            for serial_key in serial_keys:
                location = location_lookup.get(serial_key, "")
                if location:
                    records.at[row_index, "AED Location"] = location
                    break

    records = add_record_match_status(records, aed_lookup)
    records["_Service Date Parsed"] = parse_service_date_series(records["Service Date"])
    records["_Submitted At Parsed"] = parse_submitted_at_series(records["Submitted At"])
    records["_Original Row Index"] = records.index
    return records.fillna("")
