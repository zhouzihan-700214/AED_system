from __future__ import annotations

import html
from typing import Any

import pandas as pd

from utils.text_utils import clean_text


def safe_html(value: Any) -> str:
    return html.escape(clean_text(value))

def format_display_date(value: Any) -> str:
    text = clean_text(value)

    if not text:
        return "—"

    parsed = pd.to_datetime(
        text,
        format="%d-%m-%Y",
        errors="coerce",
    )

    if pd.isna(parsed):
        return text

    return parsed.strftime("%d %b %Y")
