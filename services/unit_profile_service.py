from __future__ import annotations

import csv
import os
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from services.manual_service_storage import MANUAL_SERVICE_RECORDS_FILE
from services.aed_table_edit_service import normalize_value
from services.csv_storage import atomic_write_csv, read_csv_safe
from services.pm_service import calculate_next_pm_date
from utils.text_utils import clean_text


SERVICE_HISTORY_COLUMNS = [
    "Service Date",
    "Service Type",
    "Source",
    "Technician",
    "Reference",
    "Status",
    "Details",
]


MANUAL_SERVICE_PREFIX = "[SERVICE]"


MANUAL_SERVICE_RECORD_COLUMNS = [
    "Service Record ID",
    "Created At",
    "Created By",
    "AED Serial Number",
    "AED Model",
    "AED Location",
    "Postal Code",
    "Lift Lobby",
    "Service Date",
    "Service Type",
    "Technician",
    "Reference",
    "Status",
    "Details",
    "Master Data Updated",
    "PM Dates Updated",
    "Battery Replaced",
    "Battery History Updated",
    "PM Interval Months Used",
    "Linked Plan ID",
    "Master Operation ID",
    "Source",
]



def generate_manual_service_record_id(now: datetime | None = None) -> str:
    timestamp = now or datetime.now().astimezone()
    return f"SRV-{timestamp.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"


def build_manual_service_update_plan(
    master_row: Mapping[str, Any],
    *,
    service_date: date,
    service_type: str,
    technician: str,
    reference: str,
    status: str,
    update_latest: bool,
    update_pm_dates: bool,
    interval_months: int,
) -> dict[str, Any]:
    """Build the exact Excel changes and durable record flags for Add Service.

    Blank optional values never erase existing IB List fields. Battery history is
    only changed by a completed battery service. The returned metadata is used
    by both the UI and tests, so record flags reflect actual field changes.
    """

    status_text = clean_text(status) or "Completed"
    service_type_text = clean_text(service_type)
    technician_text = clean_text(technician)
    reference_text = clean_text(reference)
    completed = status_text.casefold() == "completed"

    if (update_latest or update_pm_dates) and not completed:
        raise ValueError(
            "Pending or follow-up records cannot update the latest completed service fields."
        )
    if update_pm_dates and not service_type_text.casefold().startswith("pm"):
        raise ValueError("PM dates can only be updated for a PM service type.")

    interval = max(1, int(interval_months))
    service_date_text = service_date.strftime("%d-%m-%Y")
    changes: dict[str, str] = {}
    originals: dict[str, str] = {}

    def add_change(field: str, raw_value: Any) -> None:
        old_value = normalize_value(field, master_row.get(field, ""))
        new_value = normalize_value(field, raw_value)
        if new_value != old_value:
            changes[field] = new_value
            originals[field] = old_value

    if update_latest:
        add_change("Job Type", service_type_text)
        # Optional fields only update when a new value is supplied. This avoids
        # a blank Technician or e-SR clearing the official IB List value.
        if technician_text:
            add_change("Last Done By", technician_text)
        if reference_text:
            add_change("Service Report e-SR", reference_text)

    if update_pm_dates:
        add_change("PM Completed Date", service_date_text)
        add_change(
            "Next PM Date",
            calculate_next_pm_date(service_date_text, interval),
        )

    type_key = service_type_text.casefold()
    battery_replaced = completed and ("batt" in type_key or "battery" in type_key)
    if battery_replaced:
        old_history = normalize_value(
            "Battery Replacement History",
            master_row.get("Battery Replacement History", ""),
        )
        dates = [clean_text(item) for item in old_history.split(";") if clean_text(item)]
        if service_date_text not in dates:
            dates.append(service_date_text)
        add_change("Battery Replacement History", "; ".join(dates))

    latest_fields = {"Job Type", "Last Done By", "Service Report e-SR"}
    pm_fields = {"PM Completed Date", "Next PM Date"}
    return {
        "changes": changes,
        "originals": originals,
        "service_date_text": service_date_text,
        "battery_replaced": battery_replaced,
        "master_fields_changed": sorted(set(changes) & latest_fields),
        "pm_fields_changed": sorted(set(changes) & pm_fields),
        "battery_history_changed": "Battery Replacement History" in changes,
        "interval_months_used": str(interval) if update_pm_dates else "",
        "complete_pm_plan": bool(completed and update_pm_dates and service_type_text.casefold().startswith("pm")),
    }

