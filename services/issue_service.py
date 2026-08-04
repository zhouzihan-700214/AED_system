from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
import uuid

import pandas as pd

from services.csv_storage import atomic_write_csv
from services.unit_color_service import set_unit_workflow_role, sync_unit_from_issue_records
from utils.text_utils import clean_text


ISSUE_STATUS_OPTIONS = [
    "Reported",
    "Assigned",
    "In Progress",
    "Pending Verification",
    "Reopened",
    "Closed",
]

PRIORITY_OPTIONS = ["Low", "Medium", "High", "Urgent"]
TEST_RESULT_OPTIONS = ["Pass", "Not Applicable"]


ALLOWED_STATUS_TRANSITIONS = {
    "Reported": {"Assigned"},
    "Assigned": {"Assigned", "In Progress"},
    "In Progress": {"Pending Verification"},
    "Pending Verification": {"Closed", "Reopened"},
    "Reopened": {"Assigned", "In Progress"},
    "Closed": set(),
}

ISSUE_RECORD_COLUMNS = [
    "Issue ID",
    "Reported At",
    "Source",
    "Source Record ID",
    "Source Field",
    "Source Value",
    "Reported By",
    "Technician",  # Kept for compatibility with older records.
    "Serial Number",
    "Model",
    "Location",
    "Postal Code",
    "Lift Lobby",
    "Is Loaner",
    "Issue Type",
    "Detailed Description",
    "Priority",
    "Status",
    "Reviewed By",
    "Reviewed At",
    "Review Notes",
    "Assigned By",
    "Current Assignee",
    "Due Date",
    "Assignment Notes",
    "Started By",
    "Started At",
    "Last Updated At",
    "Latest Submission ID",
    "Resolution Submitted By",
    "Resolution Submitted At",
    "Closed By",
    "Closed At",
    "Photo Paths",  # Kept so older pages/records remain readable.
    # Legacy workflow fields are retained during migration.
    "Noticed",
    "Noticed By",
    "Noticed At",
    "Assigned To",
    "Assigned At",
    "Resolved By",
    "Resolved At",
    "Resolution Notes",
]

ISSUE_HISTORY_COLUMNS = [
    "History ID",
    "Issue ID",
    "From Status",
    "To Status",
    "Action",
    "Action By",
    "Action At",
    "Comments",
]

RESOLUTION_SUBMISSION_COLUMNS = [
    "Submission ID",
    "Issue ID",
    "Attempt Number",
    "Submitted By",
    "Submitted At",
    "Action Taken",
    "Root Cause",
    "Parts Replaced",
    "Test Performed",
    "Test Result",
    "Resolution Notes",
    "Verification Result",
    "Verified By",
    "Verified At",
    "Verification Notes",
]

ISSUE_ATTACHMENT_COLUMNS = [
    "Attachment ID",
    "Issue ID",
    "Submission ID",
    "Stage",
    "File Name",
    "File Path",
    "Caption",
    "Uploaded By",
    "Uploaded At",
]


class IssueStorageError(RuntimeError):
    """Raised when Issue data cannot be read or written safely."""


def now_text() -> str:
    return datetime.now().astimezone().strftime("%d-%m-%Y %H:%M:%S")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"


def generate_issue_id() -> str:
    return _new_id("ISS")


