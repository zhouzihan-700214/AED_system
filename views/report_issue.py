from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from services.aed_repository import get_all_units
from services.issue_service import (
    PRIORITY_OPTIONS,
    create_issue,
)
from ui.components import page_header
from utils.text_utils import clean_text


ISSUE_OPTIONS = [
    "Unit failed after battery replacement",
    "Cover broken",
    "Glass broken",
    "Cabinet alarm not working",
    "Adult pads expired",
    "Pediatric pads expired",
    "Signage",
    "Missing Item",
    "Other",
]

AED_COLUMNS_USED = [
    "Serial Number",
    "Model",
    "Location",
    "Postal Code",
    "Lift Lobby",
]

REPORT_FORM_KEYS = [
    "report_source",
    "report_technician",
    "report_serial_number",
    "report_model",
    "report_location",
    "report_postal_code",
    "report_lift_lobby",
    "report_is_loaner",
    "report_priority",
    "report_issue_types",
    "report_description",
    "report_uploaded_photos",
]


def load_aed_data(aed_csv_file: str | Path | None = None) -> pd.DataFrame:
    del aed_csv_file
    data = get_all_units().copy()

    for column in AED_COLUMNS_USED:
        if column not in data.columns:
            data[column] = ""
        data[column] = data[column].astype(str).str.strip()

    return data


def find_matching_aeds(dataframe: pd.DataFrame, keyword: str) -> pd.DataFrame:
    keyword = clean_text(keyword).casefold()
    if not keyword:
        return dataframe.iloc[0:0].copy()

    mask = pd.Series(False, index=dataframe.index)
    for column in ["Serial Number", "Location", "Postal Code"]:
        mask |= (
            dataframe[column]
            .astype(str)
            .str.casefold()
            .str.contains(keyword, regex=False, na=False)
        )
    return dataframe.loc[mask].copy()


def clear_report_form_state() -> None:
    for key in REPORT_FORM_KEYS:
        st.session_state.pop(key, None)

    for key in [
        "report_prefill_token",
        "report_issue_prefill",
        "report_issue_search_keyword",
        "report_issue_selected_aed",
        "report_pending_submission",
    ]:
        st.session_state.pop(key, None)


def initialise_report_state(prefill: dict[str, str] | None) -> None:
    prefill = prefill or {}
    defaults = {
        "report_source": clean_text(prefill.get("Source")) or "Report Issue",
        "report_technician": clean_text(prefill.get("Technician")),
        "report_serial_number": clean_text(prefill.get("Serial Number")),
        "report_model": clean_text(prefill.get("Model")),
        "report_location": clean_text(prefill.get("Location")),
        "report_postal_code": clean_text(prefill.get("Postal Code")),
        "report_lift_lobby": clean_text(prefill.get("Lift Lobby")),
        "report_is_loaner": "No",
        "report_priority": "Medium",
    }

    prefill_token = "|".join(defaults.values())
    if st.session_state.get("report_prefill_token") != prefill_token:
        for key, value in defaults.items():
            st.session_state[key] = value
        st.session_state["report_prefill_token"] = prefill_token


def load_selected_aed_into_form(selected_row: pd.Series) -> None:
    st.session_state["report_source"] = "Report Issue"
    st.session_state["report_serial_number"] = clean_text(
        selected_row.get("Serial Number")
    )
    st.session_state["report_model"] = clean_text(selected_row.get("Model"))
    st.session_state["report_location"] = clean_text(
        selected_row.get("Location")
    )
    st.session_state["report_postal_code"] = clean_text(
        selected_row.get("Postal Code")
    )
    st.session_state["report_lift_lobby"] = clean_text(
        selected_row.get("Lift Lobby")
    )
    st.session_state["report_is_loaner"] = "No"


def find_map_target_row(
    dataframe: pd.DataFrame,
    target: dict[str, str],
) -> pd.Series | None:
    serial_number = clean_text(target.get("Serial Number"))
    postal_code = clean_text(target.get("Postal Code"))

    if serial_number:
        matches = dataframe[
            dataframe["Serial Number"]
            .astype(str)
            .str.strip()
            .str.casefold()
            .eq(serial_number.casefold())
        ]
        if not matches.empty:
            return matches.iloc[0]

    if postal_code:
        matches = dataframe[
            dataframe["Postal Code"].astype(str).str.strip().eq(postal_code)
        ]
        if not matches.empty:
            return matches.iloc[0]

    return None


