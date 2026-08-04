from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

from services.excel_sync_service import sync_excel_to_cache


def _write_generic_workbook(path: Path, rows: list[dict[str, object]]) -> None:
    dataframe = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        dataframe.to_excel(writer, sheet_name="IB List", index=False)
        pd.DataFrame({"Do Not Remove": ["preserved"]}).to_excel(
            writer,
            sheet_name="Other Sheet",
            index=False,
        )


def _write_real_ib_workbook(path: Path, duplicate: bool = False) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"

    headers = [
        "INSTALLATION DATE",
        "RELATED OBJECTS",
        "SERIAL NUMBER",
        "Block / Locations",
        "Street Name",
        "Postal Code",
        "Lift Lobby",
        "Level",
        "Adult CPR-D Padz",
        "Adult CPR-D Padz Lot Number",
        "Children Pedi-Padz",
        "Children Pedi-Padz Lot Number",
        "Battery Replacement History",
        "Battery Expiry Date",
        "PM Completed On",
        "Next PM Due",
        "JOB TYPE ",
        "Last done by",
        "Service Report / e-SR",
        "Remarks",
    ]
    sheet.append(headers)
    sheet.append([None, "(OLD SERIAL#)", None, None, None, None, None, None,
                  "Expiry", None, "Expiry", None, "DD/MMM/YYYY", None,
                  None, None, None, None, None, None])

    serial_two = "AED001" if duplicate else "AED002"
    sheet.append([
        43013, "OLD001", "AED001", 122, "Bukit Merah Lane 1", 150122,
        "B", "N/A", 47214, "0124A", 46699, "4525A", 44947, 46082,
        45842, 46204, "PM", "Russell", "e-SR15803", "Main remarks /",
    ])
    sheet.append([
        None, None, None, None, None, None, None, None, None, None,
        None, None, None, None, None, None, None, None, None,
        "Continuation remarks",
    ])
    sheet.append([
        43643, "N/A", serial_two, 128, "Bukit Merah View", 150128,
        "D", 1, 47167, "4623E", 46664, "4025A", None, 46082,
        46225, 46569, "PM", "Zihan", 5928, "Second unit",
    ])
    workbook.save(path)


def _sync_kwargs(tmp_path: Path) -> dict[str, object]:
    return {
        "cache_file": tmp_path / "aed_data.csv",
        "state_file": tmp_path / "excel_sync_state.json",
        "temp_dir": tmp_path / "temp",
        "backup_dir": tmp_path / "backups",
        "lock_file": tmp_path / "excel_sync.lock",
        "preserve_cache_only_units": False,
    }


