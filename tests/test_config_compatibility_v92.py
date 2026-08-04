from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def test_manual_storage_loads_with_legacy_config(tmp_path, monkeypatch):
    legacy_config = types.ModuleType("config")
    legacy_config.PROJECT_ROOT = tmp_path
    legacy_config.SYSTEM_STATE_PATHS = ()
    monkeypatch.setitem(sys.modules, "config", legacy_config)

    module_path = Path(__file__).resolve().parents[1] / "services" / "manual_service_storage.py"
    spec = importlib.util.spec_from_file_location("manual_service_storage_legacy_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    expected = tmp_path / "manual_service_records.csv"
    assert module.MANUAL_SERVICE_RECORDS_FILE == expected
    assert legacy_config.MANUAL_SERVICE_RECORDS_FILE == expected
    assert expected in legacy_config.SYSTEM_STATE_PATHS

    result = module.ensure_manual_service_storage()
    assert result == expected
    assert expected.exists()
    assert expected.read_text(encoding="utf-8-sig").startswith("Service Record ID,")
