from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterable

import pandas as pd


def atomic_write_csv(
    dataframe: pd.DataFrame,
    csv_file: str | Path,
    *,
    preferred_columns: Iterable[str] | None = None,
) -> None:
    """Write a CSV through a temporary file, then atomically replace it."""

    target_path = Path(csv_file)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    data = dataframe.copy().fillna("")

    if preferred_columns is not None:
        preferred = list(preferred_columns)
        for column in preferred:
            if column not in data.columns:
                data[column] = ""
        extras = [column for column in data.columns if column not in preferred]
        data = data[preferred + extras]

    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".csv",
            prefix=f".{target_path.stem}_",
            dir=target_path.parent,
            delete=False,
            encoding="utf-8-sig",
            newline="",
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            data.to_csv(temporary_file, index=False)

        os.replace(temporary_path, target_path)

    except Exception:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def read_csv_safe(
    csv_file: str | Path,
    *,
    columns: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Read a UTF-8 CSV and optionally ensure a stable column set."""

    path = Path(csv_file)
    required = list(columns or [])

    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=required)

    try:
        dataframe = pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        ).fillna("")
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=required)

    for column in required:
        if column not in dataframe.columns:
            dataframe[column] = ""

    return dataframe
