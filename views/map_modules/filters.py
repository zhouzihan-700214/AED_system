from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from utils.text_utils import clean_text


MAP_FILTER_KEYS = {
    "model": "aed_map_models",
    "assignee": "aed_map_assignees",
}

MAP_FILTER_COLUMNS = {
    "model": "Model",
    "assignee": "Assigned To",
}


def filter_without_status(
    dataframe: pd.DataFrame,
    keyword: str,
    selected_models: list[str],
    selected_assignees: list[str],
) -> pd.DataFrame:
    result = dataframe.copy()
    keyword_clean = clean_text(keyword).casefold()

    if keyword_clean:
        searchable_columns = [
            column
            for column in [
                "Serial Number",
                "Model",
                "Location",
                "Postal Code",
                "Lift Lobby",
                "Assigned To",
                "PM Status",
            ]
            if column in result.columns
        ]

        mask = pd.Series(
            False,
            index=result.index,
        )

        for column in searchable_columns:
            mask |= (
                result[column]
                .astype(str)
                .str.casefold()
                .str.contains(
                    keyword_clean,
                    na=False,
                    regex=False,
                )
            )

        result = result[mask]

    if selected_models and "Model" in result.columns:
        result = result[
            result["Model"].isin(selected_models)
        ]

    if (
        selected_assignees
        and "Assigned To" in result.columns
    ):
        result = result[
            result["Assigned To"].isin(
                selected_assignees
            )
        ]

    return result

def apply_status_filter(
    dataframe: pd.DataFrame,
    status_name: str,
) -> pd.DataFrame:
    if not clean_text(status_name):
        return dataframe.copy()

    return dataframe[
        dataframe["PM Status"]
        .astype(str)
        .str.casefold()
        .eq(status_name.casefold())
    ].copy()

def unique_clean_values(
    dataframe: pd.DataFrame,
    column: str,
) -> list[str]:
    if column not in dataframe.columns:
        return []

    return sorted(
        {
            clean_text(value)
            for value in dataframe[column]
            if clean_text(value)
        },
        key=str.casefold,
    )

def _map_filter_selections_from_state() -> dict[str, list[str]]:
    """Return the current AED Map categorical selections as clean lists."""

    selections: dict[str, list[str]] = {}

    for filter_name, session_key in MAP_FILTER_KEYS.items():
        value = st.session_state.get(session_key, [])

        if isinstance(value, (list, tuple, set)):
            selections[filter_name] = [
                clean_text(item)
                for item in value
                if clean_text(item)
            ]
        elif clean_text(value):
            selections[filter_name] = [clean_text(value)]
        else:
            selections[filter_name] = []

    return selections

def _mark_map_filter_changed(filter_name: str) -> None:
    """Remember the newest map filter so incompatible older values clear first."""

    st.session_state["aed_map_last_changed_filter"] = filter_name

def linked_map_filter_options(
    dataframe: pd.DataFrame,
    target_filter: str,
    keyword: str,
    status_name: str,
    selections: dict[str, list[str]] | None = None,
) -> list[str]:
    """Return one map filter's options after applying every other filter."""

    if target_filter not in MAP_FILTER_KEYS:
        valid_names = ", ".join(MAP_FILTER_KEYS)
        raise ValueError(
            f"Unknown AED Map filter '{target_filter}'. "
            f"Expected one of: {valid_names}."
        )

    active = {
        name: list(values or [])
        for name, values in (selections or {}).items()
        if name in MAP_FILTER_KEYS
    }

    for name in MAP_FILTER_KEYS:
        active.setdefault(name, [])

    # Excluding the target itself keeps all values compatible with the other
    # active filters and still allows multiple values in the same multiselect.
    active[target_filter] = []

    filtered = filter_without_status(
        dataframe=dataframe,
        keyword=keyword,
        selected_models=active["model"],
        selected_assignees=active["assignee"],
    )
    filtered = apply_status_filter(
        dataframe=filtered,
        status_name=status_name,
    )

    return unique_clean_values(
        filtered,
        MAP_FILTER_COLUMNS[target_filter],
    )

def _normalise_map_filter_state(
    dataframe: pd.DataFrame,
    keyword: str,
    status_name: str,
) -> None:
    """Remove map choices that no longer match the current filter scope."""

    selections = _map_filter_selections_from_state()
    last_changed = st.session_state.get(
        "aed_map_last_changed_filter"
    )

    # Preserve the newest user action when possible. It is first checked only
    # against the map scope, keyword and status; incompatible older choices are
    # then cleared from the other filter.
    if last_changed in MAP_FILTER_KEYS:
        empty_selections = {
            name: []
            for name in MAP_FILTER_KEYS
        }
        base_options = linked_map_filter_options(
            dataframe=dataframe,
            target_filter=last_changed,
            keyword=keyword,
            status_name=status_name,
            selections=empty_selections,
        )
        allowed = set(base_options)
        valid = [
            value
            for value in selections[last_changed]
            if value in allowed
        ]

        if valid != selections[last_changed]:
            selections[last_changed] = valid
            st.session_state[
                MAP_FILTER_KEYS[last_changed]
            ] = valid

    order = [
        name
        for name in MAP_FILTER_KEYS
        if name != last_changed
    ]

    if last_changed in MAP_FILTER_KEYS:
        order.append(last_changed)

    # Repeating a few times settles chains after map type, plan, keyword or
    # status changes shrink the available dataset.
    for _ in range(len(MAP_FILTER_KEYS) + 1):
        changed = False

        for filter_name in order:
            options = linked_map_filter_options(
                dataframe=dataframe,
                target_filter=filter_name,
                keyword=keyword,
                status_name=status_name,
                selections=selections,
            )
            allowed = set(options)
            valid = [
                value
                for value in selections[filter_name]
                if value in allowed
            ]

            if valid != selections[filter_name]:
                selections[filter_name] = valid
                st.session_state[
                    MAP_FILTER_KEYS[filter_name]
                ] = valid
                changed = True

        if not changed:
            break

def reset_aed_map_filters() -> None:
    """Restore the AED Map page to its initial unfiltered state."""

    defaults: dict[str, Any] = {
        "aed_map_type": "All Units Map",
        "aed_map_keyword": "",
        "aed_map_models": [],
        "aed_map_assignees": [],
        "aed_map_status_filter": "",
        "aed_map_last_changed_filter": None,
    }

    for key, value in defaults.items():
        st.session_state[key] = value

    # These widgets or selections only exist in particular map states. Removing
    # them lets Streamlit choose a valid default when they appear again.
    st.session_state.pop("aed_map_plan_id", None)
    st.session_state.pop("aed_map_selected_serial", None)
