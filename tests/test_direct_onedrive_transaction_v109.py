from __future__ import annotations

from types import SimpleNamespace

from services import aed_repository
from services.excel_sync_service import SyncResult
from services.excel_transaction_service import OperationResult


def test_direct_onedrive_write_downloads_edits_uploads_and_reads_back(monkeypatch) -> None:
    events: list[str] = []

    monkeypatch.setattr(aed_repository, "is_cloud_onedrive_enabled", lambda: True)

    def prepare(*, force: bool) -> str:
        events.append("download latest")
        assert force is True
        return "E1"

    sync_count = {"value": 0}

    def sync(*, force: bool, preserve_cache_only_units: bool = True):
        sync_count["value"] += 1
        events.append("sync before" if sync_count["value"] == 1 else "sync after")
        assert force is True
        if sync_count["value"] == 2:
            assert preserve_cache_only_units is False
        return SyncResult(
            status="synced",
            message="cache rebuilt",
            source_exists=True,
            changed=True,
            row_count=1,
        )

    def operation() -> OperationResult:
        events.append("safe cell transaction")
        return OperationResult(
            "updated",
            "local workbook updated",
            operation_id="OP-V109",
            serial_number="AED-001",
            changed_fields=("Model",),
        )

    def upload(*, expected_etag: str = ""):
        events.append("upload same item")
        assert expected_etag == "E1"
        return SimpleNamespace(message="uploaded", etag="E2")

    def readback(*, force: bool = False):
        events.append("read back remote")
        assert force is True
        return SimpleNamespace(message="downloaded", etag="E2")

    monkeypatch.setattr(aed_repository, "_prepare_workbook", prepare)
    monkeypatch.setattr(aed_repository, "sync_excel_to_cache", sync)
    monkeypatch.setattr(aed_repository, "upload_workbook", upload)
    monkeypatch.setattr(aed_repository, "download_workbook", readback)

    result = aed_repository._run_operation(operation)

    assert result.success
    assert events == [
        "download latest",
        "sync before",
        "safe cell transaction",
        "upload same item",
        "read back remote",
        "sync after",
    ]
    assert "read back from the same remote file" in result.message


def test_direct_onedrive_readback_loads_newer_external_version(monkeypatch) -> None:
    events: list[str] = []
    monkeypatch.setattr(aed_repository, "is_cloud_onedrive_enabled", lambda: True)
    monkeypatch.setattr(aed_repository, "_prepare_workbook", lambda force: "E1")

    def sync(*, force: bool, preserve_cache_only_units: bool = True):
        events.append(f"sync:{preserve_cache_only_units}")
        return SyncResult(
            status="synced", message="ok", source_exists=True, changed=True, row_count=1
        )

    monkeypatch.setattr(aed_repository, "sync_excel_to_cache", sync)
    monkeypatch.setattr(
        aed_repository,
        "upload_workbook",
        lambda expected_etag="": SimpleNamespace(message="uploaded", etag="E2"),
    )
    monkeypatch.setattr(
        aed_repository,
        "download_workbook",
        lambda force=True: SimpleNamespace(message="newer downloaded", etag="E3"),
    )

    result = aed_repository._run_operation(
        lambda: OperationResult("updated", "updated", changed_fields=("Model",))
    )

    assert result.success
    assert any("changed again immediately" in warning for warning in result.warnings)
    assert events[-1] == "sync:False"


def test_local_mode_keeps_stage5_transaction_without_cloud_calls(monkeypatch) -> None:
    monkeypatch.setattr(aed_repository, "is_cloud_onedrive_enabled", lambda: False)
    result = aed_repository._run_operation(
        lambda: OperationResult("updated", "local Stage 5 transaction")
    )
    assert result.success
    assert result.message == "local Stage 5 transaction"
