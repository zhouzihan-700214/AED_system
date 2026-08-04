from __future__ import annotations

from pathlib import Path

import pandas as pd

from services.unit_profile_service import (
    append_manual_service_record,
    build_service_history,
    load_manual_service_records,
)


def _empty_csv(path: Path) -> Path:
    path.write_text("", encoding="utf-8")
    return path


def test_manual_service_record_is_a_structured_durable_row(tmp_path: Path) -> None:
    record_file = tmp_path / "manual_service_records.csv"
    saved = append_manual_service_record(
        {
            "AED Serial Number": "AED-001",
            "Service Date": "03-08-2026",
            "Service Type": "PM+batt",
            "Technician": "Zihan",
            "Reference": "e-SR100",
            "Status": "Completed",
            "Details": "PM completed and batteries replaced.",
            "Master Data Updated": "Yes",
            "PM Dates Updated": "Yes",
        },
        path=record_file,
    )

    records = load_manual_service_records(record_file)
    assert saved["Service Record ID"].startswith("SRV-")
    assert len(records) == 1
    assert records.iloc[0]["AED Serial Number"] == "AED-001"
    assert records.iloc[0]["Service Type"] == "PM+batt"
    assert records.iloc[0]["Details"] == "PM completed and batteries replaced."


def test_manual_service_record_appears_in_unit_history_without_changing_remarks(
    tmp_path: Path,
) -> None:
    record_file = tmp_path / "manual_service_records.csv"
    append_manual_service_record(
        {
            "AED Serial Number": "AED-001",
            "Service Date": "03-08-2026",
            "Service Type": "Outgoing Check",
            "Technician": "Technician 1",
            "Status": "Completed",
            "Details": "Outgoing check passed.",
        },
        path=record_file,
    )

    master_row = pd.Series(
        {
            "Serial Number": "AED-001",
            "Job Type": "PM",
            "PM Completed Date": "01-01-2026",
            "Last Done By": "Earlier Technician",
            "Service Report e-SR": "e-SR001",
            "Remarks": "Company remark remains unchanged.",
        }
    )
    history = build_service_history(
        master_row,
        "AED-001",
        pm_responses_file=_empty_csv(tmp_path / "pm.csv"),
        issue_record_file=_empty_csv(tmp_path / "issues.csv"),
        resolution_file=_empty_csv(tmp_path / "resolutions.csv"),
        manual_service_file=record_file,
    )

    manual = history[history["Source"].eq("Unit Profile")]
    assert len(manual) == 1
    assert manual.iloc[0]["Service Type"] == "Outgoing Check"
    assert manual.iloc[0]["Details"] == "Outgoing check passed."
    assert master_row["Remarks"] == "Company remark remains unchanged."
