from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import folium
import pandas as pd
from folium.plugins import BeautifyIcon, Fullscreen, LocateControl
from streamlit_folium import st_folium

from utils.text_utils import clean_text
from views.map_modules.helpers import safe_html
from views.map_modules.status_service import (
    COLOR_PALETTE,
    active_statuses,
    status_color_lookup,
)


def marker_color_for_row(
    row: pd.Series,
    definitions: pd.DataFrame,
) -> str:
    override = clean_text(
        row.get("Color Override", "")
    ).title()

    if override in COLOR_PALETTE:
        return override

    lookup = status_color_lookup(definitions)
    status = clean_text(
        row.get("PM Status", "")
    ).casefold()

    return lookup.get(status, "Gray")

def create_marker_icon(
    color_name: str,
    selected: bool,
) -> BeautifyIcon:
    color_hex = COLOR_PALETTE.get(
        color_name,
        COLOR_PALETTE["Gray"],
    )

    return BeautifyIcon(
        icon_shape="marker",
        border_width=(
            4
            if selected
            else 2
        ),
        border_color=(
            "#101828"
            if selected
            else "#FFFFFF"
        ),
        text_color=(
            "#101828"
            if color_name in {"Yellow", "Lime", "Cyan"}
            else "#FFFFFF"
        ),
        background_color=color_hex,
        number="+",
    )

def create_popup(
    row: pd.Series,
) -> folium.Popup:
    serial = safe_html(
        row.get("Serial Number", "")
    )
    model = safe_html(
        row.get("Model", "")
    )
    location = safe_html(
        row.get("Location", "")
    )
    postal = safe_html(
        row.get("Postal Code", "")
    )
    status = safe_html(
        row.get("PM Status", "")
    )

    raw_serial = clean_text(
        row.get("Serial Number", "")
    )
    raw_postal = clean_text(
        row.get("Postal Code", "")
    )

    pm_query = urlencode(
        {
            "page": "PM Checklist",
            "serial": raw_serial,
            "postal_code": raw_postal,
        }
    )
    issue_query = urlencode(
        {
            "page": "Report Issue",
            "serial": raw_serial,
            "postal_code": raw_postal,
        }
    )

    popup_html = f"""
    <div style="
        width: 250px;
        font-family: Arial, sans-serif;
        color: #1f2937;
        line-height: 1.45;
    ">
        <div style="
            margin-bottom: 9px;
            font-size: 17px;
            font-weight: 700;
        ">
            {serial or "AED Unit"}
        </div>

        <div style="font-size: 12px;">
            <b>Model:</b> {model or "-"}<br>
            <b>Location:</b> {location or "-"}<br>
            <b>Postal Code:</b> {postal or "-"}<br>
            <b>PM Status:</b> {status or "-"}
        </div>

        <div style="
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 7px;
            margin-top: 12px;
        ">
            <a
                href="?{pm_query}"
                target="_top"
                style="
                    padding: 8px;
                    border-radius: 6px;
                    background: #1f5eea;
                    color: white;
                    font-size: 11px;
                    font-weight: 700;
                    text-align: center;
                    text-decoration: none;
                "
            >
                Start PM
            </a>

            <a
                href="?{issue_query}"
                target="_top"
                style="
                    padding: 8px;
                    border: 1px solid #f04438;
                    border-radius: 6px;
                    background: white;
                    color: #d92d20;
                    font-size: 11px;
                    font-weight: 700;
                    text-align: center;
                    text-decoration: none;
                "
            >
                Report Issue
            </a>
        </div>
    </div>
    """

    return folium.Popup(
        popup_html,
        max_width=330,
    )

def build_legend_html(
    dataframe: pd.DataFrame,
    definitions: pd.DataFrame,
) -> str:
    rows = []

    for _, status_row in active_statuses(
        definitions
    ).iterrows():
        status_name = clean_text(
            status_row["Status Name"]
        )
        count = int(
            dataframe["PM Status"]
            .astype(str)
            .str.casefold()
            .eq(status_name.casefold())
            .sum()
        )

        if count == 0:
            continue

        color_name = clean_text(
            status_row["Marker Color"]
        ).title()
        color_hex = COLOR_PALETTE.get(
            color_name,
            COLOR_PALETTE["Gray"],
        )

        rows.append(
            f"""
            <div style="
                display:flex;
                align-items:center;
                gap:7px;
                margin:4px 0;
            ">
                <span style="
                    width:10px;
                    height:10px;
                    border-radius:50%;
                    background:{color_hex};
                    display:inline-block;
                "></span>
                <span>{safe_html(status_name)} ({count})</span>
            </div>
            """
        )

    if not rows:
        return ""

    return f"""
    <div style="
        position: fixed;
        right: 18px;
        bottom: 20px;
        z-index: 9999;
        min-width: 145px;
        padding: 10px 12px;
        border: 1px solid #e4e7ec;
        border-radius: 8px;
        background: rgba(255,255,255,0.96);
        box-shadow: 0 4px 16px rgba(16,24,40,0.12);
        color: #344054;
        font-family: Arial, sans-serif;
        font-size: 11px;
    ">
        <div style="
            margin-bottom: 5px;
            color:#101828;
            font-weight:700;
        ">
            Legend
        </div>
        {''.join(rows)}
    </div>
    """

def create_map(
    dataframe: pd.DataFrame,
    definitions: pd.DataFrame,
    selected_serial: str,
) -> folium.Map:
    mapped = dataframe.dropna(
        subset=[
            "Latitude",
            "Longitude",
        ]
    ).copy()

    if mapped.empty:
        raise ValueError(
            "No valid coordinates were found for the current selection."
        )

    map_object = folium.Map(
        location=[
            mapped["Latitude"].mean(),
            mapped["Longitude"].mean(),
        ],
        zoom_start=11,
        control_scale=True,
        tiles="OpenStreetMap",
    )

    Fullscreen(
        position="topright",
    ).add_to(map_object)

    LocateControl(
        position="topright",
        strings={
            "title": "Show my location",
        },
    ).add_to(map_object)

    for _, row in mapped.iterrows():
        serial = clean_text(
            row.get("Serial Number", "")
        )
        color_name = marker_color_for_row(
            row,
            definitions,
        )

        folium.Marker(
            location=[
                float(row["Latitude"]),
                float(row["Longitude"]),
            ],
            tooltip=serial or "AED",
            popup=create_popup(row),
            icon=create_marker_icon(
                color_name=color_name,
                selected=(
                    serial.casefold()
                    == clean_text(
                        selected_serial
                    ).casefold()
                ),
            ),
        ).add_to(map_object)

    if len(mapped) > 1:
        map_object.fit_bounds(
            mapped[
                [
                    "Latitude",
                    "Longitude",
                ]
            ].values.tolist(),
            padding=(28, 28),
        )

    legend_html = build_legend_html(
        mapped,
        definitions,
    )

    if legend_html:
        map_object.get_root().html.add_child(
            folium.Element(legend_html)
        )

    return map_object

def render_folium(
    map_object: folium.Map,
    map_key: str,
) -> dict[str, Any]:
    try:
        result = st_folium(
            map_object,
            width=None,
            height=540,
            returned_objects=[
                "last_object_clicked_tooltip",
            ],
            key=map_key,
        )
    except TypeError:
        result = st_folium(
            map_object,
            width=None,
            height=540,
            key=map_key,
        )

    return result or {}
