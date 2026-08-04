import streamlit as st


def inject_pm_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --pm-blue: #1f5eea;
            --pm-blue-dark: #164cc8;
            --pm-text: #172033;
            --pm-muted: #667085;
            --pm-border: #dfe4ec;
            --pm-soft: #f7f9fc;
        }

        .pm-page-title {
            margin: 0;
            color: var(--pm-text);
            font-size: 2.25rem;
            line-height: 1.15;
            font-weight: 750;
            letter-spacing: -0.035em;
        }

        .pm-page-subtitle {
            margin-top: 0.55rem;
            margin-bottom: 1.25rem;
            color: var(--pm-muted);
            font-size: 0.96rem;
        }

        .pm-section-title {
            color: var(--pm-text);
            font-size: 1.02rem;
            line-height: 1.3;
            font-weight: 700;
            margin-bottom: 0.15rem;
        }

        .pm-section-note {
            color: var(--pm-muted);
            font-size: 0.88rem;
            margin-bottom: 0.55rem;
        }

        .pm-number {
            color: #202a3c;
            font-size: 0.88rem;
            font-weight: 700;
            padding-top: 0.48rem;
            text-align: right;
        }

        .pm-label {
            color: #293246;
            font-size: 0.88rem;
            font-weight: 520;
            padding-top: 0.48rem;
        }

        .pm-help {
            color: #525d70;
            font-size: 0.80rem;
            line-height: 1.46;
            padding-top: 0.34rem;
        }

        .pm-search-count {
            color: #596579;
            font-size: 0.84rem;
            margin: 0.2rem 0 0.5rem;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--pm-border);
            border-radius: 8px;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.025);
            background: #ffffff;
        }

        div[data-testid="stExpander"] {
            border: 1px solid var(--pm-border);
            border-radius: 8px;
            background: #ffffff;
        }

        div[data-testid="stExpander"] details summary {
            font-weight: 620;
            color: #2d3748;
        }

        .stTextInput input,
        .stDateInput input,
        div[data-baseweb="select"] > div {
            min-height: 42px;
            border-radius: 6px;
            border-color: #d6dce6;
            background: #ffffff;
        }

        .stTextInput input:focus,
        .stDateInput input:focus {
            border-color: var(--pm-blue);
            box-shadow: 0 0 0 1px var(--pm-blue);
        }

        div[data-testid="stRadio"] label {
            font-size: 0.88rem;
            color: #344054;
        }

        div[data-testid="stCheckbox"] label {
            font-size: 0.86rem;
            color: #465166;
        }

        /* Make the AED result selector look like a selectable result row. */
        div[data-testid="stRadio"]:has(.pm-result-anchor) {
            border: 1px solid #dfe4ec;
            border-radius: 7px;
            padding: 0.25rem 0.7rem;
        }

        hr {
            border-color: #edf0f4;
        }

        @media (max-width: 900px) {
            [data-testid="stMainBlockContainer"] {
                padding-left: 1rem;
                padding-right: 1rem;
            }

            .pm-page-title {
                font-size: 1.9rem;
            }

            .pm-help {
                padding-top: 0;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
