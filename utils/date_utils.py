from __future__ import annotations

from datetime import date, datetime
import os
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd


DISPLAY_DATE_FORMAT = "%d-%m-%Y"
DEFAULT_APP_TIMEZONE = "Asia/Singapore"


def application_timezone() -> ZoneInfo | None:
    """Return the configured business timezone.

    Streamlit Cloud commonly runs in UTC, while this AED workflow is operated
    in Singapore. The environment variable keeps the deployment configurable
    without requiring a hard import from ``config.py``.
    """

    timezone_name = os.getenv("AED_TIMEZONE", DEFAULT_APP_TIMEZONE).strip()
    try:
        return ZoneInfo(timezone_name or DEFAULT_APP_TIMEZONE)
    except ZoneInfoNotFoundError:
        return None


def application_now() -> datetime:
    """Return the current time in the configured business timezone."""

    timezone = application_timezone()
    if timezone is None:
        return datetime.now().astimezone()
    return datetime.now(timezone)


def application_today() -> date:
    """Return today's date in the configured business timezone."""

    return application_now().date()


def parse_optional_date(value: Any) -> date | None:
    """Parse common project date values without raising on empty input."""

    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return None

    return parsed.date()


def format_optional_date(value: Any) -> str:
    """Format a date-like value as DD-MM-YYYY, or return an empty string."""

    parsed = parse_optional_date(value)
    return parsed.strftime(DISPLAY_DATE_FORMAT) if parsed else ""
