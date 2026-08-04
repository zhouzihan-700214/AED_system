import streamlit as st


def apply_map_page_styles() -> None:
    st.markdown(
        """
        <style>
        .aed-map-title {
            margin: 0;
            color: #101828;
            font-size: 2rem;
            font-weight: 760;
            letter-spacing: -0.03em;
        }

        .aed-map-subtitle {
            margin-top: 0.2rem;
            margin-bottom: 1.1rem;
            color: #667085;
            font-size: 0.94rem;
        }

        .aed-plan-summary {
            margin: 0.15rem 0 0.75rem 0;
            color: #475467;
            font-size: 0.88rem;
            font-weight: 600;
        }

        .aed-helper-bar {
            margin: 0.2rem 0 0.65rem 0;
            padding: 0.65rem 0.8rem;
            border: 1px solid #dbe8ff;
            border-radius: 9px;
            background: #f4f8ff;
            color: #31568f;
            font-size: 0.82rem;
        }

        .selected-aed-heading {
            display: flex;
            align-items: center;
            gap: 0.55rem;
            margin-bottom: 0.8rem;
        }

        .selected-aed-pin {
            width: 31px;
            height: 31px;
            display: grid;
            place-items: center;
            border-radius: 50%;
            background: #eaf1ff;
            color: #1f5eea;
            font-weight: 800;
        }

        .selected-aed-serial {
            color: #101828;
            font-size: 1.18rem;
            font-weight: 750;
        }

        .aed-detail-grid {
            display: grid;
            grid-template-columns: minmax(112px, 0.85fr) minmax(120px, 1.15fr);
            gap: 0.48rem 0.8rem;
            margin-bottom: 0.8rem;
            font-size: 0.84rem;
        }

        .aed-detail-label {
            color: #667085;
        }

        .aed-detail-value {
            color: #1d2939;
            font-weight: 560;
            overflow-wrap: anywhere;
        }

        .aed-status-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            font-weight: 650;
        }

        .aed-status-dot {
            width: 8px;
            height: 8px;
            display: inline-block;
            border-radius: 50%;
        }

        .color-choice-caption {
            margin-top: -0.2rem;
            color: #667085;
            font-size: 0.78rem;
        }

        .status-editor-note {
            margin-top: 0.5rem;
            color: #667085;
            font-size: 0.78rem;
        }

        div[data-testid="stButton"] > button {
            border-radius: 8px;
        }

        div[data-testid="stMetric"] {
            border: 1px solid #eaecf0;
            border-radius: 10px;
            padding: 0.65rem;
            background: #ffffff;
        }

        iframe[title="streamlit_folium.st_folium"] {
            border: 1px solid #e4e7ec !important;
            border-radius: 12px !important;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
        }

        .aed-side-title {
            margin: 0 0 0.8rem 0;
            color: #101828;
            font-size: 1.16rem;
            font-weight: 750;
        }

        .aed-selected-summary {
            margin-bottom: 0.8rem;
            padding: 0.75rem;
            border: 1px solid #e4e7ec;
            border-radius: 9px;
            background: #f8faff;
        }

        .aed-selected-location {
            margin-top: 0.15rem;
            color: #667085;
            font-size: 0.82rem;
            line-height: 1.35;
        }

        .aed-status-line {
            display: flex;
            align-items: center;
            gap: 0.42rem;
            margin-top: 0.55rem;
            color: #344054;
            font-size: 0.82rem;
            font-weight: 650;
        }

        .aed-status-line-dot {
            width: 9px;
            height: 9px;
            display: inline-block;
            border-radius: 50%;
        }

        .aed-key-details {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.55rem;
            margin: 0.75rem 0;
        }

        .aed-key-detail {
            min-width: 0;
            padding: 0.55rem 0.6rem;
            border: 1px solid #eaecf0;
            border-radius: 8px;
            background: #ffffff;
        }

        .aed-key-detail-label {
            color: #667085;
            font-size: 0.7rem;
            line-height: 1.2;
        }

        .aed-key-detail-value {
            margin-top: 0.2rem;
            color: #1d2939;
            font-size: 0.82rem;
            font-weight: 620;
            line-height: 1.3;
            overflow-wrap: anywhere;
        }

        .aed-control-section {
            margin-top: 0.5rem;
            padding-top: 0.75rem;
            border-top: 1px solid #eaecf0;
        }

        .aed-control-caption {
            margin-bottom: 0.45rem;
            color: #475467;
            font-size: 0.8rem;
            font-weight: 650;
        }

        @media (max-width: 900px) {
            .aed-key-details {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
