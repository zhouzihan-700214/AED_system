"""Download and upload the official Excel workbook through Microsoft Graph."""
from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

import requests

from config import (
    EXCEL_FILE,
    MICROSOFT_CONFIG,
    ONEDRIVE_CLOUD_ENABLED,
    ONEDRIVE_PENDING_DIR,
    ONEDRIVE_SYNC_STATE_FILE,
)
from services.microsoft_auth_service import get_access_token

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
REQUEST_TIMEOUT_SECONDS = 45
METADATA_CHECK_TTL_SECONDS = 8


class OneDriveError(RuntimeError):
    pass


class OneDriveAuthenticationError(OneDriveError):
    pass


class OneDriveConflictError(OneDriveError):
    pass


@dataclass(frozen=True)
class OneDriveSyncResult:
    status: str
    message: str
    changed: bool = False
    source_exists: bool = False
    etag: str = ""
    last_modified: str = ""
    remote_path: str = ""
    item_id: str = ""

    @property
    def success(self) -> bool:
        return self.status in {"downloaded", "uploaded", "up_to_date", "local_mode"}


def is_cloud_onedrive_enabled() -> bool:
    return bool(ONEDRIVE_CLOUD_ENABLED)


def _remote_path() -> str:
    path = str(MICROSOFT_CONFIG.get("onedrive_file_path", "") or "").strip()
    if not path:
        raise OneDriveError("OneDrive file path is missing from Streamlit Secrets.")
    return "/" + path.strip("/")


def _encoded_path(path: str) -> str:
    return "/".join(quote(part, safe="") for part in path.strip("/").split("/"))


def _item_url(path: str | None = None) -> str:
    target = _encoded_path(path or _remote_path())
    return f"{GRAPH_ROOT}/me/drive/root:/{target}"


def _content_url(path: str | None = None) -> str:
    return _item_url(path) + ":/content"


