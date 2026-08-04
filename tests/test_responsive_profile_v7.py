from pathlib import Path

from config import BUILD_ID

ROOT = Path(__file__).resolve().parents[1]


def test_v7_build_identifier():
    assert BUILD_ID == "2026-08-04-FULL-REBUILD-v8-SERVICE-RECORD-SCOPE"


def test_management_uses_stable_cards_and_one_full_width_filter_workspace():
    source = (ROOT / "views" / "aed_management.py").read_text()
    assert "management-kpi-card" in source
    assert "Search and filter AED units" in source
    assert "table_col, filter_col = st.columns" not in source
    assert "render_selectable_browse_table(filtered)" in source


def test_profile_uses_responsive_stats_actions_and_horizontal_navigation():
    source = (ROOT / "views" / "aed_management.py").read_text()
    assert "aed-profile-stat-grid" in source
    assert "quick_row_one = st.columns(2" in source
    assert "quick_row_two = st.columns(2" in source
    assert "section = st.segmented_control" in source
    assert 'summary_cols[2].metric("Next PM"' not in source


def test_styles_prevent_cropped_text_and_support_narrow_screens():
    styles = (ROOT / "ui" / "styles.py").read_text()
    assert "height: auto !important" in styles
    assert "white-space: normal !important" in styles
    assert "overflow-wrap: anywhere" in styles
    assert "aed-profile-fields-grid" in styles
    assert "@media (max-width: 680px)" in styles
