from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from config import (
    AED_DATA_FILE,
    AED_HISTORY_FILE,
    PM_PLAN_FILE,
    PM_RESPONSES_FILE,
)
from services.csv_storage import atomic_write_csv
from utils.text_utils import clean_text


DATE_FORMAT = "%d-%m-%Y"
DATETIME_FORMAT = "%d-%m-%Y %H:%M:%S"
DEFAULT_PM_INTERVAL_MONTHS = 12
PM_INTERVAL_COLUMN = "PM Interval Months"

PM_RESPONSE_COLUMNS = [
    "Operation ID",
    "Submission Status",
    "Excel Update Status",
    "Submitted By",
    "Service Date",
    "Technician",
    "Service Type",
    "Service Report e-SR",
    "Service Notes",
    "Postal Code",
    "Lift Lobby",
    "AED Serial Number",
    "AED Model",
    "Battery Replaced",
    "Battery Expiry Date",
    "Adult Pads Expiry Date",
    "Pediatric Pads Expiry Date",
    "Adult Pads Lot Number",
    "Pediatric Pads Lot Number",
    "AED Location",
    "PM Response ID",
    "Original Serial Number",
    "Customer / Location",
    "Loaner Unit",
    "Cabinet Inspection",
    "Cabinet Alarm",
    "AED Physical Condition",
    "Self Test Result",
    "AED Cover",
    "Adult Pads Within Expiry Date",
    "Pediatric Pads Within Expiry Date",
    "AED Signage",
    "Final Check",
    "Linked Plan ID",
    "Failed Checklist Fields",
    "Created Issue IDs",
    "Master Data Updated",
    "Submitted At",
]


PM_FAILURE_RULES = [
    ("Cabinet Inspection", "Cabinet inspection failed", "Cabinet condition did not pass the PM checklist."),
    ("Cabinet Alarm", "Cabinet alarm not working", "Cabinet alarm did not pass the PM checklist."),
    ("AED Physical Condition", "AED physical condition failed", "The AED physical condition did not pass inspection."),
    ("Self Test Result", "AED self-test failed", "The AED self-test result was Fail."),
    ("AED Cover", "Cover broken", "The AED cover did not pass inspection."),
    ("Adult Pads Within Expiry Date", "Adult pads expired", "Adult pads were recorded as outside the expiry date."),
    ("Pediatric Pads Within Expiry Date", "Pediatric pads expired", "Pediatric pads were recorded as outside the expiry date."),
    ("AED Signage", "Signage", "AED signage did not pass the final site check."),
    ("Final Check", "Final check failed", "The final readiness check did not pass."),
]


def failed_checklist_items(response: dict[str, Any]) -> list[dict[str, str]]:
    """Return one traceable Issue candidate for each failed PM checklist item."""

    failures: list[dict[str, str]] = []
    for field, issue_type, description in PM_FAILURE_RULES:
        value = clean_text(response.get(field, ""))
        failed = (
            value.casefold() == "fail"
            or (field in {
                "Adult Pads Within Expiry Date",
                "Pediatric Pads Within Expiry Date",
                "AED Signage",
                "Final Check",
            } and value.casefold() == "no")
        )
        if failed:
            failures.append({
                "Field": field,
                "Value": value,
                "Issue Type": issue_type,
                "Description": description,
                "Priority": (
                    "High"
                    if field in {"Self Test Result", "Final Check"}
                    else "Medium"
                ),
            })
    return failures


def create_pm_failure_issues(
    response: dict[str, Any],
    *,
    issue_csv_file: str | Path,
    model: str = "",
    reported_by: str = "",
) -> tuple[list[str], list[str]]:
    """Create one Issue for each failed PM field and return IDs/warnings.

    Keeping this workflow in a pure service makes the PM Checklist, Service
    Records and Issues linkage testable as one business chain.
    """
    from services.issue_service import create_issue

    failures = failed_checklist_items(response)
    issue_ids: list[str] = []
    warnings: list[str] = []
    actor = clean_text(reported_by) or clean_text(response.get("Technician", ""))

    for failure in failures:
        try:
            issue_ids.append(
                create_issue(
                    issue_csv_file,
                    issue_data={
                        "Source": "PM Checklist",
                        "Source Record ID": clean_text(response.get("PM Response ID", "")),
                        "Source Field": failure["Field"],
                        "Source Value": failure["Value"],
                        "Reported By": actor,
                        "Serial Number": clean_text(response.get("AED Serial Number", "")),
                        "Model": clean_text(model),
                        "Location": clean_text(response.get("AED Location", "")),
                        "Postal Code": clean_text(response.get("Postal Code", "")),
                        "Lift Lobby": clean_text(response.get("Lift Lobby", "")),
                        "Is Loaner": clean_text(response.get("Loaner Unit", "No")) or "No",
                        "Issue Type": failure["Issue Type"],
                        "Detailed Description": (
                            "Automatically created from PM Checklist. "
                            f"{failure['Field']}: {failure['Value']}. "
                            f"{failure['Description']}"
                        ),
                        "Priority": failure["Priority"],
                    },
                    uploaded_files=[],
                )
            )
        except Exception as error:
            warnings.append(
                f"Could not create the Issue for {failure['Field']}: {error}"
            )

    return issue_ids, warnings


