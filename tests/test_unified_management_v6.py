from pathlib import Path

from config import BUILD_ID


MANAGEMENT_SOURCE = Path("views/aed_management.py").read_text(encoding="utf-8")
NAVIGATION_SOURCE = Path("ui/navigation.py").read_text(encoding="utf-8")
REGISTRY_SOURCE = Path("views/registry.py").read_text(encoding="utf-8")


def _function_block(name: str, next_name: str | None = None) -> str:
    start = MANAGEMENT_SOURCE.index(f"def {name}(")
    if next_name:
        end = MANAGEMENT_SOURCE.index(f"def {next_name}(", start)
    else:
        end = len(MANAGEMENT_SOURCE)
    return MANAGEMENT_SOURCE[start:end]


def test_v7_build_marker_is_unique() -> None:
    assert BUILD_ID == "2026-08-05-v11-V7-DIRECT-ONEDRIVE-CORE"


def test_only_one_asset_control_sidebar_entry_is_visible() -> None:
    assert '("AED Management", "▣  AED Management")' in NAVIGATION_SOURCE
    assert '("AED Master Table", "▦  Master Table")' not in NAVIGATION_SOURCE


def test_old_master_routes_redirect_to_unified_direct_edit() -> None:
    assert '"AED Master Table": partial(' in REGISTRY_SOURCE
    assert '"AED Master Data": partial(' in REGISTRY_SOURCE
    block = _function_block("render_aed_master_table")
    assert 'st.session_state["management_table_mode"] = "Direct Edit"' in block
    assert 'st.session_state["page"] = "AED Management"' in block


def test_management_has_one_search_and_one_linked_filter_set() -> None:
    block = _function_block("_render_unified_directory", "_render_selected_management_profile")
    assert block.count("render_filters(dataframe)") == 1
    assert block.count("aed_service.apply_filters(") == 1
    assert 'options=["Browse Units", "Direct Edit"]' in block


def test_browse_table_row_click_opens_profile_by_serial_number() -> None:
    block = _function_block("render_selectable_browse_table", "render_edit_mode")
    assert 'on_select="rerun"' in block
    assert 'selection_mode="single-row"' in block
    assert 'display.iloc[selected_index].get("Serial Number")' in block
    assert 'st.session_state["aed_management_view"] = "profile"' in block


def test_back_to_list_preserves_search_and_filters() -> None:
    block = _function_block("_render_selected_management_profile", "render_aed_management")
    assert '"← Back to AED list"' in block
    assert 'reset_management_filters()' not in block
    assert 'management_browse_table_nonce' in block


def test_direct_edit_keeps_original_master_workflows() -> None:
    block = _function_block("_render_unified_directory", "_render_selected_management_profile")
    for required in [
        "render_browse_table(filtered)",
        "render_full_details_editor(filtered)",
        "render_add_and_deactivate(dataframe)",
        "render_audit_log(history_file)",
    ]:
        assert required in block


def test_profile_keeps_optimized_actions_and_sections() -> None:
    block = _function_block("_render_unit_profile", "_render_writeback_messages")
    for required in [
        "Edit Details",
        "Add Service",
        "Report Issue",
        "Fill PM Checklist",
        "Open in Table Edit",
        "View Service Records",
        "Open AED Map",
        "Service History",
        "Issues",
    ]:
        assert required in block
