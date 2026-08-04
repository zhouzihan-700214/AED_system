"""Generic Microsoft Graph file operations for a personal OneDrive.

The official IB List and the system-state archive use the same authenticated
Graph session but remain separate files.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests

from services.microsoft_auth_service import get_access_token

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
REQUEST_TIMEOUT_SECONDS = 60


class OneDriveFileError(RuntimeError):
    pass


class OneDriveFileAuthenticationError(OneDriveFileError):
    pass


class OneDriveFileConflictError(OneDriveFileError):
    pass


@dataclass(frozen=True)
class RemoteFile:
    path: str
    item_id: str = ""
    etag: str = ""
    last_modified: str = ""
    size: int = 0
    web_url: str = ""


def normalise_remote_path(path: str) -> str:
    value = str(path or "").strip()
    if not value:
        raise OneDriveFileError("OneDrive file path is empty.")
    return "/" + value.strip("/")


def _encoded_path(path: str) -> str:
    return "/".join(quote(part, safe="") for part in normalise_remote_path(path).strip("/").split("/"))


def _item_url(path: str) -> str:
    return f"{GRAPH_ROOT}/me/drive/root:/{_encoded_path(path)}"


def _content_url(path: str) -> str:
    return _item_url(path) + ":/content"


def _token() -> str:
    token = get_access_token()
    if not token:
        raise OneDriveFileAuthenticationError(
            "Microsoft sign-in has expired. Sign in again before using OneDrive."
        )
    return token


def _headers(**extra: str) -> dict[str, str]:
    result = {"Authorization": f"Bearer {_token()}"}
    result.update(extra)
    return result


def _error(response: requests.Response, action: str, path: str) -> OneDriveFileError:
    if response.status_code == 401:
        return OneDriveFileAuthenticationError("Microsoft sign-in has expired. Sign in again.")
    if response.status_code in {409, 412, 423}:
        return OneDriveFileConflictError(
            f"The OneDrive file changed or is locked while trying to {action}: {normalise_remote_path(path)}"
        )
    try:
        detail = response.json().get("error", {}).get("message", "")
    except (ValueError, AttributeError):
        detail = response.text[:500]
    return OneDriveFileError(
        f"OneDrive {action} failed ({response.status_code}) for {normalise_remote_path(path)}. {detail}".strip()
    )


def get_metadata(path: str, *, missing_ok: bool = False) -> RemoteFile | None:
    remote_path = normalise_remote_path(path)
    response = requests.get(
        _item_url(remote_path),
        headers=_headers(),
        params={"$select": "id,name,size,eTag,cTag,lastModifiedDateTime,webUrl"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code == 404 and missing_ok:
        return None
    if not response.ok:
        raise _error(response, "metadata request", remote_path)
    payload: dict[str, Any] = response.json()
    return RemoteFile(
        path=remote_path,
        item_id=str(payload.get("id", "") or ""),
        etag=str(payload.get("eTag", "") or ""),
        last_modified=str(payload.get("lastModifiedDateTime", "") or ""),
        size=int(payload.get("size", 0) or 0),
        web_url=str(payload.get("webUrl", "") or ""),
    )


def download_bytes(path: str) -> tuple[bytes, RemoteFile]:
    remote_path = normalise_remote_path(path)
    metadata = get_metadata(remote_path)
    assert metadata is not None
    response = requests.get(
        _content_url(remote_path),
        headers=_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
        allow_redirects=True,
    )
    if not response.ok:
        raise _error(response, "download", remote_path)
    return response.content, metadata


def upload_bytes(
    path: str,
    content: bytes,
    *,
    content_type: str = "application/octet-stream",
    expected_etag: str = "",
) -> RemoteFile:
    remote_path = normalise_remote_path(path)
    current = get_metadata(remote_path, missing_ok=True)
    if expected_etag and current is not None and current.etag and current.etag != expected_etag:
        raise OneDriveFileConflictError(
            f"The OneDrive file changed after it was loaded: {remote_path}"
        )

    response = requests.put(
        _content_url(remote_path),
        headers=_headers(**{"Content-Type": content_type}),
        data=content,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if not response.ok:
        raise _error(response, "upload", remote_path)
    payload: dict[str, Any] = response.json() if response.content else {}
    return RemoteFile(
        path=remote_path,
        item_id=str(payload.get("id", "") or ""),
        etag=str(payload.get("eTag", "") or ""),
        last_modified=str(payload.get("lastModifiedDateTime", "") or ""),
        size=int(payload.get("size", len(content)) or len(content)),
        web_url=str(payload.get("webUrl", "") or ""),
    )
