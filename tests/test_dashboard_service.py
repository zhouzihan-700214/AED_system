from datetime import date
from pathlib import Path

import pandas as pd

from services.dashboard_service import (
    DashboardPaths,
    apply_dashboard_filters,
    build_dashboard_snapshot,
    build_data_exception_queue,
    build_issue_queue,
    build_pm_queue,
    build_readiness_queue,
    build_recent_activity,
    build_unified_work_queue,
    calculate_pm_summary,
)


def test_empty_sources_return_stable_queues() -> None:
    empty = pd.DataFrame()
    assert build_pm_queue(empty, empty, date(2026, 7, 29)).empty
    assert build_issue_queue(empty, date(2026, 7, 29)).empty
    assert build_readiness_queue(empty, date(2026, 7, 29)).empty
    assert build_data_exception_queue(empty).empty


def test_pm_queue_identifies_overdue_and_due_soon() -> None:
    aed_data = pd.DataFrame(
        [
            {
                "Serial Number": "AED-OVERDUE",
                "Location": "Lobby A",
                "Next PM Date": "20-07-2026",
            },
            {
                "Serial Number": "AED-SOON",
                "Location": "Lobby B",
                "Next PM Date": "02-08-2026",
            },
            {
                "Serial Number": "AED-LATER",
                "Location": "Lobby C",
                "Next PM Date": "30-09-2026",
            },
        ]
    )
    plans = pd.DataFrame(
        [
            {
                "Plan ID": "PM-2026-07",
                "Plan Month": "2026-07",
                "Planned Date": "20-07-2026",
                "Serial Number": "AED-OVERDUE",
                "Assigned To": "Zihan",
                "PM Status": "Pending",
                "Created At": "01-07-2026 09:00:00",
            }
        ]
    )

    queue = build_pm_queue(aed_data, plans, date(2026, 7, 29))

    assert set(queue["Item"]) == {"AED-OVERDUE", "AED-SOON"}
    overdue = queue.loc[queue["Item"].eq("AED-OVERDUE")].iloc[0]
    due_soon = queue.loc[queue["Item"].eq("AED-SOON")].iloc[0]
    assert overdue["Priority"] == "Critical"
    assert overdue["Owner"] == "Zihan"
    assert "overdue" in overdue["Due / Age"]
    assert due_soon["Priority"] == "High"


def test_pending_verification_is_not_duplicated_as_open_issue() -> None:
    issues = pd.DataFrame(
        [
            {
                "Issue ID": "ISS-VERIFY",
                "Reported At": "20-07-2026 10:00:00",
                "Serial Number": "AED-001",
                "Location": "Lobby",
                "Issue Type": "Cover broken",
                "Priority": "Medium",
                "Status": "Pending Verification",
                "Current Assignee": "A",
            },
            {
                "Issue ID": "ISS-HIGH",
                "Reported At": "28-07-2026 10:00:00",
                "Serial Number": "AED-002",
                "Location": "Lobby",
                "Issue Type": "RFU fault",
                "Priority": "High",
                "Status": "In Progress",
                "Current Assignee": "B",
            },
        ]
    )

    queue = build_issue_queue(issues, date(2026, 7, 29))
    verification = queue.loc[queue["Item"].eq("ISS-VERIFY")]

    assert len(verification) == 1
    assert verification.iloc[0]["Category"] == "Verification"
    assert verification.iloc[0]["Next Action"] == "Verify resolution"


def test_unified_queue_prioritises_critical_work() -> None:
    pm_queue = pd.DataFrame(
        [
            {
                "Queue ID": "PM:1",
                "Category": "PM",
                "Priority": "Critical",
                "Item": "AED-1",
                "Title": "PM",
                "Serial Number": "AED-1",
                "Location": "A",
                "Due Date": "20-07-2026",
                "Due / Age": "9 days overdue",
                "Age Days": "9",
                "Owner": "Unassigned",
                "Status": "Overdue",
                "Next Action": "Assign",
                "Sort Score": 100009,
                "Source Index": "0",
            }
        ]
    )
    issue_queue = pd.DataFrame(
        [
            {
                "Queue ID": "ISSUE:1",
                "Category": "Issue",
                "Priority": "Medium",
                "Item": "ISS-1",
                "Title": "Issue",
                "Serial Number": "AED-2",
                "Location": "B",
                "Due Date": "—",
                "Due / Age": "Open 1 day",
                "Age Days": "1",
                "Owner": "B",
                "Status": "In Progress",
                "Next Action": "Update",
                "Sort Score": 70001,
                "Source Index": "0",
            }
        ]
    )

    combined = build_unified_work_queue(pm_queue, issue_queue)
    assert combined.iloc[0]["Queue ID"] == "PM:1"


def test_readiness_ignores_implausible_1930_date() -> None:
    aed_data = pd.DataFrame(
        [
            {
                "Serial Number": "AED-BAD-YEAR",
                "Location": "A",
                "Adult Pads Expiry Date": "16-02-1930",
                "Pediatric Pads Expiry Date": "",
                "Battery Expiry Date": "",
            },
            {
                "Serial Number": "AED-EXPIRED",
                "Location": "B",
                "Adult Pads Expiry Date": "",
                "Pediatric Pads Expiry Date": "",
                "Battery Expiry Date": "01-03-2026",
            },
        ]
    )

    queue = build_readiness_queue(aed_data, date(2026, 7, 29))
    assert "AED-BAD-YEAR" not in set(queue["Item"])
    assert "AED-EXPIRED" in set(queue["Item"])


