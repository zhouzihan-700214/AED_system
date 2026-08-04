"""Append-only Stage 4 transaction, conflict and field audit records."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from config import AUDIT_HISTORY_FILE, CONFLICT_HISTORY_FILE, TRANSACTION_HISTORY_FILE


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _append(path: Path, columns: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


TRANSACTION_COLUMNS = [
    "Operation ID", "Operation Type", "User", "Session ID", "Serial Numbers",
    "Source Page", "Started At", "Finished At", "Result", "Final Step", "Message",
]
AUDIT_COLUMNS = [
    "Operation ID", "Timestamp", "User", "Session ID", "Operation Type",
    "Source Page", "Serial Number", "Field", "Original Value", "Current Value",
    "Desired Value", "Result", "Message",
]
CONFLICT_COLUMNS = AUDIT_COLUMNS


def record_transaction(**row: Any) -> None:
    payload = {**row, "Finished At": row.get("Finished At") or _now()}
    _append(Path(TRANSACTION_HISTORY_FILE), TRANSACTION_COLUMNS, [payload])


def record_field_audit(rows: list[dict[str, Any]]) -> None:
    stamped = [{**row, "Timestamp": row.get("Timestamp") or _now()} for row in rows]
    if stamped:
        _append(Path(AUDIT_HISTORY_FILE), AUDIT_COLUMNS, stamped)


def record_conflicts(rows: list[dict[str, Any]]) -> None:
    stamped = [{**row, "Timestamp": row.get("Timestamp") or _now()} for row in rows]
    if stamped:
        _append(Path(CONFLICT_HISTORY_FILE), CONFLICT_COLUMNS, stamped)
