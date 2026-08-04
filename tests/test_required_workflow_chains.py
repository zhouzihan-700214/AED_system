from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from services import aed_repository, issue_service, pm_service
from services.excel_sync_service import SyncResult
from services.excel_transaction_service import OperationResult
from services.service_record_service import load_service_records
from services.unit_profile_service import filter_unit_profiles


class FakeUpload:
    def __init__(self, name: str = "completion.jpg", content: bytes = b"photo") -> None:
        self.name = name
        self._content = content

    def getbuffer(self) -> bytes:
        return self._content


def test_system_write_uploads_same_excel_and_external_excel_refreshes_system(monkeypatch) -> None:
    calls: dict[str, object] = {}

    monkeypatch.setattr(aed_repository, "is_cloud_onedrive_enabled", lambda: True)
    monkeypatch.setattr(aed_repository, "_prepare_workbook", lambda force: "etag-before")
    monkeypatch.setattr(
        aed_repository,
        "sync_excel_to_cache",
        lambda force, **kwargs: calls.setdefault("cache_force", force)
        or SyncResult("synced", "cache refreshed", True, True, 1),
    )

    def fake_upload(*, expected_etag: str = ""):
        calls["uploaded_etag"] = expected_etag
        return SimpleNamespace(message="uploaded")

    monkeypatch.setattr(aed_repository, "upload_workbook", fake_upload)
    result = aed_repository._run_operation(
        lambda: OperationResult(
            "updated",
            "local workbook updated",
            operation_id="OP-1",
            serial_number="AED-001",
            changed_fields=("Model",),
        )
    )

    assert result.success
    assert calls["uploaded_etag"] == "etag-before"
    assert "OneDrive Excel updated" in result.message

    download_calls: list[bool] = []
    monkeypatch.setattr(
        aed_repository,
        "download_workbook",
        lambda force=False: download_calls.append(force)
        or SimpleNamespace(etag="etag-after", message="downloaded"),
    )
    monkeypatch.setattr(
        aed_repository,
        "_prepare_workbook",
        lambda force: aed_repository.download_workbook(force=force).etag,
    )
    monkeypatch.setattr(
        aed_repository,
        "sync_excel_to_cache",
        lambda force=False, **kwargs: SyncResult(
            "synced", "external Excel loaded", True, True, 1
        ),
    )
    refreshed = aed_repository.ensure_cache_current(force=False)

    assert refreshed.changed
    assert download_calls == [False]


def test_pm_checklist_record_is_visible_in_service_records_and_failures_create_issues(
    monkeypatch,
    tmp_path: Path,
) -> None:
    pm_file = tmp_path / "pm_responses.csv"
    manual_file = tmp_path / "manual_service_records.csv"
    issue_file = tmp_path / "issue_records.csv"
    monkeypatch.setattr(pm_service, "PM_RESPONSES_FILE", pm_file)

    response = {
        column: "" for column in pm_service.PM_RESPONSE_COLUMNS
    }
    response.update(
        {
            "Operation ID": "OP-001",
            "Submission Status": "COMMITTED",
            "Excel Update Status": "UPDATED",
            "Submitted By": "Zihan",
            "Service Date": "03-08-2026",
            "Technician": "Zihan",
            "Service Type": "Preventive Maintenance (PM)",
            "Postal Code": "123456",
            "Lift Lobby": "A",
            "AED Serial Number": "AED-001",
            "Original Serial Number": "AED-001",
            "AED Location": "Block 1 Lobby",
            "PM Response ID": "PM-TEST-001",
            "Cabinet Inspection": "Fail",
            "Cabinet Alarm": "Pass",
            "AED Physical Condition": "Pass",
            "Self Test Result": "Pass",
            "AED Cover": "Pass",
            "Adult Pads Within Expiry Date": "Yes",
            "Pediatric Pads Within Expiry Date": "Yes",
            "AED Signage": "Yes",
            "Final Check": "Yes",
            "Master Data Updated": "Yes",
            "Submitted At": "03-08-2026 20:30:00",
        }
    )

    pm_service.append_pm_response(response)
    records = load_service_records(
        response_csv_file=pm_file,
        manual_service_file=manual_file,
        aed_dataframe=pd.DataFrame(
            [
                {
                    "Serial Number": "AED-001",
                    "Model": "AED Plus",
                    "Location": "Block 1 Lobby",
                }
            ]
        ),
    )

    saved = records[records["PM Response ID"].eq("PM-TEST-001")]
    assert len(saved) == 1
    assert saved.iloc[0]["Record Source"] == "PM Checklist"
    assert saved.iloc[0]["AED Model"] == "AED Plus"

    issue_ids, warnings = pm_service.create_pm_failure_issues(
        response,
        issue_csv_file=issue_file,
        model="AED Plus",
        reported_by="Zihan",
    )
    assert not warnings
    assert len(issue_ids) == 1

    issue = issue_service.get_issue_record(issue_file, issue_ids[0])
    assert issue["Source"] == "PM Checklist"
    assert issue["Serial Number"] == "AED-001"
    assert issue["Status"] == "Reported"


