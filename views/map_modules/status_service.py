from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from services.csv_storage import atomic_write_csv
from utils.text_utils import clean_text


PLAN_REQUIRED_COLUMNS = [
    "Plan ID",
    "Plan Month",
    "Planned Date",
    "Serial Number",
    "Assigned To",
    "PM Status",
    "Completed Date",
    "Is Loaner",
    "Color Override",
    "Location Snapshot",
    "Postal Code Snapshot",
    "Latitude Snapshot",
    "Longitude Snapshot",
    "Created At",
]

STATUS_COLUMNS = [
    "Status ID",
    "Status Name",
    "Marker Color",
    "Active",
    "Display Order",
    "Workflow Role",
]

UNIT_STATE_COLUMNS = [
    "Serial Number",
    "Status",
    "Color Override",
    "Updated At",
]

COLOR_PALETTE = {
    "Blue": "#2563EB",
    "Green": "#16A34A",
    "Red": "#DC2626",
    "Orange": "#F97316",
    "Yellow": "#FACC15",
    "Purple": "#7C3AED",
    "Gray": "#6B7280",
    "Pink": "#DB2777",
    "Teal": "#0F766E",
    "Cyan": "#06B6D4",
    "Indigo": "#4338CA",
    "Lime": "#84CC16",
    "Brown": "#92400E",
    "Maroon": "#881337",
    "Black": "#111827",
}

COLOR_EMOJI = {
    "Blue": "🔵",
    "Green": "🟢",
    "Red": "🔴",
    "Orange": "🟠",
    "Yellow": "🟡",
    "Purple": "🟣",
    "Gray": "⚪",
    "Pink": "🌸",
    "Teal": "◆",
    "Cyan": "💠",
    "Indigo": "🔷",
    "Lime": "🟩",
    "Brown": "🟫",
    "Maroon": "♦",
    "Black": "⚫",
}

DEFAULT_STATUSES = [
    {
        "Status ID": "STATUS-001",
        "Status Name": "Pending",
        "Marker Color": "Blue",
        "Active": "Yes",
        "Display Order": "1",
        "Workflow Role": "Pending",
    },
    {
        "Status ID": "STATUS-002",
        "Status Name": "Completed",
        "Marker Color": "Green",
        "Active": "Yes",
        "Display Order": "2",
        "Workflow Role": "Completed",
    },
    {
        "Status ID": "STATUS-003",
        "Status Name": "Follow-up",
        "Marker Color": "Yellow",
        "Active": "Yes",
        "Display Order": "3",
        "Workflow Role": "None",
    },
    {
        "Status ID": "STATUS-004",
        "Status Name": "Special Case",
        "Marker Color": "Purple",
        "Active": "Yes",
        "Display Order": "4",
        "Workflow Role": "None",
    },
    {
        "Status ID": "STATUS-005",
        "Status Name": "Issue",
        "Marker Color": "Red",
        "Active": "Yes",
        "Display Order": "5",
        "Workflow Role": "Issue",
    },
    {
        "Status ID": "STATUS-006",
        "Status Name": "Overdue",
        "Marker Color": "Orange",
        "Active": "Yes",
        "Display Order": "6",
        "Workflow Role": "None",
    },
    {
        "Status ID": "STATUS-007",
        "Status Name": "Not Applicable",
        "Marker Color": "Gray",
        "Active": "Yes",
        "Display Order": "7",
        "Workflow Role": "None",
    },
    {
        "Status ID": "STATUS-008",
        "Status Name": "Pending Verification",
        "Marker Color": "Yellow",
        "Active": "Yes",
        "Display Order": "8",
        "Workflow Role": "Pending Verification",
    },
    {
        "Status ID": "STATUS-009",
        "Status Name": "Out of Service",
        "Marker Color": "Black",
        "Active": "Yes",
        "Display Order": "9",
        "Workflow Role": "Out of Service",
    },
]


def now_text() -> str:
    return datetime.now().astimezone().strftime("%d-%m-%Y %H:%M:%S")

