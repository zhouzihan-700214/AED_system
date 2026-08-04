from __future__ import annotations

from datetime import date, datetime
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

from config import AED_DATA_FILE, ISSUE_RECORD_FILE, PM_PLAN_FILE
from services.aed_repository import get_all_units
from services.unit_color_service import sync_unit_from_issue_records
from services.pm_service import (
    append_pm_response,
    build_response,
    classify_pm_excel_update_result,
    complete_matching_pm_plan,
    create_pm_failure_issues,
    failed_checklist_items,
    parse_optional_date,
    record_value,
    update_selected_aed,
    validate_submission,
)
from ui.components import page_header
from ui.pm_styles import inject_pm_css
from utils.streamlit_utils import rerun_app
from utils.text_utils import clean_text


# =========================================================
# File paths are centralized in config.py.
# =========================================================


SEARCH_COLUMNS = ["Serial Number", "Location", "Postal Code"]


# =========================================================
# Styling
# =========================================================


# =========================================================
# Data helpers
# =========================================================

def get_aed_dataframe() -> pd.DataFrame:
    """Return the latest master table through the shared repository."""

    return get_all_units().copy()



def find_matching_rows(dataframe: pd.DataFrame, keyword: str) -> pd.DataFrame:
    search_text = clean_text(keyword).casefold()

    if not search_text:
        return dataframe.iloc[0:0]

    mask = pd.Series(False, index=dataframe.index)

    for column in SEARCH_COLUMNS:
        if column in dataframe.columns:
            mask = mask | (
                dataframe[column]
                .astype(str)
                .str.casefold()
                .str.contains(search_text, na=False, regex=False)
            )

    return dataframe.loc[mask]


def result_label(dataframe: pd.DataFrame, row_index: int) -> str:
    row = dataframe.loc[row_index]
    serial = record_value(row, "Serial Number") or "No serial number"
    location = record_value(row, "Location") or "No location"
    postal = record_value(row, "Postal Code") or "No postal code"
    return f"{serial}    |    {location}    |    {postal}"


# =========================================================
# Session-state helpers
# =========================================================

FORM_KEYS = [
    "pm_service_date",
    "pm_technician",
    "pm_service_type",
    "pm_service_report_id",
    "pm_service_notes",
    "pm_customer_location",
    "pm_postal_code",
    "pm_lift_lobby",
    "pm_loaner",
    "pm_cabinet_inspection",
    "pm_cabinet_alarm",
    "pm_serial_number",
    "pm_aed_physical_condition",
    "pm_self_test_result",
    "pm_battery_expiry",
    "pm_aed_cover",
    "pm_adult_pads_expiry",
    "pm_adult_pads_lot",
    "pm_adult_pads_within_expiry",
    "pm_pediatric_pads_expiry",
    "pm_pediatric_pads_lot",
    "pm_pediatric_pads_within_expiry",
    "pm_aed_signage",
    "pm_final_check",
    "pm_confirmed",
]


