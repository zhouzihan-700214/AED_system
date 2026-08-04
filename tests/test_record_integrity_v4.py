from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from services import pm_service
from services.issue_service import (
    assign_issue,
    create_issue,
    load_issue_records,
    start_issue_work,
    submit_issue_resolution,
    verify_issue_resolution,
)
from services.service_record_service import load_service_records
from services.unit_profile_service import (
    MANUAL_SERVICE_RECORD_COLUMNS,
    append_manual_service_record,
)


class UploadedImage:
    def __init__(self, name: str = "evidence.jpg", content: bytes = b"image") -> None:
        self.name = name
        self._content = content

    def getbuffer(self):
        return memoryview(self._content)


def test_pm_response_preserves_reference_notes_model_and_battery_type() -> None:
    response = pm_service.build_response(
        service_date=date(2026, 8, 3),
        technician="Tech",
        service_type="PM+batt",
        customer_location="SCDF / SAL",
        postal_code="123456",
        lift_lobby="A",
        loaner_unit="No",
        cabinet_inspection="Pass",
        cabinet_alarm="Pass",
        serial_number="AED-001",
        physical_condition="Pass",
        self_test_result="Pass",
        battery_expiry=date(2030, 1, 1),
        aed_cover="Pass",
        adult_pads_expiry=date(2028, 1, 1),
        adult_pads_lot="ALOT",
        adult_pads_within_expiry="Yes",
        pediatric_pads_expiry=date(2028, 2, 1),
        pediatric_pads_lot="PLOT",
        pediatric_pads_within_expiry="Yes",
        aed_signage="Yes",
        final_check="Yes",
        aed_location="Lobby",
        original_serial_number="AED-001",
        service_report_id="e-SR900",
        service_notes="Battery replaced and unit tested.",
        aed_model="AED Plus",
    )

    assert response["Service Report e-SR"] == "e-SR900"
    assert response["Service Notes"] == "Battery replaced and unit tested."
    assert response["AED Model"] == "AED Plus"
    assert response["Battery Replaced"] == "Yes"


