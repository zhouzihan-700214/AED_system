from __future__ import annotations

from pathlib import Path
import sys
import types

import pandas as pd

if "streamlit" not in sys.modules:
    fake_streamlit = types.ModuleType("streamlit")
    fake_streamlit.session_state = {}
    sys.modules["streamlit"] = fake_streamlit

from services.service_record_service import (
    add_record_match_status,
    issue_resolution_records_for_service_page,
    service_record_scope_counts,
)
from views.service_records import apply_filters, available_months


def _records() -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            {
                "AED Serial Number": "S-001",
                "Original Serial Number": "S-001",
                "Postal Code": "150001",
                "Loaner Unit": "No",
                "Technician": "A",
                "Service Type": "PM",
                "Battery Replaced": "No",
                "AED Model": "AED Plus",
                "Record Source": "PM Checklist",
                "Record Status": "Completed",
                "Service Date": "01-08-2026",
                "Submitted At": "01-08-2026 10:00:00",
            },
            {
                "AED Serial Number": "S-002",
                "Original Serial Number": "S-002",
                "Postal Code": "150001",
                "Loaner Unit": "No",
                "Technician": "B",
                "Service Type": "PM",
                "Battery Replaced": "No",
                "AED Model": "AED Pro",
                "Record Source": "PM Checklist",
                "Record Status": "Completed",
                "Service Date": "02-08-2026",
                "Submitted At": "02-08-2026 10:00:00",
            },
            {
                "AED Serial Number": "LOAN-1",
                "Original Serial Number": "LOAN-1",
                "Postal Code": "150001",
                "Loaner Unit": "Yes",
                "Technician": "C",
                "Service Type": "PM",
                "Battery Replaced": "No",
                "AED Model": "AED Plus",
                "Record Source": "PM Checklist",
                "Record Status": "Completed",
                "Service Date": "03-08-2026",
                "Submitted At": "03-08-2026 10:00:00",
            },
        ]
    )
    frame["_Service Date Parsed"] = pd.to_datetime(
        frame["Service Date"], dayfirst=True
    )
    frame["_Submitted At Parsed"] = pd.to_datetime(
        frame["Submitted At"], dayfirst=True
    )
    return frame


def _master() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Serial Number": "S-001",
                "Postal Code": "150001",
                "Model": "AED Plus",
                "Location": "Block 1",
            },
            {
                "Serial Number": "S-002",
                "Postal Code": "150002",
                "Model": "AED Pro",
                "Location": "Block 2",
            },
            # More than one AED can legitimately share a postal code.
            {
                "Serial Number": "S-003",
                "Postal Code": "150001",
                "Model": "AED Plus",
                "Location": "Block 1 Lobby B",
            },
        ]
    )


def test_record_match_scope_uses_postal_to_serial_relationship() -> None:
    checked = add_record_match_status(_records(), _master())

    assert checked["Record Match"].tolist() == [
        "Matched",
        "Mismatch",
        "Loaner",
    ]
    assert checked["Loaner Unit"].tolist() == ["No", "No", "Yes"]
    assert service_record_scope_counts(checked) == {
        "All Records": 3,
        "Matched": 1,
        "Mismatch": 1,
        "Loaner": 1,
    }
    assert "Master Postal Code" not in checked.columns
    assert "Mismatch Reason" not in checked.columns


def test_scope_and_loaner_filter_are_both_interactive_filters() -> None:
    checked = add_record_match_status(_records(), _master())

    common = dict(
        dataframe=checked,
        keyword="",
        start_date=None,
        end_date=None,
        selected_month="",
        technicians=[],
        service_types=[],
        battery_replaced_values=[],
        models=[],
        record_sources=[],
        record_statuses=[],
    )

    mismatch = apply_filters(**common, record_scope="Mismatch", loaner_values=[])
    assert mismatch["AED Serial Number"].tolist() == ["S-002"]

    loaners = apply_filters(**common, record_scope="All Records", loaner_values=["Yes"])
    assert loaners["AED Serial Number"].tolist() == ["LOAN-1"]

    matched_non_loaners = apply_filters(
        **common,
        record_scope="Matched",
        loaner_values=["No"],
    )
    assert matched_non_loaners["AED Serial Number"].tolist() == ["S-001"]


def test_issue_resolution_inherits_loaner_status(tmp_path: Path) -> None:
    issue_file = tmp_path / "issue_records.csv"
    resolution_file = tmp_path / "issue_resolution_submissions.csv"

    pd.DataFrame(
        [
            {
                "Issue ID": "ISS-1",
                "Serial Number": "LOAN-1",
                "Model": "AED Plus",
                "Location": "Temporary site",
                "Postal Code": "150001",
                "Lift Lobby": "A",
                "Is Loaner": "Yes",
                "Issue Type": "Cabinet",
                "Status": "Closed",
            }
        ]
    ).to_csv(issue_file, index=False)
    pd.DataFrame(
        [
            {
                "Submission ID": "RES-1",
                "Issue ID": "ISS-1",
                "Attempt Number": "1",
                "Submitted By": "Tech",
                "Submitted At": "04-08-2026 09:00:00",
                "Action Taken": "Checked",
                "Root Cause": "",
                "Parts Replaced": "",
                "Test Performed": "Self test",
                "Test Result": "Pass",
                "Resolution Notes": "Completed",
                "Verification Result": "Approved",
                "Verified By": "Supervisor",
                "Verified At": "04-08-2026 10:00:00",
                "Verification Notes": "",
            }
        ]
    ).to_csv(resolution_file, index=False)

    result = issue_resolution_records_for_service_page(issue_file, resolution_file)
    assert result.iloc[0]["Loaner Unit"] == "Yes"


def test_service_month_filter_uses_service_date() -> None:
    records = _records()
    september = records.iloc[[0]].copy()
    september["Service Date"] = "15-09-2026"
    september["_Service Date Parsed"] = pd.to_datetime(
        september["Service Date"], dayfirst=True
    )
    combined = pd.concat([records, september], ignore_index=True)

    filtered = apply_filters(
        dataframe=combined,
        keyword="",
        start_date=None,
        end_date=None,
        selected_month="2026-09",
        technicians=[],
        service_types=[],
        battery_replaced_values=[],
        models=[],
        record_sources=[],
        record_statuses=[],
        loaner_values=[],
        record_scope="All Records",
    )

    assert len(filtered) == 1
    assert filtered.iloc[0]["Service Date"] == "15-09-2026"


def test_available_months_are_unique_and_newest_first() -> None:
    records = _records().copy()
    extra = records.iloc[[0]].copy()
    extra["Service Date"] = "15-07-2026"
    extra["_Service Date Parsed"] = pd.to_datetime(
        extra["Service Date"], dayfirst=True
    )
    combined = pd.concat([records, extra], ignore_index=True)

    assert available_months(combined) == [
        ("2026-08", "August 2026"),
        ("2026-07", "July 2026"),
    ]