def reset_form_for_selected_aed(
    selected_record: pd.Series,
    original_index: int,
) -> None:
    for key in FORM_KEYS:
        st.session_state.pop(key, None)

    st.session_state["pm_original_index"] = int(original_index)
    st.session_state["pm_original_serial_number"] = record_value(
        selected_record,
        "Serial Number",
    )
    st.session_state["pm_selected_location"] = record_value(
        selected_record,
        "Location",
    )
    st.session_state["pm_selected_model"] = record_value(
        selected_record,
        "Model",
    )

    st.session_state["pm_service_date"] = date.today()
    st.session_state["pm_technician"] = ""
    st.session_state["pm_service_type"] = "Preventive Maintenance (PM)"
    st.session_state["pm_service_report_id"] = record_value(
        selected_record, "Service Report e-SR"
    )
    st.session_state["pm_service_notes"] = ""
    st.session_state["pm_customer_location"] = None

    st.session_state["pm_postal_code"] = record_value(
        selected_record,
        "Postal Code",
    )
    st.session_state["pm_lift_lobby"] = record_value(
        selected_record,
        "Lift Lobby",
    )
    st.session_state["pm_loaner"] = "No"
    st.session_state["pm_cabinet_inspection"] = "Pass"
    st.session_state["pm_cabinet_alarm"] = "Pass"

    st.session_state["pm_serial_number"] = record_value(
        selected_record,
        "Serial Number",
    )
    st.session_state["pm_aed_physical_condition"] = "Pass"
    st.session_state["pm_self_test_result"] = "Pass"

    st.session_state["pm_battery_expiry"] = parse_optional_date(
        record_value(selected_record, "Battery Expiry Date")
    )
    st.session_state["pm_aed_cover"] = "Pass"

    st.session_state["pm_adult_pads_expiry"] = parse_optional_date(
        record_value(selected_record, "Adult Pads Expiry Date")
    )
    st.session_state["pm_adult_pads_lot"] = record_value(
        selected_record,
        "Adult Pads Lot Number",
    )
    st.session_state["pm_adult_pads_within_expiry"] = "Yes"

    st.session_state["pm_pediatric_pads_expiry"] = parse_optional_date(
        record_value(selected_record, "Pediatric Pads Expiry Date")
    )
    st.session_state["pm_pediatric_pads_lot"] = record_value(
        selected_record,
        "Pediatric Pads Lot Number",
    )
    st.session_state["pm_pediatric_pads_within_expiry"] = "Yes"

    st.session_state["pm_aed_signage"] = "Yes"
    st.session_state["pm_final_check"] = "Yes"
    st.session_state["pm_confirmed"] = False


def find_map_target_index(
    dataframe: pd.DataFrame,
    target: dict[str, str],
) -> int | None:
    """Find the exact AED selected from the map."""

    serial_number = clean_text(
        target.get("Serial Number", "")
    )
    postal_code = clean_text(
        target.get("Postal Code", "")
    )

    if serial_number and "Serial Number" in dataframe.columns:
        serial_matches = dataframe[
            dataframe["Serial Number"]
            .astype(str)
            .str.strip()
            .str.casefold()
            .eq(serial_number.casefold())
        ]

        if not serial_matches.empty:
            return int(serial_matches.index[0])

    if postal_code and "Postal Code" in dataframe.columns:
        postal_matches = dataframe[
            dataframe["Postal Code"]
            .astype(str)
            .str.strip()
            .eq(postal_code)
        ]

        if not postal_matches.empty:
            return int(postal_matches.index[0])

    return None


def apply_map_pm_target(dataframe: pd.DataFrame) -> None:
    """Preselect the AED passed from an AED Map marker."""

    target = st.session_state.pop(
        "map_pm_target",
        None,
    )

    if not isinstance(target, dict):
        return

    selected_index = find_map_target_index(
        dataframe,
        target,
    )

    if selected_index is None:
        st.session_state["pm_map_target_error"] = (
            "The AED selected on the map could not be found in the AED master data."
        )
        return

    selected_record = dataframe.loc[selected_index]
    reset_form_for_selected_aed(
        selected_record,
        selected_index,
    )

    serial_number = record_value(
        selected_record,
        "Serial Number",
    )
    postal_code = record_value(
        selected_record,
        "Postal Code",
    )

    st.session_state["pm_search_keyword"] = (
        serial_number or postal_code
    )
    st.session_state["pm_search_results"] = [
        selected_index
    ]
    st.session_state["pm_result_choice"] = (
        selected_index
    )
    st.session_state["pm_loaded_index"] = (
        selected_index
    )
    st.session_state["pm_map_target_message"] = (
        f"{serial_number or 'The selected AED'} was loaded from AED Map."
    )


# =========================================================
# Layout helpers
# =========================================================

