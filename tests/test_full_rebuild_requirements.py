from __future__ import annotations

import ast
from pathlib import Path

from config import BUILD_ID, MICROSOFT_CONFIG
from services.aed_field_schema import JOB_TYPE_OPTIONS
from views.map_modules.status_service import COLOR_PALETTE


RUNTIME_ROOTS = [Path("streamlit_app.py"), Path("ui"), Path("views"), Path("services")]


def _runtime_python_text() -> str:
    parts: list[str] = []
    for root in RUNTIME_ROOTS:
        if root.is_file():
            parts.append(root.read_text(encoding="utf-8"))
        else:
            for path in root.rglob("*.py"):
                parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_full_rebuild_has_unique_deployment_marker() -> None:
    assert BUILD_ID == "2026-08-05-v10.8-DIRECT-SECRETS-READ"
    navigation = Path("ui/navigation.py").read_text(encoding="utf-8")
    assert "build_id" in navigation


def test_streamlit_entrypoint_is_the_only_cloud_entrypoint() -> None:
    source = Path("streamlit_app.py").read_text(encoding="utf-8")
    assert not Path("app.py").exists()
    assert "st.set_page_config" in source
    assert "def main()" in source
    assert "page_registry.render_current_page" in source
    assert "from app import main" not in source
    assert "import app" not in source


def test_old_asset_readiness_wording_is_not_in_runtime_code() -> None:
    runtime = _runtime_python_text().casefold()
    assert "asset readiness" not in runtime


def test_unit_profiles_replace_the_old_home_scope() -> None:
    dashboard_service = Path("services/dashboard_service.py").read_text(encoding="utf-8")
    dashboard_view = Path("views/dashboard.py").read_text(encoding="utf-8")
    dashboard_ui = Path("ui/dashboard_components.py").read_text(encoding="utf-8")
    assert 'DASHBOARD_VIEWS = ["PM", "Issues", "Unit Profiles"]' in dashboard_service
    assert 'DASHBOARD_VIEWS = ["Overview"' not in dashboard_service
    assert 'st.session_state.setdefault("dashboard_view", "PM")' in dashboard_ui
    assert 'dashboard_view", "Overview"' not in dashboard_ui
    assert 'filters["view"] == "Unit Profiles"' in dashboard_view
    assert "Open selected profile" in dashboard_ui
    assert "Browse all profiles" in dashboard_ui


def test_aed_management_uses_one_search_filter_and_table_workspace() -> None:
    source = Path("views/aed_management.py").read_text(encoding="utf-8")
    start = source.index("def render_aed_management(")
    end = source.index("def render_aed_master_table(", start)
    block = source[start:end]
    assert "_render_unified_directory(dataframe, history_file)" in block
    assert "render_dashboard_unit_profiles(" not in block
    unified_start = source.index("def _render_unified_directory(")
    unified_end = source.index("def _render_selected_management_profile(", unified_start)
    unified = source[unified_start:unified_end]
    assert unified.count("render_filters(dataframe)") == 1
    assert "Browse Units" in unified
    assert "Direct Edit" in unified
    assert "render_selectable_browse_table(filtered)" in unified
    assert "render_browse_table(filtered)" in unified

def test_unit_profile_is_directly_selectable_and_fully_operational() -> None:
    source = Path("views/aed_management.py").read_text(encoding="utf-8")
    for required in [
        "Click any AED row to open its complete profile",
        "Overview",
        "Edit Details",
        "Service History",
        "Add Service",
        "Issues",
        "Confirm and update Excel",
        "Review new service record",
        "Fill PM Checklist",
        "Report Issue",
        "Open in Table Edit",
        "View Service Records",
        "Open AED Map",
    ]:
        assert required in source

def test_master_table_is_merged_but_old_routes_remain_compatible() -> None:
    navigation = Path("ui/navigation.py").read_text(encoding="utf-8")
    registry = Path("views/registry.py").read_text(encoding="utf-8")
    management = Path("views/aed_management.py").read_text(encoding="utf-8")
    assert '("AED Management", "▣  AED Management")' in navigation
    assert '("AED Master Table", "▦  Master Table")' not in navigation
    assert '"AED Master Table": partial(' in registry
    assert '"AED Master Data": partial(' in registry
    assert 'st.session_state["management_table_mode"] = "Direct Edit"' in management
    assert 'st.session_state["page"] = "AED Management"' in management

def test_service_type_order_matches_business_request() -> None:
    assert JOB_TYPE_OPTIONS[1] == "PM"
    assert JOB_TYPE_OPTIONS[2] == "Commissioning"
    assert JOB_TYPE_OPTIONS[-3:] == ["PM+batt", "PM+glass", "PM +batt +glass"]