def apply_map_report_target(dataframe: pd.DataFrame) -> None:
    target = st.session_state.pop("map_report_target", None)
    if not isinstance(target, dict):
        return

    selected_row = find_map_target_row(dataframe, target)
    if selected_row is None:
        st.session_state["report_map_target_error"] = (
            "The AED selected on the map could not be found in the AED master data."
        )
        return

    clear_report_form_state()
    serial_number = clean_text(selected_row.get("Serial Number"))
    st.session_state["report_issue_prefill"] = {
        "Source": "AED Map",
        "Serial Number": serial_number,
        "Model": clean_text(selected_row.get("Model")),
        "Location": clean_text(selected_row.get("Location")),
        "Postal Code": clean_text(selected_row.get("Postal Code")),
        "Lift Lobby": clean_text(selected_row.get("Lift Lobby")),
        "Technician": "",
    }
    st.session_state["report_map_target_message"] = (
        f"{serial_number or 'The selected AED'} was loaded from AED Map."
    )


def _render_issue_confirmation(
    issue_csv_file: str | Path,
    pending: dict[str, Any],
) -> None:
    issue_data = dict(pending.get("issue_data", {}))
    uploaded_files = list(pending.get("uploaded_files", []))

    with st.container(border=True):
        st.subheader("Confirm Issue Report")
        st.caption(
            "Nothing has been saved yet. Confirming creates the Issue record and "
            "changes the unit marker to the customizable Issue colour."
        )
        summary = pd.DataFrame(
            [
                ("Serial Number", clean_text(issue_data.get("Serial Number")) or "—"),
                ("Location", clean_text(issue_data.get("Location")) or "—"),
                ("Issue Type", clean_text(issue_data.get("Issue Type")) or "—"),
                ("Priority", clean_text(issue_data.get("Priority")) or "Medium"),
                ("Reported By", clean_text(issue_data.get("Reported By")) or "—"),
                ("Evidence Photos", str(len(uploaded_files))),
                ("Marker Change", "→ Issue colour"),
            ],
            columns=["Item", "Value"],
        )
        st.dataframe(summary, width="stretch", hide_index=True)
        description = clean_text(issue_data.get("Detailed Description"))
        if description:
            st.markdown("**Description**")
            st.write(description)

        back_col, confirm_col = st.columns(2)
        with back_col:
            if st.button(
                "Back to Edit",
                width="stretch",
                key="cancel_issue_confirmation",
            ):
                st.session_state.pop("report_pending_submission", None)
                st.rerun()
        with confirm_col:
            if st.button(
                "Confirm and Report",
                type="primary",
                width="stretch",
                key="confirm_issue_submission",
            ):
                try:
                    issue_id = create_issue(
                        issue_csv_file,
                        issue_data=issue_data,
                        uploaded_files=uploaded_files,
                    )
                except Exception as error:
                    st.error(f"Failed to save the Issue: {error}")
                    return

                clear_report_form_state()
                st.session_state["report_issue_success_message"] = (
                    f"Issue submitted successfully. Issue ID: {issue_id}. "
                    "The unit marker now follows the Issue colour definition."
                )
                st.session_state["report_last_issue_id"] = issue_id
                st.rerun()