def form_row(
    number: int,
    label: str,
    widget,
    help_text: str = "",
):
    number_col, label_col, input_col, help_col = st.columns(
        [0.34, 2.05, 2.35, 3.55],
        gap="medium",
        vertical_alignment="center",
    )

    with number_col:
        st.markdown(
            f'<div class="pm-number">{number}.</div>',
            unsafe_allow_html=True,
        )

    with label_col:
        st.markdown(
            f'<div class="pm-label">{label}</div>',
            unsafe_allow_html=True,
        )

    with input_col:
        value = widget()

    with help_col:
        if help_text:
            st.markdown(
                f'<div class="pm-help">{help_text}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="pm-help">&nbsp;</div>', unsafe_allow_html=True)

    return value


def render_sop() -> None:
    with st.expander("View Full Preventive Maintenance SOP"):
        st.markdown(
            """
            1. Search for the AED by serial number, location, or postal code.
            2. Select the correct AED and verify all pre-filled information.
            3. Complete the checklist from Item 1 to Item 22 in order.
            4. Replace cabinet or AED batteries when required, then repeat the test.
            5. Confirm that all information was physically verified before submission.
            6. Loaner-unit responses are saved, but they do not update the master AED file.
            """
        )


def render_search_section(dataframe: pd.DataFrame) -> None:
    with st.container(border=True):
        st.markdown(
            '<div class="pm-section-title">Search AED</div>',
            unsafe_allow_html=True,
        )

        search_col, button_col = st.columns([7.4, 1.2], vertical_alignment="bottom")

        with search_col:
            st.text_input(
                "Search AED",
                placeholder="Enter serial number, location, or postal code",
                label_visibility="collapsed",
                key="pm_search_keyword",
            )

        with button_col:
            search_clicked = st.button(
                "Search",
                type="primary",
                width="stretch",
                key="pm_search_button",
            )

        if search_clicked:
            keyword = st.session_state.get("pm_search_keyword", "")
            matches = find_matching_rows(dataframe, keyword)

            st.session_state["pm_search_results"] = [
                int(index) for index in matches.index.tolist()
            ]
            st.session_state.pop("pm_result_choice", None)
            st.session_state.pop("pm_loaded_index", None)
            st.session_state.pop("pm_original_index", None)

        result_indices = st.session_state.get("pm_search_results", [])

        if result_indices:
            result_word = "result" if len(result_indices) == 1 else "results"
            st.markdown(
                f'<div class="pm-search-count">{len(result_indices)} '
                f'{result_word} found</div>',
                unsafe_allow_html=True,
            )

            with st.container(border=True):
                selected_index = st.radio(
                    "AED search results",
                    options=result_indices,
                    format_func=lambda row_index: result_label(dataframe, row_index),
                    index=0,
                    label_visibility="collapsed",
                    key="pm_result_choice",
                )

            if st.session_state.get("pm_loaded_index") != selected_index:
                reset_form_for_selected_aed(
                    dataframe.loc[selected_index],
                    selected_index,
                )
                st.session_state["pm_loaded_index"] = selected_index
                rerun_app()

        elif search_clicked:
            st.warning("No matching AED was found.")


