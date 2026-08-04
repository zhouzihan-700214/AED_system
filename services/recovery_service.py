"""Recover incomplete Stage 4 Excel transactions without repeating Excel writes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import ACTIVE_TRANSACTION_FILE, EXCEL_OPERATION_LOCK_FILE
from services.audit_service import record_transaction
from services.excel_lock_service import inspect_lock, operation_lock
from services.excel_transaction_service import _sync_without_relocking


def load_active_transaction() -> dict[str, Any] | None:
    path = Path(ACTIVE_TRANSACTION_FILE)
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def recover_incomplete_transaction() -> dict[str, Any]:
    transaction = load_active_transaction()
    if not transaction:
        return {"status": "none", "message": ""}

    lock_status = inspect_lock(EXCEL_OPERATION_LOCK_FILE)
    if lock_status.get("active"):
        lock_operation = str(lock_status.get("payload", {}).get("operation_id", ""))
        if lock_operation == str(transaction.get("operation_id", "")):
            return {"status": "active", "message": "An Excel transaction is still active."}

    step = str(transaction.get("last_completed_step", ""))
    temp_file = Path(str(transaction.get("temp_file") or "")) if transaction.get("temp_file") else None
    operation_id = str(transaction.get("operation_id", "recovery"))

    if step not in {"SOURCE_REPLACED", "CACHE_SYNCED", "RECOVERY_REQUIRED"}:
        if temp_file is not None:
            temp_file.unlink(missing_ok=True)
        Path(ACTIVE_TRANSACTION_FILE).unlink(missing_ok=True)
        message = "An incomplete pre-replacement transaction was cleaned up; the official Excel file was not changed."
        record_transaction(**{
            "Operation ID": operation_id,
            "Operation Type": transaction.get("operation_type", "RECOVERY"),
            "User": transaction.get("user", "System"),
            "Session ID": transaction.get("session_id", "recovery"),
            "Serial Numbers": "; ".join(transaction.get("serial_numbers", [])),
            "Source Page": "Startup Recovery",
            "Started At": transaction.get("started_at", ""),
            "Result": "Recovered-Cleanup",
            "Final Step": step,
            "Message": message,
        })
        return {"status": "cleaned", "message": message}

    metadata = {
        "operation_id": f"recovery-{operation_id}",
        "operation_type": "RECOVERY",
        "user": "System",
        "session_id": "startup-recovery",
        "serial_numbers": transaction.get("serial_numbers", []),
    }
    try:
        with operation_lock(metadata, EXCEL_OPERATION_LOCK_FILE):
            result = _sync_without_relocking()
        if not result.success:
            return {"status": "failed", "message": result.message}
        Path(ACTIVE_TRANSACTION_FILE).unlink(missing_ok=True)
        message = "Recovered an Excel update that had completed before the website cache refresh."
        record_transaction(**{
            "Operation ID": operation_id,
            "Operation Type": transaction.get("operation_type", "RECOVERY"),
            "User": transaction.get("user", "System"),
            "Session ID": transaction.get("session_id", "recovery"),
            "Serial Numbers": "; ".join(transaction.get("serial_numbers", [])),
            "Source Page": "Startup Recovery",
            "Started At": transaction.get("started_at", ""),
            "Result": "Recovered",
            "Final Step": "CACHE_SYNCED",
            "Message": message,
        })
        return {"status": "recovered", "message": message, "warnings": list(result.warnings)}
    except Exception as error:
        return {"status": "failed", "message": f"Recovery is still required: {error}"}