def test_data_exceptions_find_duplicates_coordinates_and_bad_year() -> None:
    aed_data = pd.DataFrame(
        [
            {
                "Serial Number": "AED-001",
                "Location": "A",
                "Postal Code": "123456",
                "Next PM Date": "01-08-2026",
                "PM Completed Date": "01-08-2025",
                "Adult Pads Expiry Date": "16-02-1930",
                "Pediatric Pads Expiry Date": "",
                "Battery Expiry Date": "",
                "Latitude": "",
                "Longitude": "",
            },
            {
                "Serial Number": "AED-001",
                "Location": "B",
                "Postal Code": "654321",
                "Next PM Date": "01-09-2026",
                "PM Completed Date": "01-09-2025",
                "Adult Pads Expiry Date": "",
                "Pediatric Pads Expiry Date": "",
                "Battery Expiry Date": "",
                "Latitude": "1.30",
                "Longitude": "103.80",
            },
        ]
    )

    queue = build_data_exception_queue(aed_data)
    titles = set(queue["Title"])
    assert "Duplicate Serial Number" in titles
    assert "Missing Map Coordinates" in titles
    assert "Implausible Date Year" in titles


def test_pm_summary_uses_selected_plan_month() -> None:
    plans = pd.DataFrame(
        [
            {
                "Plan Month": "2026-07",
                "PM Status": "Completed",
                "Assigned To": "A",
            },
            {
                "Plan Month": "2026-07",
                "PM Status": "Pending",
                "Assigned To": "",
            },
            {
                "Plan Month": "2026-08",
                "PM Status": "Completed",
                "Assigned To": "B",
            },
        ]
    )
    aed_data = pd.DataFrame(
        [
            {"Next PM Date": "10-07-2026"},
            {"Next PM Date": "12-07-2026"},
            {"Next PM Date": "10-08-2026"},
        ]
    )

    summary = calculate_pm_summary(plans, aed_data, "2026-07")
    assert summary["planned"] == 2
    assert summary["completed"] == 1
    assert summary["pending"] == 1
    assert summary["unassigned"] == 1
    assert summary["due_this_period"] == 2
    assert summary["completion_percent"] == 50


def test_recent_activity_is_combined_and_sorted() -> None:
    pm = pd.DataFrame(
        [
            {
                "Submitted At": "29-07-2026 12:00:00",
                "AED Serial Number": "AED-001",
                "Technician": "Zihan",
                "PM Response ID": "PM-1",
            }
        ]
    )
    issue_history = pd.DataFrame(
        [
            {
                "Action At": "29-07-2026 13:00:00",
                "Issue ID": "ISS-1",
                "Action": "Work started",
                "Action By": "B",
            }
        ]
    )

    activity = build_recent_activity(
        pm,
        issue_history,
        pd.DataFrame(),
        pd.DataFrame(),
    )

    assert activity.iloc[0]["Activity Type"] == "Issue"
    assert activity.iloc[1]["Activity Type"] == "PM"


def test_dashboard_filters_by_view_owner_and_keyword() -> None:
    queue = pd.DataFrame(
        [
            {
                "Category": "PM",
                "Owner": "Zihan",
                "Item": "AED-001",
                "Serial Number": "AED-001",
                "Location": "Bukit Merah",
                "Title": "PM",
                "Status": "Pending",
            },
            {
                "Category": "Issue",
                "Owner": "B",
                "Item": "ISS-1",
                "Serial Number": "AED-002",
                "Location": "Jurong",
                "Title": "Cover broken",
                "Status": "In Progress",
            },
        ]
    )

    filtered = apply_dashboard_filters(
        queue,
        view="PM",
        assignee="Zihan",
        keyword="bukit",
    )
    assert len(filtered) == 1
    assert filtered.iloc[0]["Item"] == "AED-001"


def test_snapshot_initialises_empty_operational_files(tmp_path: Path) -> None:
    aed_file = tmp_path / "aed_data.csv"
    pd.DataFrame(
        [
            {
                "Serial Number": "AED-001",
                "Location": "Lobby",
                "Postal Code": "123456",
                "Next PM Date": "01-08-2026",
                "Latitude": "1.30",
                "Longitude": "103.80",
            }
        ]
    ).to_csv(aed_file, index=False, encoding="utf-8-sig")

    issue_file = tmp_path / "issue_records.csv"
    paths = DashboardPaths(
        aed_data=aed_file,
        issue_records=issue_file,
        pm_responses=tmp_path / "pm_responses.csv",
        pm_plan=tmp_path / "pm_plan_records.csv",
        aed_history=tmp_path / "aed_management_history.csv",
        issue_history=tmp_path / "issue_history.csv",
    )

    snapshot = build_dashboard_snapshot(
        paths=paths,
        selected_period="2026-07",
        today=date(2026, 7, 29),
    )

    assert snapshot["data_health"]["total_units"] == 1
    for path in [paths.pm_responses, paths.pm_plan, paths.aed_history]:
        assert path.exists()
        assert path.stat().st_size > 3
