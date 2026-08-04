from pathlib import Path
import html

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium


# =========================================================
# 文件位置
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

CSV_FILE = BASE_DIR / "aed_data_with_coordinates.csv"


# =========================================================
# 辅助函数
# =========================================================

def safe_text(value) -> str:
    """
    把 CSV 内容转换成可安全显示在地图 Popup 中的文字。
    """

    if pd.isna(value):
        return ""

    return html.escape(str(value).strip())


def load_aed_data() -> pd.DataFrame:
    """
    读取已经包含经纬度的 AED CSV。
    """

    if not CSV_FILE.exists():
        raise FileNotFoundError(
            f"找不到文件：{CSV_FILE}"
        )

    dataframe = pd.read_csv(
        CSV_FILE,
        dtype={
            "Postal Code": str,
        },
    )

    required_columns = {
        "Serial Number",
        "Location",
        "Postal Code",
        "Latitude",
        "Longitude",
    }

    missing_columns = (
        required_columns - set(dataframe.columns)
    )

    if missing_columns:
        raise ValueError(
            "CSV 缺少以下栏目："
            + ", ".join(sorted(missing_columns))
        )

    # 确保经纬度是数字
    dataframe["Latitude"] = pd.to_numeric(
        dataframe["Latitude"],
        errors="coerce",
    )

    dataframe["Longitude"] = pd.to_numeric(
        dataframe["Longitude"],
        errors="coerce",
    )

    return dataframe


def create_popup(row: pd.Series) -> folium.Popup:
    """
    创建点击 Marker 后显示的 AED 信息。
    """

    serial_number = safe_text(
        row["Serial Number"]
    )

    location = safe_text(
        row["Location"]
    )

    postal_code = safe_text(
        row["Postal Code"]
    )

    model = safe_text(
        row.get("Model", "")
    )

    lift_lobby = safe_text(
        row.get("Lift Lobby", "")
    )

    popup_html = f"""
    <div style="
        width: 260px;
        font-family: Arial, sans-serif;
        line-height: 1.5;
    ">
        <h4 style="margin-bottom: 8px;">
            {serial_number}
        </h4>

        <b>Model:</b> {model}<br>
        <b>Location:</b> {location}<br>
        <b>Postal Code:</b> {postal_code}<br>
        <b>Lift Lobby:</b> {lift_lobby}
    </div>
    """

    return folium.Popup(
        popup_html,
        max_width=320,
    )


def create_aed_map(
    dataframe: pd.DataFrame,
) -> folium.Map:
    """
    根据 AED 数据创建地图。
    """

    valid_data = dataframe.dropna(
        subset=[
            "Latitude",
            "Longitude",
        ]
    ).copy()

    if valid_data.empty:
        raise ValueError(
            "CSV 中没有可用的 Latitude 和 Longitude。"
        )

    # 使用所有 AED 坐标的平均值作为地图中心
    centre_latitude = (
        valid_data["Latitude"].mean()
    )

    centre_longitude = (
        valid_data["Longitude"].mean()
    )

    map_object = folium.Map(
        location=[
            centre_latitude,
            centre_longitude,
        ],
        zoom_start=11,
        control_scale=True,
    )

    for _, row in valid_data.iterrows():
        serial_number = safe_text(
            row["Serial Number"]
        )

        folium.Marker(
            location=[
                row["Latitude"],
                row["Longitude"],
            ],
            tooltip=serial_number,
            popup=create_popup(row),
            icon=folium.Icon(
                color="blue",
                icon="info-sign",
            ),
        ).add_to(map_object)

    # 自动调整地图范围，使所有 AED 都能显示
    map_object.fit_bounds(
        valid_data[
            ["Latitude", "Longitude"]
        ].values.tolist()
    )

    return map_object


# =========================================================
# Streamlit 页面
# =========================================================

st.set_page_config(
    page_title="AED Map Test",
    page_icon="📍",
    layout="wide",
)

st.title("AED Location Map")

st.caption(
    "AED locations generated from Singapore Postal Codes"
)

try:
    aed_data = load_aed_data()

    valid_count = (
        aed_data[
            ["Latitude", "Longitude"]
        ]
        .dropna()
        .shape[0]
    )

    missing_count = len(aed_data) - valid_count

    column1, column2 = st.columns(2)

    with column1:
        st.metric(
            "AED Markers",
            valid_count,
        )

    with column2:
        st.metric(
            "Missing Coordinates",
            missing_count,
        )

    aed_map = create_aed_map(aed_data)

    st_folium(
        aed_map,
        width=None,
        height=650,
    )

    if missing_count > 0:
        st.warning(
            f"{missing_count} 台 AED 没有有效坐标，"
            "因此没有显示在地图上。"
        )

except (FileNotFoundError, ValueError) as error:
    st.error(str(error))

except Exception as error:
    st.error(
        f"地图加载失败：{error}"
    )