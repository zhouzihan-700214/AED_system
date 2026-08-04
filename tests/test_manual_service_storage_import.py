from __future__ import annotations

import csv

from services.manual_service_storage import (
    MANUAL_SERVICE_RECORD_COLUMNS,
    ensure_manual_service_storage,
)


def test_startup_storage_bootstrap_is_independent_of_unit_profile_service(tmp_path):
    target = tmp_path / "nested" / "manual_service_records.csv"

    result = ensure_manual_service_storage(target)

    assert result == target
    assert target.exists()
    with target.open("r", newline="", encoding="utf-8-sig") as handle:
        header = next(csv.reader(handle))
    assert header == MANUAL_SERVICE_RECORD_COLUMNS
