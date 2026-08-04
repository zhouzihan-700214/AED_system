from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import streamlit_app as app


class _FakeStreamlit:
    def __init__(self, secrets):
        self.secrets = secrets


def test_runtime_refresh_reads_standard_microsoft_section(monkeypatch) -> None:
    fake = _FakeStreamlit(
        {
            "microsoft": {
                "client_id": "client-standard",
                "client_secret": "secret-standard",
                "authority": "https://login.microsoftonline.com/consumers",
                "redirect_uri": "https://zollaed.streamlit.app/",
                "onedrive_file_path": "/AED System/IB_list_TEST.xlsx",
                "system_state_path": "/AED System/AED_System_State.zip",
            },
            "deployment": {"allow_local_data_mode": False},
        }
    )
    monkeypatch.setattr(app, "st", fake)
    monkeypatch.setattr(app.config, "MICROSOFT_CONFIG", {})
    monkeypatch.setattr(app.config, "ONEDRIVE_CLOUD_ENABLED", False)
    monkeypatch.setattr(app.config, "ONEDRIVE_CACHE_DIR", Path("/tmp/onedrive-cache"))

    app._refresh_runtime_cloud_configuration()

    assert app.config.ONEDRIVE_CLOUD_ENABLED is True
    assert app.config.MICROSOFT_CONFIG["client_id"] == "client-standard"
    assert app.config.MICROSOFT_CONFIG["client_secret"] == "secret-standard"
    assert app.config.MICROSOFT_CONFIG["redirect_uri"] == "https://zollaed.streamlit.app/"
    assert app.config.MICROSOFT_MISSING_KEYS == ()
    assert app.config.MICROSOFT_SECRET_SOURCE == "[microsoft]"
    assert app.config.EXCEL_FILE == Path("/tmp/onedrive-cache/IB_list_TEST.xlsx")


def test_runtime_refresh_accepts_legacy_case_and_aliases(monkeypatch) -> None:
    fake = _FakeStreamlit(
        {
            "Microsoft": {
                "CLIENT_ID": "client-legacy",
                "CLIENT_SECRET": "secret-legacy",
                "REDIRECT_URI": "https://zollaed.streamlit.app/",
                "ONEDRIVE_FILE_PATH": "/AED System/IB_list_TEST.xlsx",
            }
        }
    )
    monkeypatch.setattr(app, "st", fake)
    monkeypatch.setattr(app.config, "MICROSOFT_CONFIG", {})
    monkeypatch.setattr(app.config, "ONEDRIVE_CLOUD_ENABLED", False)
    monkeypatch.setattr(app.config, "ONEDRIVE_CACHE_DIR", Path("/tmp/onedrive-cache"))

    app._refresh_runtime_cloud_configuration()

    assert app.config.ONEDRIVE_CLOUD_ENABLED is True
    assert app.config.MICROSOFT_CONFIG["client_id"] == "client-legacy"
    assert app.config.MICROSOFT_SECRET_SOURCE == "[Microsoft]"


def test_runtime_refresh_reports_exact_missing_keys(monkeypatch) -> None:
    fake = _FakeStreamlit(
        {
            "microsoft": {
                "client_id": "client-only",
                "onedrive_file_path": "/AED System/IB_list_TEST.xlsx",
            }
        }
    )
    monkeypatch.setattr(app, "st", fake)
    monkeypatch.setattr(app.config, "MICROSOFT_CONFIG", {})
    monkeypatch.setattr(app.config, "ONEDRIVE_CLOUD_ENABLED", True)

    app._refresh_runtime_cloud_configuration()

    assert app.config.ONEDRIVE_CLOUD_ENABLED is False
    assert app.config.MICROSOFT_MISSING_KEYS == ("client_secret", "redirect_uri")
