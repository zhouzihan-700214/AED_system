from __future__ import annotations

from pathlib import Path

import config
from services import cloud_runtime


def test_nested_flexible_secret_keys_are_detected() -> None:
    settings = cloud_runtime.load_cloud_settings(
        {
            "Connections": {
                "Microsoft OneDrive": {
                    "Client-ID": "client-107",
                    "Client Secret Value": "secret-107",
                    "Reply URL": "https://zollaed.streamlit.app/",
                    "Workbook Path": "/AED System/Official.xlsx",
                }
            }
        }
    )

    assert settings.configured is True
    assert settings.client_id == "client-107"
    assert settings.client_secret == "secret-107"
    assert settings.redirect_uri == "https://zollaed.streamlit.app/"
    assert settings.onedrive_file_path == "/AED System/Official.xlsx"


def test_apply_to_config_replaces_stale_empty_import_values(monkeypatch) -> None:
    monkeypatch.setattr(config, "MICROSOFT_CONFIG", {"client_id": ""})
    monkeypatch.setattr(config, "ONEDRIVE_CLOUD_ENABLED", False)
    monkeypatch.setattr(config, "ONEDRIVE_CACHE_DIR", Path("/tmp/v107-cloud-cache"))

    settings = cloud_runtime.load_cloud_settings(
        {
            "microsoft": {
                "client_id": "fresh-client",
                "client_secret": "fresh-secret",
                "redirect_uri": "https://example.streamlit.app/",
                "onedrive_file_path": "/AED System/IB_list_TEST.xlsx",
            }
        }
    )
    cloud_runtime.apply_to_config(config, settings)

    assert config.ONEDRIVE_CLOUD_ENABLED is True
    assert config.MICROSOFT_CONFIG["client_id"] == "fresh-client"
    assert config.EXCEL_FILE == Path("/tmp/v107-cloud-cache/IB_list_TEST.xlsx")
    assert config.ALLOW_LOCAL_DATA_MODE is False
    assert config.REQUIRE_ONEDRIVE_SIGN_IN is True


def test_old_deployment_flag_does_not_bypass_cloud_requirement() -> None:
    settings = cloud_runtime.load_cloud_settings(
        {
            "deployment": {"allow_local_data_mode": True},
            "microsoft": {"client_id": "only-client"},
        }
    )

    assert settings.configured is False
    assert settings.missing_keys == ("client_secret", "redirect_uri")