PM_PLAN_COLUMNS = [
    "Operation ID",
    "Plan ID",
    "Plan Month",
    "Planned Date",
    "Serial Number",
    "Assigned To",
    "PM Status",
    "Completed Date",
    "Completed By",
    "Completion Record ID",
    "Completion Operation ID",
    "Is Loaner",
    "Color Override",
    "Location Snapshot",
    "Postal Code Snapshot",
    "Latitude Snapshot",
    "Longitude Snapshot",
    "Created At",
]

AED_HISTORY_COLUMNS = [
    "Source",
    "Action",
    "Changed At",
    "Serial Number Before",
    "Serial Number After",
    "Field Name",
    "Old Value",
    "New Value",
]


def _read_csv_with_schema(path: str | Path, columns: list[str]) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return pd.DataFrame(columns=columns)

    try:
        dataframe = pd.read_csv(
            csv_path,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        ).fillna("")
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=columns)

    for column in columns:
        if column not in dataframe.columns:
            dataframe[column] = ""
    return dataframe[columns]


def ensure_pm_storage(
    *,
    pm_responses_file: str | Path = PM_RESPONSES_FILE,
    pm_plan_file: str | Path = PM_PLAN_FILE,
    aed_history_file: str | Path = AED_HISTORY_FILE,
) -> None:
    """Ensure optional operational CSV files always contain stable headers."""

    storage = [
        (Path(pm_responses_file), PM_RESPONSE_COLUMNS),
        (Path(pm_plan_file), PM_PLAN_COLUMNS),
        (Path(aed_history_file), AED_HISTORY_COLUMNS),
    ]

    for path, columns in storage:
        if not path.exists() or path.stat().st_size <= 3:
            atomic_write_csv(
                pd.DataFrame(columns=columns),
                path,
                preferred_columns=columns,
            )
            continue

        try:
            raw = pd.read_csv(
                path,
                dtype=str,
                keep_default_na=False,
                encoding="utf-8-sig",
            ).fillna("")
        except pd.errors.EmptyDataError:
            raw = pd.DataFrame(columns=columns)

        if any(column not in raw.columns for column in columns):
            for column in columns:
                if column not in raw.columns:
                    raw[column] = ""
            atomic_write_csv(
                raw,
                path,
                preferred_columns=columns,
            )


def ensure_aed_pm_fields(
    aed_data_file: str | Path = AED_DATA_FILE,
    *,
    default_interval_months: int = DEFAULT_PM_INTERVAL_MONTHS,
) -> bool:
    """Add and normalise the PM interval field in AED master data once."""

    path = Path(aed_data_file)
    if not path.exists() or path.stat().st_size == 0:
        return False

    try:
        dataframe = pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        ).fillna("")
    except pd.errors.EmptyDataError:
        return False

    changed = False
    if PM_INTERVAL_COLUMN not in dataframe.columns:
        dataframe[PM_INTERVAL_COLUMN] = str(default_interval_months)
        changed = True
    else:
        raw = dataframe[PM_INTERVAL_COLUMN].astype(str).str.strip()
        invalid = ~raw.str.fullmatch(r"\d+", na=False) | raw.eq("0")
        if invalid.any():
            dataframe.loc[invalid, PM_INTERVAL_COLUMN] = str(default_interval_months)
            changed = True

    if changed:
        atomic_write_csv(dataframe, path)
    return changed


def record_value(record: pd.Series, column: str) -> str:
    if column not in record.index:
        return ""
    return clean_text(record.get(column, ""))


