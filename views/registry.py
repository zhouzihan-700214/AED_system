from __future__ import annotations

from collections.abc import Callable
from functools import partial

from config import (
    AED_DATA_FILE,
    AED_HISTORY_FILE,
    ISSUE_HISTORY_FILE,
    ISSUE_RECORD_FILE,
    ISSUE_RESOLUTION_FILE,
    PM_PLAN_FILE,
    PM_RESPONSES_FILE,
)
from services.manual_service_storage import MANUAL_SERVICE_RECORDS_FILE
from views.aed_management import render_aed_management, render_aed_master_table
from views.dashboard import render_dashboard
from views.aed_map import render_aed_map_page
from views.issues import render_issues_page
from views.pm_checklist import render_pm_checklist
from views.pm_planning import render_pm_planning_page
from views.report_issue import render_report_issue_page
from views.service_records import render_service_records_page


PageRenderer = Callable[[], None]


PAGE_RENDERERS: dict[str, PageRenderer] = {
    "Operations Dashboard": partial(
        render_dashboard,
        aed_data_file=AED_DATA_FILE,
        issue_record_file=ISSUE_RECORD_FILE,
        pm_response_file=PM_RESPONSES_FILE,
        pm_plan_file=PM_PLAN_FILE,
        aed_history_file=AED_HISTORY_FILE,
        issue_history_file=ISSUE_HISTORY_FILE,
    ),
    "AED Management": partial(
        render_aed_management,
        aed_data_file=AED_DATA_FILE,
        history_file=AED_HISTORY_FILE,
    ),
    "AED Master Table": partial(
        render_aed_master_table,
        aed_data_file=AED_DATA_FILE,
        history_file=AED_HISTORY_FILE,
    ),
    # Preserve old bookmarked/session routes from earlier builds.
    "AED Master Data": partial(
        render_aed_master_table,
        aed_data_file=AED_DATA_FILE,
        history_file=AED_HISTORY_FILE,
    ),
    "AED Map": partial(
        render_aed_map_page,
        aed_csv_file=AED_DATA_FILE,
    ),
    "PM Planning": partial(
        render_pm_planning_page,
        aed_csv_file=AED_DATA_FILE,
    ),
    "PM Checklist": render_pm_checklist,
    "Service Records": partial(
        render_service_records_page,
        response_csv_file=PM_RESPONSES_FILE,
        aed_csv_file=AED_DATA_FILE,
        manual_service_file=MANUAL_SERVICE_RECORDS_FILE,
        issue_record_file=ISSUE_RECORD_FILE,
        resolution_file=ISSUE_RESOLUTION_FILE,
    ),
    "Report Issue": partial(
        render_report_issue_page,
        aed_csv_file=AED_DATA_FILE,
        issue_csv_file=ISSUE_RECORD_FILE,
    ),
    "Issues": partial(
        render_issues_page,
        issue_csv_file=ISSUE_RECORD_FILE,
    ),
}


def render_current_page(page_name: str) -> None:
    """Render one registered page and fail safely for an unknown route."""

    renderer = PAGE_RENDERERS.get(page_name, PAGE_RENDERERS["Operations Dashboard"])
    renderer()