def today_text() -> str:
    return date.today().strftime("%d-%m-%Y")

def yes_no(value: Any) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"

    return (
        "Yes"
        if clean_text(value).casefold() in {"yes", "true", "1", "y"}
        else "No"
    )

def safe_int(value: Any, fallback: int) -> int:
    try:
        return int(float(clean_text(value)))
    except (TypeError, ValueError):
        return fallback

def load_plan_records(plan_file: str | Path) -> pd.DataFrame:
    path = Path(plan_file)

    if not path.exists():
        return pd.DataFrame(columns=PLAN_REQUIRED_COLUMNS)

    try:
        dataframe = pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        ).fillna("")
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=PLAN_REQUIRED_COLUMNS)

    for column in PLAN_REQUIRED_COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = ""

    return dataframe

def save_plan_records(
    dataframe: pd.DataFrame,
    plan_file: str | Path,
) -> None:
    atomic_write_csv(
        dataframe.fillna(""),
        plan_file,
        preferred_columns=PLAN_REQUIRED_COLUMNS,
    )

def normalise_status_definitions(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    result = dataframe.copy()

    for column in STATUS_COLUMNS:
        if column not in result.columns:
            result[column] = ""

    result = result[STATUS_COLUMNS]

    for column in STATUS_COLUMNS:
        result[column] = (
            result[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    rows: list[dict[str, str]] = []

    for index, row in result.iterrows():
        name = clean_text(row["Status Name"])

        if not name:
            continue

        color = clean_text(row["Marker Color"]).title()
        if color not in COLOR_PALETTE:
            color = "Gray"

        workflow_role = clean_text(
            row["Workflow Role"]
        ).title()

        inferred_roles = {
            "pending": "Pending",
            "completed": "Completed",
            "issue": "Issue",
            "issue open": "Issue",
            "pending verification": "Pending Verification",
            "out of service": "Out of Service",
        }
        if workflow_role in {"", "None"}:
            workflow_role = inferred_roles.get(name.casefold(), "None")

        if workflow_role not in {
            "Pending",
            "Completed",
            "Issue",
            "Pending Verification",
            "Out Of Service",
            "Out of Service",
            "None",
        }:
            workflow_role = "None"
        if workflow_role == "Out Of Service":
            workflow_role = "Out of Service"

        rows.append(
            {
                "Status ID": clean_text(row["Status ID"]),
                "Status Name": name,
                "Marker Color": color,
                "Active": yes_no(row["Active"]),
                "Display Order": str(
                    safe_int(row["Display Order"], index + 1)
                ),
                "Workflow Role": workflow_role,
            }
        )

    normalised = pd.DataFrame(rows, columns=STATUS_COLUMNS)

    if normalised.empty:
        normalised = pd.DataFrame(
            DEFAULT_STATUSES,
            columns=STATUS_COLUMNS,
        )

    normalised["_Order"] = normalised[
        "Display Order"
    ].map(lambda value: safe_int(value, 9999))

    normalised = (
        normalised
        .sort_values(
            by=["_Order", "Status Name"],
            kind="stable",
        )
        .drop(columns="_Order")
        .reset_index(drop=True)
    )

    return normalised

def load_status_definitions(
    status_file: str | Path,
) -> pd.DataFrame:
    path = Path(status_file)

    if not path.exists():
        defaults = pd.DataFrame(
            DEFAULT_STATUSES,
            columns=STATUS_COLUMNS,
        )
        save_status_definitions(defaults, path)
        return defaults

    try:
        dataframe = pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        ).fillna("")
    except pd.errors.EmptyDataError:
        dataframe = pd.DataFrame(
            DEFAULT_STATUSES,
            columns=STATUS_COLUMNS,
        )

    result = normalise_status_definitions(dataframe)

    # Add any operational roles introduced by newer versions without removing
    # the user's existing names, colours or display order.
    existing_roles = {
        clean_text(value)
        for value in result.get("Workflow Role", pd.Series(dtype=str))
        if clean_text(value)
    }
    missing_defaults = [
        row for row in DEFAULT_STATUSES
        if clean_text(row["Workflow Role"]) in {
            "Pending", "Completed", "Issue", "Pending Verification", "Out of Service"
        }
        and clean_text(row["Workflow Role"]) not in existing_roles
    ]
    if missing_defaults:
        existing_ids = {
            clean_text(value)
            for value in result.get("Status ID", pd.Series(dtype=str))
            if clean_text(value)
        }
        additions = []
        id_source = result.copy()
        for default_row in missing_defaults:
            row = dict(default_row)
            candidate_id = next_status_id(id_source)
            while candidate_id in existing_ids:
                number = safe_int(candidate_id.split("-")[-1], 0) + 1
                candidate_id = f"STATUS-{number:03d}"
            row["Status ID"] = candidate_id
            existing_ids.add(candidate_id)
            additions.append(row)
            id_source = pd.concat(
                [id_source, pd.DataFrame([row], columns=STATUS_COLUMNS)],
                ignore_index=True,
            )
        result = pd.concat(
            [result, pd.DataFrame(additions, columns=STATUS_COLUMNS)],
            ignore_index=True,
        )
        result = normalise_status_definitions(result)

    save_status_definitions(result, path)
    return result

def save_status_definitions(
    dataframe: pd.DataFrame,
    status_file: str | Path,
) -> None:
    atomic_write_csv(
        normalise_status_definitions(dataframe),
        status_file,
        preferred_columns=STATUS_COLUMNS,
    )

def active_statuses(
    definitions: pd.DataFrame,
) -> pd.DataFrame:
    result = definitions[
        definitions["Active"].str.casefold().eq("yes")
    ].copy()

    result["_Order"] = result[
        "Display Order"
    ].map(lambda value: safe_int(value, 9999))

    return (
        result
        .sort_values(
            by=["_Order", "Status Name"],
            kind="stable",
        )
        .drop(columns="_Order")
        .reset_index(drop=True)
    )

def status_name_for_workflow_role(
    definitions: pd.DataFrame,
    workflow_role: str,
) -> str:
    matches = definitions[
        definitions["Workflow Role"]
        .str.casefold()
        .eq(workflow_role.casefold())
        &
        definitions["Active"]
        .str.casefold()
        .eq("yes")
    ]

    if matches.empty:
        return ""

    return clean_text(matches.iloc[0]["Status Name"])

def status_color_lookup(
    definitions: pd.DataFrame,
) -> dict[str, str]:
    return {
        clean_text(row["Status Name"]).casefold():
        clean_text(row["Marker Color"]).title()
        for _, row in definitions.iterrows()
        if clean_text(row["Status Name"])
    }

def next_status_id(definitions: pd.DataFrame) -> str:
    numbers: list[int] = []

    for value in definitions.get(
        "Status ID",
        pd.Series(dtype=str),
    ):
        text = clean_text(value)

        try:
            numbers.append(int(text.split("-")[-1]))
        except (ValueError, IndexError):
            continue

    next_number = max(numbers, default=0) + 1
    return f"STATUS-{next_number:03d}"

def load_unit_state(
    state_file: str | Path,
) -> pd.DataFrame:
    path = Path(state_file)

    if not path.exists():
        return pd.DataFrame(columns=UNIT_STATE_COLUMNS)

    try:
        dataframe = pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        ).fillna("")
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=UNIT_STATE_COLUMNS)

    for column in UNIT_STATE_COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = ""

    return dataframe[UNIT_STATE_COLUMNS]

