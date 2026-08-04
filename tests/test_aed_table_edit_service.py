from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from services.aed_table_edit_service import (
    build_cell_changes,
    group_changes_for_repository,
    prepare_editor_dataframe,
    validate_table_changes,
)


def _source() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Serial Number": "AED002",
                "Model": "AED Plus",
                "Block / Locations": "200",
                "Street Name": "Beta Street",
                "Postal Code": "012345",
                "Level": "1",
                "Lift Lobby": "Lift Lobby B",
                "Adult Pads Expiry Date": "15-08-2029",
                "Adult Pads Lot Number": "A1",
                "Pediatric Pads Expiry Date": "",
                "Pediatric Pads Lot Number": "",
                "Battery Expiry Date": "01-03-2030",
                "PM Completed Date": "01-07-2026",
                "Next PM Date": "01-07-2027",
                "Job Type": "PM",
                "Last Done By": "Zihan",
                "Service Report e-SR": "SR-2",
                "Repaired?": "No",
            },
            {
                "Serial Number": "AED001",
                "Model": "AED Plus",
                "Block / Locations": "100",
                "Street Name": "Alpha Street",
                "Postal Code": "150100",
                "Level": "",
                "Lift Lobby": "Lift Lobby A",
                "Adult Pads Expiry Date": "15-08-2028",
                "Adult Pads Lot Number": "A0",
                "Pediatric Pads Expiry Date": "15-09-2028",
                "Pediatric Pads Lot Number": "P0",
                "Battery Expiry Date": "01-03-2029",
                "PM Completed Date": "01-07-2025",
                "Next PM Date": "01-07-2026",
                "Job Type": "PM",
                "Last Done By": "Tech",
                "Service Report e-SR": "SR-1",
                "Repaired?": "",
            },
        ]
    )


def test_prepare_editor_uses_serial_as_stable_identity_and_dates() -> None:
    editor = prepare_editor_dataframe(_source())
    assert list(editor.index) == ["AED001", "AED002"]
    assert editor.loc["AED001", "Postal Code"] == "150100"
    assert editor.loc["AED002", "Adult Pads Expiry Date"] == date(2029, 8, 15)


def test_build_cell_changes_returns_only_changed_cells() -> None:
    original = prepare_editor_dataframe(_source())
    edited = original.copy()
    edited.loc["AED001", "Block / Locations"] = "100A"
    edited.loc["AED002", "Next PM Date"] = date(2027, 10, 15)

    changes = build_cell_changes(original, edited)
    assert changes == [
        {
            "serial_number": "AED001",
            "field": "Block / Locations",
            "original_value": "100",
            "desired_value": "100A",
        },
        {
            "serial_number": "AED002",
            "field": "Next PM Date",
            "original_value": "01-07-2027",
            "desired_value": "15-10-2027",
        },
    ]


def test_rows_cannot_be_added_or_removed() -> None:
    original = prepare_editor_dataframe(_source())
    edited = original.iloc[:1].copy()
    with pytest.raises(ValueError, match="added or removed"):
        build_cell_changes(original, edited)


def test_validation_blocks_missing_required_and_bad_pm_order() -> None:
    original = prepare_editor_dataframe(_source())
    changes = [
        {
            "serial_number": "AED001",
            "field": "Street Name",
            "original_value": "Alpha Street",
            "desired_value": "",
        },
        {
            "serial_number": "AED001",
            "field": "Next PM Date",
            "original_value": "01-07-2026",
            "desired_value": "01-01-2025",
        },
    ]
    errors, _ = validate_table_changes(original, changes)
    assert any("Street Name is required" in item for item in errors)
    assert any("cannot be before PM Completed Date" in item for item in errors)


def test_group_changes_builds_one_batch_item_per_serial() -> None:
    changes = [
        {
            "serial_number": "AED001",
            "field": "Block / Locations",
            "original_value": "100",
            "desired_value": "100A",
        },
        {
            "serial_number": "AED001",
            "field": "Postal Code",
            "original_value": "150100",
            "desired_value": "150101",
        },
        {
            "serial_number": "AED002",
            "field": "Job Type",
            "original_value": "PM",
            "desired_value": "Repair",
        },
    ]
    grouped = group_changes_for_repository(changes)
    assert len(grouped) == 2
    first = next(item for item in grouped if item["serial_number"] == "AED001")
    assert first["desired_values"] == {
        "Block / Locations": "100A",
        "Postal Code": "150101",
    }
