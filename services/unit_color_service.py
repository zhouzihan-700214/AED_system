"""System-only AED map colour and operational status synchronization.

The map state is intentionally stored outside the company Excel workbook.
Formal Excel fields such as Job Type and PM dates continue to use the existing
safe Excel transaction workflow, while marker colours remain an internal UI
state in ``map_unit_state.csv``.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from config import MAP_STATUS_FILE, MAP_UNIT_STATE_FILE
from services.csv_storage import atomic_write_csv
from utils.text_utils import clean_text

STATE_COLUMNS = ["Serial Number", "Status", "Color Override", "Updated At"]

ROLE_FALLBACK_NAMES = {
    "Pending": "Pending",
    "Completed": "Completed",
    "Issue": "Issue",
    "Pending Verification": "Pending Verification",
    "Out of Service": "Out of Service",
}


def _now_text() -> str:
    return datetime.now().astimezone().strftime("%d-%m-%Y %H:%M:%S")


def _read_csv(path: str | Path) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(
            csv_path,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        ).fillna("")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _load_state(path: str | Path = MAP_UNIT_STATE_FILE) -> pd.DataFrame:
    state = _read_csv(path)
    for column in STATE_COLUMNS:
        if column not in state.columns:
            state[column] = ""
    return state[STATE_COLUMNS].copy()


def _save_state(state: pd.DataFrame, path: str | Path = MAP_UNIT_STATE_FILE) -> None:
    output = state.copy()
    for column in STATE_COLUMNS:
        if column not in output.columns:
            output[column] = ""
    atomic_write_csv(output[STATE_COLUMNS], path, preferred_columns=STATE_COLUMNS)


def status_name_for_role(
    workflow_role: str,
    status_file: str | Path = MAP_STATUS_FILE,
) -> str:
    """Return the active customizable status assigned to a workflow role."""

    role = clean_text(workflow_role)
    definitions = _read_csv(status_file)
    if not definitions.empty:
        for column in ["Status Name", "Active", "Workflow Role"]:
            if column not in definitions.columns:
                definitions[column] = ""
        matches = definitions[
            definitions["Workflow Role"].astype(str).str.casefold().eq(role.casefold())
            & definitions["Active"].astype(str).str.casefold().eq("yes")
        ]
        if not matches.empty:
            name = clean_text(matches.iloc[0]["Status Name"])
            if name:
                return name
    return ROLE_FALLBACK_NAMES.get(role, role or "Pending")


def set_unit_workflow_role(
    serial_number: Any,
    workflow_role: str,
    *,
    clear_manual_colour: bool = True,
    state_file: str | Path = MAP_UNIT_STATE_FILE,
    status_file: str | Path = MAP_STATUS_FILE,
) -> None:
    """Set one unit's operational map status without touching the Excel sheet."""

    serial = clean_text(serial_number)
    if not serial:
        return

    status_name = status_name_for_role(workflow_role, status_file=status_file)
    state = _load_state(state_file)
    mask = state["Serial Number"].astype(str).str.casefold().eq(serial.casefold())

    if mask.any():
        state.loc[mask, "Status"] = status_name
        if clear_manual_colour:
            state.loc[mask, "Color Override"] = ""
        state.loc[mask, "Updated At"] = _now_text()
    else:
        state = pd.concat(
            [
                state,
                pd.DataFrame(
                    [
                        {
                            "Serial Number": serial,
                            "Status": status_name,
                            "Color Override": "",
                            "Updated At": _now_text(),
                        }
                    ],
                    columns=STATE_COLUMNS,
                ),
            ],
            ignore_index=True,
        )

    _save_state(state, state_file)


def unresolved_issue_rows(
    issue_csv_file: str | Path,
    serial_number: Any,
) -> pd.DataFrame:
    serial = clean_text(serial_number)
    issues = _read_csv(issue_csv_file)
    if not serial or issues.empty:
        return pd.DataFrame()
    for column in ["Serial Number", "Status"]:
        if column not in issues.columns:
            issues[column] = ""
    mask = (
        issues["Serial Number"].astype(str).str.casefold().eq(serial.casefold())
        & ~issues["Status"].astype(str).str.casefold().isin({"closed", "resolved"})
    )
    return issues.loc[mask].copy()


def sync_unit_from_issue_records(
    issue_csv_file: str | Path,
    serial_number: Any,
    *,
    clear_role: str = "Completed",
    state_file: str | Path | None = None,
    status_file: str | Path | None = None,
) -> str:
    """Recalculate a unit colour after an Issue lifecycle action.

    Any unresolved working Issue keeps the unit in the Issue role (normally
    red). If every remaining Issue is awaiting verification, the unit uses the
    Pending Verification role (normally yellow). When none remain, the caller's
    clear role is used, normally Completed (green).
    """

    serial = clean_text(serial_number)
    if not serial:
        return ""

    unresolved = unresolved_issue_rows(issue_csv_file, serial)
    if unresolved.empty:
        role = clear_role
    else:
        statuses = unresolved["Status"].astype(str).str.casefold()
        role = (
            "Pending Verification"
            if statuses.eq("pending verification").all()
            else "Issue"
        )

    base_directory = Path(issue_csv_file).resolve().parent
    effective_state_file = state_file or (base_directory / "map_unit_state.csv")
    effective_status_file = status_file or (base_directory / "map_status_definitions.csv")
    set_unit_workflow_role(
        serial,
        role,
        clear_manual_colour=True,
        state_file=effective_state_file,
        status_file=effective_status_file,
    )
    return role
