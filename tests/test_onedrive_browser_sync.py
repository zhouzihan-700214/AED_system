from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b"", text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.content = content
        self.text = text

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


def test_path_urls_are_encoded(monkeypatch):
    from services import onedrive_excel_service as service

    monkeypatch.setattr(service, "MICROSOFT_CONFIG", {"onedrive_file_path": "/AED System/IB list.xlsx"})
    assert service._item_url().endswith("/me/drive/root:/AED%20System/IB%20list.xlsx")
    assert service._content_url().endswith("/me/drive/root:/AED%20System/IB%20list.xlsx:/content")


def test_download_workbook_saves_cloud_file(monkeypatch, tmp_path):
    from services import onedrive_excel_service as service

    workbook = tmp_path / "cache" / "IB_list_TEST.xlsx"
    state = tmp_path / "state.json"
    monkeypatch.setattr(service, "ONEDRIVE_CLOUD_ENABLED", True)
    monkeypatch.setattr(service, "EXCEL_FILE", workbook)
    monkeypatch.setattr(service, "ONEDRIVE_SYNC_STATE_FILE", state)
    monkeypatch.setattr(service, "MICROSOFT_CONFIG", {"onedrive_file_path": "/AED System/IB_list_TEST.xlsx"})
    monkeypatch.setattr(service, "get_access_token", lambda: "token")
    monkeypatch.setattr(service, "get_remote_metadata", lambda: {
        "id": "item-1", "eTag": "etag-1", "lastModifiedDateTime": "2026-08-03T00:00:00Z"
    })
    monkeypatch.setattr(service.requests, "get", lambda *args, **kwargs: FakeResponse(content=b"PK\x03\x04xlsx"))

    result = service.download_workbook(force=True)

    assert result.status == "downloaded"
    assert workbook.read_bytes() == b"PK\x03\x04xlsx"
    assert service.load_onedrive_state()["etag"] == "etag-1"


def test_download_skips_matching_etag(monkeypatch, tmp_path):
    from services import onedrive_excel_service as service

    workbook = tmp_path / "IB_list_TEST.xlsx"
    workbook.write_bytes(b"PK\x03\x04existing")
    state = tmp_path / "state.json"
    state.write_text('{"etag":"etag-1","remote_path":"/AED System/IB_list_TEST.xlsx"}')
    monkeypatch.setattr(service, "ONEDRIVE_CLOUD_ENABLED", True)
    monkeypatch.setattr(service, "EXCEL_FILE", workbook)
    monkeypatch.setattr(service, "ONEDRIVE_SYNC_STATE_FILE", state)
    monkeypatch.setattr(service, "MICROSOFT_CONFIG", {"onedrive_file_path": "/AED System/IB_list_TEST.xlsx"})
    monkeypatch.setattr(service, "get_remote_metadata", lambda: {"id": "item-1", "eTag": "etag-1"})

    result = service.download_workbook(force=False)

    assert result.status == "up_to_date"
    assert not result.changed


def test_upload_refuses_newer_cloud_version(monkeypatch, tmp_path):
    from services import onedrive_excel_service as service

    workbook = tmp_path / "IB_list_TEST.xlsx"
    workbook.write_bytes(b"PK\x03\x04local")
    monkeypatch.setattr(service, "ONEDRIVE_CLOUD_ENABLED", True)
    monkeypatch.setattr(service, "EXCEL_FILE", workbook)
    monkeypatch.setattr(service, "MICROSOFT_CONFIG", {"onedrive_file_path": "/AED System/IB_list_TEST.xlsx"})
    monkeypatch.setattr(service, "get_remote_metadata", lambda: {"id": "item-1", "eTag": "newer"})

    try:
        service.upload_workbook(expected_etag="older")
    except service.OneDriveConflictError:
        pass
    else:
        raise AssertionError("A newer OneDrive eTag must stop the upload")


def test_upload_replaces_existing_item_by_id(monkeypatch, tmp_path):
    from services import onedrive_excel_service as service

    workbook = tmp_path / "IB_list_TEST.xlsx"
    workbook.write_bytes(b"PK\x03\x04local")
    state = tmp_path / "state.json"
    captured = {}
    monkeypatch.setattr(service, "ONEDRIVE_CLOUD_ENABLED", True)
    monkeypatch.setattr(service, "EXCEL_FILE", workbook)
    monkeypatch.setattr(service, "ONEDRIVE_SYNC_STATE_FILE", state)
    monkeypatch.setattr(service, "MICROSOFT_CONFIG", {"onedrive_file_path": "/AED System/IB_list_TEST.xlsx"})
    monkeypatch.setattr(service, "get_access_token", lambda: "token")
    monkeypatch.setattr(service, "get_remote_metadata", lambda: {"id": "item!1", "eTag": "etag-1"})

    def fake_put(url, **kwargs):
        captured["url"] = url
        captured["data"] = kwargs["data"]
        captured["headers"] = kwargs["headers"]
        return FakeResponse(payload={"id": "item!1", "eTag": "etag-2"}, content=b"{}")

    monkeypatch.setattr(service.requests, "put", fake_put)
    result = service.upload_workbook(expected_etag="etag-1")

    assert result.status == "uploaded"
    assert captured["url"].endswith("/me/drive/items/item%211/content")
    assert captured["data"] == b"PK\x03\x04local"
    assert captured["headers"]["If-Match"] == "etag-1"
    assert service.load_onedrive_state()["etag"] == "etag-2"