def _headers(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _token() -> str:
    token = get_access_token()
    if not token:
        raise OneDriveAuthenticationError(
            "Microsoft sign-in has expired. Sign in again before using OneDrive."
        )
    return token


def _request_error(response: requests.Response, action: str) -> OneDriveError:
    if response.status_code == 401:
        return OneDriveAuthenticationError("Microsoft sign-in has expired. Sign in again.")
    if response.status_code == 404:
        return OneDriveError(
            f"The OneDrive workbook was not found at {_remote_path()}."
        )
    if response.status_code in {409, 412, 423}:
        return OneDriveConflictError(
            "The OneDrive workbook changed or is temporarily locked. Refresh AED Data and try again."
        )
    try:
        detail = response.json().get("error", {}).get("message", "")
    except (ValueError, AttributeError):
        detail = response.text[:500]
    return OneDriveError(
        f"OneDrive {action} failed ({response.status_code}). {detail}".strip()
    )


def load_onedrive_state() -> dict[str, Any]:
    path = Path(ONEDRIVE_SYNC_STATE_FILE)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _save_state(payload: Mapping[str, Any]) -> None:
    path = Path(ONEDRIVE_SYNC_STATE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(dict(payload), indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)




def _recent_metadata_check(state: Mapping[str, Any]) -> bool:
    value = str(state.get("last_metadata_check_time", "") or "")
    if not value:
        return False
    try:
        checked = datetime.fromisoformat(value)
        if checked.tzinfo is None:
            checked = checked.astimezone()
        age = (datetime.now().astimezone() - checked.astimezone()).total_seconds()
        return 0 <= age < METADATA_CHECK_TTL_SECONDS
    except ValueError:
        return False

def get_remote_metadata() -> dict[str, Any]:
    if not ONEDRIVE_CLOUD_ENABLED:
        return {}
    response = requests.get(
        _item_url(),
        headers=_headers(_token()),
        params={"$select": "id,name,size,eTag,cTag,lastModifiedDateTime,webUrl"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if not response.ok:
        raise _request_error(response, "metadata request")
    payload = response.json()
    if not isinstance(payload, dict):
        raise OneDriveError("OneDrive returned invalid workbook metadata.")
    return payload


def _atomic_write_local(content: bytes, destination: Path) -> None:
    if len(content) < 4 or not content.startswith(b"PK"):
        raise OneDriveError("The downloaded OneDrive file is not a valid .xlsx workbook.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.download")
    temp.write_bytes(content)
    os.replace(temp, destination)


def download_workbook(*, force: bool = False) -> OneDriveSyncResult:
    """Download the latest OneDrive workbook into the app's private local cache."""
    if not ONEDRIVE_CLOUD_ENABLED:
        return OneDriveSyncResult(
            "local_mode", "Using the project-local Excel workbook.",
            changed=False, source_exists=Path(EXCEL_FILE).exists(),
        )
    state = load_onedrive_state()
    local = Path(EXCEL_FILE)
    if (
        not force
        and local.exists()
        and str(state.get("remote_path", "")) == _remote_path()
        and _recent_metadata_check(state)
    ):
        return OneDriveSyncResult(
            "up_to_date", "OneDrive Excel was checked recently.",
            changed=False, source_exists=True,
            etag=str(state.get("etag", "") or ""),
            last_modified=str(state.get("last_modified", "") or ""),
            remote_path=_remote_path(), item_id=str(state.get("item_id", "") or ""),
        )

    metadata = get_remote_metadata()
    etag = str(metadata.get("eTag", "") or "")
    if (
        not force
        and local.exists()
        and etag
        and etag == str(state.get("etag", "") or "")
        and str(state.get("remote_path", "")) == _remote_path()
    ):
        checked = datetime.now().astimezone().isoformat(timespec="seconds")
        refreshed_state = dict(state)
        refreshed_state.update({
            "last_metadata_check_time": checked,
            "last_modified": str(metadata.get("lastModifiedDateTime", "") or ""),
            "item_id": str(metadata.get("id", "") or ""),
        })
        _save_state(refreshed_state)
        return OneDriveSyncResult(
            "up_to_date", "OneDrive Excel is already up to date.",
            changed=False, source_exists=True, etag=etag,
            last_modified=str(metadata.get("lastModifiedDateTime", "") or ""),
            remote_path=_remote_path(), item_id=str(metadata.get("id", "") or ""),
        )

    response = requests.get(
        _content_url(),
        headers=_headers(_token()),
        timeout=REQUEST_TIMEOUT_SECONDS,
        allow_redirects=True,
    )
    if not response.ok:
        raise _request_error(response, "download")
    _atomic_write_local(response.content, local)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    _save_state({
        "remote_path": _remote_path(),
        "item_id": str(metadata.get("id", "") or ""),
        "etag": etag,
        "last_modified": str(metadata.get("lastModifiedDateTime", "") or ""),
        "last_download_time": now,
        "last_metadata_check_time": now,
        "last_upload_time": str(state.get("last_upload_time", "") or ""),
        "web_url": str(metadata.get("webUrl", "") or ""),
    })
    return OneDriveSyncResult(
        "downloaded", "Latest Excel downloaded from OneDrive.",
        changed=True, source_exists=True, etag=etag,
        last_modified=str(metadata.get("lastModifiedDateTime", "") or ""),
        remote_path=_remote_path(), item_id=str(metadata.get("id", "") or ""),
    )


def preserve_pending_local_copy(label: str = "pending") -> Path | None:
    source = Path(EXCEL_FILE)
    if not source.exists():
        return None
    destination_dir = Path(ONEDRIVE_PENDING_DIR)
    destination_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = destination_dir / f"{source.stem}_{label}_{timestamp}_{uuid.uuid4().hex[:8]}{source.suffix}"
    shutil.copy2(source, destination)
    return destination


def upload_workbook(*, expected_etag: str = "") -> OneDriveSyncResult:
    """Replace the same OneDrive workbook, refusing to overwrite a newer version."""
    if not ONEDRIVE_CLOUD_ENABLED:
        return OneDriveSyncResult(
            "local_mode", "Local Excel saved.", changed=True,
            source_exists=Path(EXCEL_FILE).exists(),
        )
    local = Path(EXCEL_FILE)
    if not local.exists():
        raise OneDriveError("The local workbook cache is missing; refresh AED Data first.")

    current = get_remote_metadata()
    current_etag = str(current.get("eTag", "") or "")
    expected = expected_etag or str(load_onedrive_state().get("etag", "") or "")
    if expected and current_etag and expected != current_etag:
        raise OneDriveConflictError(
            "The OneDrive Excel file changed after this page was loaded. Refresh AED Data before saving."
        )

    item_id = str(current.get("id", "") or "")
    if not item_id:
        raise OneDriveError("OneDrive did not return the workbook item ID.")
    headers = _headers(
        _token(),
        **{"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )
    response = requests.put(
        f"{GRAPH_ROOT}/me/drive/items/{quote(item_id, safe='')}/content",
        headers=headers,
        data=local.read_bytes(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if not response.ok:
        raise _request_error(response, "upload")
    payload = response.json() if response.content else {}
    new_etag = str(payload.get("eTag", "") or "")
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    state = load_onedrive_state()
    _save_state({
        "remote_path": _remote_path(),
        "item_id": str(payload.get("id", current.get("id", "")) or ""),
        "etag": new_etag,
        "last_modified": str(payload.get("lastModifiedDateTime", "") or ""),
        "last_download_time": str(state.get("last_download_time", "") or ""),
        "last_metadata_check_time": now,
        "last_upload_time": now,
        "web_url": str(payload.get("webUrl", current.get("webUrl", "")) or ""),
    })
    return OneDriveSyncResult(
        "uploaded", "OneDrive Excel updated successfully.",
        changed=True, source_exists=True, etag=new_etag,
        last_modified=str(payload.get("lastModifiedDateTime", "") or ""),
        remote_path=_remote_path(), item_id=str(payload.get("id", "") or ""),
    )
