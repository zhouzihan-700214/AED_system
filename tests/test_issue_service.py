from pathlib import Path

import pytest

from services import issue_service


def test_status_transition_rules() -> None:
    issue_service.validate_status_transition("Reported", "Assigned")
    issue_service.validate_status_transition("Assigned", "In Progress")
    issue_service.validate_status_transition("In Progress", "Pending Verification")
    issue_service.validate_status_transition("Pending Verification", "Closed")

    with pytest.raises(ValueError):
        issue_service.validate_status_transition("Reported", "Closed")


def test_basic_issue_workflow(tmp_path: Path) -> None:
    issue_file = tmp_path / "issue_records.csv"
    issue_id = issue_service.create_issue(
        issue_file,
        issue_data={
            "Reported By": "Reporter",
            "Issue Type": "Cabinet alarm not working",
            "Priority": "High",
            "Serial Number": "AED-001",
            "Detailed Description": "Alarm did not sound.",
        },
    )

    issue_service.assign_issue(
        issue_file,
        issue_id=issue_id,
        reviewed_by="Supervisor",
        assigned_to="Technician",
    )
    issue_service.start_issue_work(
        issue_file,
        issue_id=issue_id,
        started_by="Technician",
    )
    issue_service.add_issue_progress_update(
        issue_file,
        issue_id=issue_id,
        updated_by="Technician",
        progress_notes="Checked cabinet wiring.",
    )

    record = issue_service.get_issue_record(issue_file, issue_id)
    history = issue_service.get_history_for_issue(issue_file, issue_id)
    assert record["Status"] == "In Progress"
    assert len(history) >= 4