def ensure_manual_service_storage(
    path: str | Path = MANUAL_SERVICE_RECORDS_FILE,
) -> Path:
    record_path = Path(path)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    if not record_path.exists() or record_path.stat().st_size == 0:
        temp = record_path.with_name(f".{record_path.name}.{uuid.uuid4().hex}.tmp")
        with temp.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=MANUAL_SERVICE_RECORD_COLUMNS)
            writer.writeheader()
        os.replace(temp, record_path)
    return record_path


def load_manual_service_records(
    path: str | Path = MANUAL_SERVICE_RECORDS_FILE,
) -> pd.DataFrame:
    record_path = ensure_manual_service_storage(path)
    records = read_csv_safe(record_path)
    for column in MANUAL_SERVICE_RECORD_COLUMNS:
        if column not in records.columns:
            records[column] = ""
    return records[MANUAL_SERVICE_RECORD_COLUMNS].fillna("")


def append_manual_service_record(
    record: Mapping[str, Any],
    *,
    path: str | Path = MANUAL_SERVICE_RECORDS_FILE,
) -> dict[str, str]:
    record_path = ensure_manual_service_storage(path)
    now = datetime.now().astimezone()
    saved = {column: clean_text(record.get(column, "")) for column in MANUAL_SERVICE_RECORD_COLUMNS}
    saved["Service Record ID"] = saved["Service Record ID"] or generate_manual_service_record_id(now)
    saved["Created At"] = saved["Created At"] or now.strftime("%d-%m-%Y %H:%M:%S")
    saved["Source"] = saved["Source"] or "Unit Profile"

    existing = load_manual_service_records(record_path)
    duplicate = existing[
        existing["Service Record ID"].astype(str).str.strip().eq(saved["Service Record ID"])
    ]
    if not duplicate.empty:
        return {column: clean_text(duplicate.iloc[0].get(column, "")) for column in MANUAL_SERVICE_RECORD_COLUMNS}

    updated = pd.concat(
        [existing, pd.DataFrame([saved], columns=MANUAL_SERVICE_RECORD_COLUMNS)],
        ignore_index=True,
    )
    atomic_write_csv(
        updated,
        record_path,
        preferred_columns=MANUAL_SERVICE_RECORD_COLUMNS,
    )
    return saved


def _manual_service_rows(serial: str, path: str | Path) -> list[dict[str, str]]:
    records = load_manual_service_records(path)
    matches = _matching_rows(records, serial, ("AED Serial Number",))
    rows: list[dict[str, str]] = []
    for _, row in matches.iterrows():
        detail_parts = [clean_text(row.get("Details"))]
        interval = clean_text(row.get("PM Interval Months Used"))
        linked_plan = clean_text(row.get("Linked Plan ID"))
        if interval:
            detail_parts.append(f"PM interval used: {interval} month(s)")
        if linked_plan:
            detail_parts.append(f"Linked PM plan: {linked_plan}")
        if clean_text(row.get("Battery History Updated")).casefold() == "yes":
            detail_parts.append("Battery replacement history updated")

        rows.append({
            "Service Date": clean_text(row.get("Service Date")),
            "Service Type": clean_text(row.get("Service Type")) or "Service",
            "Source": clean_text(row.get("Source")) or "Unit Profile",
            "Technician": clean_text(row.get("Technician")),
            "Reference": clean_text(row.get("Reference")) or clean_text(row.get("Service Record ID")),
            "Status": clean_text(row.get("Status")) or "Recorded",
            "Details": " · ".join(part for part in detail_parts if part),
        })
    return rows


