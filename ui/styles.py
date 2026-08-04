import streamlit as st


def apply_global_styles() -> None:
    """Apply the shared control-frame and light-workspace visual system."""

    st.markdown(
        """
        <style>
        :root {
            --nav-bg: #0f172a;
            --nav-surface: #172033;
            --nav-hover: #1e293b;
            --nav-text: #f8fafc;
            --nav-muted: #cbd5e1;

            --page-bg: #f4f6f8;
            --surface: #ffffff;
            --surface-subtle: #f8fafc;
            --border: #d8dee8;
            --border-strong: #c4ccd8;

            --text-primary: #172033;
            --text-secondary: #5b6575;
            --text-tertiary: #667085;

            --primary: #2563eb;
            --primary-hover: #1d4ed8;
            --primary-soft: #eff6ff;

            --danger-text: #b42318;
            --danger-bg: #fef3f2;
            --warning-text: #b45309;
            --warning-bg: #fffaeb;
            --success-text: #15803d;
            --success-bg: #ecfdf3;
            --info-text: #175cd3;
            --info-bg: #eff8ff;

            /* Compatibility aliases used by existing pages. */
            --aed-ink: var(--text-primary);
            --aed-muted: var(--text-secondary);
            --aed-paper: var(--page-bg);
            --aed-panel: var(--surface);
            --aed-blue: var(--primary);
            --aed-blue-dark: var(--primary-hover);
            --aed-coral: var(--danger-text);
            --aed-green: var(--success-text);
            --aed-amber: var(--warning-text);
            --aed-line: var(--border);
            --aed-soft: var(--primary-soft);
            --aed-code: #172033;
        }

        html { scroll-behavior: smooth; }

        .stApp {
            color: var(--text-primary);
            background: var(--page-bg);
        }

        [data-testid="stAppViewContainer"] > .main { background: transparent; }

        .main .block-container,
        [data-testid="stMainBlockContainer"] {
            max-width: 1440px;
            padding: 1.5rem 2rem 4rem;
        }

        h1, h2, h3, h4 {
            color: var(--text-primary);
            letter-spacing: -0.025em;
        }

        p, li { line-height: 1.55; }

        /* Sidebar ----------------------------------------------------- */
        [data-testid="stSidebar"] {
            min-width: 276px;
            max-width: 276px;
            background: var(--nav-bg);
            border-right: 1px solid rgba(255, 255, 255, 0.09);
        }

        [data-testid="stSidebar"] > div:first-child { padding-top: 1.1rem; }
        [data-testid="stSidebar"] * { color: var(--nav-text); }
        [data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.12); }

        /* Keep sidebar expanders and form controls dark. The generic
           workspace expander rule below uses a white surface, which would
           otherwise produce white text on a white card in the sidebar. */
        [data-testid="stSidebar"] [data-testid="stExpander"] {
            border-color: rgba(203, 213, 225, 0.18) !important;
            background: var(--nav-surface) !important;
        }

        [data-testid="stSidebar"] [data-testid="stExpander"] details,
        [data-testid="stSidebar"] [data-testid="stExpander"] summary {
            background: transparent !important;
        }

        [data-testid="stSidebar"] [data-testid="stExpander"] summary,
        [data-testid="stSidebar"] [data-testid="stExpander"] summary *,
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] *,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] *,
        [data-testid="stSidebar"] .stCaption,
        [data-testid="stSidebar"] .stCaption * {
            color: var(--nav-muted) !important;
        }

        [data-testid="stSidebar"] [data-testid="stExpander"] summary,
        [data-testid="stSidebar"] [data-testid="stExpander"] summary * {
            color: var(--nav-text) !important;
            font-weight: 700;
        }

        [data-testid="stSidebar"] div[data-baseweb="select"] > div,
        [data-testid="stSidebar"] .stTextInput input,
        [data-testid="stSidebar"] .stDateInput input,
        [data-testid="stSidebar"] .stNumberInput input {
            border-color: #475569 !important;
            background: #0f172a !important;
            color: var(--nav-text) !important;
        }

        [data-testid="stSidebar"] div[data-baseweb="select"] span,
        [data-testid="stSidebar"] div[data-baseweb="select"] svg,
        [data-testid="stSidebar"] input {
            color: var(--nav-text) !important;
            fill: var(--nav-text) !important;
        }

        [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button {
            border-color: #475569 !important;
            background: #1e293b !important;
            color: var(--nav-text) !important;
        }

        [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button:hover {
            border-color: #64748b !important;
            background: #334155 !important;
        }

        .aed-brand {
            display: flex;
            align-items: center;
            gap: 0.72rem;
            margin: 0.1rem 0 0.2rem 0.15rem;
        }

        .aed-brand-icon {
            width: 38px;
            height: 38px;
            display: grid;
            place-items: center;
            border-radius: 10px;
            background: var(--primary);
            color: #fff;
            font-size: 1.05rem;
            font-weight: 800;
        }

        .aed-brand-icon span { transform: none; }
        .aed-brand-name { color: #fff; font-size: 1.03rem; font-weight: 750; }

        .aed-brand-subtitle {
            margin: 0 0 1.1rem 3.45rem;
            color: #9fb0c8;
            font-size: 0.68rem;
            font-weight: 700;
            letter-spacing: 0.12em;
        }

        .aed-nav-section {
            margin: 1rem 0 0.38rem 0.18rem;
            color: #94a3b8;
            font-size: 0.66rem;
            font-weight: 800;
            letter-spacing: 0.13em;
        }

        [data-testid="stSidebar"] .stButton > button {
            justify-content: flex-start;
            min-height: 41px;
            border: 1px solid transparent;
            border-radius: 8px;
            box-shadow: none;
            padding-left: 0.78rem;
            font-weight: 620;
            transition: background 0.15s ease, border-color 0.15s ease;
        }

        [data-testid="stSidebar"] .stButton > button[kind="secondary"] {
            background: transparent;
            color: #e5edf8;
        }

        [data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
            background: var(--nav-hover);
            border-color: rgba(255,255,255,0.08);
            color: #fff;
        }

        [data-testid="stSidebar"] .stButton > button[kind="primary"] {
            background: #1d4ed8;
            border-color: #3b82f6;
            color: #fff;
            box-shadow: inset 3px 0 0 #93c5fd;
        }

        .aed-sidebar-summary {
            margin-top: 1rem;
            padding: 0.82rem 0.85rem;
            border: 1px solid rgba(203, 213, 225, 0.15);
            border-radius: 10px;
            background: var(--nav-surface);
        }

        .aed-sidebar-summary strong {
            display: block;
            margin-bottom: 0.2rem;
            color: #fff;
            font-size: 0.76rem;
        }

        .aed-sidebar-summary span {
            color: #b5c1d2;
            font-size: 0.7rem;
            line-height: 1.45;
        }

        .aed-version { margin-top: 1rem; color: #7f8da3; font-size: 0.66rem; }

        /* Existing page headers -------------------------------------- */
        .aed-hero {
            padding: 1.35rem 1.5rem;
            margin-bottom: 1rem;
            border: 1px solid var(--border);
            border-radius: 12px;
            background: var(--surface);
        }

        .aed-hero::after { display: none; }

        .aed-hero-eyebrow {
            color: var(--primary);
            font-size: 0.69rem;
            font-weight: 800;
            letter-spacing: 0.13em;
        }

        .aed-hero h1 {
            margin: 0.28rem 0 0.38rem;
            font-size: clamp(1.8rem, 3vw, 2.45rem);
            line-height: 1.1;
        }

        .aed-hero p {
            max-width: 900px;
            margin: 0;
            color: var(--text-secondary);
            font-size: 0.94rem;
        }

        .aed-chip {
            display: inline-block;
            margin-top: 0.75rem;
            padding: 0.34rem 0.62rem;
            border-radius: 999px;
            background: var(--primary-soft);
            color: var(--primary);
            font-size: 0.72rem;
            font-weight: 750;
        }

        .aed-capability-cards {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.75rem;
            margin: 0 0 1.1rem;
        }

        .aed-capability-card {
            min-width: 0;
            padding: 0.9rem 1rem;
            border: 1px solid var(--border);
            border-radius: 10px;
            background: var(--surface);
        }

        .aed-capability-card strong {
            display: block;
            margin-bottom: 0.25rem;
            color: var(--text-primary);
            font-size: 0.87rem;
        }

        .aed-capability-card span {
            color: var(--text-secondary);
            font-size: 0.8rem;
            line-height: 1.45;
        }

        .aed-section-label,
        .ops-toolbar-label {
            margin: 1rem 0 0.5rem;
            color: var(--text-tertiary);
            font-size: 0.68rem;
            font-weight: 800;
            letter-spacing: 0.12em;
        }

        .aed-note-panel {
            margin: 0.75rem 0;
            padding: 0.85rem 0.95rem;
            border: 1px solid var(--border);
            border-left: 4px solid var(--primary);
            border-radius: 10px;
            background: var(--surface);
            color: var(--text-secondary);
        }

        .aed-note-panel strong {
            display: block;
            margin-bottom: 0.18rem;
            color: var(--text-primary);
            font-size: 0.72rem;
            letter-spacing: 0.08em;
        }

        /* Operations Control header ---------------------------------- */
        .ops-control-header {
            min-height: 112px;
            padding: 1.25rem 1.4rem;
            border: 1px solid #26334a;
            border-radius: 12px;
            background: #172033;
        }

        .ops-control-eyebrow {
            color: #93c5fd;
            font-size: 0.68rem;
            font-weight: 800;
            letter-spacing: 0.13em;
        }

        .ops-control-header h1 {
            margin: 0.25rem 0 0.28rem;
            color: #f8fafc;
            font-size: clamp(1.85rem, 3.2vw, 2.55rem);
            line-height: 1.08;
        }

        .ops-control-header p {
            margin: 0;
            color: #cbd5e1;
            font-size: 0.91rem;
        }

        .ops-control-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
            margin-top: 0.72rem;
            color: #9fb0c8;
            font-size: 0.72rem;
        }

        .ops-control-meta-divider { color: #64748b; }
        .ops-header-action-spacer { height: 36px; }

        /* Toolbar ----------------------------------------------------- */
        [data-testid="stSegmentedControl"] {
            min-height: 40px;
        }

        [data-testid="stSegmentedControl"] button {
            border-radius: 7px;
            font-weight: 650;
        }

        /* KPI cards --------------------------------------------------- */
        .ops-kpi {
            min-height: 128px;
            padding: 0.95rem 1rem;
            border: 1px solid var(--border);
            border-top: 3px solid var(--primary);
            border-radius: 10px;
            background: var(--surface);
        }

        .ops-kpi-label {
            color: var(--text-tertiary);
            font-size: 0.67rem;
            font-weight: 800;
            letter-spacing: 0.1em;
        }

        .ops-kpi-value {
            margin: 0.22rem 0 0.18rem;
            color: var(--text-primary);
            font-size: 2rem;
            font-weight: 760;
            line-height: 1.05;
        }

        .ops-kpi-note { color: var(--text-secondary); font-size: 0.76rem; }
        .ops-kpi-coral { border-top-color: var(--danger-text); }
        .ops-kpi-amber { border-top-color: var(--warning-text); }
        .ops-kpi-green { border-top-color: var(--success-text); }
        .ops-kpi-blue { border-top-color: var(--primary); }

        /* Section headings ------------------------------------------- */
        .ops-section-heading {
            display: flex;
            align-items: end;
            justify-content: space-between;
            gap: 1rem;
            margin: 1.45rem 0 0.58rem;
        }

        .ops-section-heading-compact { margin-top: 1.45rem; }
        .ops-section-heading span {
            display: block;
            margin-bottom: 0.12rem;
            color: var(--text-tertiary);
            font-size: 0.66rem;
            font-weight: 800;
            letter-spacing: 0.11em;
        }

        .ops-section-heading h2 {
            margin: 0;
            font-size: 1.18rem;
            line-height: 1.2;
        }

        .ops-section-count {
            padding: 0.28rem 0.5rem;
            border: 1px solid var(--border);
            border-radius: 7px;
            background: var(--surface-subtle);
            color: var(--text-secondary);
            font-size: 0.72rem;
            font-weight: 650;
        }

        /* Selected item / summaries ---------------------------------- */
        .ops-detail-panel,
        .ops-summary-card,
        .ops-activity-feed {
            border: 1px solid var(--border);
            border-radius: 10px;
            background: var(--surface);
        }

        .ops-detail-panel { padding: 1rem; }
        .ops-detail-kicker {
            color: var(--primary);
            font-size: 0.66rem;
            font-weight: 800;
            letter-spacing: 0.1em;
        }

        .ops-detail-panel h3 {
            margin: 0.25rem 0 0.35rem;
            font-size: 1.15rem;
        }

        .ops-detail-panel p {
            margin: 0 0 0.75rem;
            color: var(--text-secondary);
            font-size: 0.8rem;
        }

        .ops-detail-list,
        .ops-summary-list { border-top: 1px solid var(--border); }

        .ops-detail-row {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
            gap: 0.7rem;
            padding: 0.5rem 0;
            border-bottom: 1px solid #edf0f4;
        }

        .ops-detail-row span { color: var(--text-secondary); font-size: 0.75rem; }
        .ops-detail-row strong {
            color: var(--text-primary);
            font-size: 0.76rem;
            font-weight: 650;
            text-align: right;
            overflow-wrap: anywhere;
        }

        .ops-summary-card {
            min-height: 255px;
            padding: 1rem;
        }

        .ops-summary-card > strong,
        .ops-summary-card p strong { font-size: 0.9rem; }

        /* Activity ---------------------------------------------------- */
        .ops-activity-feed { padding: 0.2rem 0.9rem; }
        .ops-activity-item {
            display: flex;
            gap: 0.75rem;
            padding: 0.78rem 0;
            border-bottom: 1px solid #edf0f4;
        }
        .ops-activity-item:last-child { border-bottom: 0; }
        .ops-activity-marker {
            flex: 0 0 auto;
            width: 30px;
            height: 30px;
            display: grid;
            place-items: center;
            border-radius: 8px;
            background: var(--primary-soft);
            color: var(--primary);
            font-size: 0.72rem;
            font-weight: 800;
        }
        .ops-activity-body { min-width: 0; }
        .ops-activity-body strong {
            display: block;
            color: var(--text-primary);
            font-size: 0.8rem;
        }
        .ops-activity-body span {
            display: block;
            margin-top: 0.12rem;
            color: var(--text-secondary);
            font-size: 0.7rem;
        }

        /* Existing custom utility classes ---------------------------- */
        .aed-helper-bar,
        .aed-plan-summary,
        .aed-selected-summary,
        .aed-key-details,
        .aed-detail-grid {
            border: 1px solid var(--border);
            border-radius: 10px;
            background: var(--surface);
        }

        .aed-helper-bar,
        .aed-plan-summary,
        .aed-selected-summary { padding: 0.85rem 0.95rem; }
        .aed-key-details,
        .aed-detail-grid { display: grid; gap: 0.6rem; padding: 0.85rem; }
        .aed-key-details { grid-template-columns: repeat(3, minmax(0, 1fr)); }
        .aed-detail-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .aed-key-detail,
        .aed-detail-label,
        .aed-detail-value,
        .aed-selected-location,
        .aed-status-line,
        .aed-control-caption,
        .pm-help,
        .pm-section-note,
        .status-editor-note { color: var(--text-secondary); }
        .aed-key-detail-label,
        .aed-detail-label,
        .pm-label { font-size: 0.7rem; color: var(--text-tertiary); }
        .aed-key-detail-value,
        .aed-detail-value,
        .selected-aed-serial { color: var(--text-primary); font-weight: 700; }
        .pm-number { color: var(--primary); font-weight: 750; }
        .pm-section-title,
        .selected-aed-heading,
        .aed-side-title { color: var(--text-primary); font-weight: 700; }

        /* Streamlit controls ----------------------------------------- */
        [data-testid="stMetric"],
        [data-testid="stExpander"],
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--border);
            border-radius: 10px;
            background: var(--surface);
            box-shadow: none;
        }

        [data-testid="stMetric"] { padding: 0.75rem; }

        .stButton > button,
        [data-testid="stFormSubmitButton"] > button {
            min-height: 40px;
            border-radius: 8px;
            box-shadow: none;
            font-weight: 680;
            transition: background 0.15s ease, border-color 0.15s ease;
        }

        .stButton > button:hover,
        [data-testid="stFormSubmitButton"] > button:hover {
            transform: none;
            border-color: var(--primary);
            box-shadow: none;
        }

        .stButton > button[kind="primary"],
        [data-testid="stFormSubmitButton"] > button[kind="primary"] {
            background: var(--primary);
            border-color: var(--primary);
        }

        .stButton > button[kind="primary"]:hover,
        [data-testid="stFormSubmitButton"] > button[kind="primary"]:hover {
            background: var(--primary-hover);
            border-color: var(--primary-hover);
        }

        .stTextInput input,
        .stDateInput input,
        .stNumberInput input,
        div[data-baseweb="select"] > div {
            min-height: 40px;
            border-radius: 8px;
        }

        [data-testid="stDataFrame"],
        [data-testid="stDataEditor"] {
            overflow: hidden;
            border: 1px solid var(--border);
            border-radius: 10px;
            box-shadow: none;
        }

        [data-testid="stTabs"] [data-baseweb="tab-list"] { gap: 0.25rem; }
        [data-testid="stTabs"] button[role="tab"] { font-weight: 650; }
        .management-subtitle { color: var(--text-secondary); margin-top: -0.5rem; }

        /* Responsive Management and Unit Profile -------------------- */
        [data-testid="stColumn"] { min-width: 0; }

        .aed-control-top-spacer { height: 1.72rem; }

        .management-kpi-card {
            min-height: 128px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            margin-bottom: 0.42rem;
            padding: 1rem 1.05rem;
            border: 1px solid var(--border);
            border-left: 4px solid var(--primary);
            border-radius: 11px;
            background: var(--surface);
        }

        .management-kpi-blue { border-left-color: var(--primary); }
        .management-kpi-amber { border-left-color: var(--warning-text); }
        .management-kpi-coral { border-left-color: var(--danger-text); }
        .management-kpi-green { border-left-color: var(--success-text); }

        .management-kpi-label {
            color: var(--text-tertiary);
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .management-kpi-value {
            margin: 0.22rem 0 0.28rem;
            color: var(--text-primary);
            font-size: clamp(1.8rem, 3vw, 2.25rem);
            font-weight: 780;
            line-height: 1;
        }

        .management-kpi-note {
            color: var(--text-secondary);
            font-size: 0.82rem;
            line-height: 1.42;
            white-space: normal;
            overflow-wrap: anywhere;
        }

        .aed-profile-top-gap { height: 0.2rem; }

        .aed-profile-identity { min-width: 0; }
        .aed-profile-eyebrow,
        .aed-profile-actions-title {
            color: var(--text-tertiary);
            font-size: 0.68rem;
            font-weight: 800;
            letter-spacing: 0.11em;
        }

        .aed-profile-identity h2 {
            margin: 0.28rem 0 0.2rem;
            font-size: clamp(1.65rem, 3vw, 2.25rem);
            line-height: 1.08;
            overflow-wrap: anywhere;
        }

        .aed-profile-model {
            color: var(--text-primary);
            font-size: 0.98rem;
            font-weight: 720;
            overflow-wrap: anywhere;
        }

        .aed-profile-location,
        .aed-profile-postal {
            margin-top: 0.2rem;
            color: var(--text-secondary);
            font-size: 0.84rem;
            line-height: 1.45;
            white-space: normal;
            overflow-wrap: anywhere;
        }

        .aed-profile-stat-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.62rem;
            margin-top: 1rem;
        }

        .aed-profile-stat {
            min-width: 0;
            min-height: 78px;
            padding: 0.72rem 0.78rem;
            border: 1px solid var(--border);
            border-radius: 9px;
            background: var(--surface-subtle);
        }

        .aed-profile-stat span,
        .aed-profile-field span,
        .aed-snapshot-row span,
        .aed-issue-count-grid span,
        .aed-directory-count span {
            display: block;
            color: var(--text-tertiary);
            font-size: 0.69rem;
            font-weight: 700;
        }

        .aed-profile-stat strong {
            display: block;
            margin-top: 0.28rem;
            color: var(--text-primary);
            font-size: 0.95rem;
            line-height: 1.28;
            white-space: normal;
            overflow-wrap: anywhere;
        }

        .aed-profile-actions-title { margin-bottom: 0.42rem; }
        .aed-profile-actions-title-spaced { margin-top: 0.95rem; }
        .aed-profile-tab-divider {
            height: 1px;
            margin: 1.05rem 0 0.82rem;
            background: var(--border);
        }

        .aed-profile-overview-card,
        .aed-profile-section-card {
            min-width: 0;
            border: 1px solid var(--border);
            border-radius: 10px;
            background: var(--surface);
        }

        .aed-profile-overview-card {
            min-height: 255px;
            padding: 1rem;
        }

        .aed-profile-section-card {
            margin-top: 0.8rem;
            padding: 1rem;
        }

        .aed-profile-card-title,
        .aed-profile-section-card h4 {
            margin: 0 0 0.75rem;
            color: var(--text-primary);
            font-size: 0.94rem;
            font-weight: 760;
        }

        .aed-profile-section-card h4 { margin-bottom: 0.72rem; }
        .aed-snapshot-list { border-top: 1px solid var(--border); }

        .aed-snapshot-row {
            display: grid;
            grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.35fr);
            gap: 0.75rem;
            align-items: start;
            padding: 0.56rem 0;
            border-bottom: 1px solid #edf0f4;
        }

        .aed-snapshot-row strong {
            color: var(--text-primary);
            font-size: 0.78rem;
            font-weight: 680;
            line-height: 1.38;
            text-align: right;
            white-space: normal;
            overflow-wrap: anywhere;
        }

        .aed-issue-count-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.58rem;
            margin-bottom: 0.75rem;
        }

        .aed-issue-count-grid > div {
            min-width: 0;
            padding: 0.7rem;
            border: 1px solid var(--border);
            border-radius: 8px;
            background: var(--surface-subtle);
        }

        .aed-issue-count-grid strong {
            display: block;
            margin-top: 0.2rem;
            color: var(--text-primary);
            font-size: 1.25rem;
            line-height: 1;
        }

        .aed-profile-empty-state {
            padding: 0.72rem 0;
            color: var(--text-secondary);
            font-size: 0.8rem;
            line-height: 1.45;
        }

        .aed-profile-fields-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.62rem;
        }

        .aed-profile-field {
            min-width: 0;
            min-height: 72px;
            padding: 0.68rem 0.75rem;
            border: 1px solid #e7ebf0;
            border-radius: 8px;
            background: var(--surface-subtle);
        }

        .aed-profile-field-wide { grid-column: 1 / -1; }

        .aed-profile-field strong {
            display: block;
            margin-top: 0.25rem;
            color: var(--text-primary);
            font-size: 0.79rem;
            font-weight: 650;
            line-height: 1.42;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            word-break: break-word;
        }

        .aed-directory-count {
            min-height: 40px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            padding: 0.55rem 0.72rem;
            border: 1px solid var(--border);
            border-radius: 8px;
            background: var(--surface);
        }

        .aed-directory-count strong {
            color: var(--text-primary);
            font-size: 0.86rem;
            white-space: nowrap;
        }

        /* Never crop a Streamlit button label. */
        .stButton > button,
        [data-testid="stFormSubmitButton"] > button {
            height: auto !important;
            min-height: 42px;
            padding-top: 0.56rem;
            padding-bottom: 0.56rem;
            white-space: normal !important;
        }

        .stButton > button p,
        [data-testid="stFormSubmitButton"] > button p,
        .stButton > button span,
        [data-testid="stFormSubmitButton"] > button span {
            margin: 0;
            line-height: 1.25 !important;
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: clip !important;
            overflow-wrap: anywhere;
        }

        [data-testid="stMetricValue"],
        [data-testid="stMetricValue"] * {
            white-space: normal !important;
            overflow-wrap: anywhere;
            line-height: 1.15 !important;
        }

        [data-testid="stSegmentedControl"] [role="radiogroup"] {
            flex-wrap: wrap !important;
            gap: 0.35rem !important;
        }

        [data-testid="stSegmentedControl"] button {
            min-height: 40px;
            white-space: normal !important;
        }

        @media (prefers-reduced-motion: reduce) {
            html { scroll-behavior: auto; }
            *, *::before, *::after {
                animation-duration: 0.01ms !important;
                animation-iteration-count: 1 !important;
                transition-duration: 0.01ms !important;
                scroll-behavior: auto !important;
            }
        }

        @media (max-width: 980px) {
            .main .block-container,
            [data-testid="stMainBlockContainer"] { padding: 1rem 1rem 3.5rem; }
            .aed-capability-cards { grid-template-columns: 1fr; }
            .aed-key-details,
            .aed-detail-grid,
            .aed-profile-fields-grid { grid-template-columns: 1fr; }
            .aed-profile-field-wide { grid-column: auto; }
            .ops-header-action-spacer { height: 0; }
            .ops-control-header { min-height: 0; }
            .aed-profile-overview-card { min-height: 0; }
        }

        @media (max-width: 680px) {
            .aed-profile-stat-grid,
            .aed-issue-count-grid { grid-template-columns: 1fr; }
            .aed-snapshot-row { grid-template-columns: 1fr; gap: 0.2rem; }
            .aed-snapshot-row strong { text-align: left; }
            .management-kpi-card { min-height: 0; }
            .aed-control-top-spacer { height: 0; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
