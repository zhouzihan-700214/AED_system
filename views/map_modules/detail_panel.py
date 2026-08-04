from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from utils.streamlit_utils import rerun_app
from utils.text_utils import clean_text
from views.map_modules.helpers import format_display_date, safe_html
from views.map_modules.renderer import marker_color_for_row
from views.map_modules.status_service import (
    COLOR_EMOJI,
    COLOR_PALETTE,
    UNIT_STATE_COLUMNS,
    active_statuses,
    load_plan_records,
    load_unit_state,
    now_text,
    save_plan_records,
    save_unit_state,
    status_color_lookup,
    status_name_for_workflow_role,
    today_text,
)


def save_selected_status(
    map_type: str,
    plan_id: str,
    serial: str,
    new_status: str,
    definitions: pd.DataFrame,
    state_file: str | Path,
    plan_file: str | Path,
) -> None:
    completed_status = status_name_for_workflow_role(
        definitions,
        "Completed",
    )

    if map_type == "All Units Map":
        state = load_unit_state(state_file)
        mask = (
            state["Serial Number"]
            .astype(str)
            .str.casefold()
            .eq(serial.casefold())
        )

        if mask.any():
            state.loc[mask, "Status"] = new_status
            state.loc[mask, "Updated At"] = now_text()
        else:
            state = pd.concat(
                [
                    state,
                    pd.DataFrame(
                        [
                            {
                                "Serial Number": serial,
                                "Status": new_status,
                                "Color Override": "",
                                "Updated At": now_text(),
                            }
                        ],
                        columns=UNIT_STATE_COLUMNS,
                    ),
                ],
                ignore_index=True,
            )

        save_unit_state(state, state_file)
        return

    plans = load_plan_records(plan_file)
    mask = (
        plans["Plan ID"].eq(plan_id)
        &
        plans["Serial Number"]
        .astype(str)
        .str.casefold()
        .eq(serial.casefold())
    )

    if not mask.any():
        raise ValueError(
            "The selected AED is not present in this monthly plan."
        )

    plans.loc[mask, "PM Status"] = new_status

    if (
        completed_status
        and new_status.casefold()
        == completed_status.casefold()
    ):
        plans.loc[
            mask
            &
            plans["Completed Date"].astype(str).str.strip().eq(""),
            "Completed Date",
        ] = today_text()
    else:
        plans.loc[mask, "Completed Date"] = ""

    save_plan_records(plans, plan_file)

def save_selected_color(
    map_type: str,
    plan_id: str,
    serial: str,
    selected_color: str,
    state_file: str | Path,
    plan_file: str | Path,
) -> None:
    override = (
        ""
        if selected_color == "Automatic"
        else selected_color
    )

    if map_type == "All Units Map":
        state = load_unit_state(state_file)
        mask = (
            state["Serial Number"]
            .astype(str)
            .str.casefold()
            .eq(serial.casefold())
        )

        if not mask.any():
            raise ValueError(
                "The selected AED does not have an All Units Map state."
            )

        state.loc[mask, "Color Override"] = override
        state.loc[mask, "Updated At"] = now_text()
        save_unit_state(state, state_file)
        return

    plans = load_plan_records(plan_file)
    mask = (
        plans["Plan ID"].eq(plan_id)
        &
        plans["Serial Number"]
        .astype(str)
        .str.casefold()
        .eq(serial.casefold())
    )

    if not mask.any():
        raise ValueError(
            "The selected AED is not present in this monthly plan."
        )

    plans.loc[mask, "Color Override"] = override
    save_plan_records(plans, plan_file)

def detail_row_html(
    label: str,
    value: Any,
) -> str:
    return (
        '<div class="aed-detail-label">'
        f"{safe_html(label)}"
        "</div>"
        '<div class="aed-detail-value">'
        f"{safe_html(value) or '—'}"
        "</div>"
    )

def selected_status_color(
    selected_row: pd.Series,
    definitions: pd.DataFrame,
) -> str:
    color_name = marker_color_for_row(
        selected_row,
        definitions,
    )

    return COLOR_PALETTE.get(
        color_name,
        COLOR_PALETTE["Gray"],
    )

def navigate_to_pm(
    selected_row: pd.Series,
) -> None:
    st.session_state["map_pm_target"] = {
        "Serial Number": clean_text(
            selected_row.get("Serial Number", "")
        ),
        "Postal Code": clean_text(
            selected_row.get("Postal Code", "")
        ),
    }
    st.session_state["page"] = "PM Checklist"
    rerun_app()

def navigate_to_issue(
    selected_row: pd.Series,
) -> None:
    st.session_state["map_report_target"] = {
        "Serial Number": clean_text(
            selected_row.get("Serial Number", "")
        ),
        "Postal Code": clean_text(
            selected_row.get("Postal Code", "")
        ),
    }
    st.session_state["page"] = "Report Issue"
    rerun_app()