def format_manual_service_remark(
    *,
    service_date: str,
    service_type: str,
    technician: str = "",
    reference: str = "",
    status: str = "Completed",
    details: str = "",
) -> str:
    """Create one stable, human-readable service-history line for Remarks."""
    parts = [
        f"{MANUAL_SERVICE_PREFIX} {clean_text(service_date)}",
        f"Type: {clean_text(service_type) or 'Service'}",
    ]
    if clean_text(technician):
        parts.append(f"Technician: {clean_text(technician)}")
    if clean_text(reference):
        parts.append(f"Reference: {clean_text(reference)}")
    if clean_text(status):
        parts.append(f"Status: {clean_text(status)}")
    if clean_text(details):
        compact = re.sub(r"\s+", " ", clean_text(details))
        parts.append(f"Details: {compact}")
    return " | ".join(parts)


def append_manual_service_remark(existing_remarks: str, service_line: str) -> str:
    """Append one service-history line without altering earlier Remarks text."""
    existing = clean_text(existing_remarks)
    line = clean_text(service_line)
    if not existing:
        return line
    if not line or line in existing.splitlines():
        return existing
    return f"{existing.rstrip()}\n{line}"


def _parse_structured_service_remark(piece: str) -> dict[str, str] | None:
    value = clean_text(piece)
    if not value.startswith(MANUAL_SERVICE_PREFIX):
        return None

    chunks = [clean_text(chunk) for chunk in value.split("|") if clean_text(chunk)]
    if not chunks:
        return None

    fields: dict[str, str] = {}
    first = chunks[0].removeprefix(MANUAL_SERVICE_PREFIX).strip()
    for chunk in chunks[1:]:
        if ":" not in chunk:
            continue
        key, raw = chunk.split(":", 1)
        fields[clean_text(key).casefold()] = clean_text(raw)

    return {
        "Service Date": _extract_date(first) or first,
        "Service Type": fields.get("type", "Service"),
        "Source": "Profile Service Record",
        "Technician": fields.get("technician", ""),
        "Reference": fields.get("reference", ""),
        "Status": fields.get("status", "Recorded"),
        "Details": fields.get("details", ""),
    }