def test_generic_excel_sync_builds_valid_csv_mirror(tmp_path: Path) -> None:
    excel_file = tmp_path / "IB_list_TEST.xlsx"
    _write_generic_workbook(
        excel_file,
        [
            {
                "Serial No.": "AED001",
                "Model": "ZOLL AED Plus",
                "Location": "Test Location",
                "Postal code": 18956,
                "PM Completed Date": pd.Timestamp("2026-07-01"),
                "Next PM Date": pd.Timestamp("2027-07-01"),
            }
        ],
    )

    kwargs = _sync_kwargs(tmp_path)
    result = sync_excel_to_cache(
        force=True,
        excel_file=excel_file,
        excel_sheet="IB List",
        **kwargs,
    )

    assert result.status == "synced"
    assert result.changed is True
    assert result.row_count == 1

    mirrored = pd.read_csv(
        kwargs["cache_file"],
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    assert mirrored.loc[0, "Serial Number"] == "AED001"
    assert mirrored.loc[0, "Postal Code"] == "018956"
    assert mirrored.loc[0, "PM Completed Date"] == "01-07-2026"
    assert mirrored.loc[0, "Next PM Date"] == "01-07-2027"
    assert mirrored.loc[0, "PM Interval Months"] == "12"


def test_real_ib_layout_merges_continuation_and_preserves_coordinates(
    tmp_path: Path,
) -> None:
    excel_file = tmp_path / "IB_list_TEST.xlsx"
    _write_real_ib_workbook(excel_file)
    kwargs = _sync_kwargs(tmp_path)

    pd.DataFrame(
        [
            {
                "Serial Number": "AED001",
                "Model": "ZOLL AED Plus",
                "Postal Code": "150122",
                "Latitude": "1.2864",
                "Longitude": "103.8042",
                "OneMap Address": "122 BUKIT MERAH LANE 1",
                "Geocoding Status": "Success",
                "PM Interval Months": "12",
            }
        ]
    ).to_csv(kwargs["cache_file"], index=False, encoding="utf-8-sig")

    result = sync_excel_to_cache(
        force=True,
        excel_file=excel_file,
        excel_sheet="Sheet1",
        **kwargs,
    )

    mirrored = pd.read_csv(
        kwargs["cache_file"],
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    first = mirrored[mirrored["Serial Number"] == "AED001"].iloc[0]
    second = mirrored[mirrored["Serial Number"] == "AED002"].iloc[0]

    assert result.row_count == 2
    assert any("row 4" in warning for warning in result.warnings)
    assert "Continuation remarks" in first["Remarks"]
    assert first["Location"] == "Blk 122 Bukit Merah Lane 1"
    assert first["Lift Lobby"] == "Lift Lobby B"
    assert first["Adult Pads Expiry Date"] == "06-04-2029"
    assert first["Battery Replacement History"] == "21-01-2023"
    assert first["Latitude"] == "1.2864"
    assert first["Longitude"] == "103.8042"
    assert second["Location"] == "Blk 128 Bukit Merah View"
    assert second["Lift Lobby"] == "Lift Lobby D"
    assert second["Level"] == "1"
    assert second["Service Report e-SR"] == "5928"


def test_postal_change_clears_stale_coordinates(tmp_path: Path) -> None:
    excel_file = tmp_path / "IB_list_TEST.xlsx"
    _write_real_ib_workbook(excel_file)
    kwargs = _sync_kwargs(tmp_path)

    pd.DataFrame(
        [
            {
                "Serial Number": "AED001",
                "Postal Code": "999999",
                "Latitude": "1.0",
                "Longitude": "103.0",
                "OneMap Address": "OLD ADDRESS",
                "Geocoding Status": "Success",
            }
        ]
    ).to_csv(kwargs["cache_file"], index=False, encoding="utf-8-sig")

    result = sync_excel_to_cache(
        force=True,
        excel_file=excel_file,
        excel_sheet="Sheet1",
        **kwargs,
    )
    mirrored = pd.read_csv(
        kwargs["cache_file"], dtype=str, keep_default_na=False,
        encoding="utf-8-sig",
    )
    first = mirrored[mirrored["Serial Number"] == "AED001"].iloc[0]
    assert first["Latitude"] == ""
    assert first["Longitude"] == ""
    assert "Postal Code changed" in first["Geocoding Status"]
    assert any("coordinates were cleared" in warning for warning in result.warnings)


def test_unchanged_workbook_does_not_rebuild_cache(tmp_path: Path) -> None:
    excel_file = tmp_path / "IB_list_TEST.xlsx"
    _write_generic_workbook(excel_file, [{"Serial Number": "AED001"}])
    kwargs = _sync_kwargs(tmp_path)

    first = sync_excel_to_cache(
        force=True,
        excel_file=excel_file,
        excel_sheet="IB List",
        **kwargs,
    )
    cache_file = Path(kwargs["cache_file"])
    first_cache_time = cache_file.stat().st_mtime_ns

    second = sync_excel_to_cache(
        force=False,
        excel_file=excel_file,
        excel_sheet="IB List",
        **kwargs,
    )

    assert first.status == "synced"
    assert second.status == "up_to_date"
    assert second.changed is False
    assert cache_file.stat().st_mtime_ns == first_cache_time


def test_invalid_duplicate_serials_do_not_overwrite_last_valid_cache(
    tmp_path: Path,
) -> None:
    excel_file = tmp_path / "IB_list_TEST.xlsx"
    _write_real_ib_workbook(excel_file, duplicate=True)
    kwargs = _sync_kwargs(tmp_path)
    cache_file = Path(kwargs["cache_file"])

    pd.DataFrame([{"Serial Number": "SAFE001", "Location": "Existing"}]).to_csv(
        cache_file,
        index=False,
        encoding="utf-8-sig",
    )
    original_bytes = cache_file.read_bytes()

    with pytest.raises(ValueError, match="Duplicate Serial Number"):
        sync_excel_to_cache(
            force=True,
            excel_file=excel_file,
            excel_sheet="Sheet1",
            **kwargs,
        )

    assert cache_file.read_bytes() == original_bytes


def test_missing_required_real_ib_column_keeps_cache(tmp_path: Path) -> None:
    excel_file = tmp_path / "IB_list_TEST.xlsx"
    _write_real_ib_workbook(excel_file)
    workbook = pd.ExcelFile(excel_file)
    dataframe = pd.read_excel(workbook, sheet_name="Sheet1", header=None)
    dataframe = dataframe.drop(columns=[15])  # remove Next PM Due
    with pd.ExcelWriter(excel_file, engine="openpyxl") as writer:
        dataframe.to_excel(writer, sheet_name="Sheet1", index=False, header=False)

    kwargs = _sync_kwargs(tmp_path)
    cache_file = Path(kwargs["cache_file"])
    pd.DataFrame([{"Serial Number": "SAFE001"}]).to_csv(
        cache_file, index=False, encoding="utf-8-sig"
    )
    original_bytes = cache_file.read_bytes()

    with pytest.raises(ValueError, match="Next PM Due"):
        sync_excel_to_cache(
            force=True,
            excel_file=excel_file,
            excel_sheet="Sheet1",
            **kwargs,
        )
    assert cache_file.read_bytes() == original_bytes


def test_missing_excel_uses_existing_csv_fallback(tmp_path: Path) -> None:
    excel_file = tmp_path / "missing.xlsx"
    kwargs = _sync_kwargs(tmp_path)
    cache_file = Path(kwargs["cache_file"])

    pd.DataFrame([{"Serial Number": "CSV001"}]).to_csv(
        cache_file,
        index=False,
        encoding="utf-8-sig",
    )

    result = sync_excel_to_cache(
        excel_file=excel_file,
        excel_sheet="Sheet1",
        **kwargs,
    )

    assert result.status == "csv_fallback"
    assert result.source_exists is False
    assert result.row_count == 1
