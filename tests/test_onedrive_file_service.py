from __future__ import annotations


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b"", text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content
        self.text = text

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


def test_generic_path_is_encoded(monkeypatch):
    from services import onedrive_file_service as service

    monkeypatch.setattr(service, "get_access_token", lambda: "token")
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        return FakeResponse(payload={"id": "1", "eTag": "e1"})

    monkeypatch.setattr(service.requests, "get", fake_get)
    service.get_metadata("/AED System/AED System State.zip")
    assert captured["url"].endswith("/me/drive/root:/AED%20System/AED%20System%20State.zip")


def test_generic_upload_creates_missing_file(monkeypatch):
    from services import onedrive_file_service as service

    monkeypatch.setattr(service, "get_access_token", lambda: "token")
    monkeypatch.setattr(service, "get_metadata", lambda path, missing_ok=False: None)
    captured = {}

    def fake_put(url, **kwargs):
        captured["url"] = url
        captured["data"] = kwargs["data"]
        return FakeResponse(payload={"id": "1", "eTag": "e2", "size": 3}, content=b"{}")

    monkeypatch.setattr(service.requests, "put", fake_put)
    result = service.upload_bytes("/AED System/state.zip", b"zip", content_type="application/zip")
    assert result.etag == "e2"
    assert captured["data"] == b"zip"
    assert captured["url"].endswith("/me/drive/root:/AED%20System/state.zip:/content")


def test_generic_upload_stops_on_etag_conflict(monkeypatch):
    from services import onedrive_file_service as service

    monkeypatch.setattr(
        service,
        "get_metadata",
        lambda path, missing_ok=False: service.RemoteFile(path=path, etag="new"),
    )
    try:
        service.upload_bytes("/AED System/state.zip", b"zip", expected_etag="old")
    except service.OneDriveFileConflictError:
        pass
    else:
        raise AssertionError("ETag conflict must stop a state archive overwrite")
