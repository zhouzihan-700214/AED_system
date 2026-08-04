from pathlib import Path
import ast

import pandas as pd

from services.aed_field_schema import JOB_TYPE_OPTIONS
from views.map_modules.status_service import COLOR_PALETTE


def _literal_page_names() -> set[str]:
    tree = ast.parse(Path("ui/navigation.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "PAGE_NAMES":
                    return set(ast.literal_eval(node.value))
    raise AssertionError("PAGE_NAMES was not found")


def test_management_and_master_table_share_one_visible_workspace():
    page_names = _literal_page_names()
    assert {
        "Operations Dashboard",
        "AED Management",
        "AED Master Table",
        "AED Map",
        "PM Planning",
        "PM Checklist",
        "Service Records",
        "Report Issue",
        "Issues",
    }.issubset(page_names)

    source = Path("ui/navigation.py").read_text(encoding="utf-8")
    assert '("AED Management", "▣  AED Management")' in source
    assert '("AED Master Table", "▦  Master Table")' not in source

def test_old_master_data_route_remains_as_backward_compatible_alias():
    navigation = Path("ui/navigation.py").read_text(encoding="utf-8")
    registry = Path("views/registry.py").read_text(encoding="utf-8")
    assert '"AED Master Data"' in navigation
    assert '"AED Master Data": partial(' in registry
    assert 'render_aed_master_table' in registry


def test_combined_pm_service_types_are_at_end_and_original_core_positions_remain():
    assert JOB_TYPE_OPTIONS[1] == "PM"
    assert JOB_TYPE_OPTIONS[2] == "Commissioning"
    assert JOB_TYPE_OPTIONS[-3:] == ["PM+batt", "PM+glass", "PM +batt +glass"]


def test_unified_management_keeps_all_original_master_workflows():
    source = Path("views/aed_management.py").read_text(encoding="utf-8")
    assert "def render_aed_management(" in source
    assert "def render_aed_master_table(" in source
    assert '"Browse Units"' in source
    assert '"Direct Edit"' in source
    assert "render_selectable_browse_table(filtered)" in source
    assert "render_browse_table(filtered)" in source
    assert "render_full_details_editor(filtered)" in source
    assert "render_add_and_deactivate(dataframe)" in source
    assert "render_audit_log(history_file)" in source
    assert 'if mode == "edit"' in source
    assert 'if mode == "review"' in source
    assert '"Open in Table Edit"' in source

def test_dashboard_edit_links_open_the_dedicated_master_table():
    source = Path("ui/dashboard_components.py").read_text(encoding="utf-8")
    assert '_navigate("AED Master Table")' in source
    assert '("Add / edit AED", "AED Master Table")' in source


def test_existing_custom_status_definitions_are_preserved_and_new_roles_are_appended():
    statuses = pd.read_csv("map_status_definitions.csv", dtype=str, keep_default_na=False)
    by_id = statuses.set_index("Status ID")
    assert by_id.loc["STATUS-003", "Status Name"] == "Zihan_Pending"
    assert by_id.loc["STATUS-006", "Status Name"] == "Overdue"
    assert by_id.loc["STATUS-007", "Status Name"] == "Not Applicable"
    assert "Pending Verification" in set(statuses["Status Name"])
    assert "Out of Service" in set(statuses["Status Name"])
    assert len(COLOR_PALETTE) >= 15