def _commit_pm_submission(
    dataframe: pd.DataFrame,
    selected_index: int,
    response: dict[str, str],
) -> tuple[str, list[str], list[str]]:
    """Commit the reviewed PM response, linked Issues and system-only colour."""

    audit_user = clean_text(
        st.session_state.get("audit_user", response.get("Technician", ""))
    )
    session_id = clean_text(st.session_state.get("session_id", ""))
    loaner_unit = clean_text(response.get("Loaner Unit", "No"))
    warnings: list[str] = []

    if loaner_unit == "Yes":
        response["Operation ID"] = str(uuid.uuid4())
        response["Submission Status"] = "COMMITTED"
        response["Excel Update Status"] = "NOT_REQUIRED_LOANER"
        response["Submitted By"] = audit_user
        message = (
            f"PM response {response['PM Response ID']} was saved. "
            "The IB List was not updated because this is a loaner unit."
        )
    else:
        excel_result = update_selected_aed(
            dataframe=dataframe,
            original_index=int(selected_index),
            values=response,
            user=audit_user,
            session_id=session_id,
        )
        if excel_result.status == "conflict":
            conflict_lines = [
                f"{field}: opened '{values.get('original', '')}', "
                f"current '{values.get('current', '')}', "
                f"checklist '{values.get('desired', '')}'"
                for field, values in excel_result.conflicts.items()
            ]
            raise ValueError(
                excel_result.message + "\n" + "\n".join(conflict_lines)
            )
        excel_update_status = classify_pm_excel_update_result(excel_result)

        response["Operation ID"] = excel_result.operation_id
        response["Submission Status"] = "COMMITTED"
        response["Excel Update Status"] = excel_update_status
        response["Master Data Updated"] = (
            "Yes" if excel_update_status in {"UPDATED", "ALREADY_APPLIED"} else "No"
        )
        response["Submitted By"] = audit_user
        message = (
            f"PM response {response['PM Response ID']} was saved and the selected "
            "AED record was safely updated in the IB List."
        )

    failures = failed_checklist_items(response)
    issue_ids, issue_warnings = create_pm_failure_issues(
        response,
        issue_csv_file=ISSUE_RECORD_FILE,
        model=clean_text(st.session_state.get("pm_selected_model", "")),
        reported_by=audit_user,
    )
    warnings.extend(issue_warnings)

    response["Failed Checklist Fields"] = "; ".join(
        failure["Field"] for failure in failures
    )
    response["Created Issue IDs"] = "; ".join(issue_ids)

    service_type_key = clean_text(response.get("Service Type", "")).casefold()
    linked_plan_id = ""
    if service_type_key.startswith("pm") or "preventive maintenance" in service_type_key:
        linked_plan_id = complete_matching_pm_plan(
            response.get("AED Serial Number", ""),
            response.get("Service Date", ""),
            operation_id=response.get("Operation ID", ""),
            response_id=response.get("PM Response ID", ""),
            completed_by=audit_user,
            plan_file=PM_PLAN_FILE,
        )
    response["Linked Plan ID"] = linked_plan_id

    # Save once after all durable cross-record links are known. The service
    # function is idempotent, so a confirmation retry cannot duplicate the row.
    append_pm_response(response)

    if linked_plan_id:
        message += f" PM plan {linked_plan_id} was marked Completed."

    if not failures:
        role = sync_unit_from_issue_records(
            ISSUE_RECORD_FILE,
            response.get("AED Serial Number", ""),
            clear_role="Completed",
        )
        message += (
            " Marker status is Completed."
            if role == "Completed"
            else f" Marker status remains {role} because another Issue is still open."
        )
    elif issue_ids:
        message += f" {len(issue_ids)} Issue record(s) were created from failed items."

    return message, warnings, issue_ids


