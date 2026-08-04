from __future__ import annotations

from datetime import date, datetime
from html import escape
from pathlib import Path
import math
import re

import pandas as pd
import streamlit as st

from services.issue_service import (
    add_issue_progress_update,
    assign_issue,
    get_attachments_for_issue,
    get_history_for_issue,
    get_open_issue_count,
    get_resolution_submissions_for_issue,
    is_closed_status,
    load_issue_records,
    load_resolution_submissions,
    resolve_attachment_path,
    start_issue_work,
    submit_issue_resolution,
    verify_issue_resolution,
    TEST_RESULT_OPTIONS,
)

from ui.components import page_header
from utils.text_utils import clean_text


STATUS_HELP = {
    "Reported": "The Issue has been submitted and is waiting for review and assignment.",
    "Assigned": "A person has been assigned to handle the Issue.",
    "In Progress": "Work has started and progress updates can be recorded.",
    "Pending Verification": (
        "Resolution details and evidence were submitted and are waiting for review."
    ),
    "Reopened": "Verification failed or more work is required.",
    "Closed": "The submitted resolution was verified and approved.",
}


def _safe_key(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", clean_text(value)) or "issue"


def _parse_due_date(value: object) -> date | None:
    text = clean_text(value)
    if not text:
        return None

    for date_format in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    return None


def _legacy_photo_paths(
    photo_paths_text: str,
    issue_csv_file: str | Path,
) -> list[Path]:
    paths: list[Path] = []
    for item in clean_text(photo_paths_text).split(";"):
        item = clean_text(item)
        if item:
            paths.append(resolve_attachment_path(issue_csv_file, item))
    return paths


def _render_evidence(
    row: pd.Series,
    issue_csv_file: str | Path,
) -> None:
    issue_id = clean_text(row.get("Issue ID"))
    attachments = get_attachments_for_issue(issue_csv_file, issue_id)

    evidence: list[tuple[Path, str, str]] = []
    if not attachments.empty:
        for _, attachment in attachments.iterrows():
            path = resolve_attachment_path(
                issue_csv_file,
                clean_text(attachment.get("File Path")),
            )
            evidence.append(
                (
                    path,
                    clean_text(attachment.get("Caption")) or path.name,
                    clean_text(attachment.get("Stage")) or "Evidence",
                )
            )
    else:
        for path in _legacy_photo_paths(
            clean_text(row.get("Photo Paths")), issue_csv_file
        ):
            evidence.append((path, path.name, "Legacy Report"))

    if not evidence:
        st.caption("No photos were uploaded.")
        return

    visible = [item for item in evidence if item[0].exists()]
    if visible:
        columns = st.columns(min(len(visible), 3))
        for index, (path, caption, stage) in enumerate(visible):
            with columns[index % len(columns)]:
                st.image(
                    str(path),
                    caption=f"{stage}: {caption}",
                    width="stretch",
                )

    missing = [path.name for path, _, _ in evidence if not path.exists()]
    if missing:
        st.warning(
            "These saved photo files could not be found: " + ", ".join(missing)
        )


def _render_history(issue_id: str, issue_csv_file: str | Path) -> None:
    history = get_history_for_issue(issue_csv_file, issue_id)
    if history.empty:
        st.caption(
            "No structured activity history is available for this legacy Issue."
        )
        return

    history = history.copy()
    history["_SortAt"] = history["Action At"].map(_parse_datetime)
    history = history.sort_values("_SortAt", ascending=False, na_position="last")

    for _, event in history.iterrows():
        action = clean_text(event.get("Action")) or "Updated"
        action_at = _format_datetime(event.get("Action At"))
        actor = clean_text(event.get("Action By")) or "Unknown"
        from_status = clean_text(event.get("From Status"))
        to_status = clean_text(event.get("To Status"))
        comments = clean_text(event.get("Comments"))
        transition = ""
        if from_status or to_status:
            transition = f"{from_status or '—'} → {to_status or '—'}"

        transition_html = f" · {escape(transition)}" if transition else ""
        comments_html = f"<p>{escape(comments)}</p>" if comments else ""
        st.markdown(
            f"""
            <div class="issue-activity-item">
                <div class="issue-activity-marker">•</div>
                <div class="issue-activity-body">
                    <strong>{escape(action)}</strong>
                    <span>{escape(action_at)} · By {escape(actor)}{transition_html}</span>
                    {comments_html}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_resolution_submissions(
    issue_id: str,
    issue_csv_file: str | Path,
) -> None:
    submissions = get_resolution_submissions_for_issue(
        issue_csv_file,
        issue_id,
    )
    if submissions.empty:
        st.caption("No resolution has been submitted yet.")
        return

    for _, submission in submissions.iterrows():
        attempt = clean_text(submission.get("Attempt Number")) or "—"
        submitted_by = clean_text(submission.get("Submitted By")) or "—"
        submitted_at = clean_text(submission.get("Submitted At")) or "—"
        verification = (
            clean_text(submission.get("Verification Result")) or "Pending"
        )

        with st.container(border=True):
            header_left, header_right = st.columns([3, 1])
            with header_left:
                st.markdown(f"**Resolution Attempt {attempt}**")
                st.caption(f"Submitted by {submitted_by} at {submitted_at}")
            with header_right:
                st.markdown(f"**Verification:** {verification}")

            st.markdown("**Action Taken**")
            st.write(clean_text(submission.get("Action Taken")) or "—")

            root_cause = clean_text(submission.get("Root Cause"))
            parts_replaced = clean_text(submission.get("Parts Replaced"))
            if root_cause:
                st.markdown(f"**Root Cause:** {root_cause}")
            if parts_replaced:
                st.markdown(f"**Parts Replaced:** {parts_replaced}")

            test_left, test_right = st.columns([3, 1])
            with test_left:
                st.markdown("**Test Performed**")
                st.write(clean_text(submission.get("Test Performed")) or "—")
            with test_right:
                st.markdown(
                    "**Test Result:** "
                    + (clean_text(submission.get("Test Result")) or "—")
                )

            st.markdown("**Resolution Notes**")
            st.write(clean_text(submission.get("Resolution Notes")) or "—")

            verification_notes = clean_text(
                submission.get("Verification Notes")
            )
            verified_by = clean_text(submission.get("Verified By"))
            verified_at = clean_text(submission.get("Verified At"))
            if verification_notes or verified_by or verified_at:
                st.markdown("**Verification Details**")
                st.write(
                    f"Verified By: {verified_by or '—'} | "
                    f"Verified At: {verified_at or '—'}"
                )
                if verification_notes:
                    st.write(verification_notes)

def build_issue_copy_text(row: pd.Series) -> str:
    lines = [
        "AED ISSUE REPORT",
        f"Issue ID: {clean_text(row.get('Issue ID')) or '—'}",
        f"Status: {clean_text(row.get('Status')) or 'Reported'}",
        f"Reported At: {clean_text(row.get('Reported At')) or '—'}",
        f"Reported By: {clean_text(row.get('Reported By')) or clean_text(row.get('Technician')) or '—'}",
        f"Source: {clean_text(row.get('Source')) or 'Report Issue'}",
        f"Source Record ID: {clean_text(row.get('Source Record ID')) or '—'}",
        f"Source Field: {clean_text(row.get('Source Field')) or '—'}",
        f"Source Value: {clean_text(row.get('Source Value')) or '—'}",
        "",
        "AED INFORMATION",
        f"Serial Number: {clean_text(row.get('Serial Number')) or '—'}",
        f"Model: {clean_text(row.get('Model')) or '—'}",
        f"Location: {clean_text(row.get('Location')) or '—'}",
        f"Postal Code: {clean_text(row.get('Postal Code')) or '—'}",
        f"Lift Lobby: {clean_text(row.get('Lift Lobby')) or '—'}",
        f"Loaner Unit: {clean_text(row.get('Is Loaner')) or 'No'}",
        "",
        "ISSUE DETAILS",
        f"Issue Type: {clean_text(row.get('Issue Type')) or '—'}",
        f"Description: {clean_text(row.get('Detailed Description')) or '—'}",
        "",
        "REVIEW AND ASSIGNMENT",
        f"Reviewed By: {clean_text(row.get('Reviewed By')) or '—'}",
        f"Current Assignee: {clean_text(row.get('Current Assignee')) or '—'}",
        f"Due Date: {clean_text(row.get('Due Date')) or '—'}",
        f"Started By: {clean_text(row.get('Started By')) or '—'}",
        f"Started At: {clean_text(row.get('Started At')) or '—'}",
    ]
    return "\n".join(lines)


def _show_action_success() -> None:
    message = st.session_state.pop("issue_action_success_message", "")
    if message:
        st.success(message)


def _save_success(message: str) -> None:
    st.session_state["issue_action_success_message"] = message
    st.rerun()


def _render_assignment_form(
    row: pd.Series,
    issue_csv_file: str | Path,
    *,
    key_prefix: str,
    title: str,
) -> None:
    issue_id = clean_text(row.get("Issue ID"))
    existing_due_date = _parse_due_date(row.get("Due Date"))
    current_assignee = clean_text(row.get("Current Assignee"))

    st.subheader(title)
    st.caption(
        "The reviewer records the decision and assigns responsibility. "
        "The reviewer and assignee may be different people."
    )

    with st.form(f"{key_prefix}_assignment_form"):
        left, right = st.columns(2)
        with left:
            reviewed_by = st.text_input(
                "Reviewed / Assigned By *",
                key=f"{key_prefix}_reviewed_by",
                help="The administrator or supervisor who reviewed and assigned the Issue.",
            )
            assigned_to = st.text_input(
                "Assigned To *",
                value=current_assignee,
                key=f"{key_prefix}_assigned_to",
                help="The person responsible for carrying out the work.",
            )
        with right:
            set_due_date = st.checkbox(
                "Set a due date",
                value=existing_due_date is not None,
                key=f"{key_prefix}_set_due_date",
            )
            due_date_value = st.date_input(
                "Due Date",
                value=existing_due_date or date.today(),
                disabled=not set_due_date,
                key=f"{key_prefix}_due_date",
            )

        review_notes = st.text_area(
            "Review Notes",
            value=clean_text(row.get("Review Notes")),
            placeholder="Confirm what was reviewed and any important observations.",
            key=f"{key_prefix}_review_notes",
        )
        assignment_notes = st.text_area(
            "Assignment Instructions",
            value=clean_text(row.get("Assignment Notes")),
            placeholder="Describe what the assignee should check, repair, or prepare.",
            key=f"{key_prefix}_assignment_notes",
        )

        submitted = st.form_submit_button(
            "Save Assignment",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return

    try:
        assign_issue(
            issue_csv_file,
            issue_id=issue_id,
            reviewed_by=reviewed_by,
            assigned_to=assigned_to,
            due_date=due_date_value.isoformat() if set_due_date else "",
            review_notes=review_notes,
            assignment_notes=assignment_notes,
        )
    except Exception as error:
        st.error(f"Failed to save the assignment: {error}")
        return

    _save_success(f"{issue_id} was assigned to {clean_text(assigned_to)}.")


def _render_start_work_form(
    row: pd.Series,
    issue_csv_file: str | Path,
    *,
    key_prefix: str,
) -> None:
    issue_id = clean_text(row.get("Issue ID"))
    current_assignee = clean_text(row.get("Current Assignee"))

    st.subheader("Start Work")
    st.caption(
        "Starting work changes the Issue to In Progress and records who began the work."
    )

    with st.form(f"{key_prefix}_start_work_form"):
        started_by = st.text_input(
            "Started By *",
            value=current_assignee,
            key=f"{key_prefix}_started_by",
        )
        work_notes = st.text_area(
            "Starting Notes",
            placeholder="Optional: record the initial inspection or planned action.",
            key=f"{key_prefix}_starting_notes",
        )
        submitted = st.form_submit_button(
            "Start Work",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return

    try:
        start_issue_work(
            issue_csv_file,
            issue_id=issue_id,
            started_by=started_by,
            work_notes=work_notes,
        )
    except Exception as error:
        st.error(f"Failed to start work: {error}")
        return

    _save_success(f"Work on {issue_id} is now In Progress.")


def _render_progress_update_form(
    row: pd.Series,
    issue_csv_file: str | Path,
    *,
    key_prefix: str,
) -> None:
    issue_id = clean_text(row.get("Issue ID"))
    default_actor = (
        clean_text(row.get("Current Assignee"))
        or clean_text(row.get("Started By"))
    )

    st.subheader("Add Progress Update")
    st.caption(
        "Use progress updates for site findings, parts required, delays, and work completed so far."
    )

    with st.form(f"{key_prefix}_progress_form"):
        updated_by = st.text_input(
            "Updated By *",
            value=default_actor,
            key=f"{key_prefix}_progress_by",
        )
        progress_notes = st.text_area(
            "Progress Notes *",
            placeholder=(
                "Example: Reached site, confirmed cabinet alarm fault, and requested a replacement switch."
            ),
            height=130,
            key=f"{key_prefix}_progress_notes",
        )
        submitted = st.form_submit_button(
            "Save Progress Update",
            width="stretch",
        )

    if not submitted:
        return

    try:
        add_issue_progress_update(
            issue_csv_file,
            issue_id=issue_id,
            updated_by=updated_by,
            progress_notes=progress_notes,
        )
    except Exception as error:
        st.error(f"Failed to save the progress update: {error}")
        return

    _save_success(f"Progress was added to {issue_id}.")



def _render_resolution_submission_form(
    row: pd.Series,
    issue_csv_file: str | Path,
    *,
    key_prefix: str,
) -> None:
    issue_id = clean_text(row.get("Issue ID"))
    default_actor = (
        clean_text(row.get("Current Assignee"))
        or clean_text(row.get("Started By"))
    )

    st.subheader("Submit Resolution")
    st.caption(
        "Submit what was done, how the result was tested, and completion photos. "
        "This does not close the Issue; it sends the Issue for verification."
    )

    with st.form(f"{key_prefix}_resolution_form", clear_on_submit=False):
        submitted_by = st.text_input(
            "Submitted By *",
            value=default_actor,
            key=f"{key_prefix}_resolution_by",
        )
        action_taken = st.text_area(
            "Action Taken *",
            placeholder=(
                "Describe the repair, replacement, correction, or other action completed."
            ),
            height=120,
            key=f"{key_prefix}_action_taken",
        )

        detail_left, detail_right = st.columns(2)
        with detail_left:
            root_cause = st.text_area(
                "Root Cause (optional)",
                placeholder="Describe the confirmed cause, if known.",
                key=f"{key_prefix}_root_cause",
            )
        with detail_right:
            parts_replaced = st.text_area(
                "Parts Replaced (optional)",
                placeholder="List replaced parts, or leave blank.",
                key=f"{key_prefix}_parts_replaced",
            )

        test_performed = st.text_area(
            "Test Performed *",
            placeholder=(
                "Describe how you checked that the Issue was resolved, including the test steps."
            ),
            height=110,
            key=f"{key_prefix}_test_performed",
        )
        test_result = st.selectbox(
            "Test Result *",
            options=TEST_RESULT_OPTIONS,
            key=f"{key_prefix}_test_result",
            help=(
                "Choose Pass when the functional check succeeded. Choose Not Applicable "
                "only when no functional test applies, and explain why in the notes."
            ),
        )
        resolution_notes = st.text_area(
            "Resolution Notes *",
            placeholder=(
                "Summarise the final condition and any follow-up, monitoring, or limitation."
            ),
            height=120,
            key=f"{key_prefix}_resolution_notes",
        )
        completion_photos = st.file_uploader(
            "Completion Photos *",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key=f"{key_prefix}_completion_photos",
            help=(
                "Upload at least one clear photo showing the repaired area, final condition, "
                "or test evidence."
            ),
        )
        resolution_confirmed = st.checkbox(
            "I confirm this resolution is ready for verification. The unit marker will change to the Pending Verification colour.",
            key=f"{key_prefix}_resolution_confirmed",
        )

        submitted = st.form_submit_button(
            "Submit for Verification",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return
    if not resolution_confirmed:
        st.error("Confirm the resolution and resulting marker status before submitting.")
        return

    try:
        submission_id = submit_issue_resolution(
            issue_csv_file,
            issue_id=issue_id,
            submitted_by=submitted_by,
            action_taken=action_taken,
            root_cause=root_cause,
            parts_replaced=parts_replaced,
            test_performed=test_performed,
            test_result=test_result,
            resolution_notes=resolution_notes,
            uploaded_files=completion_photos or [],
        )
    except Exception as error:
        st.error(f"Failed to submit the resolution: {error}")
        return

    _save_success(
        f"Resolution {submission_id} was submitted. {issue_id} is now Pending Verification and the unit marker follows that colour."
    )


def _render_verification_form(
    row: pd.Series,
    issue_csv_file: str | Path,
    *,
    key_prefix: str,
) -> None:
    issue_id = clean_text(row.get("Issue ID"))
    latest_submission_id = clean_text(row.get("Latest Submission ID"))
    submissions = get_resolution_submissions_for_issue(
        issue_csv_file,
        issue_id,
    )

    if submissions.empty or not latest_submission_id:
        st.error(
            "This Issue is Pending Verification, but no linked resolution submission "
            "could be found."
        )
        return

    matching = submissions.loc[
        submissions["Submission ID"]
        .astype(str)
        .str.strip()
        .eq(latest_submission_id)
    ]
    if matching.empty:
        st.error(
            f"The latest resolution submission ({latest_submission_id}) could not be found."
        )
        return

    submission = matching.iloc[0]
    submitted_by = clean_text(submission.get("Submitted By")) or "—"
    attempt = clean_text(submission.get("Attempt Number")) or "—"

    st.subheader("Verify Submitted Resolution")
    st.caption(
        "Review the work description, test result, and completion photos. "
        "Approval closes the Issue; rejection returns it for more work."
    )

    with st.container(border=True):
        st.markdown(
            f"**Resolution Attempt {attempt}** · "
            f"Submitted by {submitted_by} · "
            f"{clean_text(submission.get('Submitted At')) or 'Unknown time'}"
        )
        st.markdown("**Action Taken**")
        st.write(clean_text(submission.get("Action Taken")) or "—")

        detail_left, detail_right = st.columns(2)
        with detail_left:
            st.markdown("**Test Performed**")
            st.write(clean_text(submission.get("Test Performed")) or "—")
        with detail_right:
            st.markdown("**Test Result**")
            st.write(clean_text(submission.get("Test Result")) or "—")

        st.markdown("**Resolution Notes**")
        st.write(clean_text(submission.get("Resolution Notes")) or "—")

        attachments = get_attachments_for_issue(issue_csv_file, issue_id)
        if not attachments.empty:
            attachments = attachments.loc[
                attachments["Submission ID"]
                .astype(str)
                .str.strip()
                .eq(latest_submission_id)
            ]

        if attachments.empty:
            st.error(
                "No completion photo is linked to this resolution submission. "
                "Do not approve it until the evidence problem is corrected."
            )
        else:
            st.markdown("**Completion Photos**")
            valid_photos: list[tuple[Path, str]] = []
            missing_names: list[str] = []
            for _, attachment in attachments.iterrows():
                photo_path = resolve_attachment_path(
                    issue_csv_file,
                    clean_text(attachment.get("File Path")),
                )
                if photo_path.exists():
                    valid_photos.append(
                        (
                            photo_path,
                            clean_text(attachment.get("Caption")) or photo_path.name,
                        )
                    )
                else:
                    missing_names.append(photo_path.name)

            if valid_photos:
                photo_columns = st.columns(min(len(valid_photos), 3))
                for index, (photo_path, caption) in enumerate(valid_photos):
                    with photo_columns[index % len(photo_columns)]:
                        st.image(
                            str(photo_path),
                            caption=caption,
                            width="stretch",
                        )
            if missing_names:
                st.warning(
                    "Some saved completion photos could not be found: "
                    + ", ".join(missing_names)
                )

    with st.form(f"{key_prefix}_verification_form"):
        verified_by = st.text_input(
            "Verified By *",
            key=f"{key_prefix}_verified_by",
            help="The administrator or supervisor making the final decision.",
        )
        decision = st.radio(
            "Verification Decision *",
            options=["Approve and Close", "Reject and Reopen"],
            key=f"{key_prefix}_verification_decision",
            help=(
                "Approve only when the written result and photos provide sufficient "
                "evidence. Reject when more work, clearer evidence, or another test is needed."
            ),
        )
        verification_notes = st.text_area(
            "Verification Notes / Rejection Reason *",
            placeholder=(
                "State what was checked and why the submission is accepted, or explain "
                "exactly what must be corrected before resubmission."
            ),
            height=130,
            key=f"{key_prefix}_verification_notes",
        )
        evidence_confirmed = st.checkbox(
            "I reviewed the resolution details, test result, and completion photos.",
            key=f"{key_prefix}_evidence_confirmed",
        )
        submitted = st.form_submit_button(
            "Save Verification Decision",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return
    if not evidence_confirmed:
        st.error("Confirm that the submitted evidence was reviewed.")
        return

    verifier = clean_text(verified_by)
    if verifier and verifier.casefold() == submitted_by.casefold():
        st.warning(
            "The verifier is the same person who submitted the resolution. "
            "Independent verification is recommended where possible."
        )

    approve = decision == "Approve and Close"
    try:
        verify_issue_resolution(
            issue_csv_file,
            issue_id=issue_id,
            verified_by=verified_by,
            verification_notes=verification_notes,
            approve=approve,
        )
    except Exception as error:
        st.error(f"Failed to save the verification decision: {error}")
        return

    if approve:
        _save_success(
            f"{issue_id} was verified and closed. The unit marker was recalculated from all remaining Issues."
        )
    else:
        _save_success(
            f"{issue_id} was rejected and reopened for additional work."
        )

def _render_actions(
    row: pd.Series,
    issue_csv_file: str | Path,
    *,
    key_prefix: str,
) -> None:
    status = clean_text(row.get("Status")) or "Reported"

    if status == "Reported":
        _render_assignment_form(
            row,
            issue_csv_file,
            key_prefix=key_prefix,
            title="Review and Assign",
        )
        return

    if status == "Assigned":
        _render_start_work_form(
            row,
            issue_csv_file,
            key_prefix=key_prefix,
        )
        with st.expander("Update or change the assignment"):
            _render_assignment_form(
                row,
                issue_csv_file,
                key_prefix=f"{key_prefix}_reassign",
                title="Update Assignment",
            )
        return

    if status == "Reopened":
        st.warning(
            "This Issue was reopened. The existing assignee may continue the work, "
            "or an administrator may assign it to someone else."
        )
        _render_start_work_form(
            row,
            issue_csv_file,
            key_prefix=f"{key_prefix}_restart",
        )
        with st.expander("Review and reassign"):
            _render_assignment_form(
                row,
                issue_csv_file,
                key_prefix=f"{key_prefix}_reassign",
                title="Review and Reassign",
            )
        return

    if status == "In Progress":
        _render_progress_update_form(
            row,
            issue_csv_file,
            key_prefix=key_prefix,
        )
        st.divider()
        _render_resolution_submission_form(
            row,
            issue_csv_file,
            key_prefix=key_prefix,
        )
        return

    if status == "Pending Verification":
        _render_verification_form(
            row,
            issue_csv_file,
            key_prefix=key_prefix,
        )
        return

    if status == "Closed":
        st.success("This Issue is closed. No further action is required.")
        return

    st.warning(f"No action form is configured for status: {status}")


ISSUE_FILTER_KEYS = [
    "issue_filter_search",
    "issue_filter_month",
    "issue_filter_type",
    "issue_filter_status",
    "issue_filter_reported_by",
    "issue_filter_assigned_by",
    "issue_filter_assigned_to",
    "issue_filter_started_by",
    "issue_filter_resolution_by",
    "issue_filter_verified_by",
    "issue_filter_date_type",
    "issue_filter_from_date",
    "issue_filter_to_date",
]

DATE_FILTER_COLUMNS = {
    "Reported Date": "Reported At",
    "Assigned Date": "_Assigned Date",
    "Started Date": "Started At",
    "Resolution Submitted Date": "Resolution Submitted At",
    "Closed Date": "Closed At",
    "Last Updated Date": "Last Updated At",
}

UNRESOLVED_STATUSES = {"Reported", "Assigned", "In Progress", "Reopened"}


def _apply_issue_page_styles() -> None:
    st.markdown(
        """
        <style>
        .issue-summary-line {
            display: flex; align-items: center; justify-content: space-between;
            gap: 1rem; margin: 0.25rem 0 0.65rem;
            color: var(--text-secondary); font-size: 0.78rem;
        }
        .issue-summary-line strong { color: var(--text-primary); }
        .issue-list-card { min-width: 0; padding: 0.1rem 0; }
        .issue-list-topline {
            display: flex; align-items: center; justify-content: space-between;
            gap: 0.7rem; margin-bottom: 0.24rem;
        }
        .issue-list-date {
            color: var(--text-tertiary); font-size: 0.7rem; font-weight: 700;
        }
        .issue-list-card h4 {
            margin: 0.05rem 0 0.18rem; color: var(--text-primary);
            font-size: 0.98rem; line-height: 1.25; overflow-wrap: anywhere;
        }
        .issue-list-card p {
            margin: 0.1rem 0; color: var(--text-secondary);
            font-size: 0.74rem; line-height: 1.42; overflow-wrap: anywhere;
        }
        .issue-list-card .issue-list-people {
            margin-top: 0.42rem; color: var(--text-tertiary); font-size: 0.69rem;
        }
        .issue-status-badge {
            flex: 0 0 auto; display: inline-flex; align-items: center;
            min-height: 24px; padding: 0.22rem 0.48rem;
            border: 1px solid var(--border); border-radius: 999px;
            background: var(--surface-subtle); color: var(--text-secondary);
            font-size: 0.65rem; font-weight: 760; white-space: nowrap;
        }
        .issue-status-reported { color: #175cd3; background: #eff8ff; border-color: #b2ddff; }
        .issue-status-assigned { color: #b54708; background: #fffaeb; border-color: #fedf89; }
        .issue-status-progress { color: #175cd3; background: #eff8ff; border-color: #b2ddff; }
        .issue-status-verification { color: #027a48; background: #ecfdf3; border-color: #abefc6; }
        .issue-status-reopened { color: #6941c6; background: #f4f3ff; border-color: #d9d6fe; }
        .issue-status-closed { color: #475467; background: #f2f4f7; border-color: #d0d5dd; }
        .issue-workspace-header { padding: 0.2rem 0 0.35rem; }
        .issue-workspace-id {
            color: var(--primary); font-size: 0.68rem;
            font-weight: 800; letter-spacing: 0.08em;
        }
        .issue-workspace-header h2 {
            margin: 0.26rem 0 0.22rem; font-size: clamp(1.35rem, 2.4vw, 1.85rem);
            line-height: 1.15; overflow-wrap: anywhere;
        }
        .issue-workspace-header p {
            margin: 0.08rem 0; color: var(--text-secondary);
            font-size: 0.8rem; line-height: 1.45; overflow-wrap: anywhere;
        }
        .issue-next-action {
            min-height: 126px; display: flex; flex-direction: column;
            justify-content: center; padding: 0.9rem;
            border: 1px solid var(--border); border-left: 4px solid var(--primary);
            border-radius: 9px; background: var(--surface-subtle);
        }
        .issue-next-action span {
            color: var(--text-tertiary); font-size: 0.66rem;
            font-weight: 800; letter-spacing: 0.1em;
        }
        .issue-next-action strong {
            display: block; margin-top: 0.28rem; color: var(--text-primary);
            font-size: 0.94rem; line-height: 1.35;
        }
        .issue-detail-card {
            min-width: 0; min-height: 285px; padding: 0.95rem;
            border: 1px solid var(--border); border-radius: 9px;
            background: var(--surface);
        }
        .issue-detail-card h4 { margin: 0 0 0.7rem; font-size: 0.88rem; }
        .issue-detail-list { border-top: 1px solid var(--border); }
        .issue-detail-row {
            display: grid; grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.25fr);
            gap: 0.55rem; padding: 0.48rem 0; border-bottom: 1px solid #edf0f4;
        }
        .issue-detail-row span { color: var(--text-tertiary); font-size: 0.69rem; }
        .issue-detail-row strong {
            color: var(--text-primary); font-size: 0.72rem; font-weight: 680;
            line-height: 1.4; text-align: right; overflow-wrap: anywhere;
        }
        .issue-activity-item {
            display: flex; gap: 0.72rem; padding: 0.78rem 0.1rem;
            border-bottom: 1px solid #edf0f4;
        }
        .issue-activity-marker {
            flex: 0 0 auto; width: 28px; height: 28px;
            display: grid; place-items: center; border-radius: 999px;
            background: var(--primary-soft); color: var(--primary);
            font-size: 1rem; line-height: 1;
        }
        .issue-activity-body { min-width: 0; }
        .issue-activity-body strong {
            display: block; color: var(--text-primary); font-size: 0.8rem;
        }
        .issue-activity-body span {
            display: block; margin-top: 0.12rem;
            color: var(--text-secondary); font-size: 0.69rem;
        }
        .issue-activity-body p {
            margin: 0.35rem 0 0; color: var(--text-secondary);
            font-size: 0.74rem; white-space: pre-wrap;
        }
        @media (max-width: 980px) { .issue-detail-card { min-height: 0; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _parse_datetime(value: object) -> pd.Timestamp | None:
    text = clean_text(value)
    if not text:
        return None
    for date_format in (
        "%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d",
    ):
        try:
            return pd.Timestamp(datetime.strptime(text, date_format))
        except ValueError:
            continue
    try:
        parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    except Exception:
        return None
    return None if pd.isna(parsed) else pd.Timestamp(parsed)


def _format_datetime(value: object) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        return clean_text(value) or "—"
    if parsed.hour == 0 and parsed.minute == 0 and parsed.second == 0:
        return parsed.strftime("%d %b %Y")
    return parsed.strftime("%d %b %Y · %H:%M")


def _format_list_datetime(value: object) -> tuple[str, str]:
    parsed = _parse_datetime(value)
    if parsed is None:
        return clean_text(value) or "Unknown date", ""
    return parsed.strftime("%d %b %Y"), parsed.strftime("%H:%M")


def _status_class(status: object) -> str:
    return {
        "Reported": "reported", "Assigned": "assigned",
        "In Progress": "progress", "Pending Verification": "verification",
        "Reopened": "reopened", "Closed": "closed",
    }.get(clean_text(status), "closed")


def _next_action_label(status: object) -> str:
    return {
        "Reported": "Review and Assign",
        "Assigned": "Start Work",
        "In Progress": "Update Progress or Submit Resolution",
        "Reopened": "Continue Work or Reassign",
        "Pending Verification": "Verify Resolution",
        "Closed": "No Further Action",
    }.get(clean_text(status), "Review Issue")


def _unique_values(dataframe: pd.DataFrame, column: str) -> list[str]:
    if column not in dataframe.columns or dataframe.empty:
        return []
    values = {clean_text(value) for value in dataframe[column].tolist() if clean_text(value)}
    return sorted(values, key=str.casefold)


def _combined_unique_values(dataframe: pd.DataFrame, columns: list[str]) -> list[str]:
    values: set[str] = set()
    for column in columns:
        values.update(_unique_values(dataframe, column))
    return sorted(values, key=str.casefold)


def _enrich_issue_records(records: pd.DataFrame, issue_csv_file: str | Path) -> pd.DataFrame:
    enriched = records.copy()
    for column in ("_Verified By", "_Verified At", "_Assigned Date"):
        enriched[column] = ""

    reviewed_at = enriched["Reviewed At"].astype(str).str.strip()
    assigned_at = enriched["Assigned At"].astype(str).str.strip()
    enriched["_Assigned Date"] = reviewed_at.where(reviewed_at.ne(""), assigned_at)

    try:
        submissions = load_resolution_submissions(issue_csv_file)
    except Exception:
        submissions = pd.DataFrame()

    if submissions.empty:
        enriched["_Verified By"] = enriched["Closed By"]
        enriched["_Verified At"] = enriched["Closed At"]
        return enriched

    verified_by_map: dict[str, str] = {}
    verified_at_map: dict[str, str] = {}
    for issue_id, group in submissions.groupby("Issue ID", dropna=False):
        people = [clean_text(value) for value in group["Verified By"].tolist() if clean_text(value)]
        verified_by_map[clean_text(issue_id)] = "; ".join(dict.fromkeys(people))
        dated = []
        for value in group["Verified At"].tolist():
            parsed = _parse_datetime(value)
            if parsed is not None:
                dated.append((parsed, clean_text(value)))
        if dated:
            verified_at_map[clean_text(issue_id)] = max(dated, key=lambda item: item[0])[1]

    issue_ids = enriched["Issue ID"].astype(str).str.strip()
    enriched["_Verified By"] = issue_ids.map(verified_by_map).fillna("")
    enriched["_Verified At"] = issue_ids.map(verified_at_map).fillna("")
    enriched["_Verified By"] = enriched["_Verified By"].where(
        enriched["_Verified By"].astype(str).str.strip().ne(""), enriched["Closed By"]
    )
    enriched["_Verified At"] = enriched["_Verified At"].where(
        enriched["_Verified At"].astype(str).str.strip().ne(""), enriched["Closed At"]
    )
    return enriched


def _month_options(records: pd.DataFrame) -> list[str]:
    months: set[pd.Period] = set()
    for value in records["Reported At"].tolist():
        parsed = _parse_datetime(value)
        if parsed is not None:
            months.add(parsed.to_period("M"))
    return [period.strftime("%B %Y") for period in sorted(months, reverse=True)]


def _person_matches(value: object, selected_person: str) -> bool:
    if not selected_person or selected_person.startswith("All "):
        return True
    people = {clean_text(item).casefold() for item in clean_text(value).split(";") if clean_text(item)}
    return selected_person.casefold() in people


def _filter_issue_records(
    records: pd.DataFrame, *, search_text: str, selected_month: str,
    issue_type: str, status_filter: str, reported_by: str,
    assigned_by: str, assigned_to: str, started_by: str,
    resolution_by: str, verified_by: str, date_type: str,
    from_date: date | None, to_date: date | None,
) -> pd.DataFrame:
    filtered = records.copy()
    query = clean_text(search_text).casefold()
    if query:
        search_columns = [
            "Issue ID", "Serial Number", "Model", "Location", "Postal Code",
            "Issue Type", "Detailed Description", "Reported By", "Assigned By",
            "Current Assignee", "Started By", "Resolution Submitted By", "_Verified By",
        ]
        search_mask = pd.Series(False, index=filtered.index)
        for column in search_columns:
            search_mask |= filtered[column].astype(str).str.casefold().str.contains(
                query, regex=False, na=False
            )
        filtered = filtered.loc[search_mask]

    if selected_month != "All Months":
        def month_label(value: object) -> str:
            parsed = _parse_datetime(value)
            return parsed.strftime("%B %Y") if parsed is not None else ""
        filtered = filtered.loc[filtered["Reported At"].map(month_label).eq(selected_month)]

    if issue_type != "All Issue Types":
        filtered = filtered.loc[filtered["Issue Type"].astype(str).str.strip().eq(issue_type)]

    if status_filter == "Unresolved":
        filtered = filtered.loc[filtered["Status"].isin(UNRESOLVED_STATUSES)]
    elif status_filter != "All Statuses":
        filtered = filtered.loc[filtered["Status"].astype(str).str.strip().eq(status_filter)]

    for column, selected_person in [
        ("Reported By", reported_by), ("Assigned By", assigned_by),
        ("Current Assignee", assigned_to), ("Started By", started_by),
        ("Resolution Submitted By", resolution_by), ("_Verified By", verified_by),
    ]:
        if not selected_person.startswith("All "):
            filtered = filtered.loc[
                filtered[column].map(lambda value: _person_matches(value, selected_person))
            ]

    date_column = DATE_FILTER_COLUMNS.get(date_type, "Reported At")
    if from_date is not None or to_date is not None:
        date_values = filtered[date_column].map(_parse_datetime)
        date_mask = pd.Series(True, index=filtered.index)
        if from_date is not None:
            date_mask &= date_values.map(lambda value: value is not None and value.date() >= from_date)
        if to_date is not None:
            date_mask &= date_values.map(lambda value: value is not None and value.date() <= to_date)
        filtered = filtered.loc[date_mask]

    filtered = filtered.copy()
    filtered["_Reported Sort"] = filtered["Reported At"].map(_parse_datetime)
    return filtered.sort_values(
        ["_Reported Sort", "Issue ID"], ascending=[False, False],
        na_position="last", kind="stable",
    ).drop(columns=["_Reported Sort"])


def _reset_issue_filters() -> None:
    for key in ISSUE_FILTER_KEYS:
        st.session_state.pop(key, None)
    st.session_state.pop("issue_selected_id", None)
    st.session_state.pop("issue_action_open_id", None)
    st.session_state["issue_list_page"] = 1


def _render_issue_filters(records: pd.DataFrame) -> pd.DataFrame:
    month_options = ["All Months", *_month_options(records)]
    type_options = ["All Issue Types", *_unique_values(records, "Issue Type")]
    lifecycle_order = ["Reported", "Assigned", "In Progress", "Pending Verification", "Reopened", "Closed"]
    existing_statuses = set(_unique_values(records, "Status"))
    status_options = ["All Statuses", "Unresolved"] + [s for s in lifecycle_order if s in existing_statuses]

    with st.container(border=True):
        row_one = st.columns([1.35, 1, 1, 1])
        with row_one[0]:
            search_text = st.text_input(
                "Search", placeholder="Issue ID / Serial / Location / Description / Person",
                key="issue_filter_search",
            )
        with row_one[1]:
            selected_month = st.selectbox(
                "Filter by Month (Reported Date)", month_options, key="issue_filter_month"
            )
        with row_one[2]:
            issue_type = st.selectbox("Issue Type", type_options, key="issue_filter_type")
        with row_one[3]:
            status_filter = st.selectbox("Issue Status", status_options, key="issue_filter_status")

        row_two = st.columns(3)
        with row_two[0]:
            reported_by = st.selectbox(
                "Reported By", ["All Reporters", *_unique_values(records, "Reported By")],
                key="issue_filter_reported_by",
            )
        with row_two[1]:
            assigned_by = st.selectbox(
                "Assigned By", ["All Assigners", *_unique_values(records, "Assigned By")],
                key="issue_filter_assigned_by",
            )
        with row_two[2]:
            assigned_to = st.selectbox(
                "Assigned To", ["All Assignees", *_unique_values(records, "Current Assignee")],
                key="issue_filter_assigned_to",
            )

        row_three = st.columns(3)
        with row_three[0]:
            started_by = st.selectbox(
                "Started By", ["All Starters", *_unique_values(records, "Started By")],
                key="issue_filter_started_by",
            )
        with row_three[1]:
            resolution_by = st.selectbox(
                "Resolution Submitted By",
                ["All Resolution Submitters", *_unique_values(records, "Resolution Submitted By")],
                key="issue_filter_resolution_by",
            )
        with row_three[2]:
            verified_by = st.selectbox(
                "Verified / Closed By",
                ["All Verifiers", *_combined_unique_values(records, ["_Verified By", "Closed By"])],
                key="issue_filter_verified_by",
            )

        with st.expander("Custom Date Filter"):
            date_row = st.columns([1.1, 1, 1])
            with date_row[0]:
                date_type = st.selectbox(
                    "Date Type", list(DATE_FILTER_COLUMNS), key="issue_filter_date_type"
                )
            with date_row[1]:
                from_date = st.date_input(
                    "From Date", value=None, key="issue_filter_from_date", format="DD/MM/YYYY"
                )
            with date_row[2]:
                to_date = st.date_input(
                    "To Date", value=None, key="issue_filter_to_date", format="DD/MM/YYYY"
                )

        reset_col, note_col = st.columns([1, 4])
        with reset_col:
            if st.button("Reset Filters", key="issue_filter_reset", width="stretch"):
                _reset_issue_filters()
                st.rerun()
        with note_col:
            st.caption(
                "The list always stays sorted by Reported At, newest first. "
                "Filters narrow the records but never change the sort order."
            )

    if from_date is not None and to_date is not None and from_date > to_date:
        st.error("From Date cannot be later than To Date.")
        return records.iloc[0:0].copy()

    return _filter_issue_records(
        records, search_text=search_text, selected_month=selected_month,
        issue_type=issue_type, status_filter=status_filter,
        reported_by=reported_by, assigned_by=assigned_by, assigned_to=assigned_to,
        started_by=started_by, resolution_by=resolution_by, verified_by=verified_by,
        date_type=date_type, from_date=from_date, to_date=to_date,
    )


def _render_issue_list_item(row: pd.Series, *, selected: bool) -> None:
    issue_id = clean_text(row.get("Issue ID"))
    status = clean_text(row.get("Status")) or "Reported"
    issue_type = clean_text(row.get("Issue Type")) or "Issue"
    serial = clean_text(row.get("Serial Number")) or "No serial number"
    location = clean_text(row.get("Location")) or "No location"
    reported_by = clean_text(row.get("Reported By")) or clean_text(row.get("Technician"))
    assigned_to = clean_text(row.get("Current Assignee"))
    submitted_by = clean_text(row.get("Resolution Submitted By"))
    closed_by = clean_text(row.get("Closed By")) or clean_text(row.get("_Verified By"))
    date_label, time_label = _format_list_datetime(row.get("Reported At"))

    people_parts = []
    if reported_by:
        people_parts.append(f"Reported by {reported_by}")
    if assigned_to:
        people_parts.append(f"Assigned to {assigned_to}")
    if submitted_by:
        people_parts.append(f"Resolution by {submitted_by}")
    if closed_by:
        people_parts.append(f"Closed by {closed_by}")

    with st.container(border=True):
        st.markdown(
            f"""
            <div class="issue-list-card">
                <div class="issue-list-topline">
                    <span class="issue-list-date">{escape(date_label)}{f' · {escape(time_label)}' if time_label else ''}</span>
                    <span class="issue-status-badge issue-status-{_status_class(status)}">{escape(status)}</span>
                </div>
                <h4>{escape(issue_type)}</h4>
                <p><strong>{escape(serial)}</strong> · {escape(location)}</p>
                <p class="issue-list-people">{escape(' · '.join(people_parts)) if people_parts else 'No responsibility details recorded'}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button(
            "Selected" if selected else "Open Issue",
            key=f"issue_select_{_safe_key(issue_id)}",
            type="primary" if selected else "secondary",
            width="stretch", disabled=selected,
        ):
            st.session_state["issue_selected_id"] = issue_id
            st.session_state.pop("issue_action_open_id", None)
            st.rerun()


def _render_issue_list(filtered: pd.DataFrame, total_count: int) -> str:
    if filtered.empty:
        st.info("No Issues match the current filters.")
        return ""

    page_size = 6
    total_pages = max(1, math.ceil(len(filtered) / page_size))
    current_page = min(max(int(st.session_state.get("issue_list_page", 1) or 1), 1), total_pages)
    st.session_state["issue_list_page"] = current_page

    selected_id = clean_text(st.session_state.get("issue_selected_id", ""))
    filtered_ids = filtered["Issue ID"].astype(str).str.strip().tolist()
    if selected_id not in filtered_ids:
        selected_id = filtered_ids[0]
        st.session_state["issue_selected_id"] = selected_id
        st.session_state.pop("issue_action_open_id", None)

    st.markdown(
        f"""
        <div class="issue-summary-line">
            <span>Showing <strong>{len(filtered)}</strong> of {total_count} issues</span>
            <span>Reported At · Latest first</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    start = (current_page - 1) * page_size
    for _, row in filtered.iloc[start:start + page_size].iterrows():
        _render_issue_list_item(row, selected=clean_text(row.get("Issue ID")) == selected_id)

    if total_pages > 1:
        prev_col, page_col, next_col = st.columns([1, 2, 1])
        with prev_col:
            if st.button("Previous", key="issue_page_previous", width="stretch", disabled=current_page <= 1):
                st.session_state["issue_list_page"] = current_page - 1
                st.rerun()
        with page_col:
            st.markdown(
                f"<div style='text-align:center;padding-top:0.62rem;color:var(--text-secondary);font-size:0.75rem;'>Page {current_page} of {total_pages}</div>",
                unsafe_allow_html=True,
            )
        with next_col:
            if st.button("Next", key="issue_page_next", width="stretch", disabled=current_page >= total_pages):
                st.session_state["issue_list_page"] = current_page + 1
                st.rerun()
    return selected_id


def _detail_card(title: str, fields: list[tuple[str, object]]) -> None:
    rows = "".join(
        '<div class="issue-detail-row">'
        f"<span>{escape(label)}</span><strong>{escape(clean_text(value) or '—')}</strong>"
        "</div>"
        for label, value in fields
    )
    st.markdown(
        f"<div class='issue-detail-card'><h4>{escape(title)}</h4><div class='issue-detail-list'>{rows}</div></div>",
        unsafe_allow_html=True,
    )


def _render_issue_details_tab(row: pd.Series) -> None:
    detail_columns = st.columns(3)
    with detail_columns[0]:
        _detail_card("Issue Information", [
            ("Issue Type", row.get("Issue Type")),
            ("Status", row.get("Status")),
            ("Reported By", row.get("Reported By") or row.get("Technician")),
            ("Reported At", _format_datetime(row.get("Reported At"))),
            ("Description", row.get("Detailed Description")),
        ])
    with detail_columns[1]:
        _detail_card("Unit Information", [
            ("Serial Number", row.get("Serial Number")), ("Model", row.get("Model")),
            ("Location", row.get("Location")), ("Postal Code", row.get("Postal Code")),
            ("Lift Lobby", row.get("Lift Lobby")), ("Loaner Unit", row.get("Is Loaner") or "No"),
        ])
    with detail_columns[2]:
        _detail_card("Responsibility & Timeline", [
            ("Assigned By", row.get("Assigned By") or row.get("Reviewed By")),
            ("Assigned At", _format_datetime(row.get("_Assigned Date"))),
            ("Assigned To", row.get("Current Assignee") or row.get("Assigned To")),
            ("Started By", row.get("Started By")),
            ("Started At", _format_datetime(row.get("Started At"))),
            ("Due Date", _format_datetime(row.get("Due Date"))),
            ("Resolution Submitted By", row.get("Resolution Submitted By")),
            ("Resolution Submitted At", _format_datetime(row.get("Resolution Submitted At"))),
            ("Verified / Closed By", row.get("_Verified By") or row.get("Closed By")),
            ("Verified / Closed At", _format_datetime(row.get("_Verified At") or row.get("Closed At"))),
        ])

    review_notes = clean_text(row.get("Review Notes"))
    assignment_notes = clean_text(row.get("Assignment Notes"))
    if review_notes or assignment_notes:
        with st.container(border=True):
            st.markdown("**Review and Assignment Notes**")
            if review_notes:
                st.write(f"Review: {review_notes}")
            if assignment_notes:
                st.write(f"Assignment: {assignment_notes}")

    with st.expander("Source and Record Linkage"):
        source = clean_text(row.get("Source")) or "Report Issue"
        source_record_id = clean_text(row.get("Source Record ID")) or "—"
        source_field = clean_text(row.get("Source Field")) or "—"
        source_value = clean_text(row.get("Source Value")) or "—"
        source_cols = st.columns(2)
        source_cols[0].markdown(f"**Source:** {source}")
        source_cols[0].markdown(f"**Source Record ID:** {source_record_id}")
        source_cols[1].markdown(f"**Source Field:** {source_field}")
        source_cols[1].markdown(f"**Source Value:** {source_value}")

    with st.expander("Copy Issue Summary"):
        st.code(build_issue_copy_text(row), language=None, wrap_lines=True)


def _render_issue_workspace(row: pd.Series, issue_csv_file: str | Path) -> None:
    issue_id = clean_text(row.get("Issue ID"))
    status = clean_text(row.get("Status")) or "Reported"
    issue_type = clean_text(row.get("Issue Type")) or "Issue"
    serial = clean_text(row.get("Serial Number")) or "No serial number"
    location = clean_text(row.get("Location")) or "No location"
    assignee = clean_text(row.get("Current Assignee")) or "Unassigned"
    reported_by = clean_text(row.get("Reported By")) or clean_text(row.get("Technician")) or "—"
    action_label = _next_action_label(status)
    key_prefix = f"workspace_{_safe_key(issue_id)}"

    with st.container(border=True):
        header_left, action_right = st.columns([3.3, 1.2])
        with header_left:
            st.markdown(
                f"""
                <div class="issue-workspace-header">
                    <div class="issue-workspace-id">{escape(issue_id)}</div>
                    <h2>{escape(issue_type)}</h2>
                    <p><strong>{escape(serial)}</strong> · {escape(location)}</p>
                    <p>Reported by {escape(reported_by)} · {escape(_format_datetime(row.get('Reported At')))} · Assigned to {escape(assignee)}</p>
                    <span class="issue-status-badge issue-status-{_status_class(status)}">{escape(status)}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with action_right:
            st.markdown(
                f"<div class='issue-next-action'><span>NEXT ACTION</span><strong>{escape(action_label)}</strong></div>",
                unsafe_allow_html=True,
            )
            if status != "Closed":
                action_is_open = clean_text(st.session_state.get("issue_action_open_id", "")) == issue_id
                if st.button(
                    "Hide Action Form" if action_is_open else "Open Action Form",
                    key=f"{key_prefix}_action_toggle",
                    type="primary" if not action_is_open else "secondary",
                    width="stretch",
                ):
                    if action_is_open:
                        st.session_state.pop("issue_action_open_id", None)
                    else:
                        st.session_state["issue_action_open_id"] = issue_id
                    st.rerun()

        if clean_text(st.session_state.get("issue_action_open_id", "")) == issue_id:
            st.divider()
            _render_actions(row, issue_csv_file, key_prefix=key_prefix)

        st.divider()
        details_tab, evidence_tab, activity_tab = st.tabs(["Details", "Evidence & Resolution", "Activity"])
        with details_tab:
            _render_issue_details_tab(row)
        with evidence_tab:
            st.markdown("#### Original and Progress Evidence")
            _render_evidence(row, issue_csv_file)
            st.divider()
            st.markdown("#### Resolution Submissions")
            _render_resolution_submissions(issue_id, issue_csv_file)
        with activity_tab:
            _render_history(issue_id, issue_csv_file)


def render_issues_page(issue_csv_file: str | Path = "issue_records.csv") -> None:
    _apply_issue_page_styles()
    _show_action_success()
    try:
        records = _enrich_issue_records(load_issue_records(issue_csv_file), issue_csv_file)
    except Exception as error:
        st.error(f"Failed to load Issue records: {error}")
        return

    focused_issue_id = clean_text(st.session_state.pop("selected_issue_id", ""))
    if focused_issue_id:
        for key in ISSUE_FILTER_KEYS:
            st.session_state.pop(key, None)
        st.session_state["issue_selected_id"] = focused_issue_id
        st.session_state["issue_list_page"] = 1

    open_count = int((~records["Status"].map(is_closed_status)).sum()) if not records.empty else 0
    page_header(
        "Issues",
        "Find Issues by date, type, status and responsibility, then manage one selected case in a focused workspace.",
        eyebrow="ISSUE WORKFLOW · CONTROL",
        chip=f"{open_count} OPEN · {len(records)} TOTAL",
    )

    header_left, header_right = st.columns([4, 1])
    with header_left:
        st.caption("All records remain ordered by Reported At, newest first.")
    with header_right:
        if st.button("Report New Issue", key="issue_report_new", type="primary", width="stretch"):
            st.session_state["page"] = "Report Issue"
            st.rerun()

    if records.empty:
        st.info("No Issue Reports have been submitted yet.")
        return

    filtered = _render_issue_filters(records)
    list_column, workspace_column = st.columns([0.82, 1.45], gap="medium")
    with list_column:
        selected_id = _render_issue_list(filtered, len(records))
    with workspace_column:
        if not selected_id:
            st.info("Select or create an Issue to view its details.")
            return
        selected_matches = records.loc[records["Issue ID"].astype(str).str.strip().eq(selected_id)]
        if selected_matches.empty:
            st.warning("The selected Issue could not be found.")
            return
        _render_issue_workspace(selected_matches.iloc[0], issue_csv_file)


__all__ = ["get_open_issue_count", "render_issues_page"]
