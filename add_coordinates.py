"""Create a coordinate-enriched AED CSV without storing a OneMap token in code."""

from __future__ import annotations

import time

from config import AED_DATA_FILE, BASE_DIR
from services import aed_service
from services.csv_storage import atomic_write_csv
from services.geocoding_service import geocode_postal_code


OUTPUT_FILE = BASE_DIR / "aed_data_with_coordinates.csv"


def main() -> None:
    if not AED_DATA_FILE.exists():
        raise FileNotFoundError(f"Cannot find: {AED_DATA_FILE}")

    dataframe = aed_service.load_aed_data(AED_DATA_FILE)
    success_count = 0
    failure_count = 0

    for row_index, row in dataframe.iterrows():
        postal_code = aed_service.clean_text(row.get("Postal Code", ""))
        serial_number = aed_service.clean_text(row.get("Serial Number", ""))

        result = geocode_postal_code(postal_code)
        dataframe.at[row_index, "Latitude"] = result.latitude
        dataframe.at[row_index, "Longitude"] = result.longitude
        dataframe.at[row_index, "OneMap Address"] = result.address
        dataframe.at[row_index, "Geocoding Status"] = result.status

        if result.success:
            success_count += 1
            print(
                f"Success: {serial_number or row_index} | "
                f"{postal_code} | {result.latitude}, {result.longitude}"
            )
        else:
            failure_count += 1
            print(
                f"Failed: {serial_number or row_index} | "
                f"{postal_code} | {result.status}"
            )

        time.sleep(0.3)

    atomic_write_csv(
        aed_service.ensure_columns(dataframe),
        OUTPUT_FILE,
        preferred_columns=aed_service.MASTER_COLUMNS,
    )

    print(f"Saved: {OUTPUT_FILE}")
    print(f"Successful: {success_count}")
    print(f"Failed: {failure_count}")


if __name__ == "__main__":
    main()
