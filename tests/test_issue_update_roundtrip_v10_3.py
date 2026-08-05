from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import MagicMock

import pandas as pd

sys.modules.setdefault("streamlit", MagicMock())

from services import issue_service
from services.service_record_service import load_service_records
from services.unit_profile_service import build_service_history, load_unit_issues
from utils.date_utils import application_now, application_today
from views import issues as issue_view


class FakeUpload:
    def __init__(self, name: str = "completion.jpg", content: bytes = b"photo") -> None:
        self.name = name
        self._content = content

    def getbuffer(self) -> bytes:
        return self._content


def _create_issue(issue_file: Path, *, issue_type: str = "Cabinet Issue") -> str:
    return issue_service.create_issue(
        issue_file,
        issue_data={
            "Source": "Report Issue",
            "Reported By": "Reporter A",
            "Serial Number": "AED-100",
            "Model": "AED Plus",
            "Location": "Main Lobby",
            "Postal Code": "123456",
            "Lift Lobby": "A",
            "Issue Type": issue_type,
            "Detailed Description": "Cabinet condition requires attention.",
            "Priority": "Medium",
        },
    )


def _submit_resolution(
    issue_file: Path,
    issue_id: str,
    *,
    technician: str,
    suffix: str,
) -> str:
    record = issue_service.get_issue_record(issue_file, issue_id)
    if record["Status"] in {"Reported", "Reopened"}:
        issue_service.assign_issue(
            issue_file,
            issue_id=issue_id,
            reviewed_by="Supervisor A",
            assigned_to=technician,
        )
    issue_service.start_issue_work(
        issue_file,
        issue_id=issue_id,
        started_by=technician,
    )
    return issue_service.submit_issue_resolution(
        issue_file,
        issue_id=issue_id,
        submitted_by=technician,
        action_taken=f"Replaced component {suffix}",
        root_cause="Worn component",
        parts_replaced=f"Component {suffix}",
        test_performed="Functional test",
        test_result="Pass",
        resolution_notes=f"Attempt {suffix} completed.",
        uploaded_files=[FakeUpload(f"attempt_{suffix}.jpg")],
    )


def test_issue_workflow_updates_every_linked_dataset(tmp_path: Path) -> None:
    issue_file = tmp_path / "issue_records.csv"
    pm_file = tmp_path / "pm_responses.csv"
    manual_file = tmp_path / "manual_service_records.csv"
    aed_file = tmp_path / "aed_data.csv"
    resolution_file = tmp_path / "issue_resolution_submissions.csv"
    pd.DataFrame(
        [{"Serial Number": "AED-100", "Model": "AED Plus", "Location": "Main Lobby"}]
    ).to_csv(aed_file, index=False, encoding="utf-8-sig")

    issue_id = _create_issue(issue_file)
    submission_id = _submit_resolution(
        issue_file, issue_id, technician="Technician A", suffix="1"
    )

    pending = issue_service.get_issue_record(issue_file, issue_id)
    assert pending["Status"] == "Pending Verification"
    assert pending["Latest Submission ID"] == submission_id
    assert pending["Resolution Submitted By"] == "Technician A"

    attachments = issue_service.load_issue_attachments(issue_file)
    assert len(attachments) == 1
    assert attachments.iloc[0]["Submission ID"] == submission_id
    assert (tmp_path / attachments.iloc[0]["File Path"]).exists()

    map_state = pd.read_csv(
        tmp_path / "map_unit_state.csv", dtype=str, keep_default_na=False
    )
    assert map_state.iloc[0]["Status"] == "Pending Verification"

    issue_service.verify_issue_resolution(
        issue_file,
        issue_id=issue_id,
        verified_by="Supervisor A",
        verification_notes="Evidence and functional result verified.",
        approve=True,
    )

    closed = issue_service.get_issue_record(issue_file, issue_id)
    assert closed["Status"] == "Closed"
    assert closed["Closed By"] == "Supervisor A"
    assert closed["Resolved By"] == "Supervisor A"

    submissions = issue_service.load_resolution_submissions(issue_file)
    assert submissions.iloc[0]["Verification Result"] == "Approved"
    assert submissions.iloc[0]["Verified By"] == "Supervisor A"

    unit_issues = load_unit_issues("AED-100", issue_record_file=issue_file)
    assert unit_issues.iloc[0]["Status"] == "Closed"

    service_records = load_service_records(
        pm_file,
        aed_csv_file=aed_file,
        manual_service_file=manual_file,
        issue_record_file=issue_file,
        resolution_file=resolution_file,
        aed_dataframe=pd.read_csv(aed_file, dtype=str),
    )
    service_row = service_records.loc[
        service_records["Resolution Submission ID"].eq(submission_id)
    ].iloc[0]
    assert service_row["Record Source"] == "Issue Resolution"
    assert service_row["Record Status"] == "Approved"
    assert service_row["Technician"] == "Technician A"
    assert service_row["Verified By"] == "Supervisor A"

    profile_history = build_service_history(
        pd.Series({"Serial Number": "AED-100"}),
        "AED-100",
        pm_responses_file=pm_file,
        issue_record_file=issue_file,
        resolution_file=resolution_file,
        manual_service_file=manual_file,
    )
    profile_row = profile_history.loc[
        profile_history["Reference"].eq(submission_id)
    ].iloc[0]
    assert profile_row["Status"] == "Approved"
    assert profile_row["Technician"] == "Technician A"

    today_records = issue_view._records_reported_on(
        issue_view._enrich_issue_records(
            issue_service.load_issue_records(issue_file), issue_file
        ),
        application_today(),
    )
    assert today_records.iloc[0]["Status"] == "Closed"
    assert today_records.iloc[0]["Closed By"] == "Supervisor A"

    map_state = pd.read_csv(
        tmp_path / "map_unit_state.csv", dtype=str, keep_default_na=False
    )
    assert map_state.iloc[0]["Status"] == "Completed"