def _render_pm_confirmation(
    dataframe: pd.DataFrame,
    pending: dict[str, object],
) -> None:
    response = dict(pending.get("response", {}))
    selected_index = int(pending.get("selected_index", -1))
    failures = failed_checklist_items(response)

    with st.container(border=True):
        st.subheader("Confirm PM Submission")
        st.caption(
            "Nothing has been written yet. Review the final values and the resulting "
            "marker colour before confirming."
        )
        summary = pd.DataFrame(
            [
                ("Serial Number", response.get("AED Serial Number", "")),
                ("Service Date", response.get("Service Date", "")),
                ("Service Type", response.get("Service Type", "")),
                ("Technician", response.get("Technician", "")),
                ("Service Report / e-SR", response.get("Service Report e-SR", "")),
                ("Service Notes", response.get("Service Notes", "")),
                ("Checklist Result", "Failed items found" if failures else "All checks passed"),
                (
                    "Marker Change",
                    "→ Issue colour" if failures else "→ Completed colour (unless another Issue remains)",
                ),
            ],
            columns=["Item", "Value"],
        )
        st.dataframe(summary, width="stretch", hide_index=True)
        if failures:
            st.warning(
                f"{len(failures)} failed item(s) will create separate Issue records."
            )
            st.dataframe(
                pd.DataFrame(failures)[["Field", "Value", "Issue Type", "Priority"]],
                width="stretch",
                hide_index=True,
            )
        else:
            st.success("No failed checklist item was detected.")

        back_col, confirm_col = st.columns([1, 1])
        with back_col:
            if st.button("Back to Checklist", width="stretch"):
                st.session_state.pop("pm_pending_submission", None)
                rerun_app()
        with confirm_col:
            if st.button(
                "Confirm and Save",
                type="primary",
                width="stretch",
            ):
                try:
                    message, warnings, issue_ids = _commit_pm_submission(
                        dataframe, selected_index, response
                    )
                except (OSError, ValueError, IndexError, KeyError) as error:
                    st.error(f"Failed to save the PM response: {error}")
                    return
                st.session_state.pop("pm_pending_submission", None)
                st.session_state["pm_submission_success"] = message
                st.session_state["pm_submission_warnings"] = warnings
                st.session_state["pm_last_commit"] = {
                    "response_id": clean_text(response.get("PM Response ID", "")),
                    "serial_number": clean_text(response.get("AED Serial Number", "")),
                    "issue_ids": list(issue_ids),
                }
                rerun_app()


