from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from services.issue_service import (
    ISSUE_STATUS_OPTIONS,
    load_issue_history,
    load_issue_records,
)
from services.pm_service import (
    AED_HISTORY_COLUMNS,
    PM_PLAN_COLUMNS,
    PM_RESPONSE_COLUMNS,
    ensure_pm_storage,
)
from utils.text_utils import clean_text


DATE_FORMAT = "%d-%m-%Y"
DATETIME_FORMAT = "%d-%m-%Y %H:%M:%S"
OPEN_ISSUE_STATUSES = set(ISSUE_STATUS_OPTIONS) - {"Closed"}
DASHBOARD_VIEWS = ["PM", "Issues", "Unit Profiles"]

DASHBOARD_QUEUE_COLUMNS = [
    "Queue ID",
    "Category",
    "Priority",
    "Item",
    "Title",
    "Serial Number",
    "Location",
    "Due Date",
    "Due / Age",
    "Age Days",
    "Owner",
    "Status",
    "Next Action",
    "Sort Score",
    "Source Index",
]

ACTIVITY_COLUMNS = [
    "Activity At",
    "Activity Type",
    "Summary",
    "Actor",
    "Source ID",
]

SOURCE_LABELS = {
    "aed_data": "AED master data",
    "pm_plan": "PM plan",
    "pm_responses": "PM responses",
    "issues": "Issue records",
    "issue_history": "Issue history",
    "aed_history": "AED change history",
}

PRIORITY_ORDER = {
    "Critical": 0,
    "Urgent": 1,
    "High": 2,
    "Medium": 3,
    "Low": 4,
}


@dataclass(frozen=True)
class DashboardPaths:
    aed_data: Path
    issue_records: Path
    pm_responses: Path
    pm_plan: Path
    aed_history: Path
    issue_history: Path


def _clean_series(dataframe: pd.DataFrame, column: str) -> pd.Series:
    if column not in dataframe.columns:
        return pd.Series("", index=dataframe.index, dtype="object")
    return dataframe[column].fillna("").astype(str).str.strip()


def _read_csv_safely(
    path: str | Path,
    columns: Iterable[str] | None = None,
) -> pd.DataFrame:
    csv_path = Path(path)
    preferred_columns = list(columns or [])

    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return pd.DataFrame(columns=preferred_columns)

    try:
        dataframe = pd.read_csv(
            csv_path,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        ).fillna("")
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=preferred_columns)

    for column in preferred_columns:
        if column not in dataframe.columns:
            dataframe[column] = ""

    return dataframe


def _parse_date_series(dataframe: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_datetime(
        _clean_series(dataframe, column),
        format=DATE_FORMAT,
        errors="coerce",
    )


def _parse_datetime_series(dataframe: pd.DataFrame, column: str) -> pd.Series:
    raw = _clean_series(dataframe, column)
    parsed = pd.to_datetime(raw, format=DATETIME_FORMAT, errors="coerce")
    missing = parsed.isna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(
            raw.loc[missing],
            format=DATE_FORMAT,
            errors="coerce",
        )
    return parsed



def _plausible_date_mask(parsed: pd.Series, reference_day: pd.Timestamp) -> pd.Series:
    """Reject parsed but operationally impossible years such as 1930."""

    return (
        parsed.notna()
        & parsed.dt.year.ge(2000)
        & parsed.dt.year.le(reference_day.year + 15)
    )

def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(clean_text(value)))
    except (TypeError, ValueError):
        return default


def _display_date(value: Any) -> str:
    if value is None or pd.isna(value):
        return "—"
    if isinstance(value, pd.Timestamp):
        return value.strftime(DATE_FORMAT)
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        return clean_text(value) or "—"
    return parsed.strftime(DATE_FORMAT)


def _file_status(path: Path, dataframe: pd.DataFrame) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "healthy": False,
            "record_count": 0,
            "modified_at": None,
            "message": "File is missing",
        }

    modified_at = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
    has_headers = len(dataframe.columns) > 0
    return {
        "path": str(path),
        "exists": True,
        "healthy": has_headers,
        "record_count": len(dataframe),
        "modified_at": modified_at,
        "message": (
            f"{len(dataframe)} record(s)"
            if has_headers
            else "File has no readable header"
        ),
    }


