from typing import Any

import pandas as pd


def clean_text(value: Any) -> str:
    """Convert a value to stripped text and handle missing values."""

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip()