def test_reported_issue_can_be_processed_through_verification_and_closed(tmp_path: Path) -> None:
    issue_file = tmp_path / "issue_records.csv"
    issue_id = issue_service.create_issue(
        issue_file,
        issue_data={
            "Source": "Report Issue",
            "Reported By": "Zihan",
            "Serial Number": "AED-002",
            "Model": "AED Pro",
            "Location": "Main Lobby",
            "Issue Type": "Cabinet alarm not working",
            "Detailed Description": "Alarm did not sound.",
            "Priority": "High",
        },
    )

    issue_service.assign_issue(
        issue_file,
        issue_id=issue_id,
        reviewed_by="Supervisor",
        assigned_to="Technician 1",
    )
    issue_service.start_issue_work(
        issue_file,
        issue_id=issue_id,
        started_by="Technician 1",
    )
    submission_id = issue_service.submit_issue_resolution(
        issue_file,
        issue_id=issue_id,
        submitted_by="Technician 1",
        action_taken="Replaced the alarm switch.",
        test_performed="Opened the cabinet and confirmed the alarm sounded.",
        test_result="Pass",
        resolution_notes="Alarm operation restored.",
        uploaded_files=[FakeUpload()],
    )
    issue_service.verify_issue_resolution(
        issue_file,
        issue_id=issue_id,
        verified_by="Supervisor",
        verification_notes="Photo and functional test verified.",
        approve=True,
    )

    closed = issue_service.get_issue_record(issue_file, issue_id)
    submissions = issue_service.get_resolution_submissions_for_issue(
        issue_file, issue_id
    )
    assert closed["Status"] == "Closed"
    assert closed["Latest Submission ID"] == submission_id
    assert submissions.iloc[0]["Verification Result"] == "Approved"


def test_aed_management_profile_search_matches_all_required_fields() -> None:
    data = pd.DataFrame(
        [
            {
                "Serial Number": "AED-001",
                "Model": "AED Plus",
                "Location": "North Lobby",
                "Block / Locations": "Block 10",
                "Street Name": "Example Street",
                "Postal Code": "123456",
            },
            {
                "Serial Number": "AED-002",
                "Model": "AED Pro",
                "Location": "South Lobby",
                "Block / Locations": "Block 20",
                "Street Name": "Second Road",
                "Postal Code": "654321",
            },
        ]
    )

    assert filter_unit_profiles(data, "aed-001")["Serial Number"].tolist() == ["AED-001"]
    assert filter_unit_profiles(data, "pro")["Serial Number"].tolist() == ["AED-002"]
    assert filter_unit_profiles(data, "north")["Serial Number"].tolist() == ["AED-001"]
    assert filter_unit_profiles(data, "second road")["Serial Number"].tolist() == ["AED-002"]
    assert filter_unit_profiles(data, "654")["Serial Number"].tolist() == ["AED-002"]