def test_multi_type_and_multiple_resolution_people_remain_filterable(tmp_path: Path) -> None:
    issue_file = tmp_path / "issue_records.csv"
    issue_id = _create_issue(
        issue_file,
        issue_type="Cabinet Issue; Battery Issue",
    )

    _submit_resolution(issue_file, issue_id, technician="Technician A", suffix="1")
    issue_service.verify_issue_resolution(
        issue_file,
        issue_id=issue_id,
        verified_by="Verifier A",
        verification_notes="More work is required.",
        approve=False,
    )
    _submit_resolution(issue_file, issue_id, technician="Technician B", suffix="2")
    issue_service.verify_issue_resolution(
        issue_file,
        issue_id=issue_id,
        verified_by="Verifier B",
        verification_notes="Second attempt verified.",
        approve=True,
    )

    enriched = issue_view._enrich_issue_records(
        issue_service.load_issue_records(issue_file), issue_file
    )

    assert issue_view._issue_type_options(enriched) == [
        "Battery Issue",
        "Cabinet Issue",
    ]
    assert enriched.iloc[0]["_Resolution Submitted By All"] == (
        "Technician A; Technician B"
    )
    assert enriched.iloc[0]["_Verified By"] == "Verifier A; Verifier B"

    for selected_type in ("Cabinet Issue", "Battery Issue"):
        filtered = issue_view._filter_issue_records(
            enriched,
            search_text="",
            selected_month="All Months",
            issue_type=selected_type,
            status_filter="Closed",
            reported_by="All Reporters",
            assigned_by="All Assigners",
            assigned_to="All Assignees",
            started_by="All Starters",
            resolution_by="Technician A",
            verified_by="Verifier B",
            date_type="Reported Date",
            from_date=None,
            to_date=None,
        )
        assert filtered["Issue ID"].tolist() == [issue_id]


def test_empty_pm_csv_does_not_break_issue_resolution_service_records(tmp_path: Path) -> None:
    issue_file = tmp_path / "issue_records.csv"
    pm_file = tmp_path / "pm_responses.csv"
    manual_file = tmp_path / "manual_service_records.csv"
    aed_file = tmp_path / "aed_data.csv"
    resolution_file = tmp_path / "issue_resolution_submissions.csv"
    pm_file.write_text("\n", encoding="utf-8")
    pd.DataFrame([{"Serial Number": "AED-100"}]).to_csv(
        aed_file, index=False, encoding="utf-8-sig"
    )

    issue_id = _create_issue(issue_file)
    submission_id = _submit_resolution(
        issue_file, issue_id, technician="Technician A", suffix="1"
    )

    records = load_service_records(
        pm_file,
        aed_csv_file=aed_file,
        manual_service_file=manual_file,
        issue_record_file=issue_file,
        resolution_file=resolution_file,
        aed_dataframe=pd.read_csv(aed_file, dtype=str),
    )
    assert records["Resolution Submission ID"].eq(submission_id).any()


def test_issue_timestamps_use_configured_business_timezone() -> None:
    now = application_now()
    assert getattr(now.tzinfo, "key", "") == "Asia/Singapore"
    assert application_today() == now.date()
