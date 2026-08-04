"""Persist system-only records to a separate OneDrive archive.

The official IB List remains unchanged by map colours, issue workflow data,
PM planning records and photos. Those files are packed into
``AED_System_State.zip`` and synchronised independently.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from config import (
    MICROSOFT_CONFIG,
    ONEDRIVE_CLOUD_ENABLED,
    PROJECT_ROOT,
    SYSTEM_STATE_PATHS,
    SYSTEM_STATE_PENDING_DIR,
    SYSTEM_STATE_SYNC_FILE,
)
from services.onedrive_file_service import (
    OneDriveFileConflictError,
    OneDriveFileError,
    download_bytes,
    get_metadata,
    upload_bytes,
)


@dataclass(frozen=True)
class SystemStateResult:
    status: str
    message: str
    changed: bool = False
    uploaded: bool = False
    downloaded: bool = False

    @property
    def success(self) -> bool:
        return self.status in {"local_mode", "up_to_date", "uploaded", "downloaded", "initialised"}


def _remote_path() -> str:
    return str(
        MICROSOFT_CONFIG.get("system_state_path", "/AED System/AED_System_State.zip")
        or "/AED System/AED_System_State.zip"
    ).strip()


def _read_state() -> dict[str, Any]:
    path = Path(SYSTEM_STATE_SYNC_FILE)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_state(payload: dict[str, Any]) -> None:
    path = Path(SYSTEM_STATE_SYNC_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def _iter_files() -> Iterable[Path]:
    for configured in SYSTEM_STATE_PATHS:
        path = Path(configured)
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    yield child
        elif path.is_file():
            yield path


def local_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in sorted(_iter_files(), key=lambda item: str(item.relative_to(PROJECT_ROOT))):
        relative = str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        stat = path.stat()
        digest.update(relative.encode("utf-8"))
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        # Hash small operational files fully. Large photos use metadata to keep
        # the ten-second check inexpensive.
        if stat.st_size <= 2_000_000:
            digest.update(path.read_bytes())
    return digest.hexdigest()


def build_archive() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in _iter_files():
            relative = str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
            archive.write(path, arcname=relative)
    return buffer.getvalue()


def _safe_extract(content: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
        root = PROJECT_ROOT.resolve()
        for member in archive.infolist():
            target = (PROJECT_ROOT / member.filename).resolve()
            if root not in target.parents and target != root:
                raise ValueError("The OneDrive state archive contains an unsafe path.")
        archive.extractall(PROJECT_ROOT)


def _pending_copy(content: bytes, label: str) -> Path:
    folder = Path(SYSTEM_STATE_PENDING_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = folder / f"AED_System_State_{label}_{timestamp}_{uuid.uuid4().hex[:8]}.zip"
    path.write_bytes(content)
    return path


def bootstrap_system_state() -> SystemStateResult:
    """Prefer the cloud archive on first authenticated startup."""
    if not ONEDRIVE_CLOUD_ENABLED:
        return SystemStateResult("local_mode", "Using local system records.")

    remote = get_metadata(_remote_path(), missing_ok=True)
    current_fingerprint = local_fingerprint()
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    if remote is None:
        uploaded = upload_bytes(_remote_path(), build_archive(), content_type="application/zip")
        _write_state({
            "remote_path": _remote_path(),
            "etag": uploaded.etag,
            "local_fingerprint": current_fingerprint,
            "last_sync_time": now,
        })
        return SystemStateResult(
            "initialised",
            "A separate OneDrive system-state archive was created.",
            changed=True,
            uploaded=True,
        )

    state = _read_state()
    if state.get("etag") == remote.etag and state.get("local_fingerprint") == current_fingerprint:
        return SystemStateResult("up_to_date", "System records are up to date.")

    # First boot of this deployment, or cloud is newer: cloud is authoritative.
    if not state or state.get("etag") != remote.etag:
        content, downloaded = download_bytes(_remote_path())
        _safe_extract(content)
        fingerprint = local_fingerprint()
        _write_state({
            "remote_path": _remote_path(),
            "etag": downloaded.etag,
            "local_fingerprint": fingerprint,
            "last_sync_time": now,
        })
        return SystemStateResult(
            "downloaded",
            "Latest system records were loaded from OneDrive.",
            changed=True,
            downloaded=True,
        )

    return SystemStateResult("up_to_date", "System records are up to date.")


def sync_system_state(*, allow_download: bool = True) -> SystemStateResult:
    """Synchronise local operational records without touching the IB List."""
    if not ONEDRIVE_CLOUD_ENABLED:
        return SystemStateResult("local_mode", "Using local system records.")

    state = _read_state()
    remote = get_metadata(_remote_path(), missing_ok=True)
    current_fingerprint = local_fingerprint()
    previous_fingerprint = str(state.get("local_fingerprint", "") or "")
    previous_etag = str(state.get("etag", "") or "")
    local_changed = current_fingerprint != previous_fingerprint
    remote_changed = remote is not None and remote.etag != previous_etag
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    if remote is None:
        uploaded = upload_bytes(_remote_path(), build_archive(), content_type="application/zip")
        _write_state({
            "remote_path": _remote_path(),
            "etag": uploaded.etag,
            "local_fingerprint": current_fingerprint,
            "last_sync_time": now,
        })
        return SystemStateResult("uploaded", "System records uploaded to OneDrive.", True, True, False)

    if local_changed and remote_changed:
        pending = _pending_copy(build_archive(), "conflict")
        return SystemStateResult(
            "conflict",
            "System records changed in both places. A local recovery archive was saved at "
            f"{pending}. Reload before making more changes.",
        )

    if remote_changed and not allow_download:
        return SystemStateResult(
            "deferred",
            "A newer system-state archive is available. It will be loaded after the current editing workspace is closed.",
        )

    if remote_changed:
        content, downloaded = download_bytes(_remote_path())
        _safe_extract(content)
        fingerprint = local_fingerprint()
        _write_state({
            "remote_path": _remote_path(),
            "etag": downloaded.etag,
            "local_fingerprint": fingerprint,
            "last_sync_time": now,
        })
        return SystemStateResult("downloaded", "System records refreshed from OneDrive.", True, False, True)

    if local_changed:
        try:
            uploaded = upload_bytes(
                _remote_path(),
                build_archive(),
                content_type="application/zip",
                expected_etag=previous_etag,
            )
        except OneDriveFileConflictError as error:
            pending = _pending_copy(build_archive(), "upload_conflict")
            return SystemStateResult("conflict", f"{error} Recovery archive: {pending}")
        _write_state({
            "remote_path": _remote_path(),
            "etag": uploaded.etag,
            "local_fingerprint": current_fingerprint,
            "last_sync_time": now,
        })
        return SystemStateResult("uploaded", "System records saved to OneDrive.", True, True, False)

    return SystemStateResult("up_to_date", "System records are up to date.")
