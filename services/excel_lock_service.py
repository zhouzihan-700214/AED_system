"""Unified atomic lock for every operation that reads or writes the IB List."""
from __future__ import annotations

import json
import os
import socket
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from config import EXCEL_OPERATION_LOCK_FILE, LOCK_STALE_MINUTES, LOCK_WARNING_MINUTES


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def read_lock(lock_file: str | Path = EXCEL_OPERATION_LOCK_FILE) -> dict[str, Any] | None:
    path = Path(lock_file)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"invalid": True}
    except (OSError, json.JSONDecodeError):
        return {"invalid": True}


def inspect_lock(lock_file: str | Path = EXCEL_OPERATION_LOCK_FILE) -> dict[str, Any]:
    path = Path(lock_file)
    payload = read_lock(path)
    if payload is None:
        return {"exists": False, "active": False, "stale": False, "payload": {}}

    started_at = str(payload.get("started_at", ""))
    age_minutes: float | None = None
    try:
        started = datetime.fromisoformat(started_at)
        if started.tzinfo is None:
            started = started.astimezone()
        age_minutes = max(0.0, (datetime.now().astimezone() - started).total_seconds() / 60)
    except ValueError:
        pass

    same_host = str(payload.get("hostname", "")) == socket.gethostname()
    pid = int(payload.get("process_id", 0) or 0)
    process_alive = _process_exists(pid) if same_host else None
    confirmed_stale = bool(same_host and process_alive is False)
    warning = bool(age_minutes is not None and age_minutes >= LOCK_WARNING_MINUTES)
    stale_by_age = bool(age_minutes is not None and age_minutes >= LOCK_STALE_MINUTES)

    return {
        "exists": True,
        "active": not confirmed_stale,
        "confirmed_stale": confirmed_stale,
        "stale": confirmed_stale,
        "warning": warning,
        "stale_by_age": stale_by_age,
        "age_minutes": age_minutes,
        "same_host": same_host,
        "process_alive": process_alive,
        "payload": payload,
    }


def remove_confirmed_stale_lock(lock_file: str | Path = EXCEL_OPERATION_LOCK_FILE) -> bool:
    path = Path(lock_file)
    status = inspect_lock(path)
    if status.get("confirmed_stale"):
        path.unlink(missing_ok=True)
        return True
    return False


class ExcelOperationLock:
    def __init__(self, lock_file: str | Path = EXCEL_OPERATION_LOCK_FILE):
        self.path = Path(lock_file)
        self.acquired = False

    def acquire(self, metadata: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        remove_confirmed_stale_lock(self.path)
        payload = {
            **metadata,
            "hostname": socket.gethostname(),
            "process_id": os.getpid(),
            "started_at": metadata.get("started_at") or now_iso(),
        }
        try:
            descriptor = os.open(
                self.path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError as error:
            current = inspect_lock(self.path)
            existing = current.get("payload", {})
            details = (
                f" Operation: {existing.get('operation_type', 'unknown')};"
                f" user: {existing.get('user', 'unknown')};"
                f" started: {existing.get('started_at', 'unknown')}."
            )
            raise RuntimeError(
                "Another Excel operation is in progress. Try again after it finishes."
                + details
            ) from error

        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        self.acquired = True

    def release(self) -> None:
        if self.acquired:
            self.path.unlink(missing_ok=True)
            self.acquired = False


@contextmanager
def operation_lock(metadata: dict[str, Any], lock_file: str | Path = EXCEL_OPERATION_LOCK_FILE) -> Iterator[None]:
    lock = ExcelOperationLock(lock_file)
    lock.acquire(metadata)
    try:
        yield
    finally:
        lock.release()