def render_report_issue_page(
    aed_csv_file: str | Path = "aed_data.csv",
    issue_csv_file: str | Path = "issue_records.csv",
) -> None:
    page_header(
        "Report Issue",
        "Create the initial Issue record and preserve the evidence required for assignment, resolution and verification.",
        eyebrow="ISSUE WORKFLOW · REPORT",
        chip="EVIDENCE-FIRST REPORTING",
        capabilities=[
            ("Identify the AED", "Search the master list or receive a pre-filled unit from Map or Checklist."),
            ("Describe the condition", "Record issue type, priority and precise observations from the site."),
            ("Preserve evidence", "Attach photos and create a traceable Issue ID for follow-up."),
        ],
    )

    success_message = st.session_state.pop("report_issue_success_message", "")
    if success_message:
        st.success(success_message)
        last_issue_id = clean_text(st.session_state.get("report_last_issue_id", ""))
        if last_issue_id and st.button(
            "Open this Issue for processing",
            type="primary",
            width="content",
            key="report_open_created_issue",
        ):
            st.session_state["selected_issue_id"] = last_issue_id
            st.session_state["page"] = "Issues"
            st.rerun()

    try:
        data = load_aed_data(aed_csv_file)
    except FileNotFoundError:
        st.error(f"Cannot find '{aed_csv_file}'.")
        return
    except pd.errors.EmptyDataError:
        st.error(f"'{aed_csv_file}' is empty.")
        return
    except Exception as error:
        st.error(f"Failed to load AED data: {error}")
        return

    apply_map_report_target(data)

    map_message = st.session_state.pop("report_map_target_message", "")
    map_error = st.session_state.pop("report_map_target_error", "")
    if map_message:
        st.success(map_message)
    if map_error:
        st.error(map_error)

    prefill = st.session_state.get("report_issue_prefill")
    initialise_report_state(prefill)

    if prefill:
        notice_col, clear_col = st.columns([5, 1.4])
        with notice_col:
            prefill_source = clean_text(prefill.get("Source")) or "another page"
            st.info(
                f"AED information was carried over from {prefill_source}. "
                "Every field remains editable."
            )
        with clear_col:
            if st.button("Search Another AED", width="stretch"):
                clear_report_form_state()
                st.rerun()
    else:
        with st.container(border=True):
            st.subheader("Search AED")
            search_keyword = st.text_input(
                "Search AED",
                placeholder="Enter part of the Serial Number, Location, or Postal Code",
                key="report_issue_search_keyword",
            )
            matching_data = find_matching_aeds(data, search_keyword)

            if clean_text(search_keyword):
                if matching_data.empty:
                    st.warning("No matching AED units found.")
                else:
                    result_options: dict[str, int] = {}
                    for row_index, row in matching_data.iterrows():
                        label = (
                            f"{clean_text(row['Serial Number']) or 'No serial'} | "
                            f"{clean_text(row['Location']) or 'No location'} | "
                            f"{clean_text(row['Postal Code']) or 'No postal code'}"
                        )
                        result_options[label] = int(row_index)

                    selected_option = st.selectbox(
                        "Select AED",
                        options=list(result_options.keys()),
                        key="report_issue_selected_aed",
                    )
                    if st.button("Use Selected AED", type="primary"):
                        load_selected_aed_into_form(
                            data.loc[result_options[selected_option]]
                        )
                        st.rerun()

    st.divider()

    with st.form("report_issue_form", clear_on_submit=False):
        st.subheader("Reported AED Information")
        st.caption(
            "These values are saved with this Issue only. They do not update "
            "aed_data.csv."
        )

        left, right = st.columns(2)
        with left:
            reported_by = st.text_input(
                "Reported By *",
                key="report_technician",
                help="The person who observed and submitted the Issue.",
            )
            serial_number = st.text_input(
                "Serial Number", key="report_serial_number"
            )
            model = st.text_input("Model", key="report_model")
            location = st.text_input("Location", key="report_location")

        with right:
            postal_code = st.text_input(
                "Postal Code", key="report_postal_code"
            )
            lift_lobby = st.text_input(
                "Lift Lobby", key="report_lift_lobby"
            )
            is_loaner = st.radio(
                "Is this a loaner?",
                options=["No", "Yes"],
                horizontal=True,
                key="report_is_loaner",
            )
            source = st.text_input(
                "Source", key="report_source", disabled=True
            )

        st.subheader("Issue Details")
        detail_left, detail_right = st.columns([2, 1])
        with detail_left:
            issue_types = st.multiselect(
                "Issue Type *",
                options=ISSUE_OPTIONS,
                placeholder="Select one or more issue types",
                key="report_issue_types",
            )
        with detail_right:
            priority = st.selectbox(
                "Priority",
                options=PRIORITY_OPTIONS,
                index=PRIORITY_OPTIONS.index("Medium"),
                key="report_priority",
            )

        detailed_description = st.text_area(
            "Detailed Description",
            placeholder=(
                "Describe what was observed. Description is required when Other "
                "is selected."
            ),
            height=140,
            key="report_description",
        )

        uploaded_files = st.file_uploader(
            "Initial Evidence Photos",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            help=(
                "These photos are saved as Report-stage evidence. Resolution "
                "photos will be submitted separately later."
            ),
            key="report_uploaded_photos",
        )

        if uploaded_files:
            preview_columns = st.columns(min(len(uploaded_files), 3))
            for index, uploaded_file in enumerate(uploaded_files):
                with preview_columns[index % len(preview_columns)]:
                    st.image(
                        uploaded_file,
                        caption=uploaded_file.name,
                        width="stretch",
                    )

        submit_button = st.form_submit_button(
            "Submit Issue",
            type="primary",
            width="stretch",
        )

    if submit_button:
        if not clean_text(reported_by):
            st.warning("Please enter Reported By.")
            return
        if not issue_types:
            st.warning("Please select at least one Issue Type.")
            return
        if "Other" in issue_types and not clean_text(detailed_description):
            st.warning("Please describe the Issue when Other is selected.")
            return

        st.session_state["report_pending_submission"] = {
            "issue_data": {
                "Source": source,
                "Reported By": reported_by,
                "Serial Number": serial_number,
                "Model": model,
                "Location": location,
                "Postal Code": postal_code,
                "Lift Lobby": lift_lobby,
                "Is Loaner": is_loaner,
                "Issue Type": "; ".join(issue_types),
                "Detailed Description": detailed_description,
                "Priority": priority,
            },
            "uploaded_files": list(uploaded_files or []),
        }

    pending = st.session_state.get("report_pending_submission")
    if isinstance(pending, dict):
        st.divider()
        _render_issue_confirmation(issue_csv_file, pending)
