from pathlib import Path


def test_streamlit_entry_uses_v7_direct_cloud_core():
    source = Path("streamlit_app.py").read_text(encoding="utf-8")
    assert "cloud_runtime" not in source
    assert "CLOUD_SETTINGS" not in source
    assert "config.ONEDRIVE_CLOUD_ENABLED" in source or 'getattr(config, "ONEDRIVE_CLOUD_ENABLED"' in source
    assert "microsoft_auth_service.build_sign_in_url" in source


def test_cloud_services_do_not_import_runtime_proxy():
    for path in (
        Path("services/microsoft_auth_service.py"),
        Path("services/onedrive_excel_service.py"),
        Path("services/system_state_service.py"),
    ):
        source = path.read_text(encoding="utf-8")
        assert "cloud_runtime" not in source


def test_config_uses_v7_microsoft_section():
    source = Path("config.py").read_text(encoding="utf-8")
    assert '_secret_section("microsoft")' in source
    assert '"client_id"' in source
    assert '"client_secret"' in source
    assert '"onedrive_file_path"' in source


def test_upload_uses_same_item_and_if_match():
    source = Path("services/onedrive_excel_service.py").read_text(encoding="utf-8")
    assert "/me/drive/items/" in source
    assert 'conditional_headers["If-Match"] = expected' in source


def test_repository_forces_download_then_upload_then_readback():
    source = Path("services/aed_repository.py").read_text(encoding="utf-8")
    prepare = source.index("expected_etag = _prepare_workbook(force=True)")
    upload = source.index("upload_workbook(expected_etag=expected_etag)")
    readback = source.index("download_workbook(force=True)", upload)
    assert prepare < upload < readback


def test_v7_secret_reader_accepts_standard_microsoft_section(monkeypatch):
    import config

    class FakeSecrets(dict):
        pass

    class FakeStreamlit:
        secrets = FakeSecrets({
            "microsoft": {
                "client_id": "client-123",
                "client_secret": "secret-value",
                "authority": "https://login.microsoftonline.com/consumers",
                "redirect_uri": "https://example.streamlit.app/",
                "onedrive_file_path": "/AED System/IB_list_TEST.xlsx",
                "system_state_path": "/AED System/AED_System_State.zip",
            }
        })

    import sys
    monkeypatch.setitem(sys.modules, "streamlit", FakeStreamlit)
    settings = config._microsoft_configuration()
    assert settings["client_id"] == "client-123"
    assert settings["client_secret"] == "secret-value"
    assert settings["redirect_uri"] == "https://example.streamlit.app/"
    assert settings["onedrive_file_path"] == "/AED System/IB_list_TEST.xlsx"


def test_v7_auth_url_uses_direct_config(monkeypatch):
    from services import microsoft_auth_service as auth

    config = {
        "client_id": "client-123",
        "client_secret": "secret-value",
        "authority": "https://login.microsoftonline.com/consumers",
        "redirect_uri": "https://example.streamlit.app/",
        "onedrive_file_path": "/AED System/IB_list_TEST.xlsx",
    }
    monkeypatch.setattr(auth, "ONEDRIVE_CLOUD_ENABLED", True)
    monkeypatch.setattr(auth, "MICROSOFT_CONFIG", config)
    url = auth.build_sign_in_url()
    assert "client_id=client-123" in url
    assert "redirect_uri=https%3A%2F%2Fexample.streamlit.app%2F" in url
    assert "Files.ReadWrite" in url
