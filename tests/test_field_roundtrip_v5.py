from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from services import pm_service
from services.service_record_service import load_service_records
from services.unit_profile_service import (
    append_manual_service_record,
    build_manual_service_update_plan,
)


def _master_row() -> dict[str, str]:
    return {
        "Job Type": "PM",
        "Last Done By": "Existing Tech",
        "Service Report e-SR": "e-SR-OLD",
        "PM Completed Date": "01-01-2026",
        "Next PM Date": "01-01-2027",
        "Battery Replacement History": "01-01-2025",
    }



def test_pm_record_is_still_saved_when_excel_values_need_no_change() -> None:
    class Result:
        success = False
        status = "no_changes"
        message = "No changes were detected."

    assert pm_service.classify_pm_excel_update_result(Result()) == "NO_CHANGES"

def test_manual_service_blank_optional_reference_does_not_clear_master() -> None:
    plan = build_manual_service_update_plan(
        _master_row(),
        service_date=date(2026, 8, 4),
        service_type="Commissioning",
        technician="New Tech",
        reference="",
        status="Completed",
        update_latest=True,
        update_pm_dates=False,
        interval_months=12,
    )

    assert plan["changes"]["Job Type"] == "Commissioning"
    assert plan["changes"]["Last Done By"] == "New Tech"
    assert "Service Report e-SR" not in plan["changes"]
    assert plan["originals"]["Job Type"] == "PM"


def test_pending_battery_record_never_updates_battery_history() -> None:
    plan = build_manual_service_update_plan(
        _master_row(),
        service_date=date(2026, 8, 4),
        service_type="PM+batt",
        technician="Tech",
        reference="",
        status="Pending",
        update_latest=False,
        update_pm_dates=False,
        interval_months=12,
    )

    assert plan["battery_replaced"] is False
    assert plan["battery_history_changed"] is False
    assert "Battery Replacement History" not in plan["changes"]


def test_completed_pm_battery_plan_tracks_every_master_target() -> None:
    plan = build_manual_service_update_plan(
        _master_row(),
        service_date=date(2026, 8, 4),
        service_type="PM+batt",
        technician="Tech",
        reference="e-SR-NEW",
        status="Completed",
        update_latest=True,
        update_pm_dates=True,
        interval_months=6,
    )

    assert plan["changes"]["Job Type"] == "PM+batt"
    assert plan["changes"]["Last Done By"] == "Tech"
    assert plan["changes"]["Service Report e-SR"] == "e-SR-NEW"
    assert plan["changes"]["PM Completed Date"] == "04-08-2026"
    assert plan["changes"]["Next PM Date"] == "04-02-2027"
    assert plan["changes"]["Battery Replacement History"] == (
        "01-01-2025; 04-08-2026"
    )
    assert plan["battery_replaced"] is True
    assert plan["interval_months_used"] == "6"
    assert plan["complete_pm_plan"] is True


def test_manual_service_every_entered_and_generated_field_reaches_service_records(
    tmp_path: Path,
) -> None:
    pm_file = tmp_path / "pm_responses.csv"
    manual_file = tmp_path / "manual_service_records.csv"
    issue_file = tmp_path / "issue_records.csv"
    resolution_file = tmp_path / "issue_resolution_submissions.csv"
    pd.DataFrame(columns=pm_service.PM_RESPONSE_COLUMNS).to_csv(
        pm_file, index=False, encoding="utf-8-sig"
    )

    append_manual_service_record(
        {
            "Service Record ID": "SRV-ROUNDTRIP-1",
            "Created At": "04-08-2026 12:00:00",
            "Created By": "Zihan",
            "AED Serial Number": "AED-001",
            "AED Model": "AED Plus",
            "AED Location": "Block 1 Lobby",
            "Postal Code": "123456",
            "Lift Lobby": "A",
            "Service Date": "04-08-2026",
            "Service Type": "PM+batt",
            "Technician": "Tech",
            "Reference": "e-SR-123",
            "Status": "Completed",
            "Details": "Battery replaced and self-test passed.",
            "Master Data Updated": "Yes",
            "PM Dates Updated": "Yes",
            "Battery Replaced": "Yes",
            "Battery History Updated": "Yes",
            "PM Interval Months Used": "6",
            "Linked Plan ID": "PLAN-2026-08-1",
            "Master Operation ID": "OP-1",
            "Source": "Unit Profile",
        },
        path=manual_file,
    )

    records = load_service_records(
        pm_file,
        manual_service_file=manual_file,
        issue_record_file=issue_file,
        resolution_file=resolution_file,
        aed_dataframe=pd.DataFrame(
            [{"Serial Number": "AED-001", "Model": "Changed", "Location": "Changed"}]
        ),
    )
    row = records[records["Service Record ID"].eq("SRV-ROUNDTRIP-1")].iloc[0]

    expected = {
        "Submitted At": "04-08-2026 12:00:00",
        "Submitted By": "Zihan",
        "AED Serial Number": "AED-001",
        "AED Model": "AED Plus",
        "AED Location": "Block 1 Lobby",
        "Postal Code": "123456",
        "Lift Lobby": "A",
        "Service Date": "04-08-2026",
        "Service Type": "PM+batt",
        "Technician": "Tech",
        "Service Report e-SR": "e-SR-123",
        "Record Status": "Completed",
        "Service Notes": "Battery replaced and self-test passed.",
        "Master Data Updated": "Yes",
        "PM Dates Updated": "Yes",
        "Battery Replaced": "Yes",
        "Battery History Updated": "Yes",
        "PM Interval Months Used": "6",
        "Linked Plan ID": "PLAN-2026-08-1",
        "Master Operation ID": "OP-1",
        "Record Source": "Unit Profile",
    }
    for field, value in expected.items():
        assert row[field] == value, field