def render_selected_aed_panel(
    selected_row: pd.Series | None,
    map_type: str,
    plan_id: str,
    definitions: pd.DataFrame,
    state_file: str | Path,
    plan_file: str | Path,
) -> None:
    """
    Render a compact selected-AED panel.

    Status and marker color are placed near the top and saved together.
    Less-frequently used fields are kept inside a collapsed details section,
    so the user does not need to scroll to reach the marker-color controls.
    """

    with st.container(border=True):
        st.markdown(
            '<div class="aed-side-title">Selected AED</div>',
            unsafe_allow_html=True,
        )

        if selected_row is None:
            st.info(
                "Click a marker to view and edit its AED details."
            )
            return

        serial = clean_text(
            selected_row.get("Serial Number", "")
        )
        status = clean_text(
            selected_row.get("PM Status", "")
        )
        location = clean_text(
            selected_row.get("Location", "")
        )
        model = clean_text(
            selected_row.get("Model", "")
        )
        status_color_name = status_color_lookup(
            definitions
        ).get(
            status.casefold(),
            "Gray",
        )
        status_color_hex = COLOR_PALETTE.get(
            status_color_name,
            COLOR_PALETTE["Gray"],
        )

        st.markdown(
            f"""
            <div class="aed-selected-summary">
                <div class="selected-aed-heading">
                    <div class="selected-aed-pin">⌖</div>
                    <div class="selected-aed-serial">
                        {safe_html(serial)}
                    </div>
                </div>
                <div class="aed-selected-location">
                    {safe_html(model) or "No model"}
                    ·
                    {safe_html(location) or "No location"}
                </div>
                <div class="aed-status-line">
                    <span
                        class="aed-status-line-dot"
                        style="background:{status_color_hex};"
                    ></span>
                    {safe_html(status) or "No status"}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Keep the most useful operational details visible.
        key_details = [
            (
                "Postal Code",
                selected_row.get("Postal Code", ""),
            ),
            (
                "Lift Lobby",
                selected_row.get("Lift Lobby", ""),
            ),
            (
                "Previous Service",
                format_display_date(
                    selected_row.get(
                        "PM Completed Date",
                        "",
                    )
                ),
            ),
        ]

        if map_type == "Monthly PM Map":
            key_details.append(
                (
                    "Planned Date",
                    format_display_date(
                        selected_row.get(
                            "Planned Date",
                            "",
                        )
                    ),
                )
            )
        else:
            key_details.append(
                (
                    "Next PM Date",
                    format_display_date(
                        selected_row.get(
                            "Next PM Date",
                            "",
                        )
                    ),
                )
            )

        key_detail_html = "".join(
            (
                '<div class="aed-key-detail">'
                '<div class="aed-key-detail-label">'
                f"{safe_html(label)}"
                "</div>"
                '<div class="aed-key-detail-value">'
                f"{safe_html(value) or '—'}"
                "</div>"
                "</div>"
            )
            for label, value in key_details
        )

        st.markdown(
            '<div class="aed-key-details">'
            + key_detail_html
            + "</div>",
            unsafe_allow_html=True,
        )

        active = active_statuses(definitions)
        status_options = active[
            "Status Name"
        ].tolist()

        if status not in status_options and status:
            status_options.append(status)

        selected_status_index = (
            status_options.index(status)
            if status in status_options
            else 0
        )

        current_override = clean_text(
            selected_row.get(
                "Color Override",
                "",
            )
        ).title()

        role_lookup = {
            clean_text(row["Status Name"]).casefold(): clean_text(row["Workflow Role"])
            for _, row in definitions.iterrows()
        }
        current_role = role_lookup.get(status.casefold(), "None")
        manual_colour_allowed = current_role in {"Pending", "None", ""}

        color_options = [
            "Automatic",
            *list(COLOR_PALETTE.keys()),
        ]

        status_column, color_column = st.columns(
            [1.15, 1],
            gap="small",
        )

        with status_column:
            chosen_status = st.selectbox(
                "Status",
                options=status_options,
                index=selected_status_index,
                key=(
                    f"selected_status_{map_type}_"
                    f"{plan_id}_{serial}"
                ),
            )

        color_widget_key = (
            f"marker_color_select_{map_type}_"
            f"{plan_id}_{serial}"
        )
        saved_color_choice = (
            current_override
            if current_override in COLOR_PALETTE
            else "Automatic"
        )
        if color_widget_key not in st.session_state:
            st.session_state[color_widget_key] = saved_color_choice
        if not manual_colour_allowed:
            st.session_state[color_widget_key] = "Automatic"

        with color_column:
            chosen_color = st.selectbox(
                "Marker Color",
                options=color_options,
                format_func=lambda value: (
                    (
                        f"Automatic ({status_color_name})"
                        if value == "Automatic"
                        else f"{COLOR_EMOJI.get(value, '●')} {value}"
                    )
                ),
                key=color_widget_key,
                disabled=not manual_colour_allowed,
                help=(
                    "Planning colours save immediately and do not update the Excel sheet."
                    if manual_colour_allowed
                    else "This operational colour is controlled by PM and Issue status. Change its definition in Manage Statuses."
                ),
            )

        # Planning colour changes are deliberately auto-saved: no Save button,
        # no confirmation dialog, and no Excel write-back.
        if manual_colour_allowed and chosen_color != saved_color_choice:
            try:
                save_selected_color(
                    map_type=map_type,
                    plan_id=plan_id,
                    serial=serial,
                    selected_color=chosen_color,
                    state_file=state_file,
                    plan_file=plan_file,
                )
                st.session_state["aed_map_notice"] = (
                    f"{serial} marker colour changed to {chosen_color}."
                )
                rerun_app()
            except (ValueError, OSError) as error:
                st.error(str(error))

        st.markdown(
            '<div class="aed-control-caption">'
            + (
                "Planning colour saves immediately. Status changes still require confirmation."
                if manual_colour_allowed
                else "Operational colour follows the workflow status and cannot be overridden here."
            )
            + "</div>",
            unsafe_allow_html=True,
        )

        if st.button(
            "Confirm Status Change",
            type="primary",
            width="stretch",
            key=(
                f"save_status_color_{map_type}_"
                f"{plan_id}_{serial}"
            ),
            disabled=chosen_status == status,
        ):
            try:
                save_selected_status(
                    map_type=map_type,
                    plan_id=plan_id,
                    serial=serial,
                    new_status=chosen_status,
                    definitions=definitions,
                    state_file=state_file,
                    plan_file=plan_file,
                )
                chosen_role = role_lookup.get(chosen_status.casefold(), "None")
                if chosen_role not in {"Pending", "None", ""}:
                    save_selected_color(
                        map_type=map_type,
                        plan_id=plan_id,
                        serial=serial,
                        selected_color="Automatic",
                        state_file=state_file,
                        plan_file=plan_file,
                    )

                st.session_state["aed_map_notice"] = (
                    f"{serial} status changed from {status or '—'} to {chosen_status}."
                )
                rerun_app()

            except (ValueError, OSError) as error:
                st.error(str(error))

        action_left, action_right = st.columns(2)

        with action_left:
            if st.button(
                "▶ Start PM",
                type="primary",
                width="stretch",
                key=(
                    f"right_start_pm_"
                    f"{map_type}_{plan_id}_{serial}"
                ),
            ):
                navigate_to_pm(selected_row)

        with action_right:
            if st.button(
                "⚠ Report Issue",
                width="stretch",
                key=(
                    f"right_report_issue_"
                    f"{map_type}_{plan_id}_{serial}"
                ),
            ):
                navigate_to_issue(selected_row)

        with st.expander(
            "View full AED details",
            expanded=False,
        ):
            details = [
                ("Serial Number", serial),
                ("Model", model),
                ("Location", location),
                (
                    "Postal Code",
                    selected_row.get("Postal Code", ""),
                ),
                (
                    "Lift Lobby",
                    selected_row.get("Lift Lobby", ""),
                ),
            ]

            if map_type == "Monthly PM Map":
                plan_month = clean_text(
                    selected_row.get("Plan Month", "")
                )

                try:
                    readable_plan_month = (
                        pd.Period(
                            plan_month,
                            freq="M",
                        )
                        .to_timestamp()
                        .strftime("%B %Y")
                    )
                except Exception:
                    readable_plan_month = (
                        plan_month
                        or "—"
                    )

                details.extend(
                    [
                        ("Plan Month", readable_plan_month),
                        (
                            "Planned Date",
                            format_display_date(
                                selected_row.get(
                                    "Planned Date",
                                    "",
                                )
                            ),
                        ),
                    ]
                )

            details.extend(
                [
                    ("PM Status", status),
                    (
                        "Previous Service Date",
                        format_display_date(
                            selected_row.get(
                                "PM Completed Date",
                                "",
                            )
                        ),
                    ),
                ]
            )

            if map_type == "Monthly PM Map":
                details.append(
                    (
                        "Current Plan Completed Date",
                        format_display_date(
                            selected_row.get(
                                "Completed Date",
                                "",
                            )
                        ),
                    )
                )
            else:
                details.append(
                    (
                        "Next PM Date",
                        format_display_date(
                            selected_row.get(
                                "Next PM Date",
                                "",
                            )
                        ),
                    )
                )

            details.extend(
                [
                    (
                        "Assigned To",
                        selected_row.get(
                            "Assigned To",
                            "",
                        ),
                    ),
                    (
                        "Loaner",
                        selected_row.get(
                            "Is Loaner",
                            "No",
                        ),
                    ),
                ]
            )

            detail_html = "".join(
                detail_row_html(label, value)
                for label, value in details
            )

            st.markdown(
                '<div class="aed-detail-grid">'
                + detail_html
                + "</div>",
                unsafe_allow_html=True,
            )