_DATE_PATTERNS = [
    re.compile(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b"),
    re.compile(
        r"\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
        r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
        r"Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\b",
        flags=re.IGNORECASE,
    ),
]


def _matching_rows(
    dataframe: pd.DataFrame,
    serial: str,
    columns: tuple[str, ...],
) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.copy()

    target = clean_text(serial).casefold()
    if not target:
        return dataframe.iloc[0:0].copy()

    mask = pd.Series(False, index=dataframe.index)
    for column in columns:
        if column in dataframe.columns:
            mask |= dataframe[column].astype(str).str.strip().str.casefold().eq(target)
    return dataframe.loc[mask].copy()


def _extract_date(text: str) -> str:
    value = clean_text(text)
    for pattern in _DATE_PATTERNS:
        match = pattern.search(value)
        if match:
            parsed = pd.to_datetime(match.group(0), dayfirst=True, errors="coerce")
            if not pd.isna(parsed):
                return parsed.strftime("%d-%m-%Y")
    return ""


def _extract_reference(text: str) -> str:
    value = clean_text(text)
    match = re.search(r"\be[- ]?SR\s*[-:]?\s*\d+\b", value, flags=re.IGNORECASE)
    if not match:
        return ""
    return re.sub(r"\s+", "", match.group(0)).replace("ESR", "e-SR")


def _infer_service_type(text: str) -> str:
    value = clean_text(text).casefold()
    if "commission" in value:
        return "Commissioning"
    if "battery" in value and "glass" in value:
        return "PM + Battery + Glass"
    if "battery" in value:
        return "PM + Battery"
    if "glass" in value:
        return "PM + Glass"
    if "repair" in value:
        return "Repair"
    if "incoming" in value:
        return "Incoming Check"
    if "outgoing" in value:
        return "Outgoing Check"
    if "activation" in value:
        return "Activation"
    if "pm" in value or "preventive" in value:
        return "PM"
    return "Legacy Service"


def _legacy_remark_rows(master_row: pd.Series) -> list[dict[str, str]]:
    remarks = clean_text(master_row.get("Remarks"))
    if not remarks:
        return []

    pieces = [
        clean_text(piece).strip(" ,-/")
        for piece in re.split(
            r"\s*/\s*|[\r\n]+|\s*;\s*|"
            r"(?=\bPM\s+(?:completed|done)\b)|"
            r"(?=\bCommissioning\b)|(?=\bRepair(?:ed)?\b)|"
            r"(?=\bIncoming Check\b)|(?=\bOutgoing Check\b)",
            remarks,
            flags=re.IGNORECASE,
        )
        if clean_text(piece).strip(" ,-/")
    ]
    if not pieces:
        pieces = [remarks]

    rows: list[dict[str, str]] = []
    for piece in pieces:
        structured = _parse_structured_service_remark(piece)
        if structured is not None:
            rows.append(structured)
            continue
        rows.append(
            {
                "Service Date": _extract_date(piece),
                "Service Type": _infer_service_type(piece),
                "Source": "IB List Remarks",
                "Technician": "",
                "Reference": _extract_reference(piece),
                "Status": "Historical",
                "Details": piece,
            }
        )
    return rows


def _pm_response_rows(pm_responses: pd.DataFrame, serial: str) -> list[dict[str, str]]:
    matches = _matching_rows(
        pm_responses,
        serial,
        ("AED Serial Number", "Original Serial Number"),
    )
    rows: list[dict[str, str]] = []
    for _, row in matches.iterrows():
        detail_parts = []
        for label, column in [
            ("Battery replaced", "Battery Replaced"),
            ("Cabinet", "Cabinet Inspection"),
            ("Alarm", "Cabinet Alarm"),
            ("Self test", "Self Test Result"),
            ("Final check", "Final Check"),
            ("Notes", "Service Notes"),
            ("Linked plan", "Linked Plan ID"),
            ("Created Issues", "Created Issue IDs"),
        ]:
            value = clean_text(row.get(column))
            if value:
                detail_parts.append(f"{label}: {value}")

        rows.append(
            {
                "Service Date": clean_text(row.get("Service Date"))
                or clean_text(row.get("Submitted At")),
                "Service Type": clean_text(row.get("Service Type")) or "PM",
                "Source": "PM Checklist",
                "Technician": clean_text(row.get("Technician"))
                or clean_text(row.get("Submitted By")),
                "Reference": clean_text(row.get("Service Report e-SR"))
                or clean_text(row.get("PM Response ID"))
                or clean_text(row.get("Operation ID")),
                "Status": clean_text(row.get("Submission Status")) or "Submitted",
                "Details": " · ".join(detail_parts),
            }
        )
    return rows


def _master_latest_service_row(master_row: pd.Series) -> list[dict[str, str]]:
    service_date = clean_text(master_row.get("PM Completed Date"))
    service_type = clean_text(master_row.get("Job Type"))
    reference = clean_text(master_row.get("Service Report e-SR"))
    technician = clean_text(master_row.get("Last Done By"))
    if not any([service_date, service_type, reference, technician]):
        return []

    return [
        {
            "Service Date": service_date,
            "Service Type": service_type or "Latest Service",
            "Source": "IB List Current Record",
            "Technician": technician,
            "Reference": reference,
            "Status": "Recorded",
            "Details": "Latest service information currently stored in the IB List.",
        }
    ]


def _resolution_rows(
    issues: pd.DataFrame,
    resolutions: pd.DataFrame,
    serial: str,
) -> list[dict[str, str]]:
    issue_matches = _matching_rows(issues, serial, ("Serial Number",))
    if issue_matches.empty or resolutions.empty or "Issue ID" not in resolutions.columns:
        return []

    issue_lookup = {
        clean_text(row.get("Issue ID")): row
        for _, row in issue_matches.iterrows()
        if clean_text(row.get("Issue ID"))
    }
    if not issue_lookup:
        return []

    matches = resolutions[
        resolutions["Issue ID"].astype(str).str.strip().isin(issue_lookup)
    ].copy()
    rows: list[dict[str, str]] = []
    for _, row in matches.iterrows():
        issue_id = clean_text(row.get("Issue ID"))
        issue = issue_lookup.get(issue_id, pd.Series(dtype=object))
        details = []
        for label, column in [
            ("Issue", "Issue Type"),
            ("Action", "Action Taken"),
            ("Parts", "Parts Replaced"),
            ("Test", "Test Performed"),
            ("Result", "Test Result"),
            ("Notes", "Resolution Notes"),
        ]:
            source_row = issue if column == "Issue Type" else row
            value = clean_text(source_row.get(column))
            if value:
                details.append(f"{label}: {value}")

        rows.append(
            {
                "Service Date": clean_text(row.get("Submitted At"))
                or clean_text(issue.get("Resolved At"))
                or clean_text(issue.get("Closed At")),
                "Service Type": "Issue Resolution",
                "Source": "Issue Management",
                "Technician": clean_text(row.get("Submitted By"))
                or clean_text(issue.get("Resolved By")),
                "Reference": clean_text(row.get("Submission ID")) or issue_id,
                "Status": clean_text(row.get("Verification Result"))
                or clean_text(issue.get("Status")),
                "Details": " · ".join(details),
            }
        )
    return rows


def _sort_service_history(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe

    parsed = pd.to_datetime(dataframe["Service Date"], dayfirst=True, errors="coerce")
    dataframe = dataframe.assign(_sort_date=parsed)
    dataframe = dataframe.sort_values(
        ["_sort_date", "Source"],
        ascending=[False, True],
        na_position="last",
    )
    return dataframe.drop(columns=["_sort_date"]).reset_index(drop=True)


def build_service_history(
    master_row: pd.Series,
    serial: str,
    *,
    pm_responses_file: str | Path,
    issue_record_file: str | Path,
    resolution_file: str | Path,
    manual_service_file: str | Path = MANUAL_SERVICE_RECORDS_FILE,
) -> pd.DataFrame:
    pm_responses = read_csv_safe(pm_responses_file)
    issues = read_csv_safe(issue_record_file)
    resolutions = read_csv_safe(resolution_file)

    rows: list[dict[str, str]] = []
    rows.extend(_manual_service_rows(serial, manual_service_file))
    rows.extend(_pm_response_rows(pm_responses, serial))
    rows.extend(_resolution_rows(issues, resolutions, serial))
    rows.extend(_master_latest_service_row(master_row))
    rows.extend(_legacy_remark_rows(master_row))

    if not rows:
        return pd.DataFrame(columns=SERVICE_HISTORY_COLUMNS)

    history = pd.DataFrame(rows, columns=SERVICE_HISTORY_COLUMNS).fillna("")
    history = history.drop_duplicates(
        subset=["Service Date", "Service Type", "Reference", "Details"],
        keep="first",
    )
    return _sort_service_history(history)


def load_unit_issues(
    serial: str,
    *,
    issue_record_file: str | Path,
) -> pd.DataFrame:
    issues = read_csv_safe(issue_record_file)
    matches = _matching_rows(issues, serial, ("Serial Number",))
    if matches.empty:
        return matches

    if "Reported At" in matches.columns:
        parsed = pd.to_datetime(
            matches["Reported At"],
            dayfirst=True,
            errors="coerce",
        )
        matches = matches.assign(_sort_date=parsed).sort_values(
            "_sort_date", ascending=False, na_position="last"
        ).drop(columns=["_sort_date"])
    return matches.reset_index(drop=True)


UNIT_PROFILE_SEARCH_COLUMNS = (
    "Serial Number",
    "Model",
    "Location",
    "Block / Locations",
    "Street Name",
    "Postal Code",
)


def filter_unit_profiles(
    dataframe: pd.DataFrame,
    keyword: str,
) -> pd.DataFrame:
    """Return AED rows matching the visible Unit Profile search.

    Matching is case-insensitive and partial across serial, model, location,
    block, street and postal code. Empty serial rows are never offered as
    profiles.
    """
    filtered = dataframe.copy()
    search_text = clean_text(keyword).casefold()
    if search_text:
        mask = pd.Series(False, index=filtered.index)
        for column in UNIT_PROFILE_SEARCH_COLUMNS:
            if column in filtered.columns:
                mask |= (
                    filtered[column]
                    .astype(str)
                    .str.casefold()
                    .str.contains(search_text, regex=False, na=False)
                )
        filtered = filtered.loc[mask]

    if "Serial Number" not in filtered.columns:
        return filtered.iloc[0:0].copy()

    filtered = filtered[
        filtered["Serial Number"].astype(str).str.strip().ne("")
    ].copy()
    return filtered.sort_values("Serial Number", kind="stable").reset_index(drop=True)