def save_unit_state(
    dataframe: pd.DataFrame,
    state_file: str | Path,
) -> None:
    output = dataframe.copy()

    for column in UNIT_STATE_COLUMNS:
        if column not in output.columns:
            output[column] = ""

    atomic_write_csv(
        output[UNIT_STATE_COLUMNS].fillna(""),
        state_file,
        preferred_columns=UNIT_STATE_COLUMNS,
    )

def ensure_all_units_have_state(
    aed_dataframe: pd.DataFrame,
    state_dataframe: pd.DataFrame,
    definitions: pd.DataFrame,
    state_file: str | Path,
) -> pd.DataFrame:
    result = state_dataframe.copy()

    default_status = status_name_for_workflow_role(
        definitions,
        "Pending",
    )

    if not default_status:
        active = active_statuses(definitions)
        default_status = (
            clean_text(active.iloc[0]["Status Name"])
            if not active.empty
            else "Pending"
        )

    existing_serials = {
        clean_text(value).casefold()
        for value in result["Serial Number"]
        if clean_text(value)
    }

    new_rows = []

    for serial_value in aed_dataframe["Serial Number"]:
        serial = clean_text(serial_value)

        if not serial or serial.casefold() in existing_serials:
            continue

        new_rows.append(
            {
                "Serial Number": serial,
                "Status": default_status,
                "Color Override": "",
                "Updated At": now_text(),
            }
        )
        existing_serials.add(serial.casefold())

    if new_rows:
        result = pd.concat(
            [
                result,
                pd.DataFrame(
                    new_rows,
                    columns=UNIT_STATE_COLUMNS,
                ),
            ],
            ignore_index=True,
        )
        save_unit_state(result, state_file)

    return result