def parse_optional_date(value: Any) -> date | None:
    text = clean_text(value)
    if not text:
        return None

    parsed = pd.to_datetime(text, format=DATE_FORMAT, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def format_optional_date(value: date | None) -> str:
    if value is None:
        return ""
    return value.strftime(DATE_FORMAT)


def generate_response_id() -> str:
    return datetime.now().strftime("PM-%Y%m%d-%H%M%S-%f")[:-3]


def append_pm_response(response: dict[str, str]) -> None:
    """Save or refresh one PM response idempotently by PM Response ID.

    A confirmation retry must never create a second Service Record for the same
    reviewed PM submission. Existing rows are updated with any linkage fields
    (for example Created Issue IDs) that became available later in the commit.
    """

    existing = _read_csv_with_schema(PM_RESPONSES_FILE, PM_RESPONSE_COLUMNS)
    response_id = clean_text(response.get("PM Response ID", ""))
    row_values = {column: clean_text(response.get(column, "")) for column in PM_RESPONSE_COLUMNS}

    if response_id and not existing.empty:
        matches = existing.index[
            existing["PM Response ID"].astype(str).str.strip().eq(response_id)
        ].tolist()
        if matches:
            row_index = int(matches[0])
            for column, value in row_values.items():
                existing.at[row_index, column] = value
            atomic_write_csv(
                existing,
                PM_RESPONSES_FILE,
                preferred_columns=PM_RESPONSE_COLUMNS,
            )
            return

    new_row = pd.DataFrame([row_values], columns=PM_RESPONSE_COLUMNS)
    updated = pd.concat([existing, new_row], ignore_index=True)
    atomic_write_csv(
        updated,
        PM_RESPONSES_FILE,
        preferred_columns=PM_RESPONSE_COLUMNS,
    )


def complete_matching_pm_plan(
    serial_number: str,
    service_date_text: str,
    *,
    operation_id: str = "",
    response_id: str = "",
    completed_by: str = "",
    plan_file: str | Path = PM_PLAN_FILE,
) -> str:
    """Mark the exact-month pending PM plan row completed and return Plan ID.

    The function deliberately does not guess across months. If no pending row
    exists for the AED in the service month, the PM record remains unlinked.
    """

    serial = clean_text(serial_number)
    if not serial:
        return ""
    parsed = pd.to_datetime(clean_text(service_date_text), format=DATE_FORMAT, errors="coerce")
    if pd.isna(parsed):
        return ""

    plans = _read_csv_with_schema(plan_file, PM_PLAN_COLUMNS)
    if plans.empty:
        return ""
    target_month = parsed.strftime("%Y-%m")
    base_mask = (
        plans["Serial Number"].astype(str).str.strip().str.casefold().eq(serial.casefold())
        & plans["Plan Month"].astype(str).str.strip().eq(target_month)
    )
    response_key = clean_text(response_id)
    if response_key:
        already_linked = plans.index[
            base_mask
            & plans["PM Status"].astype(str).str.strip().str.casefold().eq("completed")
            & plans["Completion Record ID"].astype(str).str.strip().eq(response_key)
        ].tolist()
        if already_linked:
            return clean_text(plans.at[int(already_linked[-1]), "Plan ID"])

    mask = (
        base_mask
        & ~plans["PM Status"].astype(str).str.strip().str.casefold().eq("completed")
    )
    candidates = plans.index[mask].tolist()
    if not candidates:
        return ""

    # A monthly plan should contain one row per AED. If legacy duplicates exist,
    # complete the newest row only and leave the others visible for cleanup.
    row_index = int(candidates[-1])
    plans.at[row_index, "PM Status"] = "Completed"
    plans.at[row_index, "Completed Date"] = parsed.strftime(DATE_FORMAT)
    plans.at[row_index, "Completed By"] = clean_text(completed_by)
    plans.at[row_index, "Completion Record ID"] = clean_text(response_id)
    plans.at[row_index, "Completion Operation ID"] = clean_text(operation_id)
    plan_id = clean_text(plans.at[row_index, "Plan ID"])
    atomic_write_csv(plans, plan_file, preferred_columns=PM_PLAN_COLUMNS)
    return plan_id


def calculate_next_pm_date(
    service_date_text: str,
    interval_months: int | str = DEFAULT_PM_INTERVAL_MONTHS,
) -> str:
    """Calculate the next PM date using one explicit month interval."""

    parsed = pd.to_datetime(
        clean_text(service_date_text),
        format=DATE_FORMAT,
        errors="raise",
    )
    try:
        months = int(interval_months)
    except (TypeError, ValueError):
        months = DEFAULT_PM_INTERVAL_MONTHS
    if months <= 0:
        months = DEFAULT_PM_INTERVAL_MONTHS

    return (parsed + pd.DateOffset(months=months)).strftime(DATE_FORMAT)


def readable_service_date(service_date_text: str) -> str:
    parsed = datetime.strptime(service_date_text, DATE_FORMAT)
    return f"{parsed.day} {parsed.strftime('%B %Y')}"


def append_battery_history(existing_value: str, service_date_text: str) -> str:
    """Append a battery replacement date once, separated with semicolons."""

    existing_dates = [
        clean_text(item)
        for item in clean_text(existing_value).split(";")
        if clean_text(item)
    ]
    if service_date_text not in existing_dates:
        existing_dates.append(service_date_text)
    return "; ".join(existing_dates)


def append_history_rows(history_rows: list[dict[str, str]]) -> None:
    """Prepend AED master changes to the audit history CSV."""

    if not history_rows:
        return

    new_history = pd.DataFrame(history_rows, columns=AED_HISTORY_COLUMNS)
    existing = _read_csv_with_schema(AED_HISTORY_FILE, AED_HISTORY_COLUMNS)
    updated = pd.concat([new_history, existing], ignore_index=True)
    atomic_write_csv(
        updated,
        AED_HISTORY_FILE,
        preferred_columns=AED_HISTORY_COLUMNS,
    )



def classify_pm_excel_update_result(result: Any) -> str:
    """Return the durable PM record status for a safe Excel transaction result."""

    if bool(getattr(result, "success", False)):
        return "UPDATED"
    status = clean_text(getattr(result, "status", ""))
    if status == "already_applied":
        return "ALREADY_APPLIED"
    if status == "no_changes":
        return "NO_CHANGES"
    raise ValueError(
        "The PM response was not saved because the IB List update failed: "
        + clean_text(getattr(result, "message", "Unknown Excel update error."))
    )

def update_selected_aed(
    dataframe: pd.DataFrame,
    original_index: int,
    values: dict[str, str],
    *,
    user: str,
    session_id: str,
):
    """Update PM master fields through the Stage 4 Excel transaction service."""
    if original_index not in dataframe.index:
        raise IndexError("The originally selected AED row no longer exists.")

    from services.aed_repository import update_unit

    original_row = dataframe.loc[original_index].copy()
    serial_before = record_value(original_row, "Serial Number")
    serial_after = clean_text(values["AED Serial Number"])
    if serial_after != serial_before:
        raise ValueError(
            "Serial Number cannot be changed from the PM Checklist. "
            "Select the correct AED before submitting."
        )

    service_date_text = clean_text(values["Service Date"])
    service_type_full = clean_text(values["Service Type"])
    service_type_to_master = {
        "Preventive Maintenance (PM)": "PM",
        "Commissioning": "Commissioning",
        "PM+batt": "PM+batt",
        "PM+glass": "PM+glass",
        "PM +batt +glass": "PM +batt +glass",
        # Backward compatibility for records created by the previous draft.
        "PM + Battery": "PM+batt",
        "PM + Glass": "PM+glass",
        "PM + Battery + Glass": "PM +batt +glass",
    }
    job_type = service_type_to_master.get(service_type_full, service_type_full)
    service_report = clean_text(values.get("Service Report e-SR", ""))
    battery_replaced = clean_text(values.get("Battery Replaced", "")).casefold() == "yes"

    interval_text = record_value(original_row, PM_INTERVAL_COLUMN)
    try:
        interval_months = int(interval_text)
    except (TypeError, ValueError):
        interval_months = DEFAULT_PM_INTERVAL_MONTHS
    if interval_months <= 0:
        interval_months = DEFAULT_PM_INTERVAL_MONTHS

    desired = {
        "Postal Code": clean_text(values["Postal Code"]),
        "Lift Lobby": clean_text(values["Lift Lobby"]),
        "Battery Expiry Date": clean_text(values["Battery Expiry Date"]),
        "Adult Pads Expiry Date": clean_text(values["Adult Pads Expiry Date"]),
        "Adult Pads Lot Number": clean_text(values["Adult Pads Lot Number"]),
        "Pediatric Pads Expiry Date": clean_text(values["Pediatric Pads Expiry Date"]),
        "Pediatric Pads Lot Number": clean_text(values["Pediatric Pads Lot Number"]),
        "PM Completed Date": service_date_text,
        "Next PM Date": calculate_next_pm_date(service_date_text, interval_months),
        "Job Type": job_type,
        "Last Done By": clean_text(values["Technician"]),
    }
    if battery_replaced:
        desired["Battery Replacement History"] = append_battery_history(
            record_value(original_row, "Battery Replacement History"),
            service_date_text,
        )
    if service_report:
        desired["Service Report e-SR"] = service_report
    changes: dict[str, str] = {}
    original_values: dict[str, str] = {}
    for field, new_value in desired.items():
        old_value = record_value(original_row, field)
        if old_value != new_value:
            changes[field] = new_value
            original_values[field] = old_value

    return update_unit(
        serial_number=serial_before,
        changes=changes,
        original_values=original_values,
        user=user,
        session_id=session_id,
        source_page="PM Checklist",
    )


def build_response(
    service_date: date,
    technician: str,
    service_type: str,
    customer_location: str,
    postal_code: str,
    lift_lobby: str,
    loaner_unit: str,
    cabinet_inspection: str,
    cabinet_alarm: str,
    serial_number: str,
    physical_condition: str,
    self_test_result: str,
    battery_expiry: date | None,
    aed_cover: str,
    adult_pads_expiry: date | None,
    adult_pads_lot: str,
    adult_pads_within_expiry: str,
    pediatric_pads_expiry: date | None,
    pediatric_pads_lot: str,
    pediatric_pads_within_expiry: str,
    aed_signage: str,
    final_check: str,
    aed_location: str,
    original_serial_number: str,
    service_report_id: str = "",
    service_notes: str = "",
    aed_model: str = "",
) -> dict[str, str]:
    master_data_updated = "No" if loaner_unit == "Yes" else "Yes"
    service_type_key = clean_text(service_type).casefold()
    battery_replaced = (
        "Yes"
        if (
            self_test_result == "Pass - After installing new batteries"
            or "batt" in service_type_key
            or "battery" in service_type_key
        )
        else "No"
    )

    return {
        "Service Date": service_date.strftime(DATE_FORMAT),
        "Technician": clean_text(technician),
        "Service Type": service_type,
        "Service Report e-SR": clean_text(service_report_id),
        "Service Notes": clean_text(service_notes),
        "Postal Code": clean_text(postal_code),
        "Lift Lobby": clean_text(lift_lobby),
        "AED Serial Number": clean_text(serial_number),
        "AED Model": clean_text(aed_model),
        "Battery Replaced": battery_replaced,
        "Battery Expiry Date": format_optional_date(battery_expiry),
        "Adult Pads Expiry Date": format_optional_date(adult_pads_expiry),
        "Pediatric Pads Expiry Date": format_optional_date(pediatric_pads_expiry),
        "Adult Pads Lot Number": clean_text(adult_pads_lot),
        "Pediatric Pads Lot Number": clean_text(pediatric_pads_lot),
        "AED Location": clean_text(aed_location),
        "PM Response ID": generate_response_id(),
        "Original Serial Number": clean_text(original_serial_number),
        "Customer / Location": customer_location,
        "Loaner Unit": loaner_unit,
        "Cabinet Inspection": cabinet_inspection,
        "Cabinet Alarm": cabinet_alarm,
        "AED Physical Condition": physical_condition,
        "Self Test Result": self_test_result,
        "AED Cover": aed_cover,
        "Adult Pads Within Expiry Date": adult_pads_within_expiry,
        "Pediatric Pads Within Expiry Date": pediatric_pads_within_expiry,
        "AED Signage": aed_signage,
        "Final Check": final_check,
        "Linked Plan ID": "",
        "Failed Checklist Fields": "",
        "Created Issue IDs": "",
        "Master Data Updated": master_data_updated,
        "Submitted At": datetime.now().astimezone().strftime(DATETIME_FORMAT),
    }


def validate_submission(
    technician: str,
    customer_location: str | None,
    postal_code: str,
    serial_number: str,
    confirmed: bool,
) -> list[str]:
    errors: list[str] = []

    if not clean_text(technician):
        errors.append("Technician is required.")
    if customer_location not in {"SCDF / SAL", "Other"}:
        errors.append("Customer / Location must be selected.")
    if not clean_text(postal_code):
        errors.append("Postal Code is required.")
    if not clean_text(serial_number):
        errors.append("AED Serial Number is required.")
    if not confirmed:
        errors.append(
            "Please confirm that the information was verified during inspection."
        )

    return errors
