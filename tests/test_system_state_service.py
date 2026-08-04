from __future__ import annotations

import io
import zipfile
from pathlib import Path


def test_state_archive_contains_only_configured_system_files(monkeypatch, tmp_path: Path) -> None:
    from services import system_state_service as service

    root = tmp_path / "project"
    root.mkdir()
    issue = root / "issue_records.csv"
    issue.write_text("Issue ID,Status\nISS-1,Reported\n", encoding="utf-8")
    photos = root / "issue_photos"
    photos.mkdir()
    (photos / "photo.jpg").write_bytes(b"photo")
    official = root / "external_data" / "IB_list_TEST.xlsx"
    official.parent.mkdir()
    official.write_bytes(b"official")

    monkeypatch.setattr(service, "PROJECT_ROOT", root)
    monkeypatch.setattr(service, "SYSTEM_STATE_PATHS", (issue, photos))

    archive = service.build_archive()
    with zipfile.ZipFile(io.BytesIO(archive), "r") as bundle:
        names = set(bundle.namelist())
    assert names == {"issue_records.csv", "issue_photos/photo.jpg"}
    assert "external_data/IB_list_TEST.xlsx" not in names


def test_state_archive_round_trip(monkeypatch, tmp_path: Path) -> None:
    from services import system_state_service as service

    root = tmp_path / "project"
    root.mkdir()
    record = root / "map_unit_state.csv"
    record.write_text("Serial Number,Status\nAED-1,Pending\n", encoding="utf-8")

    monkeypatch.setattr(service, "PROJECT_ROOT", root)
    monkeypatch.setattr(service, "SYSTEM_STATE_PATHS", (record,))
    archive = service.build_archive()
    record.write_text("changed", encoding="utf-8")
    service._safe_extract(archive)
    assert "AED-1,Pending" in record.read_text(encoding="utf-8")
