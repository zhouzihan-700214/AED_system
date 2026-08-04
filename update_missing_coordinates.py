from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import shutil
import time
from typing import Any

from config import AED_DATA_FILE, BASE_DIR
from services import aed_service
from services.geocoding_service import clean_postal_code, geocode_postal_code


def file_signature(csv_file: str | Path) -> tuple[int, int] | None:
    """Return a lightweight signature used to detect a rewritten CSV file."""

    path = Path(csv_file)

    if not path.exists():
        return None

    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def is_valid_number(value: Any) -> bool:
    try:
        float(str(value).strip())
        return True
    except (TypeError, ValueError):
        return False


def address_contains_postal_code(address: Any, postal_code: Any) -> bool:
    """Return True when the saved OneMap address matches the current postal code."""

    postal = clean_postal_code(postal_code)
    address_text = str(address or "").strip()

    if not postal or not address_text:
        return False

    return bool(re.search(rf"(?<!\d){re.escape(postal)}(?!\d)", address_text))


def coordinates_are_current(row: Any) -> bool:
    """
    Check whether a row's stored coordinates still belong to its current postal code.

    This catches the important external-edit case: when Postal Code is changed
    directly in aed_data.csv but the old Latitude/Longitude values remain.
    """

    latitude = row.get("Latitude", "")
    longitude = row.get("Longitude", "")
    status = str(row.get("Geocoding Status", "")).strip()

    return (
        is_valid_number(latitude)
        and is_valid_number(longitude)
        and status == "Success"
        and address_contains_postal_code(
            row.get("OneMap Address", ""),
            row.get("Postal Code", ""),
        )
    )


def update_missing_coordinates(
    csv_file: str | Path = AED_DATA_FILE,
    *,
    create_backup: bool = False,
    pause_seconds: float = 0.2,
) -> dict[str, Any]:
    """
    Fill missing coordinates and refresh stale coordinates.

    A row is refreshed when:
    - Latitude or Longitude is missing/invalid;
    - Geocoding Status is not Success; or
    - the postal code inside OneMap Address does not match the current
      Postal Code. The last rule handles a Postal Code edited directly in
      VS Code while old coordinates are still present.
    """

    path = Path(csv_file)

    if not path.exists():
        raise FileNotFoundError(
            f"Cannot find: {path}\n"
            "Make sure aed_data.csv is in the same project folder as app.py."
        )

    dataframe = aed_service.load_aed_data(path)

    refresh_indexes: list[Any] = []

    for row_index, row in dataframe.iterrows():
        if not coordinates_are_current(row):
            refresh_indexes.append(row_index)

    summary: dict[str, Any] = {
        "total": len(dataframe),
        "missing_or_stale_before": len(refresh_indexes),
        "updated": 0,
        "failed": 0,
        "skipped": len(dataframe) - len(refresh_indexes),
        "backup_path": "",
    }

    if not refresh_indexes:
        return summary

    if create_backup:
        backup_name = (
            "aed_data_backup_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        backup_path = BASE_DIR / backup_name
        shutil.copy2(path, backup_path)
        summary["backup_path"] = str(backup_path)

    for row_index in refresh_indexes:
        row = dataframe.loc[row_index]
        serial_number = str(row.get("Serial Number", "")).strip()
        postal_code = str(row.get("Postal Code", "")).strip()

        result = geocode_postal_code(postal_code)

        dataframe.at[row_index, "Latitude"] = result.latitude
        dataframe.at[row_index, "Longitude"] = result.longitude
        dataframe.at[row_index, "OneMap Address"] = result.address
        dataframe.at[row_index, "Geocoding Status"] = result.status

        if result.success:
            summary["updated"] += 1
            print(
                f"[SUCCESS] {serial_number}: "
                f"{result.latitude}, {result.longitude}"
            )
        else:
            summary["failed"] += 1
            print(f"[FAILED] {serial_number}: {result.status}")

        if pause_seconds > 0:
            time.sleep(pause_seconds)

    # Save once after the entire batch through the project's atomic CSV writer.
    aed_service.save_aed_data(dataframe, path)

    return summary


def main() -> None:
    summary = update_missing_coordinates(
        AED_DATA_FILE,
        create_backup=True,
    )

    print("\nFinished.")
    print(f"Updated coordinates: {summary['updated']}")
    print(f"Already current: {summary['skipped']}")
    print(f"Failed: {summary['failed']}")

    if summary["backup_path"]:
        print(
            "Backup created: "
            f"{Path(summary['backup_path']).name}"
        )


if __name__ == "__main__":
    main()
