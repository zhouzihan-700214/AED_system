from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd


DISPLAY_DATE_FORMAT = "%d-%m-%Y"


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