def used_status_counts(
    unit_state: pd.DataFrame,
    plan_records: pd.DataFrame,
) -> dict[str, int]:
    counts: dict[str, int] = {}

    for series in [
        unit_state.get("Status", pd.Series(dtype=str)),
        plan_records.get("PM Status", pd.Series(dtype=str)),
    ]:
        for value in series:
            name = clean_text(value)

            if not name:
                continue

            key = name.casefold()
            counts[key] = counts.get(key, 0) + 1

    return counts

def validate_and_prepare_status_editor(
    original: pd.DataFrame,
    edited: pd.DataFrame,
    unit_state: pd.DataFrame,
    plan_records: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    dict[str, str],
]:
    candidate = edited.copy()

    if "Status ID" not in candidate.columns:
        candidate["Status ID"] = ""

    candidate = candidate[
        [
            "Status ID",
            "Status Name",
            "Marker Color",
            "Active",
            "Display Order",
            "Workflow Role",
        ]
    ]

    # Remove completely blank rows created by the dynamic editor.
    candidate = candidate[
        candidate["Status Name"]
        .fillna("")
        .astype(str)
        .str.strip()
        .ne("")
    ].copy()

    if candidate.empty:
        raise ValueError(
            "At least one status must remain."
        )

    assigned_ids = set(
        clean_text(value)
        for value in original["Status ID"]
        if clean_text(value)
    )

    next_number_source = original.copy()

    for index in candidate.index:
        status_id = clean_text(
            candidate.at[index, "Status ID"]
        )

        if not status_id:
            status_id = next_status_id(next_number_source)

            while status_id in assigned_ids:
                numeric = safe_int(
                    status_id.split("-")[-1],
                    0,
                ) + 1
                status_id = f"STATUS-{numeric:03d}"

            candidate.at[index, "Status ID"] = status_id
            assigned_ids.add(status_id)

            next_number_source = pd.concat(
                [
                    next_number_source,
                    pd.DataFrame(
                        [
                            {
                                "Status ID": status_id,
                                "Status Name": "",
                                "Marker Color": "Gray",
                                "Active": "Yes",
                                "Display Order": "999",
                                "Workflow Role": "None",
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )

    candidate["Status Name"] = (
        candidate["Status Name"]
        .fillna("")
        .astype(str)
        .str.strip()
    )
    candidate["Marker Color"] = (
        candidate["Marker Color"]
        .fillna("")
        .astype(str)
        .str.title()
    )
    candidate["Active"] = candidate[
        "Active"
    ].map(yes_no)
    candidate["Display Order"] = candidate[
        "Display Order"
    ].map(
        lambda value: str(safe_int(value, 999))
    )
    candidate["Workflow Role"] = (
        candidate["Workflow Role"]
        .fillna("None")
        .astype(str)
        .str.title()
        .replace({"Out Of Service": "Out of Service"})
    )

    names_casefold = candidate[
        "Status Name"
    ].str.casefold()

    if names_casefold.duplicated().any():
        duplicated = candidate.loc[
            names_casefold.duplicated(keep=False),
            "Status Name",
        ].tolist()

        raise ValueError(
            "Status names must be unique: "
            + ", ".join(duplicated)
        )

    invalid_colors = sorted(
        set(candidate["Marker Color"])
        - set(COLOR_PALETTE)
    )

    if invalid_colors:
        raise ValueError(
            "Unsupported marker color: "
            + ", ".join(invalid_colors)
        )

    invalid_roles = sorted(
        set(candidate["Workflow Role"])
        - {
            "Pending",
            "Completed",
            "Issue",
            "Pending Verification",
            "Out of Service",
            "None",
        }
    )

    if invalid_roles:
        raise ValueError(
            "Unsupported workflow role: "
            + ", ".join(invalid_roles)
        )

    for required_role in [
        "Pending",
        "Completed",
        "Issue",
        "Pending Verification",
    ]:
        active_role_count = len(
            candidate[
                candidate["Workflow Role"].eq(required_role)
                &
                candidate["Active"].eq("Yes")
            ]
        )

        if active_role_count != 1:
            raise ValueError(
                f"Exactly one active status must have "
                f"Workflow Role = {required_role}."
            )

    original_by_id = {
        clean_text(row["Status ID"]): row
        for _, row in original.iterrows()
    }
    candidate_ids = set(
        clean_text(value)
        for value in candidate["Status ID"]
    )
    use_counts = used_status_counts(
        unit_state,
        plan_records,
    )

    for status_id, old_row in original_by_id.items():
        old_name = clean_text(old_row["Status Name"])
        old_used = use_counts.get(
            old_name.casefold(),
            0,
        )

        if status_id not in candidate_ids and old_used > 0:
            raise ValueError(
                f"'{old_name}' is used by {old_used} record(s). "
                "Move those units to another status before deleting it."
            )

    candidate_by_id = {
        clean_text(row["Status ID"]): row
        for _, row in candidate.iterrows()
    }

    for status_id, new_row in candidate_by_id.items():
        if status_id not in original_by_id:
            continue

        old_row = original_by_id[status_id]
        old_name = clean_text(old_row["Status Name"])
        old_used = use_counts.get(
            old_name.casefold(),
            0,
        )

        if (
            clean_text(new_row["Active"]) == "No"
            and old_used > 0
        ):
            raise ValueError(
                f"'{old_name}' is used by {old_used} record(s). "
                "Move those units before deactivating it."
            )

    rename_map: dict[str, str] = {}

    for status_id, new_row in candidate_by_id.items():
        old_row = original_by_id.get(status_id)

        if old_row is None:
            continue

        old_name = clean_text(old_row["Status Name"])
        new_name = clean_text(new_row["Status Name"])

        if old_name.casefold() != new_name.casefold():
            rename_map[old_name] = new_name

    return normalise_status_definitions(candidate), rename_map

def apply_status_renames(
    unit_state: pd.DataFrame,
    plan_records: pd.DataFrame,
    rename_map: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    updated_state = unit_state.copy()
    updated_plans = plan_records.copy()

    for old_name, new_name in rename_map.items():
        if "Status" in updated_state.columns:
            mask = (
                updated_state["Status"]
                .astype(str)
                .str.casefold()
                .eq(old_name.casefold())
            )
            updated_state.loc[mask, "Status"] = new_name
            updated_state.loc[mask, "Updated At"] = now_text()

        if "PM Status" in updated_plans.columns:
            mask = (
                updated_plans["PM Status"]
                .astype(str)
                .str.casefold()
                .eq(old_name.casefold())
            )
            updated_plans.loc[mask, "PM Status"] = new_name

    return updated_state, updated_plans
