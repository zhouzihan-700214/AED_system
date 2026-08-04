from pathlib import Path

import pandas as pd

from services import aed_service


def test_clean_text_and_next_pm_date() -> None:
    assert aed_service.clean_text("  AED-001  ") == "AED-001"
    assert aed_service.clean_text(None) == ""
    assert aed_service.calculate_next_pm_date("29-02-2024") == "28-02-2025"


def test_save_and_load_aed_data(tmp_path: Path) -> None:
    csv_file = tmp_path / "aed_data.csv"
    data = pd.DataFrame(
        [
            {
                "Serial Number": "AED-001",
                "Location": "Test Lobby",
                "Postal Code": "123456",
                "PM Completed Date": "15-07-2026",
            }
        ]
    )

    aed_service.save_aed_data(data, csv_file)
    loaded = aed_service.load_aed_data(csv_file)

    assert loaded.loc[0, "Serial Number"] == "AED-001"
    assert loaded.loc[0, "Location"] == "Test Lobby"
    assert list(loaded.columns) == aed_service.MASTER_COLUMNS