def render_pm_form(dataframe: pd.DataFrame) -> None:
    selected_index = st.session_state.get("pm_original_index")

    if selected_index is None:
        st.info("Search for and select one AED before completing the checklist.")
        return

    success_message = st.session_state.pop("pm_submission_success", "")
    if success_message:
        st.success(success_message)
    for warning in st.session_state.pop("pm_submission_warnings", []):
        st.warning(warning)

    last_commit = st.session_state.get("pm_last_commit")
    if success_message and isinstance(last_commit, dict):
        action_columns = st.columns(2)
        if action_columns[0].button(
            "Open in Service Records",
            width="stretch",
            key="pm_open_saved_service_record",
        ):
            st.session_state["service_records_keyword"] = clean_text(
                last_commit.get("serial_number", "")
            )
            st.session_state["page"] = "Service Records"
            rerun_app()
        issue_ids = list(last_commit.get("issue_ids", []) or [])
        if issue_ids and action_columns[1].button(
            f"Open Created Issues ({len(issue_ids)})",
            width="stretch",
            key="pm_open_created_issues",
        ):
            st.session_state["selected_issue_id"] = clean_text(issue_ids[0])
            st.session_state["page"] = "Issues"
            rerun_app()

    pending = st.session_state.get("pm_pending_submission")
    if isinstance(pending, dict):
        _render_pm_confirmation(dataframe, pending)
        return

    with st.container(border=True):
        with st.form("pm_checklist_form", clear_on_submit=False):
            service_date = form_row(
                1,
                "Service Date",
                lambda: st.date_input(
                    "Service Date",
                    key="pm_service_date",
                    label_visibility="collapsed",
                    format="DD-MM-YYYY",
                ),
            )

            technician = form_row(
                2,
                "Technician",
                lambda: st.text_input(
                    "Technician",
                    key="pm_technician",
                    label_visibility="collapsed",
                    placeholder="Enter technician name",
                ),
            )

            service_type = form_row(
                3,
                "Service Type",
                lambda: st.selectbox(
                    "Service Type",
                    options=[
                        "Preventive Maintenance (PM)",
                        "Commissioning",
                        "PM+batt",
                        "PM+glass",
                        "PM +batt +glass",
                    ],
                    key="pm_service_type",
                    label_visibility="collapsed",
                ),
            )

            with st.container(border=True):
                st.markdown("#### Service record reference")
                reference_col, notes_col = st.columns([1.2, 2.8], gap="large")
                with reference_col:
                    service_report_id = st.text_input(
                        "Service Report / e-SR",
                        key="pm_service_report_id",
                        placeholder="e-SR reference",
                    )
                with notes_col:
                    service_notes = st.text_area(
                        "Service Notes / Site Findings",
                        key="pm_service_notes",
                        placeholder="Optional observations, work completed or follow-up notes",
                        height=92,
                    )

            customer_location = form_row(
                4,
                "Customer / Location",
                lambda: st.selectbox(
                    "Customer / Location",
                    options=["SCDF / SAL", "Other"],
                    index=None,
                    placeholder="Select an option",
                    key="pm_customer_location",
                    label_visibility="collapsed",
                ),
            )

            postal_code = form_row(
                5,
                "Postal Code",
                lambda: st.text_input(
                    "Postal Code",
                    key="pm_postal_code",
                    label_visibility="collapsed",
                ),
            )

            lift_lobby = form_row(
                6,
                "Lift Lobby",
                lambda: st.text_input(
                    "Lift Lobby",
                    key="pm_lift_lobby",
                    label_visibility="collapsed",
                ),
            )

            loaner_unit = form_row(
                7,
                "Is this a loaner unit?",
                lambda: st.radio(
                    "Is this a loaner unit?",
                    options=["No", "Yes"],
                    horizontal=True,
                    key="pm_loaner",
                    label_visibility="collapsed",
                ),
            )

            if loaner_unit == "Yes":
                st.info(
                    "This is a loaner unit. The PM response will be saved, "
                    "but aed_data.csv will not be updated."
                )

            cabinet_inspection = form_row(
                8,
                "Cabinet Inspection",
                lambda: st.radio(
                    "Cabinet Inspection",
                    options=["Pass", "Fail"],
                    horizontal=True,
                    key="pm_cabinet_inspection",
                    label_visibility="collapsed",
                ),
                (
                    "Check cabinet housing for cracks, damage, loose or missing "
                    "parts, broken glass, missing keys, and any other physical damage."
                ),
            )

            cabinet_alarm = form_row(
                9,
                "Cabinet Alarm",
                lambda: st.radio(
                    "Cabinet Alarm",
                    options=["Pass", "Fail"],
                    horizontal=True,
                    key="pm_cabinet_alarm",
                    label_visibility="collapsed",
                ),
                (
                    "Unlock the AED cabinet. Does the alarm sound? If no alarm is "
                    "heard, replace the cabinet batteries, test the alarm again, "
                    "and update the result."
                ),
            )

            serial_number = form_row(
                10,
                "AED Serial Number",
                lambda: st.text_input(
                    "AED Serial Number",
                    key="pm_serial_number",
                    label_visibility="collapsed",
                ),
            )

            physical_condition = form_row(
                11,
                "AED Physical Condition",
                lambda: st.radio(
                    "AED Physical Condition",
                    options=["Pass", "Fail"],
                    horizontal=True,
                    key="pm_aed_physical_condition",
                    label_visibility="collapsed",
                ),
                (
                    "Is the unit clean, undamaged and free of excessive wear? "
                    "Are there any cracks or loose parts in the housing?"
                ),
            )

            self_test_result = form_row(
                12,
                "Self Test Result",
                lambda: st.selectbox(
                    "Self Test Result",
                    options=[
                        "Pass",
                        "Fail",
                        "Pass - After installing new batteries",
                    ],
                    key="pm_self_test_result",
                    label_visibility="collapsed",
                ),
                (
                    'The unit says: "UNIT OK". If the unit prompts Low Battery, '
                    "install new batteries and repeat this step. Record the battery "
                    "information in the next step."
                ),
            )

            battery_expiry = form_row(
                13,
                "Battery Expiry Date",
                lambda: st.date_input(
                    "Battery Expiry Date",
                    key="pm_battery_expiry",
                    label_visibility="collapsed",
                    format="DD-MM-YYYY",
                ),
            )

            aed_cover = form_row(
                14,
                "AED Cover",
                lambda: st.radio(
                    "AED Cover",
                    options=["Pass", "Fail"],
                    horizontal=True,
                    key="pm_aed_cover",
                    label_visibility="collapsed",
                ),
                (
                    "AED Cover is not broken and is securely fitted over the "
                    "CPR-D Padz."
                ),
            )

            adult_pads_expiry = form_row(
                15,
                "Adult Pads Expiry Date",
                lambda: st.date_input(
                    "Adult Pads Expiry Date",
                    key="pm_adult_pads_expiry",
                    label_visibility="collapsed",
                    format="DD-MM-YYYY",
                ),
            )

            adult_pads_lot = form_row(
                16,
                "Adult Pads Lot Number",
                lambda: st.text_input(
                    "Adult Pads Lot Number",
                    key="pm_adult_pads_lot",
                    label_visibility="collapsed",
                ),
            )

            adult_pads_within_expiry = form_row(
                17,
                "Adult Pads Within Expiry Date",
                lambda: st.radio(
                    "Adult Pads Within Expiry Date",
                    options=["Yes", "No"],
                    horizontal=True,
                    key="pm_adult_pads_within_expiry",
                    label_visibility="collapsed",
                ),
                "The CPR-D Padz is still within the expiry date.",
            )

            pediatric_pads_expiry = form_row(
                18,
                "Pediatric Pads Expiry Date",
                lambda: st.date_input(
                    "Pediatric Pads Expiry Date",
                    key="pm_pediatric_pads_expiry",
                    label_visibility="collapsed",
                    format="DD-MM-YYYY",
                ),
            )

            pediatric_pads_lot = form_row(
                19,
                "Pediatric Pads Lot Number",
                lambda: st.text_input(
                    "Pediatric Pads Lot Number",
                    key="pm_pediatric_pads_lot",
                    label_visibility="collapsed",
                ),
            )

            pediatric_pads_within_expiry = form_row(
                20,
                "Pediatric Pads Within Expiry Date",
                lambda: st.radio(
                    "Pediatric Pads Within Expiry Date",
                    options=["Yes", "No"],
                    horizontal=True,
                    key="pm_pediatric_pads_within_expiry",
                    label_visibility="collapsed",
                ),
                "The Pedi Padz is still within the expiry date.",
            )

            aed_signage = form_row(
                21,
                "AED Signage",
                lambda: st.radio(
                    "AED Signage",
                    options=["Yes", "No"],
                    horizontal=True,
                    key="pm_aed_signage",
                    label_visibility="collapsed",
                ),
                "Is the AED signage legible, not broken and not dented?",
            )

            final_check = form_row(
                22,
                "Final Check",
                lambda: st.radio(
                    "Final Check",
                    options=["Yes", "No"],
                    horizontal=True,
                    key="pm_final_check",
                    label_visibility="collapsed",
                ),
                (
                    "Ensure RFU is visible from outside the cabinet and ensure "
                    "that all items are in good condition."
                ),
            )

            st.markdown("<div style='height:0.35rem'></div>", unsafe_allow_html=True)

            confirmed = st.checkbox(
                "I confirm that the information above has been verified "
                "during the inspection.",
                key="pm_confirmed",
            )

            submit_col, spacer_col = st.columns([2.0, 6.3])
            with submit_col:
                submitted = st.form_submit_button(
                    "Review PM Submission",
                    type="primary",
                    width="stretch",
                )

        if submitted:
            errors = validate_submission(
                technician=technician,
                customer_location=customer_location,
                postal_code=postal_code,
                serial_number=serial_number,
                confirmed=confirmed,
            )

            if errors:
                st.error("\n".join(f"• {error}" for error in errors))
                return

            response = build_response(
                service_date=service_date,
                technician=technician,
                service_type=service_type,
                customer_location=customer_location,
                postal_code=postal_code,
                lift_lobby=lift_lobby,
                loaner_unit=loaner_unit,
                cabinet_inspection=cabinet_inspection,
                cabinet_alarm=cabinet_alarm,
                serial_number=serial_number,
                physical_condition=physical_condition,
                self_test_result=self_test_result,
                battery_expiry=battery_expiry,
                aed_cover=aed_cover,
                adult_pads_expiry=adult_pads_expiry,
                adult_pads_lot=adult_pads_lot,
                adult_pads_within_expiry=adult_pads_within_expiry,
                pediatric_pads_expiry=pediatric_pads_expiry,
                pediatric_pads_lot=pediatric_pads_lot,
                pediatric_pads_within_expiry=pediatric_pads_within_expiry,
                aed_signage=aed_signage,
                final_check=final_check,
                aed_location=clean_text(
                    st.session_state.get("pm_selected_location", "")
                ),
                original_serial_number=clean_text(
                    st.session_state.get("pm_original_serial_number", "")
                ),
                service_report_id=service_report_id,
                service_notes=service_notes,
                aed_model=clean_text(
                    st.session_state.get("pm_selected_model", "")
                ),
            )

            st.session_state["pm_pending_submission"] = {
                "selected_index": int(selected_index),
                "response": response,
            }
            rerun_app()