def test_issue_source_linkage_and_loaner_fields_are_visible_in_issue_ui() -> None:
    source = (Path(__file__).parents[1] / "views" / "issues.py").read_text(
        encoding="utf-8"
    )
    for text in [
        "Source and Record Linkage",
        'row.get("Source")',
        'row.get("Source Record ID")',
        'row.get("Source Field")',
        'row.get("Source Value")',
        'row.get("Is Loaner")',
    ]:
        assert text in source


def test_deactivation_reason_has_a_visible_lifecycle_history_section() -> None:
    source = (Path(__file__).parents[1] / "views" / "aed_management.py").read_text(
        encoding="utf-8"
    )
    assert "AED Lifecycle History" in source
    assert "AED_LIFECYCLE_FILE" in source
    assert '"Reason"' in source


def test_all_official_profile_and_add_fields_have_excel_roundtrip_mapping() -> None:
    from services.aed_field_schema import ADD_FIELDS, DETAIL_EDITABLE_COLUMNS
    from services.aed_field_schema import APP_TO_EXCEL_COLUMNS

    assert set(ADD_FIELDS).issubset(APP_TO_EXCEL_COLUMNS)
    assert set(DETAIL_EDITABLE_COLUMNS).issubset(APP_TO_EXCEL_COLUMNS)

    profile_source = (Path(__file__).parents[1] / "views" / "aed_management.py").read_text(
        encoding="utf-8"
    )
    for field in DETAIL_EDITABLE_COLUMNS:
        assert field in profile_source, field


def test_pm_issue_resolution_and_planning_schemas_cover_entered_business_fields() -> None:
    from services.issue_service import (
        ISSUE_RECORD_COLUMNS,
        RESOLUTION_SUBMISSION_COLUMNS,
    )
    from services.pm_service import PM_PLAN_COLUMNS, PM_RESPONSE_COLUMNS

    pm_entered = {
        "Service Date", "Technician", "Service Type", "Service Report e-SR",
        "Service Notes", "Customer / Location", "Postal Code", "Lift Lobby",
        "Loaner Unit", "Cabinet Inspection", "Cabinet Alarm", "AED Serial Number",
        "AED Physical Condition", "Self Test Result", "Battery Expiry Date",
        "AED Cover", "Adult Pads Expiry Date", "Adult Pads Lot Number",
        "Adult Pads Within Expiry Date", "Pediatric Pads Expiry Date",
        "Pediatric Pads Lot Number", "Pediatric Pads Within Expiry Date",
        "AED Signage", "Final Check",
    }
    issue_entered = {
        "Source", "Reported By", "Serial Number", "Model", "Location",
        "Postal Code", "Lift Lobby", "Is Loaner", "Issue Type",
        "Detailed Description", "Priority",
    }
    resolution_entered = {
        "Submitted By", "Action Taken", "Root Cause", "Parts Replaced",
        "Test Performed", "Test Result", "Resolution Notes",
        "Verification Result", "Verified By", "Verified At", "Verification Notes",
    }
    planning_entered = {
        "Plan Month", "Planned Date", "Serial Number", "Assigned To",
        "Is Loaner", "Color Override",
    }

    assert pm_entered.issubset(PM_RESPONSE_COLUMNS)
    assert issue_entered.issubset(ISSUE_RECORD_COLUMNS)
    assert resolution_entered.issubset(RESOLUTION_SUBMISSION_COLUMNS)
    assert planning_entered.issubset(PM_PLAN_COLUMNS)