def test_pm_master_update_appends_battery_history(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_update_unit(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("services.aed_repository.update_unit", fake_update_unit)
    master = pd.DataFrame(
        [
            {
                "Serial Number": "AED-001",
                "PM Interval Months": "12",
                "Battery Replacement History": "01-01-2025",
                "Postal Code": "123456",
                "Lift Lobby": "A",
                "Battery Expiry Date": "01-01-2029",
                "Adult Pads Expiry Date": "01-01-2028",
                "Adult Pads Lot Number": "A",
                "Pediatric Pads Expiry Date": "01-02-2028",
                "Pediatric Pads Lot Number": "P",
                "PM Completed Date": "",
                "Next PM Date": "",
                "Job Type": "",
                "Last Done By": "",
                "Service Report e-SR": "",
            }
        ]
    )

    pm_service.update_selected_aed(
        master,
        0,
        {
            "AED Serial Number": "AED-001",
            "Service Date": "03-08-2026",
            "Service Type": "PM+batt",
            "Service Report e-SR": "e-SR901",
            "Battery Replaced": "Yes",
            "Postal Code": "123456",
            "Lift Lobby": "A",
            "Battery Expiry Date": "01-01-2031",
            "Adult Pads Expiry Date": "01-01-2028",
            "Adult Pads Lot Number": "A",
            "Pediatric Pads Expiry Date": "01-02-2028",
            "Pediatric Pads Lot Number": "P",
            "Technician": "Tech",
        },
        user="Tech",
        session_id="S1",
    )

    changes = captured["changes"]
    assert changes["Battery Replacement History"] == "01-01-2025; 03-08-2026"
    assert changes["Service Report e-SR"] == "e-SR901"


def test_pm_plan_completion_is_exact_month_and_idempotent(tmp_path: Path) -> None:
    plan_file = tmp_path / "pm_plan_records.csv"
    rows = pd.DataFrame(
        [
            {
                "Plan ID": "PM-2026-08",
                "Plan Month": "2026-08",
                "Serial Number": "AED-001",
                "PM Status": "Pending",
                "Completed Date": "",
                "Created At": "01-08-2026 08:00:00",
            },
            {
                "Plan ID": "PM-2026-09",
                "Plan Month": "2026-09",
                "Serial Number": "AED-001",
                "PM Status": "Pending",
                "Completed Date": "",
                "Created At": "01-09-2026 08:00:00",
            },
        ]
    )
    for column in pm_service.PM_PLAN_COLUMNS:
        if column not in rows.columns:
            rows[column] = ""
    rows[pm_service.PM_PLAN_COLUMNS].to_csv(plan_file, index=False, encoding="utf-8-sig")

    linked = pm_service.complete_matching_pm_plan(
        "AED-001",
        "03-08-2026",
        operation_id="OP-1",
        response_id="PM-R1",
        completed_by="Tech",
        plan_file=plan_file,
    )
    assert linked == "PM-2026-08"

    # Retrying the same commit returns the existing link instead of losing it.
    linked_again = pm_service.complete_matching_pm_plan(
        "AED-001",
        "03-08-2026",
        operation_id="OP-1",
        response_id="PM-R1",
        completed_by="Tech",
        plan_file=plan_file,
    )
    assert linked_again == "PM-2026-08"

    saved = pd.read_csv(plan_file, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    august = saved[saved["Plan ID"].eq("PM-2026-08")].iloc[0]
    september = saved[saved["Plan ID"].eq("PM-2026-09")].iloc[0]
    assert august["PM Status"] == "Completed"
    assert august["Completion Record ID"] == "PM-R1"
    assert august["Completed By"] == "Tech"
    assert september["PM Status"] == "Pending"


def test_pm_failure_issue_link_is_durable_and_deduplicated(tmp_path: Path) -> None:
    issue_file = tmp_path / "issue_records.csv"
    response = {
        "PM Response ID": "PM-R2",
        "Technician": "Tech",
        "AED Serial Number": "AED-001",
        "AED Location": "Lobby",
        "Postal Code": "123456",
        "Lift Lobby": "A",
        "Loaner Unit": "No",
        "Self Test Result": "Fail",
        "Cabinet Inspection": "Pass",
        "Cabinet Alarm": "Pass",
        "AED Physical Condition": "Pass",
        "AED Cover": "Pass",
        "Adult Pads Within Expiry Date": "Yes",
        "Pediatric Pads Within Expiry Date": "Yes",
        "AED Signage": "Yes",
        "Final Check": "Yes",
    }

    first_ids, first_warnings = pm_service.create_pm_failure_issues(
        response,
        issue_csv_file=issue_file,
        model="AED Plus",
        reported_by="Tech",
    )
    second_ids, second_warnings = pm_service.create_pm_failure_issues(
        response,
        issue_csv_file=issue_file,
        model="AED Plus",
        reported_by="Tech",
    )

    assert not first_warnings and not second_warnings
    assert first_ids == second_ids
    records = load_issue_records(issue_file)
    assert len(records) == 1
    row = records.iloc[0]
    assert row["Source Record ID"] == "PM-R2"
    assert row["Source Field"] == "Self Test Result"
    assert row["Source Value"] == "Fail"


def test_service_records_include_manual_snapshots_and_resolution_evidence(tmp_path: Path) -> None:
    pm_file = tmp_path / "pm_responses.csv"
    manual_file = tmp_path / "manual_service_records.csv"
    issue_file = tmp_path / "issue_records.csv"
    resolution_file = tmp_path / "issue_resolution_submissions.csv"

    pd.DataFrame(columns=pm_service.PM_RESPONSE_COLUMNS).to_csv(
        pm_file, index=False, encoding="utf-8-sig"
    )
    append_manual_service_record(
        {
            "AED Serial Number": "AED-001",
            "AED Model": "AED Plus",
            "AED Location": "Old Lobby",
            "Postal Code": "111111",
            "Lift Lobby": "A",
            "Service Date": "01-08-2026",
            "Service Type": "Commissioning",
            "Technician": "Tech",
            "Reference": "e-SR1",
            "Status": "Completed",
            "Details": "Commissioned.",
        },
        path=manual_file,
    )

    issue_id = create_issue(
        issue_file,
        issue_data={
            "Source": "Report Issue",
            "Reported By": "Reporter",
            "Serial Number": "AED-001",
            "Model": "AED Plus",
            "Location": "Old Lobby",
            "Postal Code": "111111",
            "Lift Lobby": "A",
            "Issue Type": "Battery",
            "Detailed Description": "Battery fault",
            "Priority": "High",
        },
    )
    assign_issue(
        issue_file,
        issue_id=issue_id,
        reviewed_by="Supervisor",
        assigned_to="Tech",
    )
    start_issue_work(issue_file, issue_id=issue_id, started_by="Tech")
    submission_id = submit_issue_resolution(
        issue_file,
        issue_id=issue_id,
        submitted_by="Tech",
        action_taken="Replaced battery",
        test_performed="Self test",
        test_result="Pass",
        resolution_notes="Unit OK",
        uploaded_files=[UploadedImage()],
        parts_replaced="Battery",
    )
    verify_issue_resolution(
        issue_file,
        issue_id=issue_id,
        verified_by="Supervisor",
        verification_notes="Evidence checked",
        approve=True,
    )

    records = load_service_records(
        pm_file,
        manual_service_file=manual_file,
        issue_record_file=issue_file,
        resolution_file=resolution_file,
        aed_dataframe=pd.DataFrame(
            [{"Serial Number": "AED-001", "Model": "NEW MODEL", "Location": "New Lobby"}]
        ),
    )

    manual = records[records["Record Source"].eq("Unit Profile")].iloc[0]
    assert manual["AED Model"] == "AED Plus"
    assert manual["AED Location"] == "Old Lobby"
    assert manual["Postal Code"] == "111111"

    resolution = records[records["Resolution Submission ID"].eq(submission_id)].iloc[0]
    assert resolution["Issue ID"] == issue_id
    assert resolution["Record Source"] == "Issue Resolution"
    assert resolution["Record Status"] == "Approved"
    assert resolution["Battery Replaced"] == "Yes"
    assert resolution["Resolution Attempt Number"] == "1"
    assert resolution["Action Taken"] == "Replaced battery"
    assert resolution["Parts Replaced"] == "Battery"
    assert resolution["Test Result"] == "Pass"
    assert resolution["Verification Notes"] == "Evidence checked"
    assert resolution["Attachment Count"] == "1"
    assert "issue_photos" in resolution["Attachment Paths"]


def test_service_record_dates_accept_current_and_legacy_formats(tmp_path: Path) -> None:
    pm_file = tmp_path / "pm_responses.csv"
    rows = pd.DataFrame(
        [
            {"PM Response ID": "R1", "Service Date": "03-08-2026", "Submitted At": "03-08-2026 09:00:00"},
            {"PM Response ID": "R2", "Service Date": "2026-08-02", "Submitted At": "2026-08-02T10:00:00"},
            {"PM Response ID": "R3", "Service Date": "01/08/2026", "Submitted At": "01/08/2026 11:00:00"},
        ]
    )
    for column in pm_service.PM_RESPONSE_COLUMNS:
        if column not in rows.columns:
            rows[column] = ""
    rows[pm_service.PM_RESPONSE_COLUMNS].to_csv(pm_file, index=False, encoding="utf-8-sig")

    records = load_service_records(
        pm_file,
        manual_service_file=tmp_path / "manual.csv",
        issue_record_file=tmp_path / "issues.csv",
        resolution_file=tmp_path / "resolutions.csv",
        aed_dataframe=pd.DataFrame(columns=["Serial Number", "Model", "Location"]),
    )

    assert records["_Service Date Parsed"].notna().sum() == 3
    assert records["_Submitted At Parsed"].notna().sum() == 3
