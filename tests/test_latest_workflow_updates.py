from __future__ import annotations

from pathlib import Path

import pandas as pd

from services.pm_service import failed_checklist_items
from services.unit_color_service import sync_unit_from_issue_records
from views.map_modules.status_service import (
    COLOR_PALETTE,
    load_status_definitions,
)


def test_new_marker_colours_are_available() -> None:
    for colour in ["Pink", "Teal", "Cyan", "Indigo", "Lime", "Brown", "Maroon", "Black"]:
        assert colour in COLOR_PALETTE


def test_status_definitions_include_issue_workflow_roles(tmp_path: Path) -> None:
    path = tmp_path / "map_status_definitions.csv"
    definitions = load_status_definitions(path)
    roles = set(definitions["Workflow Role"])
    assert {"Pending", "Completed", "Issue", "Pending Verification"}.issubset(roles)


def test_failed_pm_items_create_individual_candidates() -> None:
    failures = failed_checklist_items(
        {
            "Cabinet Inspection": "Fail",
            "Cabinet Alarm": "Pass",
            "AED Physical Condition": "Pass",
            "Self Test Result": "Fail",
            "AED Cover": "Pass",
            "Adult Pads Within Expiry Date": "No",
            "Pediatric Pads Within Expiry Date": "Yes",
            "AED Signage": "Yes",
            "Final Check": "Yes",
        }
    )
    assert [item["Field"] for item in failures] == [
        "Cabinet Inspection",
        "Self Test Result",
        "Adult Pads Within Expiry Date",
    ]


def test_issue_sync_uses_red_then_yellow_then_green_roles(tmp_path: Path) -> None:
    issue_file = tmp_path / "issue_records.csv"
    state_file = tmp_path / "map_unit_state.csv"
    status_file = tmp_path / "map_status_definitions.csv"
    load_status_definitions(status_file)

    pd.DataFrame(
        [
            {"Serial Number": "AED-X", "Status": "Reported"},
            {"Serial Number": "AED-X", "Status": "Pending Verification"},
        ]
    ).to_csv(issue_file, index=False, encoding="utf-8-sig")

    role = sync_unit_from_issue_records(
        issue_file,
        "AED-X",
        state_file=state_file,
        status_file=status_file,
    )
    assert role == "Issue"

    issues = pd.read_csv(issue_file, dtype=str, keep_default_na=False)
    issues.loc[0, "Status"] = "Closed"
    issues.to_csv(issue_file, index=False, encoding="utf-8-sig")
    role = sync_unit_from_issue_records(
        issue_file,
        "AED-X",
        state_file=state_file,
        status_file=status_file,
    )
    assert role == "Pending Verification"

    issues.loc[1, "Status"] = "Closed"
    issues.to_csv(issue_file, index=False, encoding="utf-8-sig")
    role = sync_unit_from_issue_records(
        issue_file,
        "AED-X",
        state_file=state_file,
        status_file=status_file,
    )
    assert role == "Completed"
