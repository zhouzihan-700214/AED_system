"""Startup-safe storage bootstrap for manual service records.

This module is deliberately independent from ``unit_profile_service`` so the
application entrypoint can initialise the CSV even when Streamlit Cloud has a
stale cached copy of that larger service module.
"""
from __future__ import annotations

import csv
import os
import uuid
from pathlib import Path

import config as _config


def _resolve_project_root() -> Path:
    configured = getattr(_config, "PROJECT_ROOT", None)
    if configured:
        return Path(configured)
    configured = getattr(_config, "BASE_DIR", None)
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1]


PROJECT_ROOT = _resolve_project_root()
MANUAL_SERVICE_RECORDS_FILE = Path(
    getattr(
        _config,
        "MANUAL_SERVICE_RECORDS_FILE",
        PROJECT_ROOT / "manual_service_records.csv",
    )
)

# Compatibility for deployments where a new entrypoint is temporarily paired
# with an older cached config.py.  Exposing the fallback on the imported config
# module lets legacy modules that still use ``from config import ...`` load
# normally later in the same process.
if not hasattr(_config, "MANUAL_SERVICE_RECORDS_FILE"):
    _config.MANUAL_SERVICE_RECORDS_FILE = MANUAL_SERVICE_RECORDS_FILE

_state_paths = getattr(_config, "SYSTEM_STATE_PATHS", None)
if _state_paths is not None and MANUAL_SERVICE_RECORDS_FILE not in _state_paths:
    _config.SYSTEM_STATE_PATHS = tuple(_state_paths) + (MANUAL_SERVICE_RECORDS_FILE,)


MANUAL_SERVICE_RECORD_COLUMNS = [
    "Service Record ID",
    "Created At",
    "Created By",
    "AED Serial Number",
    "AED Model",
    "AED Location",
    "Postal Code",
    "Lift Lobby",
    "Service Date",
    "Service Type",
    "Technician",
    "Reference",
    "Status",
    "Details",
    "Master Data Updated",
    "PM Dates Updated",
    "Battery Replaced",
    "Battery History Updated",
    "PM Interval Months Used",
    "Linked Plan ID",
    "Master Operation ID",
    "Source",
]


def ensure_manual_service_storage(
    path: str | Path = MANUAL_SERVICE_RECORDS_FILE,
) -> Path:
    """Create the manual-service CSV and its header when it is missing."""
    record_path = Path(path)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    if not record_path.exists() or record_path.stat().st_size == 0:
        temp = record_path.with_name(f".{record_path.name}.{uuid.uuid4().hex}.tmp")
        with temp.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=MANUAL_SERVICE_RECORD_COLUMNS)
            writer.writeheader()
        os.replace(temp, record_path)
    return record_path
