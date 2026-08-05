from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from services import aed_repository
from services.excel_sync_service import SyncResult, sync_excel_to_cache

ROOT = Path(__file__).resolve().parents[1]
REAL_WORKBOOK = ROOT / "external_data" / "IB_list_TEST.xlsx"
REAL_CACHE = ROOT / "aed_data.csv"


class _StateOnlyStreamlit:
    def __init__(self) -> None:
        self.session_state: dict[str, object] = {}



def _cloud_paths(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "excel": tmp_path / "data" / "onedrive_workbook_cache" / "IB_list_TEST.xlsx",
        "cache": tmp_path / "aed_data.csv",
        "state": tmp_path / "data" / "excel_sync_state.json",
        "temp": tmp_path / "temp",
        "lock": tmp_path / "data" / "excel_operation.lock",
        "backup": tmp_path / "backups" / "aed_cache",
    }
    paths["excel"].parent.mkdir(parents=True, exist_ok=True)
    paths["temp"].mkdir(parents=True, exist_ok=True)
    paths["backup"].mkdir(parents=True, exist_ok=True)
    shutil.copy2(REAL_WORKBOOK, paths["excel"])
    shutil.copy2(REAL_CACHE, paths["cache"])
    return paths


def test_cloud_excel_is_authoritative_and_removes_cache_only_units(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths = _cloud_paths(tmp_path)
    cache = pd.read_csv(paths["cache"], dtype=str, keep_default_na=False)
    extra = cache.iloc[[0]].copy()
    extra["Serial Number"] = "LOCAL-ONLY-SHOULD-DISAPPEAR"
    pd.concat([cache, extra], ignore_index=True).to_csv(
        paths["cache"], index=False, encoding="utf-8-sig"
    )

    monkeypatch.setattr(aed_repository, "EXCEL_FILE", paths["excel"])
    monkeypatch.setattr(aed_repository, "AED_CACHE_FILE", paths["cache"])
    monkeypatch.setattr(aed_repository, "SYNC_STATE_FILE", paths["state"])
    monkeypatch.setattr(aed_repository, "is_cloud_onedrive_enabled", lambda: True)
    monkeypatch.setattr(
        aed_repository,
        "download_workbook",
        lambda force=False: SimpleNamespace(
            status="downloaded", message="remote workbook downloaded", etag="REMOTE-E1"
        ),
    )

    captured: dict[str, object] = {}

    def actual_sync(*, force: bool = False, preserve_cache_only_units: bool = True):
        captured["preserve_cache_only_units"] = preserve_cache_only_units
        return sync_excel_to_cache(
            force=force,
            excel_file=paths["excel"],
            cache_file=paths["cache"],
            state_file=paths["state"],
            temp_dir=paths["temp"],
            lock_file=paths["lock"],
            backup_dir=paths["backup"],
            preserve_cache_only_units=preserve_cache_only_units,
        )

    monkeypatch.setattr(aed_repository, "sync_excel_to_cache", actual_sync)
    result = aed_repository.ensure_cache_current(force=True)

    assert result.status == "synced"
    assert captured["preserve_cache_only_units"] is False
    refreshed = pd.read_csv(paths["cache"], dtype=str, keep_default_na=False)
    assert "LOCAL-ONLY-SHOULD-DISAPPEAR" not in set(refreshed["Serial Number"])


def test_cloud_reader_refuses_stale_csv_after_remote_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stale = tmp_path / "aed_data.csv"
    shutil.copy2(REAL_CACHE, stale)
    monkeypatch.setattr(aed_repository, "AED_CACHE_FILE", stale)
    monkeypatch.setattr(aed_repository, "is_cloud_onedrive_enabled", lambda: True)
    monkeypatch.setattr(
        aed_repository,
        "ensure_cache_current",
        lambda force=False: SyncResult(
            "failed", "Microsoft Graph download failed", source_exists=True
        ),
    )

    with pytest.raises(RuntimeError, match="stale local AED data"):
        aed_repository.get_all_units(refresh=True)


def test_signed_in_startup_forces_remote_master_and_rejects_csv_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import streamlit_app as app

    fake_st = _StateOnlyStreamlit()
    monkeypatch.setattr(app, "st", fake_st)
    monkeypatch.setattr(app.config, "ONEDRIVE_CLOUD_ENABLED", True)
    monkeypatch.setattr(app.config, "AED_DATA_FILE", Path("/tmp/nonexistent-aed-cache.csv"))
    monkeypatch.setattr(app.config, "ensure_project_directories", lambda: None)
    monkeypatch.setattr(
        app.system_state_service,
        "bootstrap_system_state",
        lambda: SimpleNamespace(success=True, changed=False, message="state loaded"),
    )
    monkeypatch.setattr(
        app.recovery_service,
        "recover_incomplete_transaction",
        lambda: {"status": "none", "message": ""},
    )
    calls: list[bool] = []

    def fallback(*, force: bool = False):
        calls.append(force)
        return SyncResult(
            "csv_fallback", "workbook missing", source_exists=False, row_count=5
        )

    monkeypatch.setattr(app.aed_repository, "ensure_cache_current", fallback)
    monkeypatch.setattr(app.pm_service, "ensure_pm_storage", lambda: None)
    monkeypatch.setattr(app.pm_service, "ensure_aed_pm_fields", lambda path: None)
    monkeypatch.setattr(app.manual_service_storage, "ensure_manual_service_storage", lambda: None)
    monkeypatch.setattr(app.issue_service, "ensure_issue_storage", lambda path: None)

    with pytest.raises(RuntimeError, match="official OneDrive Excel"):
        app.initialise_operational_storage()
    assert calls == [True]
    assert "_onedrive_master_bootstrapped" not in fake_st.session_state


def test_missing_cloud_configuration_is_blocked_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import streamlit_app as app

    class StopCalled(RuntimeError):
        pass

    class FakeStreamlit:
        def __init__(self) -> None:
            self.messages: list[str] = []

        def title(self, value):
            self.messages.append(str(value))

        def error(self, value):
            self.messages.append(str(value))

        def code(self, value, **kwargs):
            self.messages.append(str(value))

        def write(self, value):
            self.messages.append(str(value))

        def caption(self, value):
            self.messages.append(str(value))

        def stop(self):
            raise StopCalled

    fake = FakeStreamlit()
    monkeypatch.setattr(app, "st", fake)
    monkeypatch.setattr(app.config, "ONEDRIVE_CLOUD_ENABLED", False)
    monkeypatch.setattr(app.config, "REQUIRE_ONEDRIVE_SIGN_IN", True)

    with pytest.raises(StopCalled):
        app.render_microsoft_sign_in_gate()
    assert any("will not fall back" in message for message in fake.messages)


def test_page_cycle_flushes_system_records_to_onedrive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import streamlit_app as app

    fake_st = _StateOnlyStreamlit()
    monkeypatch.setattr(app, "st", fake_st)
    monkeypatch.setattr(app.config, "ONEDRIVE_CLOUD_ENABLED", True)
    monkeypatch.setattr(
        app.microsoft_auth_service,
        "get_authentication_status",
        lambda: SimpleNamespace(authenticated=True),
    )
    calls: list[bool] = []
    monkeypatch.setattr(
        app.system_state_service,
        "sync_system_state",
        lambda allow_download=False: calls.append(allow_download)
        or SimpleNamespace(status="uploaded", uploaded=True, message="state uploaded"),
    )

    app.flush_system_state_after_page()

    assert calls == [False]
    assert fake_st.session_state["system_state_notice"] == "state uploaded"


def test_missing_remote_state_archive_is_created_without_bundled_demo_records(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import io
    import zipfile
    from services import system_state_service as state

    root = tmp_path / "project"
    root.mkdir()
    paths = {
        "aed_history": root / "aed_management_history.csv",
        "pm": root / "pm_responses.csv",
        "plan": root / "pm_plan_records.csv",
        "manual": root / "manual_service_records.csv",
        "issues": root / "issue_records.csv",
        "issue_history": root / "issue_history.csv",
        "attachments": root / "issue_attachments.csv",
        "resolutions": root / "issue_resolution_submissions.csv",
        "map_state": root / "map_unit_state.csv",
        "map_status": root / "map_status_definitions.csv",
        "map_colors": root / "map_color_settings.csv",
        "audit": root / "data" / "audit_history.csv",
        "transactions": root / "data" / "transaction_history.csv",
        "conflicts": root / "data" / "conflict_history.csv",
        "write_history": root / "data" / "excel_write_history.csv",
        "lifecycle": root / "data" / "aed_lifecycle_history.csv",
        "photos": root / "issue_photos",
        "sync": root / "data" / "system_state_sync.json",
        "pending": root / "backups" / "system_state_pending",
    }
    paths["photos"].mkdir(parents=True)
    paths["issues"].write_text("Issue ID,Status\nDEMO-ISSUE,Reported\n", encoding="utf-8")
    paths["issue_history"].write_text("History ID,Issue ID\nDEMO-H,DEMO-ISSUE\n", encoding="utf-8")
    paths["map_state"].write_text("Serial Number,Status\nDEMO-AED,Issue\n", encoding="utf-8")
    (paths["photos"] / "demo.jpg").write_bytes(b"demo")
    paths["map_status"].write_text("Status Name,Active\nPending,Yes\n", encoding="utf-8")
    paths["map_colors"].write_text("Setting,Value\nDefault,#000000\n", encoding="utf-8")

    replacements = {
        "PROJECT_ROOT": root,
        "AED_HISTORY_FILE": paths["aed_history"],
        "PM_RESPONSES_FILE": paths["pm"],
        "PM_PLAN_FILE": paths["plan"],
        "MANUAL_SERVICE_RECORDS_FILE": paths["manual"],
        "ISSUE_RECORD_FILE": paths["issues"],
        "ISSUE_HISTORY_FILE": paths["issue_history"],
        "ISSUE_ATTACHMENTS_FILE": paths["attachments"],
        "ISSUE_RESOLUTION_FILE": paths["resolutions"],
        "MAP_UNIT_STATE_FILE": paths["map_state"],
        "AUDIT_HISTORY_FILE": paths["audit"],
        "TRANSACTION_HISTORY_FILE": paths["transactions"],
        "CONFLICT_HISTORY_FILE": paths["conflicts"],
        "EXCEL_WRITE_HISTORY_FILE": paths["write_history"],
        "AED_LIFECYCLE_FILE": paths["lifecycle"],
        "ISSUE_PHOTO_DIR": paths["photos"],
        "SYSTEM_STATE_SYNC_FILE": paths["sync"],
        "SYSTEM_STATE_PENDING_DIR": paths["pending"],
        "SYSTEM_STATE_PATHS": tuple(paths[key] for key in (
            "aed_history", "pm", "plan", "manual", "issues", "issue_history",
            "attachments", "resolutions", "map_state", "map_status", "map_colors",
            "audit", "transactions", "conflicts", "write_history", "lifecycle", "photos",
        )),
        "ONEDRIVE_CLOUD_ENABLED": True,
    }
    for name, value in replacements.items():
        monkeypatch.setattr(state, name, value)

    # The compatibility storage module keeps its own default path constant.
    from services import manual_service_storage
    monkeypatch.setattr(manual_service_storage, "MANUAL_SERVICE_RECORDS_FILE", paths["manual"])

    uploaded: dict[str, bytes] = {}
    monkeypatch.setattr(state, "get_metadata", lambda path, missing_ok=True: None)
    monkeypatch.setattr(
        state,
        "upload_bytes",
        lambda path, content, *, content_type, expected_etag="": uploaded.setdefault("content", content)
        or SimpleNamespace(etag="STATE-E1"),
    )
    # setdefault returns bytes, so use an explicit implementation for the metadata result.
    def upload(path, content, *, content_type, expected_etag=""):
        uploaded["content"] = content
        return SimpleNamespace(etag="STATE-E1")
    monkeypatch.setattr(state, "upload_bytes", upload)

    result = state.bootstrap_system_state()

    assert result.status == "initialised"
    with zipfile.ZipFile(io.BytesIO(uploaded["content"]), "r") as archive:
        combined = b"\n".join(archive.read(name) for name in archive.namelist() if name.endswith(".csv"))
        names = set(archive.namelist())
    assert b"DEMO-ISSUE" not in combined
    assert b"DEMO-AED" not in combined
    assert "issue_photos/demo.jpg" not in names
    assert "map_status_definitions.csv" in names
    assert list(paths["pending"].glob("AED_System_State_pre_cloud_initialise_*.zip"))


def test_signed_in_configuration_points_excel_source_to_onedrive_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib.util
    import sys

    fake_streamlit = SimpleNamespace(
        secrets={
            "microsoft": {
                "client_id": "client",
                "client_secret": "secret",
                "redirect_uri": "https://example.streamlit.app/",
                "authority": "https://login.microsoftonline.com/consumers",
                "onedrive_file_path": "/AED System/Official IB List.xlsx",
                "system_state_path": "/AED System/AED_System_State.zip",
            },
            "deployment": {"allow_local_data_mode": False},
        }
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
    spec = importlib.util.spec_from_file_location(
        "strict_config_probe", ROOT / "config.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.ONEDRIVE_CLOUD_ENABLED is True
    assert module.REQUIRE_ONEDRIVE_SIGN_IN is True
    assert module.EXCEL_FILE == module.ONEDRIVE_CACHE_DIR / "Official IB List.xlsx"
    assert module.AED_DATA_FILE == ROOT / "aed_data.csv"