def _normalise_status(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return "Reported"

    status_map = {
        "open": "Reported",
        "noticed": "Reported",
        "reviewed": "Reported",
        "reported": "Reported",
        "assigned": "Assigned",
        "in progress": "In Progress",
        "resolution submitted": "Pending Verification",
        "pending verification": "Pending Verification",
        "reopened": "Reopened",
        "resolved": "Closed",
        "closed": "Closed",
    }
    return status_map.get(text.casefold(), text)


def is_closed_status(value: Any) -> bool:
    return _normalise_status(value) == "Closed"


def validate_status_transition(
    current_status: Any,
    next_status: Any,
) -> None:
    """Reject workflow changes that are not part of the Issue lifecycle."""

    current = _normalise_status(current_status)
    target = _normalise_status(next_status)
    allowed = ALLOWED_STATUS_TRANSITIONS.get(current, set())

    if target not in allowed:
        raise ValueError(
            f"Issue status cannot change from '{current}' to '{target}'."
        )




def get_storage_paths(issue_csv_file: str | Path) -> dict[str, Path]:
    issue_path = Path(issue_csv_file)
    base_dir = issue_path.resolve().parent
    return {
        "issues": issue_path,
        "history": base_dir / "issue_history.csv",
        "submissions": base_dir / "issue_resolution_submissions.csv",
        "attachments": base_dir / "issue_attachments.csv",
        "photos": base_dir / "issue_photos",
    }


def _empty_dataframe(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _read_csv(path: Path, required_columns: list[str]) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return _empty_dataframe(required_columns)

    try:
        data = pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        ).fillna("")
    except pd.errors.EmptyDataError:
        return _empty_dataframe(required_columns)
    except Exception as error:
        raise IssueStorageError(f"Failed to read '{path.name}': {error}") from error

    for column in required_columns:
        if column not in data.columns:
            data[column] = ""
    return data


def _atomic_write_csv(
    dataframe: pd.DataFrame,
    path: Path,
    preferred_columns: list[str],
) -> None:
    try:
        atomic_write_csv(
            dataframe,
            path,
            preferred_columns=preferred_columns,
        )
    except Exception as error:
        raise IssueStorageError(
            f"Failed to write '{path.name}': {error}"
        ) from error


def ensure_issue_storage(issue_csv_file: str | Path) -> dict[str, Path]:
    paths = get_storage_paths(issue_csv_file)
    paths["photos"].mkdir(parents=True, exist_ok=True)

    storage_files = [
        (paths["issues"], ISSUE_RECORD_COLUMNS),
        (paths["history"], ISSUE_HISTORY_COLUMNS),
        (paths["submissions"], RESOLUTION_SUBMISSION_COLUMNS),
        (paths["attachments"], ISSUE_ATTACHMENT_COLUMNS),
    ]

    for path, columns in storage_files:
        if not path.exists() or path.stat().st_size <= 3:
            _atomic_write_csv(_empty_dataframe(columns), path, columns)
            continue

        try:
            raw = pd.read_csv(
                path,
                dtype=str,
                keep_default_na=False,
                encoding="utf-8-sig",
            ).fillna("")
        except pd.errors.EmptyDataError:
            raw = _empty_dataframe(columns)

        if any(column not in raw.columns for column in columns):
            for column in columns:
                if column not in raw.columns:
                    raw[column] = ""
            _atomic_write_csv(raw, path, columns)

    return paths


def load_issue_records(issue_csv_file: str | Path) -> pd.DataFrame:
    paths = ensure_issue_storage(issue_csv_file)
    records = _read_csv(paths["issues"], ISSUE_RECORD_COLUMNS)

    # Migrate older fields in memory without destroying their original values.
    reported_by_blank = records["Reported By"].astype(str).str.strip().eq("")
    records.loc[reported_by_blank, "Reported By"] = records.loc[
        reported_by_blank, "Technician"
    ]

    technician_blank = records["Technician"].astype(str).str.strip().eq("")
    records.loc[technician_blank, "Technician"] = records.loc[
        technician_blank, "Reported By"
    ]

    records["Status"] = records["Status"].map(_normalise_status)

    assignee_blank = records["Current Assignee"].astype(str).str.strip().eq("")
    records.loc[assignee_blank, "Current Assignee"] = records.loc[
        assignee_blank, "Assigned To"
    ]

    closed_by_blank = records["Closed By"].astype(str).str.strip().eq("")
    records.loc[closed_by_blank, "Closed By"] = records.loc[
        closed_by_blank, "Resolved By"
    ]

    closed_at_blank = records["Closed At"].astype(str).str.strip().eq("")
    records.loc[closed_at_blank, "Closed At"] = records.loc[
        closed_at_blank, "Resolved At"
    ]

    if "Priority" in records.columns:
        records["Priority"] = records["Priority"].replace("", "Not set")

    return records


def save_issue_records(
    dataframe: pd.DataFrame,
    issue_csv_file: str | Path,
) -> None:
    paths = ensure_issue_storage(issue_csv_file)
    _atomic_write_csv(dataframe, paths["issues"], ISSUE_RECORD_COLUMNS)


def load_issue_history(issue_csv_file: str | Path) -> pd.DataFrame:
    paths = ensure_issue_storage(issue_csv_file)
    return _read_csv(paths["history"], ISSUE_HISTORY_COLUMNS)


def load_resolution_submissions(issue_csv_file: str | Path) -> pd.DataFrame:
    paths = ensure_issue_storage(issue_csv_file)
    return _read_csv(paths["submissions"], RESOLUTION_SUBMISSION_COLUMNS)


def load_issue_attachments(issue_csv_file: str | Path) -> pd.DataFrame:
    paths = ensure_issue_storage(issue_csv_file)
    return _read_csv(paths["attachments"], ISSUE_ATTACHMENT_COLUMNS)


def _append_row(
    path: Path,
    columns: list[str],
    row: dict[str, Any],
) -> None:
    data = _read_csv(path, columns)
    new_row = pd.DataFrame(
        [[clean_text(row.get(column, "")) for column in columns]],
        columns=columns,
    )
    updated = pd.concat([data, new_row], ignore_index=True)
    _atomic_write_csv(updated, path, columns)


def append_issue_history(
    issue_csv_file: str | Path,
    *,
    issue_id: str,
    from_status: str,
    to_status: str,
    action: str,
    action_by: str,
    comments: str = "",
) -> None:
    paths = ensure_issue_storage(issue_csv_file)
    _append_row(
        paths["history"],
        ISSUE_HISTORY_COLUMNS,
        {
            "History ID": _new_id("HIS"),
            "Issue ID": issue_id,
            "From Status": from_status,
            "To Status": to_status,
            "Action": action,
            "Action By": action_by,
            "Action At": now_text(),
            "Comments": comments,
        },
    )


def _safe_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return suffix if suffix in {".jpg", ".jpeg", ".png"} else ""


def save_issue_attachments(
    issue_csv_file: str | Path,
    *,
    issue_id: str,
    uploaded_files: Iterable[Any],
    stage: str,
    uploaded_by: str,
    submission_id: str = "",
    caption_prefix: str = "",
    folder_name: str = "",
) -> list[str]:
    paths = ensure_issue_storage(issue_csv_file)
    stage_folder_name = (
        clean_text(folder_name).casefold().replace(" ", "_")
        or clean_text(stage).casefold().replace(" ", "_")
        or "other"
    )
    destination_folder = paths["photos"] / issue_id / stage_folder_name
    destination_folder.mkdir(parents=True, exist_ok=True)

    attachments = load_issue_attachments(issue_csv_file)
    saved_relative_paths: list[str] = []
    uploaded_at = now_text()

    for index, uploaded_file in enumerate(uploaded_files, start=1):
        original_name = clean_text(getattr(uploaded_file, "name", ""))
        suffix = _safe_suffix(original_name)
        if not suffix:
            continue

        filename = f"{stage_folder_name}_{index:02d}_{uuid.uuid4().hex[:6]}{suffix}"
        destination = destination_folder / filename

        try:
            buffer = uploaded_file.getbuffer()
            destination.write_bytes(bytes(buffer))
        except Exception as error:
            raise IssueStorageError(
                f"Failed to save photo '{original_name or filename}': {error}"
            ) from error

        relative_path = destination.relative_to(paths["issues"].resolve().parent)
        relative_text = relative_path.as_posix()
        saved_relative_paths.append(relative_text)

        attachment_row = {
            "Attachment ID": _new_id("ATT"),
            "Issue ID": issue_id,
            "Submission ID": submission_id,
            "Stage": stage,
            "File Name": original_name or filename,
            "File Path": relative_text,
            "Caption": (
                f"{caption_prefix} {index}".strip()
                if caption_prefix
                else original_name
            ),
            "Uploaded By": uploaded_by,
            "Uploaded At": uploaded_at,
        }
        new_attachment = pd.DataFrame(
            [[attachment_row.get(column, "") for column in ISSUE_ATTACHMENT_COLUMNS]],
            columns=ISSUE_ATTACHMENT_COLUMNS,
        )
        attachments = pd.concat([attachments, new_attachment], ignore_index=True)

    if saved_relative_paths:
        _atomic_write_csv(
            attachments,
            paths["attachments"],
            ISSUE_ATTACHMENT_COLUMNS,
        )

    return saved_relative_paths


def _existing_source_issue_id(
    issue_csv_file: str | Path,
    *,
    source: str,
    source_record_id: str,
    source_field: str,
) -> str:
    """Return an existing Issue created from the same source event/field."""

    record_id = clean_text(source_record_id)
    field = clean_text(source_field)
    if not record_id or not field:
        return ""
    records = load_issue_records(issue_csv_file)
    if records.empty:
        return ""
    mask = (
        records["Source"].astype(str).str.strip().str.casefold().eq(clean_text(source).casefold())
        & records["Source Record ID"].astype(str).str.strip().eq(record_id)
        & records["Source Field"].astype(str).str.strip().str.casefold().eq(field.casefold())
    )
    matches = records.loc[mask, "Issue ID"].astype(str).str.strip()
    return clean_text(matches.iloc[0]) if not matches.empty else ""


def create_issue(
    issue_csv_file: str | Path,
    *,
    issue_data: dict[str, Any],
    uploaded_files: Iterable[Any] = (),
) -> str:
    reported_by = clean_text(issue_data.get("Reported By"))
    issue_types = clean_text(issue_data.get("Issue Type"))

    if not reported_by:
        raise ValueError("Reported By is required.")
    if not issue_types:
        raise ValueError("At least one Issue Type is required.")

    priority = clean_text(issue_data.get("Priority")) or "Medium"
    if priority not in PRIORITY_OPTIONS:
        raise ValueError("Please select a valid Priority.")

    source = clean_text(issue_data.get("Source"))
    source_record_id = clean_text(issue_data.get("Source Record ID"))
    source_field = clean_text(issue_data.get("Source Field"))
    existing_issue_id = _existing_source_issue_id(
        issue_csv_file,
        source=source,
        source_record_id=source_record_id,
        source_field=source_field,
    )
    if existing_issue_id:
        return existing_issue_id

    issue_id = generate_issue_id()
    reported_at = now_text()

    saved_photo_paths = save_issue_attachments(
        issue_csv_file,
        issue_id=issue_id,
        uploaded_files=uploaded_files,
        stage="Report",
        uploaded_by=reported_by,
        caption_prefix="Report evidence",
    )

    records = load_issue_records(issue_csv_file)
    record = {
        "Issue ID": issue_id,
        "Reported At": reported_at,
        "Source": source,
        "Source Record ID": source_record_id,
        "Source Field": source_field,
        "Source Value": clean_text(issue_data.get("Source Value")),
        "Reported By": reported_by,
        "Technician": reported_by,
        "Serial Number": clean_text(issue_data.get("Serial Number")),
        "Model": clean_text(issue_data.get("Model")),
        "Location": clean_text(issue_data.get("Location")),
        "Postal Code": clean_text(issue_data.get("Postal Code")),
        "Lift Lobby": clean_text(issue_data.get("Lift Lobby")),
        "Is Loaner": clean_text(issue_data.get("Is Loaner")) or "No",
        "Issue Type": issue_types,
        "Detailed Description": clean_text(issue_data.get("Detailed Description")),
        "Priority": priority,
        "Status": "Reported",
        "Reviewed By": "",
        "Reviewed At": "",
        "Review Notes": "",
        "Assigned By": "",
        "Current Assignee": "",
        "Due Date": "",
        "Assignment Notes": "",
        "Started By": "",
        "Started At": "",
        "Last Updated At": reported_at,
        "Closed By": "",
        "Closed At": "",
        "Photo Paths": "; ".join(saved_photo_paths),
        "Noticed": "No",
        "Noticed By": "",
        "Noticed At": "",
        "Assigned To": "",
        "Assigned At": "",
        "Resolved By": "",
        "Resolved At": "",
        "Resolution Notes": "",
    }

    new_record = pd.DataFrame(
        [[record.get(column, "") for column in ISSUE_RECORD_COLUMNS]],
        columns=ISSUE_RECORD_COLUMNS,
    )
    records = pd.concat([new_record, records], ignore_index=True)
    save_issue_records(records, issue_csv_file)

    append_issue_history(
        issue_csv_file,
        issue_id=issue_id,
        from_status="",
        to_status="Reported",
        action="Issue reported",
        action_by=reported_by,
        comments=clean_text(issue_data.get("Detailed Description")),
    )

    # Marker state is system-only and never written into the company Excel.
    issue_base = Path(issue_csv_file).resolve().parent
    set_unit_workflow_role(
        record.get("Serial Number", ""),
        "Issue",
        state_file=issue_base / "map_unit_state.csv",
        status_file=issue_base / "map_status_definitions.csv",
    )
    return issue_id



def _find_issue_index(records: pd.DataFrame, issue_id: str) -> int:
    clean_issue_id = clean_text(issue_id)
    if not clean_issue_id:
        raise ValueError("Issue ID is required.")

    matches = records.index[
        records["Issue ID"].astype(str).str.strip().eq(clean_issue_id)
    ].tolist()
    if not matches:
        raise ValueError(f"Issue '{clean_issue_id}' could not be found.")
    return int(matches[0])


def get_issue_record(
    issue_csv_file: str | Path,
    issue_id: str,
) -> pd.Series:
    records = load_issue_records(issue_csv_file)
    row_index = _find_issue_index(records, issue_id)
    return records.loc[row_index].copy()


def assign_issue(
    issue_csv_file: str | Path,
    *,
    issue_id: str,
    reviewed_by: str,
    assigned_to: str,
    due_date: Any = "",
    review_notes: str = "",
    assignment_notes: str = "",
) -> None:
    reviewer = clean_text(reviewed_by)
    assignee = clean_text(assigned_to)
    if not reviewer:
        raise ValueError("Reviewed / Assigned By is required.")
    if not assignee:
        raise ValueError("Assigned To is required.")

    records = load_issue_records(issue_csv_file)
    row_index = _find_issue_index(records, issue_id)
    current_status = _normalise_status(records.at[row_index, "Status"])
    validate_status_transition(current_status, "Assigned")

    timestamp = now_text()
    due_date_text = clean_text(due_date)
    records.at[row_index, "Status"] = "Assigned"
    records.at[row_index, "Reviewed By"] = reviewer
    records.at[row_index, "Reviewed At"] = timestamp
    records.at[row_index, "Review Notes"] = clean_text(review_notes)
    records.at[row_index, "Assigned By"] = reviewer
    records.at[row_index, "Current Assignee"] = assignee
    records.at[row_index, "Due Date"] = due_date_text
    records.at[row_index, "Assignment Notes"] = clean_text(assignment_notes)
    records.at[row_index, "Last Updated At"] = timestamp

    # Keep legacy columns synchronized while the project is transitioning.
    records.at[row_index, "Noticed"] = "Yes"
    records.at[row_index, "Noticed By"] = reviewer
    records.at[row_index, "Noticed At"] = timestamp
    records.at[row_index, "Assigned To"] = assignee
    records.at[row_index, "Assigned At"] = timestamp

    save_issue_records(records, issue_csv_file)

    comments = []
    if clean_text(review_notes):
        comments.append(f"Review: {clean_text(review_notes)}")
    comments.append(f"Assigned to: {assignee}")
    if due_date_text:
        comments.append(f"Due date: {due_date_text}")
    if clean_text(assignment_notes):
        comments.append(f"Assignment: {clean_text(assignment_notes)}")

    append_issue_history(
        issue_csv_file,
        issue_id=clean_text(issue_id),
        from_status=current_status,
        to_status="Assigned",
        action=(
            "Issue reviewed and assigned"
            if current_status == "Reported"
            else "Issue reassigned"
        ),
        action_by=reviewer,
        comments="\n".join(comments),
    )


def start_issue_work(
    issue_csv_file: str | Path,
    *,
    issue_id: str,
    started_by: str,
    work_notes: str = "",
) -> None:
    worker = clean_text(started_by)
    if not worker:
        raise ValueError("Started By is required.")

    records = load_issue_records(issue_csv_file)
    row_index = _find_issue_index(records, issue_id)
    current_status = _normalise_status(records.at[row_index, "Status"])
    validate_status_transition(current_status, "In Progress")

    timestamp = now_text()
    records.at[row_index, "Status"] = "In Progress"
    records.at[row_index, "Started By"] = worker
    records.at[row_index, "Started At"] = timestamp
    records.at[row_index, "Last Updated At"] = timestamp
    if not clean_text(records.at[row_index, "Current Assignee"]):
        records.at[row_index, "Current Assignee"] = worker
        records.at[row_index, "Assigned To"] = worker

    save_issue_records(records, issue_csv_file)
    append_issue_history(
        issue_csv_file,
        issue_id=clean_text(issue_id),
        from_status=current_status,
        to_status="In Progress",
        action="Work started",
        action_by=worker,
        comments=clean_text(work_notes),
    )


def add_issue_progress_update(
    issue_csv_file: str | Path,
    *,
    issue_id: str,
    updated_by: str,
    progress_notes: str,
) -> None:
    actor = clean_text(updated_by)
    notes = clean_text(progress_notes)
    if not actor:
        raise ValueError("Updated By is required.")
    if not notes:
        raise ValueError("Progress Notes are required.")

    records = load_issue_records(issue_csv_file)
    row_index = _find_issue_index(records, issue_id)
    current_status = _normalise_status(records.at[row_index, "Status"])
    if current_status != "In Progress":
        raise ValueError("Progress updates can only be added while work is In Progress.")

    records.at[row_index, "Last Updated At"] = now_text()
    save_issue_records(records, issue_csv_file)
    append_issue_history(
        issue_csv_file,
        issue_id=clean_text(issue_id),
        from_status=current_status,
        to_status=current_status,
        action="Progress update",
        action_by=actor,
        comments=notes,
    )


def submit_issue_resolution(
    issue_csv_file: str | Path,
    *,
    issue_id: str,
    submitted_by: str,
    action_taken: str,
    test_performed: str,
    test_result: str,
    resolution_notes: str,
    uploaded_files: Iterable[Any],
    root_cause: str = "",
    parts_replaced: str = "",
) -> str:
    """Submit completion details and evidence for administrator verification."""

    actor = clean_text(submitted_by)
    action = clean_text(action_taken)
    test = clean_text(test_performed)
    result = clean_text(test_result)
    notes = clean_text(resolution_notes)
    uploads = list(uploaded_files or [])
    valid_uploads = [
        uploaded_file
        for uploaded_file in uploads
        if _safe_suffix(clean_text(getattr(uploaded_file, "name", "")))
    ]

    if not actor:
        raise ValueError("Submitted By is required.")
    if not action:
        raise ValueError("Action Taken is required.")
    if not test:
        raise ValueError("Test Performed is required.")
    if result not in TEST_RESULT_OPTIONS:
        raise ValueError("Please select a valid Test Result.")
    if not notes:
        raise ValueError("Resolution Notes are required.")
    if not valid_uploads:
        raise ValueError(
            "Upload at least one JPG, JPEG, or PNG completion photo."
        )

    records = load_issue_records(issue_csv_file)
    row_index = _find_issue_index(records, issue_id)
    current_status = _normalise_status(records.at[row_index, "Status"])
    validate_status_transition(current_status, "Pending Verification")

    submissions = load_resolution_submissions(issue_csv_file)
    issue_submissions = submissions[
        submissions["Issue ID"].astype(str).str.strip().eq(clean_text(issue_id))
    ]
    attempt_number = len(issue_submissions) + 1
    submission_id = _new_id("SUB")
    submitted_at = now_text()

    saved_photo_paths = save_issue_attachments(
        issue_csv_file,
        issue_id=clean_text(issue_id),
        uploaded_files=valid_uploads,
        stage="Resolution",
        uploaded_by=actor,
        submission_id=submission_id,
        caption_prefix=f"Resolution attempt {attempt_number}",
        folder_name=f"resolution_{attempt_number}",
    )
    if not saved_photo_paths:
        raise IssueStorageError("No valid completion photo could be saved.")

    _append_row(
        ensure_issue_storage(issue_csv_file)["submissions"],
        RESOLUTION_SUBMISSION_COLUMNS,
        {
            "Submission ID": submission_id,
            "Issue ID": clean_text(issue_id),
            "Attempt Number": str(attempt_number),
            "Submitted By": actor,
            "Submitted At": submitted_at,
            "Action Taken": action,
            "Root Cause": clean_text(root_cause),
            "Parts Replaced": clean_text(parts_replaced),
            "Test Performed": test,
            "Test Result": result,
            "Resolution Notes": notes,
            "Verification Result": "Pending",
            "Verified By": "",
            "Verified At": "",
            "Verification Notes": "",
        },
    )

    records.at[row_index, "Status"] = "Pending Verification"
    records.at[row_index, "Latest Submission ID"] = submission_id
    records.at[row_index, "Resolution Submitted By"] = actor
    records.at[row_index, "Resolution Submitted At"] = submitted_at
    records.at[row_index, "Last Updated At"] = submitted_at
    save_issue_records(records, issue_csv_file)

    history_comments = [
        f"Attempt: {attempt_number}",
        f"Action taken: {action}",
        f"Test result: {result}",
        f"Completion photos: {len(saved_photo_paths)}",
        f"Resolution notes: {notes}",
    ]
    if clean_text(root_cause):
        history_comments.insert(2, f"Root cause: {clean_text(root_cause)}")
    if clean_text(parts_replaced):
        history_comments.insert(3, f"Parts replaced: {clean_text(parts_replaced)}")

    append_issue_history(
        issue_csv_file,
        issue_id=clean_text(issue_id),
        from_status=current_status,
        to_status="Pending Verification",
        action="Resolution submitted for verification",
        action_by=actor,
        comments="\n".join(history_comments),
    )

    sync_unit_from_issue_records(
        issue_csv_file,
        records.at[row_index, "Serial Number"],
    )
    return submission_id



def verify_issue_resolution(
    issue_csv_file: str | Path,
    *,
    issue_id: str,
    verified_by: str,
    verification_notes: str,
    approve: bool,
) -> None:
    """Approve the latest resolution and close the Issue, or reject and reopen it."""

    verifier = clean_text(verified_by)
    notes = clean_text(verification_notes)
    if not verifier:
        raise ValueError("Verified By is required.")
    if not notes:
        if approve:
            raise ValueError(
                "Verification Notes are required to record why the resolution was approved."
            )
        raise ValueError("A rejection reason is required before reopening the Issue.")

    records = load_issue_records(issue_csv_file)
    row_index = _find_issue_index(records, issue_id)
    current_status = _normalise_status(records.at[row_index, "Status"])

    submission_id = clean_text(records.at[row_index, "Latest Submission ID"])
    if not submission_id:
        raise ValueError("No submitted resolution is linked to this Issue.")

    paths = ensure_issue_storage(issue_csv_file)
    submissions = load_resolution_submissions(issue_csv_file)
    matches = submissions.index[
        submissions["Submission ID"].astype(str).str.strip().eq(submission_id)
        & submissions["Issue ID"].astype(str).str.strip().eq(clean_text(issue_id))
    ].tolist()
    if not matches:
        raise ValueError(
            f"Resolution submission '{submission_id}' could not be found."
        )

    submission_index = int(matches[0])
    existing_result = clean_text(
        submissions.at[submission_index, "Verification Result"]
    )
    if existing_result and existing_result.casefold() not in {"pending", ""}:
        raise ValueError(
            f"Resolution submission '{submission_id}' has already been verified."
        )

    verified_at = now_text()
    decision = "Approved" if approve else "Rejected"
    next_status = "Closed" if approve else "Reopened"
    validate_status_transition(current_status, next_status)

    submissions.at[submission_index, "Verification Result"] = decision
    submissions.at[submission_index, "Verified By"] = verifier
    submissions.at[submission_index, "Verified At"] = verified_at
    submissions.at[submission_index, "Verification Notes"] = notes

    records.at[row_index, "Status"] = next_status
    records.at[row_index, "Last Updated At"] = verified_at

    if approve:
        records.at[row_index, "Closed By"] = verifier
        records.at[row_index, "Closed At"] = verified_at
        # Keep legacy fields aligned for pages that still read them.
        records.at[row_index, "Resolved By"] = verifier
        records.at[row_index, "Resolved At"] = verified_at
        records.at[row_index, "Resolution Notes"] = clean_text(
            submissions.at[submission_index, "Resolution Notes"]
        )
    else:
        # A rejected submission remains in history, while the Issue returns to work.
        records.at[row_index, "Closed By"] = ""
        records.at[row_index, "Closed At"] = ""
        records.at[row_index, "Resolved By"] = ""
        records.at[row_index, "Resolved At"] = ""

    _atomic_write_csv(
        submissions,
        paths["submissions"],
        RESOLUTION_SUBMISSION_COLUMNS,
    )
    save_issue_records(records, issue_csv_file)

    attempt_number = clean_text(
        submissions.at[submission_index, "Attempt Number"]
    ) or "—"
    action = (
        "Resolution approved and Issue closed"
        if approve
        else "Resolution rejected and Issue reopened"
    )
    append_issue_history(
        issue_csv_file,
        issue_id=clean_text(issue_id),
        from_status=current_status,
        to_status=next_status,
        action=action,
        action_by=verifier,
        comments=(
            f"Resolution attempt: {attempt_number}\n"
            f"Submission ID: {submission_id}\n"
            f"Verification decision: {decision}\n"
            f"Verification notes: {notes}"
        ),
    )

    sync_unit_from_issue_records(
        issue_csv_file,
        records.at[row_index, "Serial Number"],
    )

def get_resolution_submissions_for_issue(
    issue_csv_file: str | Path,
    issue_id: str,
) -> pd.DataFrame:
    submissions = load_resolution_submissions(issue_csv_file)
    if submissions.empty:
        return submissions

    result = submissions[
        submissions["Issue ID"].astype(str).str.strip().eq(clean_text(issue_id))
    ].copy()
    if result.empty:
        return result

    result["_attempt_sort"] = pd.to_numeric(
        result["Attempt Number"], errors="coerce"
    ).fillna(0)
    result = result.sort_values(
        ["_attempt_sort", "Submitted At"],
        ascending=[False, False],
        kind="stable",
    ).drop(columns=["_attempt_sort"])
    return result.reset_index(drop=True)

def get_open_issue_count(issue_csv_file: str | Path) -> int:
    try:
        records = load_issue_records(issue_csv_file)
    except Exception:
        return 0

    if records.empty:
        return 0
    return int((~records["Status"].map(is_closed_status)).sum())


def get_history_for_issue(
    issue_csv_file: str | Path,
    issue_id: str,
) -> pd.DataFrame:
    history = load_issue_history(issue_csv_file)
    if history.empty:
        return history

    result = history[
        history["Issue ID"].astype(str).eq(str(issue_id))
    ].copy()
    return result.iloc[::-1].reset_index(drop=True)


def get_attachments_for_issue(
    issue_csv_file: str | Path,
    issue_id: str,
    stage: str | None = None,
) -> pd.DataFrame:
    attachments = load_issue_attachments(issue_csv_file)
    if attachments.empty:
        return attachments

    result = attachments[
        attachments["Issue ID"].astype(str).eq(str(issue_id))
    ].copy()
    if stage:
        result = result[
            result["Stage"].astype(str).str.casefold().eq(stage.casefold())
        ]
    return result.reset_index(drop=True)


def resolve_attachment_path(
    issue_csv_file: str | Path,
    saved_path: str | Path,
) -> Path:
    path = Path(saved_path)
    if path.is_absolute():
        return path
    return Path(issue_csv_file).resolve().parent / path