def test_map_keeps_many_user_definable_colours() -> None:
    assert len(COLOR_PALETTE) >= 15
    for colour in ["Blue", "Green", "Red", "Yellow", "Purple", "Pink", "Teal", "Black"]:
        assert colour in COLOR_PALETTE
    source = Path("views/aed_map.py").read_text(encoding="utf-8") + Path("views/map_modules/status_service.py").read_text(encoding="utf-8")
    assert "Manage Statuses" in source
    assert "Color Override" in source


def test_official_excel_and_system_state_are_separate_onedrive_files() -> None:
    assert MICROSOFT_CONFIG["onedrive_file_path"].endswith("IB_list_TEST.xlsx")
    assert MICROSOFT_CONFIG["system_state_path"].endswith("AED_System_State.zip")
    assert MICROSOFT_CONFIG["onedrive_file_path"] != MICROSOFT_CONFIG["system_state_path"]


def test_cloud_auto_refresh_covers_excel_and_system_records() -> None:
    source = Path("streamlit_app.py").read_text(encoding="utf-8")
    assert '@st.fragment(run_every=AUTO_REFRESH_INTERVAL)' in source
    assert "aed_repository.ensure_cache_current(force=False)" in source
    assert "system_state_service.sync_system_state()" in source


def test_secret_example_contains_only_placeholders() -> None:
    source = Path(".streamlit/secrets.toml.example").read_text(encoding="utf-8")
    assert "REPLACE_WITH_ONEMAP_EMAIL" in source
    assert "REPLACE_WITH_ONEMAP_PASSWORD" in source
    assert "REPLACE_WITH_APPLICATION_CLIENT_ID" in source
    assert "REPLACE_WITH_CLIENT_SECRET_VALUE" in source


def test_deprecated_streamlit_width_argument_removed() -> None:
    assert "use_container_width" not in _runtime_python_text()


def test_dashboard_does_not_nest_source_health_expanders() -> None:
    source = Path("views/dashboard.py").read_text(encoding="utf-8")
    assert 'with st.expander("System source status"' not in source
    assert "render_source_health(snapshot)" in source


def test_profile_add_service_uses_structured_record_not_remarks() -> None:
    source = Path("views/aed_management.py").read_text(encoding="utf-8")
    block_start = source.index("def _render_add_service_record")
    block_end = source.index("def _render_service_history", block_start)
    block = source[block_start:block_end]
    assert "append_manual_service_record" in block
    assert 'changes["Remarks"]' not in block
    assert "Service Records" in block


def test_auto_refresh_defers_downloads_while_editing() -> None:
    app_source = Path("streamlit_app.py").read_text(encoding="utf-8")
    state_source = Path("services/system_state_service.py").read_text(encoding="utf-8")
    assert "editing = user_is_editing()" in app_source
    assert "system_state_service.sync_system_state(allow_download=not editing)" in app_source
    assert "allow_download: bool = True" in state_source
    assert 'status == "deferred"' in app_source


def test_manual_service_records_are_persisted_separately() -> None:
    from config import MANUAL_SERVICE_RECORDS_FILE, SYSTEM_STATE_PATHS
    assert MANUAL_SERVICE_RECORDS_FILE in SYSTEM_STATE_PATHS
    assert Path("manual_service_records.csv").exists()
    source = Path("views/service_records.py").read_text(encoding="utf-8")
    assert "load_manual_service_records" in source
    assert "Unit Profile" in source


def test_system_state_archive_does_not_duplicate_official_workbook_cache() -> None:
    from config import AED_CACHE_FILE, SYSTEM_STATE_PATHS
    assert AED_CACHE_FILE not in SYSTEM_STATE_PATHS


def test_initial_workbook_refresh_is_also_paused_in_active_editors() -> None:
    source = Path("streamlit_app.py").read_text(encoding="utf-8")
    assert "editing_at_start = user_is_editing()" in source
    assert "initialise_operational_storage(allow_remote_refresh=not editing_at_start)" in source
    assert "if first_cloud_load or allow_remote_refresh or not Path(config.AED_DATA_FILE).exists():" in source


def test_every_visible_sidebar_page_has_a_registered_renderer() -> None:
    navigation = Path("ui/navigation.py").read_text(encoding="utf-8")
    registry = Path("views/registry.py").read_text(encoding="utf-8")
    visible_pages = [
        "Operations Dashboard",
        "PM Planning",
        "PM Checklist",
        "Report Issue",
        "Issues",
        "AED Management",
        "AED Map",
        "Service Records",
    ]
    for page in visible_pages:
        assert f'("{page}",' in navigation
        assert f'"{page}":' in registry