def render_report_issue_card() -> None:
    with st.container(border=True):
        st.markdown(
            '<div class="pm-section-title">Report Issue</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="pm-section-note">'
            "Report an AED fault or abnormal condition for follow-up. "
            "The current checklist information will be carried over."
            "</div>",
            unsafe_allow_html=True,
        )

        if st.button(
            "Report an Issue for This AED",
            key="pm_open_report_issue",
        ):
            selected_index = st.session_state.get("pm_original_index")

            if selected_index is None:
                st.warning("Search for and select an AED first.")
                return

            st.session_state["report_issue_prefill"] = {
                "Source": "PM Checklist",
                "Serial Number": clean_text(
                    st.session_state.get("pm_serial_number", "")
                ),
                "Model": clean_text(
                    st.session_state.get("pm_selected_model", "")
                ),
                "Location": clean_text(
                    st.session_state.get("pm_selected_location", "")
                ),
                "Postal Code": clean_text(
                    st.session_state.get("pm_postal_code", "")
                ),
                "Lift Lobby": clean_text(
                    st.session_state.get("pm_lift_lobby", "")
                ),
                "Technician": clean_text(
                    st.session_state.get("pm_technician", "")
                ),
            }
            st.session_state["page"] = "Report Issue"
            rerun_app()


# =========================================================
# Public page function
# =========================================================