def load_dashboard_sources(
    paths: DashboardPaths,
    *,
    aed_data: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Load every source required by the control centre without fragile reads."""

    ensure_pm_storage(
        pm_responses_file=paths.pm_responses,
        pm_plan_file=paths.pm_plan,
        aed_history_file=paths.aed_history,
    )

    aed_data = (
        aed_data.copy()
        if aed_data is not None
        else _read_csv_safely(paths.aed_data)
    )
    pm_plan = _read_csv_safely(paths.pm_plan, PM_PLAN_COLUMNS)
    pm_responses = _read_csv_safely(paths.pm_responses, PM_RESPONSE_COLUMNS)
    aed_history = _read_csv_safely(paths.aed_history, AED_HISTORY_COLUMNS)

    try:
        issues = load_issue_records(paths.issue_records)
    except Exception:
        issues = _read_csv_safely(paths.issue_records)

    try:
        issue_history = load_issue_history(paths.issue_records)
    except Exception:
        issue_history = _read_csv_safely(paths.issue_history)

    dataframes = {
        "aed_data": aed_data,
        "pm_plan": pm_plan,
        "pm_responses": pm_responses,
        "issues": issues,
        "issue_history": issue_history,
        "aed_history": aed_history,
    }

    source_paths = {
        "aed_data": paths.aed_data,
        "pm_plan": paths.pm_plan,
        "pm_responses": paths.pm_responses,
        "issues": paths.issue_records,
        "issue_history": paths.issue_history,
        "aed_history": paths.aed_history,
    }

    source_status = {
        key: {
            "label": SOURCE_LABELS[key],
            **_file_status(source_paths[key], dataframe),
        }
        for key, dataframe in dataframes.items()
    }

    return {**dataframes, "source_status": source_status}


def _latest_pending_plan_by_serial(plan_records: pd.DataFrame) -> dict[str, pd.Series]:
    if plan_records.empty or "Serial Number" not in plan_records.columns:
        return {}

    plans = plan_records.copy()
    plans["_Serial Key"] = _clean_series(plans, "Serial Number").str.casefold()
    plans["_Created Parsed"] = _parse_datetime_series(plans, "Created At")
    plans["_Planned Parsed"] = _parse_date_series(plans, "Planned Date")
    plans["_Sort Date"] = plans["_Created Parsed"].fillna(plans["_Planned Parsed"])
    plans = plans.sort_values("_Sort Date", ascending=False, na_position="last")

    result: dict[str, pd.Series] = {}
    for _, row in plans.iterrows():
        serial_key = clean_text(row.get("_Serial Key"))
        if serial_key and serial_key not in result:
            result[serial_key] = row
    return result


def build_pm_queue(
    aed_data: pd.DataFrame,
    plan_records: pd.DataFrame,
    today: date | pd.Timestamp,
    *,
    due_horizon_days: int = 30,
) -> pd.DataFrame:
    """Return overdue and near-due PM work, enriched with the latest plan."""

    if aed_data.empty:
        return pd.DataFrame(columns=DASHBOARD_QUEUE_COLUMNS)

    current_day = pd.Timestamp(today).normalize()
    horizon = current_day + pd.Timedelta(days=due_horizon_days)
    next_pm = _parse_date_series(aed_data, "Next PM Date")
    latest_plans = _latest_pending_plan_by_serial(plan_records)

    rows: list[dict[str, Any]] = []
    for index, source_row in aed_data.iterrows():
        due_date = next_pm.loc[index]
        if pd.isna(due_date) or due_date > horizon:
            continue

        serial = clean_text(source_row.get("Serial Number"))
        if not serial:
            continue

        day_difference = int((due_date - current_day).days)
        serial_key = serial.casefold()
        plan_row = latest_plans.get(serial_key)
        owner = clean_text(plan_row.get("Assigned To")) if plan_row is not None else ""
        plan_status = clean_text(plan_row.get("PM Status")) if plan_row is not None else ""

        if day_difference < 0:
            overdue_days = abs(day_difference)
            priority = "Critical"
            status = plan_status or "Overdue"
            due_age = f"{overdue_days} day(s) overdue"
            action = "Start PM checklist" if owner else "Assign and start PM"
            sort_score = 100_000 + min(overdue_days, 9_999)
        else:
            priority = "High" if day_difference <= 7 else "Medium"
            status = plan_status or "Not planned"
            due_age = "Due today" if day_difference == 0 else f"Due in {day_difference} day(s)"
            action = "Start PM checklist" if owner else "Add to PM plan"
            sort_score = 80_000 - day_difference

        rows.append(
            {
                "Queue ID": f"PM:{serial}:{due_date.strftime(DATE_FORMAT)}",
                "Category": "PM",
                "Priority": priority,
                "Item": serial,
                "Title": "Preventive maintenance",
                "Serial Number": serial,
                "Location": clean_text(source_row.get("Location")),
                "Due Date": due_date.strftime(DATE_FORMAT),
                "Due / Age": due_age,
                "Age Days": str(abs(day_difference) if day_difference < 0 else day_difference),
                "Owner": owner or "Unassigned",
                "Status": status,
                "Next Action": action,
                "Sort Score": sort_score,
                "Source Index": str(index),
            }
        )

    return _queue_dataframe(rows)


def _issue_next_action(status: str) -> str:
    return {
        "Reported": "Review and assign",
        "Assigned": "Start work",
        "In Progress": "Update work or submit resolution",
        "Pending Verification": "Verify resolution",
        "Reopened": "Restart or reassign work",
    }.get(status, "Review issue")


def build_issue_queue(
    issue_records: pd.DataFrame,
    today: date | pd.Timestamp,
) -> pd.DataFrame:
    if issue_records.empty:
        return pd.DataFrame(columns=DASHBOARD_QUEUE_COLUMNS)

    current_day = pd.Timestamp(today).normalize()
    reported_at = _parse_datetime_series(issue_records, "Reported At")
    due_dates = _parse_date_series(issue_records, "Due Date")
    rows: list[dict[str, Any]] = []

    for index, source_row in issue_records.iterrows():
        status = clean_text(source_row.get("Status")) or "Reported"
        if status not in OPEN_ISSUE_STATUSES:
            continue

        issue_id = clean_text(source_row.get("Issue ID"))
        if not issue_id:
            continue

        reported = reported_at.loc[index]
        age_days = (
            max(0, int((current_day - reported.normalize()).days))
            if not pd.isna(reported)
            else 0
        )
        due_date = due_dates.loc[index]
        overdue_days = (
            max(0, int((current_day - due_date.normalize()).days))
            if not pd.isna(due_date)
            else 0
        )

        original_priority = clean_text(source_row.get("Priority")) or "Medium"
        priority = original_priority if original_priority in PRIORITY_ORDER else "Medium"
        category = "Verification" if status == "Pending Verification" else "Issue"

        base_score = {
            "Urgent": 95_000,
            "High": 90_000,
            "Medium": 70_000,
            "Low": 60_000,
        }.get(priority, 70_000)
        if status == "Pending Verification":
            base_score = max(base_score, 92_000)
        if overdue_days:
            base_score += min(overdue_days, 1_000)

        if overdue_days:
            due_age = f"{overdue_days} day(s) past due"
        elif not pd.isna(due_date):
            remaining = int((due_date.normalize() - current_day).days)
            due_age = "Due today" if remaining == 0 else f"Due in {remaining} day(s)"
        else:
            due_age = f"Open {age_days} day(s)"

        rows.append(
            {
                "Queue ID": f"ISSUE:{issue_id}",
                "Category": category,
                "Priority": priority,
                "Item": issue_id,
                "Title": clean_text(source_row.get("Issue Type")) or "Reported issue",
                "Serial Number": clean_text(source_row.get("Serial Number")),
                "Location": clean_text(source_row.get("Location")),
                "Due Date": _display_date(due_date),
                "Due / Age": due_age,
                "Age Days": str(age_days),
                "Owner": clean_text(source_row.get("Current Assignee")) or "Unassigned",
                "Status": status,
                "Next Action": _issue_next_action(status),
                "Sort Score": base_score + min(age_days, 999),
                "Source Index": str(index),
            }
        )

    return _queue_dataframe(rows)


def build_readiness_queue(
    aed_data: pd.DataFrame,
    today: date | pd.Timestamp,
    *,
    horizon_days: int = 90,
) -> pd.DataFrame:
    if aed_data.empty:
        return pd.DataFrame(columns=DASHBOARD_QUEUE_COLUMNS)

    current_day = pd.Timestamp(today).normalize()
    horizon = current_day + pd.Timedelta(days=horizon_days)
    expiry_fields = [
        ("Adult Pads Expiry Date", "Adult pads"),
        ("Pediatric Pads Expiry Date", "Pediatric pads"),
        ("Battery Expiry Date", "Battery"),
    ]

    rows: list[dict[str, Any]] = []
    for column, label in expiry_fields:
        parsed_dates = _parse_date_series(aed_data, column)
        plausible_dates = _plausible_date_mask(parsed_dates, current_day)
        for index, source_row in aed_data.iterrows():
            expiry_date = parsed_dates.loc[index]
            if not plausible_dates.loc[index] or expiry_date > horizon:
                continue

            serial = clean_text(source_row.get("Serial Number"))
            if not serial:
                continue

            day_difference = int((expiry_date - current_day).days)
            if day_difference < 0:
                overdue_days = abs(day_difference)
                priority = "Critical"
                due_age = f"Expired {overdue_days} day(s) ago"
                sort_score = 88_000 + min(overdue_days, 4_000)
                status = "Expired"
            else:
                priority = "High" if day_difference <= 30 else "Medium"
                due_age = "Expires today" if day_difference == 0 else f"Expires in {day_difference} day(s)"
                sort_score = 65_000 - day_difference
                status = "Attention"

            slug = column.casefold().replace(" ", "-")
            rows.append(
                {
                    "Queue ID": f"READINESS:{serial}:{slug}",
                    "Category": "Unit",
                    "Priority": priority,
                    "Item": serial,
                    "Title": label,
                    "Serial Number": serial,
                    "Location": clean_text(source_row.get("Location")),
                    "Due Date": expiry_date.strftime(DATE_FORMAT),
                    "Due / Age": due_age,
                    "Age Days": str(abs(day_difference)),
                    "Owner": "Unassigned",
                    "Status": status,
                    "Next Action": "Verify and update consumable",
                    "Sort Score": sort_score,
                    "Source Index": str(index),
                }
            )

    return _queue_dataframe(rows)


def build_data_exception_queue(aed_data: pd.DataFrame) -> pd.DataFrame:
    if aed_data.empty:
        return pd.DataFrame(columns=DASHBOARD_QUEUE_COLUMNS)

    rows: list[dict[str, Any]] = []
    serials = _clean_series(aed_data, "Serial Number")
    duplicate_mask = serials.ne("") & serials.str.casefold().duplicated(keep=False)
    latitude = pd.to_numeric(_clean_series(aed_data, "Latitude"), errors="coerce")
    longitude = pd.to_numeric(_clean_series(aed_data, "Longitude"), errors="coerce")

    checks: list[tuple[str, pd.Series, str, str, str]] = [
        (
            "missing-serial",
            serials.eq(""),
            "Missing Serial Number",
            "Critical",
            "Update AED master data",
        ),
        (
            "duplicate-serial",
            duplicate_mask,
            "Duplicate Serial Number",
            "High",
            "Resolve duplicate master records",
        ),
        (
            "missing-location",
            _clean_series(aed_data, "Location").eq(""),
            "Missing Location",
            "High",
            "Update AED master data",
        ),
        (
            "missing-postal",
            _clean_series(aed_data, "Postal Code").eq(""),
            "Missing Postal Code",
            "High",
            "Update AED master data",
        ),
        (
            "missing-next-pm",
            _clean_series(aed_data, "Next PM Date").eq(""),
            "Missing Next PM Date",
            "High",
            "Confirm PM cycle and update date",
        ),
        (
            "missing-coordinates",
            latitude.isna() | longitude.isna(),
            "Missing Map Coordinates",
            "Medium",
            "Run coordinate update",
        ),
    ]

    invalid_date_mask = pd.Series(False, index=aed_data.index)
    implausible_date_mask = pd.Series(False, index=aed_data.index)
    reference_day = pd.Timestamp(date.today()).normalize()
    for date_column in [
        "Next PM Date",
        "PM Completed Date",
        "Adult Pads Expiry Date",
        "Pediatric Pads Expiry Date",
        "Battery Expiry Date",
    ]:
        raw = _clean_series(aed_data, date_column)
        parsed = _parse_date_series(aed_data, date_column)
        invalid_date_mask |= raw.ne("") & parsed.isna()
        implausible_date_mask |= (
            raw.ne("")
            & parsed.notna()
            & ~_plausible_date_mask(parsed, reference_day)
        )

    checks.extend(
        [
            (
                "invalid-date",
                invalid_date_mask,
                "Invalid Date Format",
                "High",
                "Verify DD-MM-YYYY source value",
            ),
            (
                "implausible-date",
                implausible_date_mask,
                "Implausible Date Year",
                "High",
                "Verify the source year before planning work",
            ),
        ]
    )

    for slug, mask, title, priority, action in checks:
        for index in aed_data.index[mask.fillna(False)]:
            source_row = aed_data.loc[index]
            serial = clean_text(source_row.get("Serial Number")) or f"Row {index + 1}"
            rows.append(
                {
                    "Queue ID": f"DATA:{serial}:{slug}:{index}",
                    "Category": "Data",
                    "Priority": priority,
                    "Item": serial,
                    "Title": title,
                    "Serial Number": clean_text(source_row.get("Serial Number")),
                    "Location": clean_text(source_row.get("Location")),
                    "Due Date": "—",
                    "Due / Age": "Data exception",
                    "Age Days": "0",
                    "Owner": "Unassigned",
                    "Status": "Needs correction",
                    "Next Action": action,
                    "Sort Score": 58_000 if priority == "High" else 50_000,
                    "Source Index": str(index),
                }
            )

    return _queue_dataframe(rows)


def _queue_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=DASHBOARD_QUEUE_COLUMNS)

    dataframe = pd.DataFrame(rows)
    for column in DASHBOARD_QUEUE_COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = ""
    dataframe = dataframe[DASHBOARD_QUEUE_COLUMNS]
    dataframe["Sort Score"] = pd.to_numeric(
        dataframe["Sort Score"], errors="coerce"
    ).fillna(0).astype(int)
    return dataframe


def build_unified_work_queue(*queues: pd.DataFrame) -> pd.DataFrame:
    available = [queue for queue in queues if not queue.empty]
    if not available:
        return pd.DataFrame(columns=DASHBOARD_QUEUE_COLUMNS)

    combined = pd.concat(available, ignore_index=True)
    combined = combined.sort_values(
        ["Sort Score", "Priority", "Category", "Item"],
        ascending=[False, True, True, True],
        key=lambda series: (
            series.map(PRIORITY_ORDER).fillna(99)
            if series.name == "Priority"
            else series
        ),
        na_position="last",
    ).reset_index(drop=True)
    return combined[DASHBOARD_QUEUE_COLUMNS]


def calculate_pm_summary(
    plan_records: pd.DataFrame,
    aed_data: pd.DataFrame,
    selected_period: str,
) -> dict[str, int]:
    period_plans = plan_records[
        _clean_series(plan_records, "Plan Month").eq(selected_period)
    ].copy() if not plan_records.empty else pd.DataFrame()

    status = _clean_series(period_plans, "PM Status").str.casefold()
    planned = len(period_plans)
    completed = int(status.eq("completed").sum())
    in_progress = int(status.eq("in progress").sum())
    pending = max(0, planned - completed - in_progress)
    unassigned = int(_clean_series(period_plans, "Assigned To").eq("").sum())

    next_pm = _parse_date_series(aed_data, "Next PM Date")
    due_period = next_pm.dt.to_period("M")
    due_this_period = int(due_period.eq(pd.Period(selected_period, freq="M")).sum())

    return {
        "planned": planned,
        "completed": completed,
        "in_progress": in_progress,
        "pending": pending,
        "unassigned": unassigned,
        "due_this_period": due_this_period,
        "completion_percent": round((completed / planned) * 100) if planned else 0,
    }


def calculate_issue_summary(issue_records: pd.DataFrame) -> dict[str, int]:
    status = _clean_series(issue_records, "Status")
    priority = _clean_series(issue_records, "Priority")
    open_mask = status.isin(OPEN_ISSUE_STATUSES)
    open_records = issue_records.loc[open_mask]

    return {
        "open": int(open_mask.sum()),
        "reported": int(status.eq("Reported").sum()),
        "assigned": int(status.eq("Assigned").sum()),
        "in_progress": int(status.eq("In Progress").sum()),
        "pending_verification": int(status.eq("Pending Verification").sum()),
        "reopened": int(status.eq("Reopened").sum()),
        "high_urgent": int(
            (priority.isin(["High", "Urgent"]) & open_mask).sum()
        ),
        "unassigned": int(
            _clean_series(open_records, "Current Assignee").eq("").sum()
        ),
    }


def calculate_readiness_summary(
    aed_data: pd.DataFrame,
    today: date | pd.Timestamp,
    *,
    horizon_days: int = 90,
) -> dict[str, int]:
    current_day = pd.Timestamp(today).normalize()
    horizon = current_day + pd.Timedelta(days=horizon_days)

    summary: dict[str, int] = {}
    for column, key in [
        ("Adult Pads Expiry Date", "adult_pads"),
        ("Pediatric Pads Expiry Date", "pediatric_pads"),
        ("Battery Expiry Date", "battery"),
    ]:
        parsed = _parse_date_series(aed_data, column)
        plausible = _plausible_date_mask(parsed, current_day)
        summary[key] = int((plausible & parsed.le(horizon)).sum())
        summary[f"{key}_expired"] = int((plausible & parsed.lt(current_day)).sum())

    latitude = pd.to_numeric(_clean_series(aed_data, "Latitude"), errors="coerce")
    longitude = pd.to_numeric(_clean_series(aed_data, "Longitude"), errors="coerce")
    summary["missing_next_pm"] = int(_clean_series(aed_data, "Next PM Date").eq("").sum())
    summary["missing_coordinates"] = int((latitude.isna() | longitude.isna()).sum())
    summary["expiring_total"] = (
        summary["adult_pads"]
        + summary["pediatric_pads"]
        + summary["battery"]
    )
    return summary


def calculate_dashboard_kpis(
    *,
    view: str,
    queue: pd.DataFrame,
    pm_summary: dict[str, int],
    issue_summary: dict[str, int],
    readiness_summary: dict[str, int],
) -> list[dict[str, str]]:
    overdue_pm = int(
        (
            queue["Category"].eq("PM")
            & queue["Due / Age"].astype(str).str.contains("overdue", case=False, na=False)
        ).sum()
    ) if not queue.empty else 0
    due_pm = int(
        (
            queue["Category"].eq("PM")
            & ~queue["Due / Age"].astype(str).str.contains("overdue", case=False, na=False)
        ).sum()
    ) if not queue.empty else 0

    if view == "PM":
        return [
            {"label": "PLANNED THIS MONTH", "value": str(pm_summary["planned"]), "note": f"{pm_summary['due_this_period']} unit(s) due", "tone": "blue"},
            {"label": "COMPLETED", "value": str(pm_summary["completed"]), "note": f"{pm_summary['completion_percent']}% of saved plan", "tone": "green"},
            {"label": "PENDING", "value": str(pm_summary["pending"]), "note": f"{pm_summary['in_progress']} in progress", "tone": "amber"},
            {"label": "UNASSIGNED", "value": str(pm_summary["unassigned"]), "note": "Plan records without owner", "tone": "coral" if pm_summary["unassigned"] else "green"},
        ]

    if view == "Issues":
        return [
            {"label": "OPEN ISSUES", "value": str(issue_summary["open"]), "note": "Reported through verification", "tone": "coral" if issue_summary["open"] else "green"},
            {"label": "HIGH / URGENT", "value": str(issue_summary["high_urgent"]), "note": "Priority follow-up", "tone": "coral" if issue_summary["high_urgent"] else "green"},
            {"label": "PENDING VERIFICATION", "value": str(issue_summary["pending_verification"]), "note": "Administrator action required", "tone": "amber" if issue_summary["pending_verification"] else "green"},
            {"label": "UNASSIGNED", "value": str(issue_summary["unassigned"]), "note": "Open issues without owner", "tone": "coral" if issue_summary["unassigned"] else "green"},
        ]

    if view == "Unit Profiles":
        return [
            {"label": "PADS EXPIRING", "value": str(readiness_summary["adult_pads"] + readiness_summary["pediatric_pads"]), "note": "Within 90 days or expired", "tone": "amber"},
            {"label": "BATTERY EXPIRING", "value": str(readiness_summary["battery"]), "note": "Within 90 days or expired", "tone": "amber"},
            {"label": "MISSING PM DATE", "value": str(readiness_summary["missing_next_pm"]), "note": "Needs master-data correction", "tone": "coral" if readiness_summary["missing_next_pm"] else "green"},
            {"label": "MISSING COORDINATES", "value": str(readiness_summary["missing_coordinates"]), "note": "Map data incomplete", "tone": "blue" if readiness_summary["missing_coordinates"] else "green"},
        ]

    return [
        {"label": "OVERDUE PM", "value": str(overdue_pm), "note": "Immediate action required", "tone": "coral" if overdue_pm else "green"},
        {"label": "DUE IN 30 DAYS", "value": str(due_pm), "note": "Planning window", "tone": "amber" if due_pm else "green"},
        {"label": "OPEN ISSUES", "value": str(issue_summary["open"]), "note": f"{issue_summary['pending_verification']} pending verification", "tone": "coral" if issue_summary["open"] else "green"},
        {"label": "EXPIRING CONSUMABLES", "value": str(readiness_summary["expiring_total"]), "note": "Within 90 days or expired", "tone": "amber" if readiness_summary["expiring_total"] else "green"},
    ]


def build_recent_activity(
    pm_responses: pd.DataFrame,
    issue_history: pd.DataFrame,
    aed_history: pd.DataFrame,
    plan_records: pd.DataFrame,
    *,
    limit: int = 12,
) -> pd.DataFrame:
    rows: list[dict[str, str]] = []

    for _, row in pm_responses.iterrows():
        serial = clean_text(row.get("AED Serial Number"))
        actor = clean_text(row.get("Technician"))
        rows.append(
            {
                "Activity At": clean_text(row.get("Submitted At")) or clean_text(row.get("Service Date")),
                "Activity Type": "PM",
                "Summary": f"PM response saved for {serial or 'an AED'}",
                "Actor": actor,
                "Source ID": clean_text(row.get("PM Response ID")),
            }
        )

    for _, row in issue_history.iterrows():
        issue_id = clean_text(row.get("Issue ID"))
        action = clean_text(row.get("Action")) or "Issue updated"
        rows.append(
            {
                "Activity At": clean_text(row.get("Action At")),
                "Activity Type": "Issue",
                "Summary": f"{action} · {issue_id}" if issue_id else action,
                "Actor": clean_text(row.get("Action By")),
                "Source ID": issue_id,
            }
        )

    for _, row in aed_history.iterrows():
        serial = clean_text(row.get("Serial Number After")) or clean_text(row.get("Serial Number Before"))
        field_name = clean_text(row.get("Field Name"))
        summary = f"AED master data updated for {serial or 'a record'}"
        if field_name:
            summary += f" · {field_name}"
        rows.append(
            {
                "Activity At": clean_text(row.get("Changed At")),
                "Activity Type": "Asset",
                "Summary": summary,
                "Actor": clean_text(row.get("Source")),
                "Source ID": serial,
            }
        )

    for _, row in plan_records.iterrows():
        serial = clean_text(row.get("Serial Number"))
        plan_id = clean_text(row.get("Plan ID"))
        rows.append(
            {
                "Activity At": clean_text(row.get("Created At")),
                "Activity Type": "Plan",
                "Summary": f"{plan_id or 'PM plan'} added {serial or 'an AED'}",
                "Actor": clean_text(row.get("Assigned To")),
                "Source ID": plan_id,
            }
        )

    if not rows:
        return pd.DataFrame(columns=ACTIVITY_COLUMNS)

    activity = pd.DataFrame(rows, columns=ACTIVITY_COLUMNS)
    activity["_Parsed"] = pd.to_datetime(
        activity["Activity At"],
        format=DATETIME_FORMAT,
        errors="coerce",
    )
    missing = activity["_Parsed"].isna()
    activity.loc[missing, "_Parsed"] = pd.to_datetime(
        activity.loc[missing, "Activity At"],
        format=DATE_FORMAT,
        errors="coerce",
    )
    activity = activity.sort_values("_Parsed", ascending=False, na_position="last")
    return activity.head(limit)[ACTIVITY_COLUMNS].reset_index(drop=True)


def build_data_health(
    aed_data: pd.DataFrame,
    queue: pd.DataFrame,
    source_status: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    data_exceptions = queue[queue["Category"].eq("Data")] if not queue.empty else queue
    unhealthy_sources = [
        key for key, status in source_status.items() if not status.get("healthy", False)
    ]
    empty_operational_sources = [
        key
        for key in ["pm_plan", "pm_responses", "aed_history"]
        if source_status.get(key, {}).get("record_count", 0) == 0
    ]
    return {
        "total_units": len(aed_data),
        "exception_count": len(data_exceptions),
        "unhealthy_source_count": len(unhealthy_sources),
        "empty_operational_sources": empty_operational_sources,
        "warning_count": len(data_exceptions) + len(unhealthy_sources),
    }


def build_dashboard_snapshot(
    *,
    paths: DashboardPaths,
    selected_period: str | None = None,
    today: date | None = None,
    aed_data: pd.DataFrame | None = None,
) -> dict[str, Any]:
    current_date = today or date.today()
    period = selected_period or pd.Period(current_date, freq="M").strftime("%Y-%m")
    sources = load_dashboard_sources(paths, aed_data=aed_data)

    pm_queue = build_pm_queue(sources["aed_data"], sources["pm_plan"], current_date)
    issue_queue = build_issue_queue(sources["issues"], current_date)
    readiness_queue = build_readiness_queue(sources["aed_data"], current_date)
    data_queue = build_data_exception_queue(sources["aed_data"])
    unified_queue = build_unified_work_queue(
        pm_queue,
        issue_queue,
        readiness_queue,
        data_queue,
    )

    pm_summary = calculate_pm_summary(
        sources["pm_plan"], sources["aed_data"], period
    )
    issue_summary = calculate_issue_summary(sources["issues"])
    readiness_summary = calculate_readiness_summary(
        sources["aed_data"], current_date
    )
    recent_activity = build_recent_activity(
        sources["pm_responses"],
        sources["issue_history"],
        sources["aed_history"],
        sources["pm_plan"],
    )
    data_health = build_data_health(
        sources["aed_data"], unified_queue, sources["source_status"]
    )

    return {
        "as_of": datetime.now().astimezone(),
        "today": current_date,
        "period": period,
        "queue": unified_queue,
        "pm_queue": pm_queue,
        "issue_queue": issue_queue,
        "readiness_queue": readiness_queue,
        "data_queue": data_queue,
        "pm_summary": pm_summary,
        "issue_summary": issue_summary,
        "readiness_summary": readiness_summary,
        "recent_activity": recent_activity,
        "data_health": data_health,
        "source_status": sources["source_status"],
        "aed_data": sources["aed_data"],
        "issues": sources["issues"],
        "pm_plan": sources["pm_plan"],
    }


def apply_dashboard_filters(
    queue: pd.DataFrame,
    *,
    view: str,
    assignee: str = "All",
    keyword: str = "",
) -> pd.DataFrame:
    filtered = queue.copy()

    category_map = {
        "PM": {"PM"},
        "Issues": {"Issue", "Verification"},
        "Unit Profiles": {"Unit", "Data"},
    }
    categories = category_map.get(view)
    if categories:
        filtered = filtered[filtered["Category"].isin(categories)]

    clean_assignee = clean_text(assignee)
    if clean_assignee and clean_assignee != "All":
        if clean_assignee == "Unassigned":
            filtered = filtered[filtered["Owner"].eq("Unassigned")]
        else:
            filtered = filtered[filtered["Owner"].str.casefold().eq(clean_assignee.casefold())]

    clean_keyword = clean_text(keyword).casefold()
    if clean_keyword:
        searchable = (
            filtered[["Item", "Serial Number", "Location", "Title", "Status"]]
            .fillna("")
            .astype(str)
            .agg(" ".join, axis=1)
            .str.casefold()
        )
        filtered = filtered[searchable.str.contains(clean_keyword, regex=False, na=False)]

    return filtered.reset_index(drop=True)


def build_period_options(
    *,
    today: date | None = None,
    months_before: int = 6,
    months_after: int = 12,
) -> list[str]:
    current = pd.Period(today or date.today(), freq="M")
    return [
        (current + offset).strftime("%Y-%m")
        for offset in range(-months_before, months_after + 1)
    ]


def get_assignee_options(queue: pd.DataFrame) -> list[str]:
    if queue.empty:
        return ["All", "Unassigned"]
    owners = sorted(
        {
            clean_text(owner)
            for owner in queue["Owner"].tolist()
            if clean_text(owner) and clean_text(owner) != "Unassigned"
        },
        key=str.casefold,
    )
    return ["All", *owners, "Unassigned"]


def find_selected_source(snapshot: dict[str, Any], selected_item: pd.Series) -> pd.Series | None:
    category = clean_text(selected_item.get("Category"))
    source_index = _safe_int(selected_item.get("Source Index"), default=-1)

    if category in {"PM", "Unit", "Data"}:
        dataframe = snapshot.get("aed_data", pd.DataFrame())
    elif category in {"Issue", "Verification"}:
        dataframe = snapshot.get("issues", pd.DataFrame())
    else:
        return None

    if source_index not in dataframe.index:
        return None
    return dataframe.loc[source_index].copy()
