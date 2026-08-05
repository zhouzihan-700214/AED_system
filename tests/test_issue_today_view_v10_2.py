from datetime import date
from pathlib import Path
import sys
from unittest.mock import MagicMock

import pandas as pd

# The lightweight CI environment validates Streamlit source without installing
# the UI runtime. A module stub is enough because these tests exercise pure
# filtering helpers only.
sys.modules.setdefault("streamlit", MagicMock())

from views.issues import _filter_issue_records, _records_reported_on


BASE_COLUMNS = {
    "Model": "ZOLL AED Plus",
    "Postal Code": "150161",
    "Detailed Description": "Test issue",
    "Assigned By": "",
    "Current Assignee": "",
    "Started By": "",
    "Resolution Submitted By": "",
    "_Verified By": "",
    "_Assigned Date": "",
    "Started At": "",
    "Resolution Submitted At": "",
    "Closed At": "",
    "Last Updated At": "",
}


def _row(issue_id: str, reported_at: str, issue_type: str, status: str, reporter: str) -> dict:
    return {
        **BASE_COLUMNS,
        "Issue ID": issue_id,
        "Reported At": reported_at,
        "Issue Type": issue_type,
        "Status": status,
        "Reported By": reporter,
        "Serial Number": f"SER-{issue_id}",
        "Location": "Test Location",
    }


def test_today_scope_selects_only_records_reported_on_target_date() -> None:
    records = pd.DataFrame(
        [
            _row("A", "04-08-2026 08:00:00", "Cabinet", "Reported", "Zihan"),
            _row("B", "04-08-2026 14:30:00", "Battery", "Closed", "Alex"),
            _row("C", "03-08-2026 23:59:59", "Pads", "In Progress", "Zihan"),
            _row("D", "not-a-date", "Device", "Reported", "Ben"),
        ]
    )

    today_records = _records_reported_on(records, date(2026, 8, 4))

    assert today_records["Issue ID"].tolist() == ["A", "B"]


def test_today_scope_still_supports_all_issue_filters() -> None:
    records = pd.DataFrame(
        [
            _row("A", "04-08-2026 08:00:00", "Cabinet", "Reported", "Zihan"),
            _row("B", "04-08-2026 14:30:00", "Battery", "Closed", "Alex"),
            _row("C", "03-08-2026 23:59:59", "Cabinet", "Reported", "Zihan"),
        ]
    )
    today_records = _records_reported_on(records, date(2026, 8, 4))

    filtered = _filter_issue_records(
        today_records,
        search_text="",
        selected_month="All Months",
        issue_type="Cabinet",
        status_filter="Reported",
        reported_by="Zihan",
        assigned_by="All Assigners",
        assigned_to="All Assignees",
        started_by="All Starters",
        resolution_by="All Resolution Submitters",
        verified_by="All Verifiers",
        date_type="Reported Date",
        from_date=None,
        to_date=None,
    )

    assert filtered["Issue ID"].tolist() == ["A"]


def test_today_view_is_present_in_runtime_source() -> None:
    source = (Path(__file__).parents[1] / "views" / "issues.py").read_text(encoding="utf-8")

    assert 'ISSUE_VIEW_OPTIONS = ["All Issues", "Today’s Issues"]' in source
    assert "All filters below remain available" in source
    assert "_render_issue_view_selector(records)" in source