def render_pm_checklist() -> None:
    inject_pm_css()

    page_header(
        "PM Checklist",
        "Search for an AED, verify the pre-filled information, complete the inspection and submit the service response.",
        eyebrow="MAINTENANCE · EXECUTE",
        chip="FIELD CHECK + MASTER UPDATE",
        capabilities=[
            ("Find the unit", "Search by serial number, location or postal code and confirm the exact AED."),
            ("Complete the check", "Work through the structured inspection while preserving pre-filled details."),
            ("Submit once", "Create the service record and update the current master information together."),
        ],
    )

    render_sop()

    dataframe = get_aed_dataframe()

    if dataframe.empty:
        st.error(
            "No AED records are available. Check the Data Source panel and "
            "the configured Excel worksheet."
        )
        return

    missing_search_columns = [
        column for column in SEARCH_COLUMNS if column not in dataframe.columns
    ]

    if missing_search_columns:
        st.error(
            "AED master data is missing required search columns: "
            + ", ".join(missing_search_columns)
        )
        return

    apply_map_pm_target(dataframe)

    map_target_message = st.session_state.pop(
        "pm_map_target_message",
        "",
    )
    map_target_error = st.session_state.pop(
        "pm_map_target_error",
        "",
    )

    if map_target_message:
        st.success(map_target_message)

    if map_target_error:
        st.error(map_target_error)

    render_search_section(dataframe)
    render_pm_form(dataframe)
    render_report_issue_card()


if __name__ == "__main__":
    st.set_page_config(
        page_title="PM Checklist",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    render_pm_checklist()
