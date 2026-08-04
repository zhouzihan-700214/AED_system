"""Safe one-way synchronization from the external IB List into the CSV mirror.

Stage 2 implements Excel -> website only. The source workbook is never edited.
The supplied company workbook has a two-row header and Remarks continuation
rows, so this module normalises that real layout before rebuilding aed_data.csv.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from config import (
    AED_CACHE_FILE,
    CACHE_BACKUP_DIR,
    EXCEL_FILE,
    EXCEL_SHEET,
    MAX_CACHE_BACKUPS,
    PRESERVE_CACHE_ONLY_UNITS,
    SERIAL_COLUMN,
    SYNC_LOCK_FILE,
    SYNC_STATE_FILE,
    TEMP_DIR,
    ensure_project_directories,
)
from services.aed_service import (
    DATE_COLUMNS,
    MASTER_COLUMNS,
    ensure_columns,
    load_aed_data,
    save_aed_data,
)
from services.excel_lock_service import operation_lock
from services.column_mapping import (
    clean_excel_header,
    map_excel_header,
    normalise_header,
)
from utils.text_utils import clean_text


@dataclass(frozen=True)
class ExcelSignature:
    modified_time_ns: int
    size: int


@dataclass(frozen=True)
class SyncResult:
    status: str
    message: str
    source_exists: bool
    changed: bool = False
    row_count: int = 0
    synced_at: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def success(self) -> bool:
        return self.status in {"synced", "up_to_date", "csv_fallback"}


CACHE_OWNED_COLUMNS = [
    "Latitude",
    "Longitude",
    "OneMap Address",
    "Geocoding Status",
    "PM Interval Months",
]

REAL_IB_REQUIRED_HEADERS = {
    "Serial Number",
    "Block / Locations",
    "Street Name",
    "Postal Code",
    "Next PM Due",
}

EMPTY_MARKERS = {"", "n/a", "na", "nil", "none", "nan", "-"}


def _now_text() -> str:
    return datetime.now().astimezone().strftime("%d-%m-%Y %H:%M:%S")


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def get_excel_signature(excel_file: str | Path = EXCEL_FILE) -> ExcelSignature | None:
    path = Path(excel_file)
    if not path.exists() or not path.is_file():
        return None

    stat = path.stat()
    return ExcelSignature(modified_time_ns=stat.st_mtime_ns, size=stat.st_size)


def _signature_dict(signature: ExcelSignature | None) -> dict[str, int] | None:
    return asdict(signature) if signature is not None else None


def load_sync_state(state_file: str | Path = SYNC_STATE_FILE) -> dict[str, Any]:
    path = Path(state_file)
    if not path.exists() or path.stat().st_size == 0:
        return {}

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}

    return data if isinstance(data, dict) else {}


def save_sync_state(
    state: dict[str, Any],
    state_file: str | Path = SYNC_STATE_FILE,
) -> None:
    path = Path(state_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix=f".{path.stem}_",
            dir=path.parent,
            delete=False,
            encoding="utf-8",
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(state, handle, indent=2, ensure_ascii=False)
        temporary_path.replace(path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _record_result(
    result: SyncResult,
    *,
    signature: ExcelSignature | None,
    state_file: str | Path,
    excel_file: str | Path,
    excel_sheet: str,
) -> None:
    previous = load_sync_state(state_file)
    state = {
        **previous,
        "excel_file": str(Path(excel_file)),
        "excel_sheet": excel_sheet,
        "observed_excel_signature": _signature_dict(signature),
        "last_checked_at": _now_text(),
        "last_sync_time": result.synced_at or previous.get("last_sync_time", ""),
        "sync_status": result.status,
        "sync_message": result.message,
        "row_count": result.row_count,
        "warnings": list(result.warnings),
    }
    if result.status in {"synced", "up_to_date"} and signature is not None:
        state["last_successful_signature"] = _signature_dict(signature)
    save_sync_state(state, state_file)


def _copy_stable_snapshot(source: Path, temp_dir: Path) -> tuple[Path, ExcelSignature]:
    """Copy a workbook only when its version is stable before and after copying."""

    temp_dir.mkdir(parents=True, exist_ok=True)

    for _ in range(3):
        before = get_excel_signature(source)
        if before is None:
            raise FileNotFoundError(f"Cannot find the Excel source: {source}")

        snapshot = temp_dir / (
            f"read_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
            f"{source.suffix}"
        )
        shutil.copy2(source, snapshot)

        after = get_excel_signature(source)
        if before == after:
            return snapshot, after

        snapshot.unlink(missing_ok=True)

    raise OSError(
        "The Excel file changed while it was being copied. Save the workbook "
        "completely, then refresh again."
    )


def _normalise_lock_path(
    lock_file: str | Path,
    state_file: str | Path,
) -> Path:
    configured = Path(lock_file)
    if configured == Path(SYNC_LOCK_FILE) and Path(state_file) != Path(SYNC_STATE_FILE):
        return Path(state_file).with_suffix(".lock")
    return configured


@contextmanager
def _acquire_sync_lock(lock_file: Path, stale_seconds: int = 300) -> Iterator[None]:
    del stale_seconds
    metadata = {
        "operation_id": f"refresh-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "operation_type": "REFRESH_EXCEL",
        "user": "System",
        "session_id": "manual-refresh",
        "serial_numbers": [],
    }
    with operation_lock(metadata, lock_file):
        yield


def _is_empty_marker(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return clean_text(value).casefold() in EMPTY_MARKERS


def _clean_scalar(value: Any) -> str:
    if _is_empty_marker(value):
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = clean_text(value)
    if re.fullmatch(r"-?\d+\.0", text):
        return text[:-2]
    return text


def _format_excel_date(value: Any) -> str:
    if _is_empty_marker(value):
        return ""

    if isinstance(value, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(value).strftime("%d-%m-%Y")

    text = clean_text(value)

    try:
        numeric_value = float(text)
        if numeric_value.is_integer() and 20_000 <= numeric_value <= 80_000:
            parsed = pd.Timestamp("1899-12-30") + pd.to_timedelta(
                int(numeric_value), unit="D"
            )
            return parsed.strftime("%d-%m-%Y")
    except (TypeError, ValueError):
        pass

    if re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:\D|$)", text):
        parsed = pd.to_datetime(text, errors="coerce", yearfirst=True)
    else:
        parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)

    if pd.isna(parsed):
        return text
    return pd.Timestamp(parsed).strftime("%d-%m-%Y")


def _format_battery_history(value: Any) -> str:
    """Format a single Excel date, but retain multi-date history text verbatim."""

    if _is_empty_marker(value):
        return ""
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return _format_excel_date(value)

    text = _clean_scalar(value)
    if "," in text or ";" in text or " / " in text:
        return text

    if re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:\s|$)", text):
        parsed = pd.to_datetime(text, errors="coerce", yearfirst=True)
        if not pd.isna(parsed):
            return pd.Timestamp(parsed).strftime("%d-%m-%Y")

    try:
        numeric_value = float(text)
        if numeric_value.is_integer() and 20_000 <= numeric_value <= 80_000:
            return _format_excel_date(numeric_value)
    except (TypeError, ValueError):
        pass
    return text


def _format_postal_code(value: Any) -> str:
    if _is_empty_marker(value):
        return ""

    text = _clean_scalar(value)
    try:
        number = float(text)
        if number.is_integer():
            digits = str(int(number))
            if digits.isdigit() and len(digits) <= 6:
                return digits.zfill(6)
    except (TypeError, ValueError):
        pass

    compact = text.replace(" ", "")
    if compact.isdigit() and len(compact) <= 6:
        return compact.zfill(6)
    return text


def _header_lookup(columns: list[object]) -> dict[str, str]:
    return {
        normalise_header(column): clean_excel_header(column)
        for column in columns
    }


def _find_header(columns: list[object], name: str) -> str | None:
    return _header_lookup(columns).get(normalise_header(name))


def _is_real_ib_layout(raw: pd.DataFrame) -> bool:
    headers = {normalise_header(column) for column in raw.columns}
    return {
        normalise_header("SERIAL NUMBER"),
        normalise_header("Block / Locations"),
        normalise_header("Street Name"),
    }.issubset(headers)


def _validate_real_ib_headers(raw: pd.DataFrame) -> None:
    lookup = _header_lookup(list(raw.columns))
    missing = [
        header
        for header in sorted(REAL_IB_REQUIRED_HEADERS)
        if normalise_header(header) not in lookup
    ]
    if missing:
        raise ValueError(
            "The Excel sheet is missing required column(s): " + ", ".join(missing)
        )


def _combine_remarks(existing: Any, continuation: Any) -> str:
    first = _clean_scalar(existing)
    second = _clean_scalar(continuation)
    if not first:
        return second
    if not second:
        return first
    return f"{first.rstrip()} {second.lstrip()}"


def _prepare_real_ib_rows(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Skip the auxiliary header and merge blank-serial Remarks continuation rows."""

    _validate_real_ib_headers(raw)
    source = raw.copy()
    source.columns = [clean_excel_header(column) for column in source.columns]

    serial_column = _find_header(list(source.columns), "SERIAL NUMBER")
    remarks_column = _find_header(list(source.columns), "Remarks")
    if serial_column is None:
        raise ValueError("The Excel sheet is missing required column: SERIAL NUMBER")

    records: list[dict[str, Any]] = []
    warnings: list[str] = []

    for index, row in source.iterrows():
        excel_row = int(index) + 2  # row 1 is the main header
        serial = _clean_scalar(row.get(serial_column, ""))

        if serial:
            record = row.to_dict()
            record[serial_column] = serial
            records.append(record)
            continue

        continuation = (
            _clean_scalar(row.get(remarks_column, ""))
            if remarks_column is not None
            else ""
        )
        if continuation and records and remarks_column is not None:
            records[-1][remarks_column] = _combine_remarks(
                records[-1].get(remarks_column, ""), continuation
            )
            serial_value = _clean_scalar(records[-1].get(serial_column, ""))
            warnings.append(
                f"Excel row {excel_row} was merged into {serial_value} Remarks."
            )
        # The second auxiliary header row and completely blank rows are ignored.

    if not records:
        raise ValueError("The Excel sheet contains no AED rows with Serial Number.")

    return pd.DataFrame(records), warnings


def _build_location(block_value: Any, street_value: Any) -> str:
    block = _clean_scalar(block_value)
    street = _clean_scalar(street_value)
    if block and not block.casefold().startswith("blk"):
        block = f"Blk {block}"
    return " ".join(part for part in [block, street] if part).strip()


def _format_lift_lobby(value: Any) -> str:
    lobby = _clean_scalar(value)
    if not lobby or lobby.casefold() in {"n/a", "na", "none", "-"}:
        return lobby
    if lobby.casefold().startswith("lift lobby"):
        return lobby
    return f"Lift Lobby {lobby}"


def _combine_duplicate_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    if not dataframe.columns.duplicated().any():
        return dataframe

    combined: dict[str, pd.Series] = {}
    for column in dict.fromkeys(dataframe.columns):
        selected = dataframe.loc[:, dataframe.columns == column]
        value = selected.iloc[:, 0]
        for position in range(1, selected.shape[1]):
            replacement = selected.iloc[:, position]
            empty = value.map(_is_empty_marker)
            value = value.where(~empty, replacement)
        combined[column] = value
    return pd.DataFrame(combined)


def _normalise_excel_dataframe(
    raw: pd.DataFrame,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    warnings: list[str] = []
    dataframe = raw.copy()

    if _is_real_ib_layout(dataframe):
        dataframe, continuation_warnings = _prepare_real_ib_rows(dataframe)
        warnings.extend(continuation_warnings)

        block_column = _find_header(list(dataframe.columns), "Block / Locations")
        street_column = _find_header(list(dataframe.columns), "Street Name")
        dataframe["Location"] = dataframe.apply(
            lambda row: _build_location(
                row.get(block_column, "") if block_column else "",
                row.get(street_column, "") if street_column else "",
            ),
            axis=1,
        )

    dataframe.columns = [map_excel_header(column) for column in dataframe.columns]
    dataframe = _combine_duplicate_columns(dataframe)
    if "Lift Lobby" in dataframe.columns:
        dataframe["Lift Lobby"] = dataframe["Lift Lobby"].map(_format_lift_lobby)
    dataframe = ensure_columns(dataframe)

    for column in MASTER_COLUMNS:
        dataframe[column] = dataframe[column].map(_clean_scalar)

    for column in DATE_COLUMNS:
        dataframe[column] = dataframe[column].map(_format_excel_date)

    dataframe["Battery Replacement History"] = dataframe[
        "Battery Replacement History"
    ].map(_format_battery_history)
    dataframe[SERIAL_COLUMN] = dataframe[SERIAL_COLUMN].map(_clean_scalar)
    dataframe["Postal Code"] = dataframe["Postal Code"].map(_format_postal_code)

    intervals = pd.to_numeric(
        dataframe["PM Interval Months"], errors="coerce"
    ).fillna(12).clip(lower=1, upper=60).astype(int)
    dataframe["PM Interval Months"] = intervals.astype(str)

    for index, row in dataframe.iterrows():
        serial = _clean_scalar(row.get(SERIAL_COLUMN, "")) or f"row {index + 2}"
        for column in DATE_COLUMNS:
            value = _clean_scalar(row.get(column, ""))
            if not value:
                continue
            parsed = pd.to_datetime(value, format="%d-%m-%Y", errors="coerce")
            if not pd.isna(parsed) and not 2000 <= int(parsed.year) <= 2100:
                warnings.append(
                    f"{serial} {column} looks unusual ({value}). "
                    "Check the source Excel cell."
                )

    return dataframe[MASTER_COLUMNS].copy(), tuple(warnings)


def _validate_excel_dataframe(dataframe: pd.DataFrame) -> None:
    if SERIAL_COLUMN not in dataframe.columns:
        raise ValueError(f"The Excel sheet is missing: {SERIAL_COLUMN}")
    if dataframe.empty:
        raise ValueError("The Excel sheet contains no AED rows.")

    serials = dataframe[SERIAL_COLUMN].fillna("").astype(str).str.strip()
    if serials.eq("").any():
        rows = (serials[serials.eq("")].index + 2).tolist()
        preview = ", ".join(str(row) for row in rows[:8])
        raise ValueError(f"Serial Number is blank in parsed row(s): {preview}.")

    duplicate_mask = serials.str.casefold().duplicated(keep=False)
    if duplicate_mask.any():
        duplicates = sorted(set(serials[duplicate_mask].tolist()), key=str.casefold)
        raise ValueError(
            "Duplicate Serial Number values were found: "
            + ", ".join(duplicates[:10])
        )


def _serial_key(value: Any) -> str:
    return _clean_scalar(value).casefold()


def _merge_excel_with_cache(
    excel_dataframe: pd.DataFrame,
    cache_file: Path,
    *,
    preserve_cache_only_units: bool,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Retain website-only fields and coordinates for unchanged postal codes."""

    if not cache_file.exists() or cache_file.stat().st_size == 0:
        return ensure_columns(excel_dataframe), ()

    try:
        cache = load_aed_data(cache_file)
    except Exception:
        return ensure_columns(excel_dataframe), (
            "The previous CSV mirror could not be read, so website-only fields "
            "were not preserved.",
        )

    result = ensure_columns(excel_dataframe).copy()
    cache = ensure_columns(cache)
    cache_lookup = {
        _serial_key(row[SERIAL_COLUMN]): row
        for _, row in cache.iterrows()
        if _serial_key(row[SERIAL_COLUMN])
    }

    warnings: list[str] = []
    excel_keys: set[str] = set()

    for index, row in result.iterrows():
        key = _serial_key(row[SERIAL_COLUMN])
        excel_keys.add(key)
        existing = cache_lookup.get(key)
        if existing is None:
            continue

        for column in ["PM Interval Months"]:
            result.at[index, column] = _clean_scalar(existing.get(column, ""))

        old_postal = _format_postal_code(existing.get("Postal Code", ""))
        new_postal = _format_postal_code(row.get("Postal Code", ""))
        if old_postal == new_postal:
            for column in [
                "Latitude",
                "Longitude",
                "OneMap Address",
                "Geocoding Status",
            ]:
                result.at[index, column] = _clean_scalar(existing.get(column, ""))
        else:
            result.at[index, "Latitude"] = ""
            result.at[index, "Longitude"] = ""
            result.at[index, "OneMap Address"] = ""
            result.at[index, "Geocoding Status"] = "Postal Code changed - pending"
            warnings.append(
                f"{row[SERIAL_COLUMN]} Postal Code changed; coordinates were cleared "
                "for automatic refresh."
            )

    cache_only = cache[
        ~cache[SERIAL_COLUMN].map(_serial_key).isin(excel_keys)
    ].copy()
    if preserve_cache_only_units and not cache_only.empty:
        result = pd.concat([result, cache_only], ignore_index=True)
        warnings.append(
            f"Retained {len(cache_only)} existing website unit(s) not present in "
            "the test Excel because PRESERVE_CACHE_ONLY_UNITS is enabled."
        )

    return ensure_columns(result), tuple(warnings)


def _backup_cache(cache_file: Path, backup_dir: Path, max_backups: int) -> None:
    if not cache_file.exists() or cache_file.stat().st_size == 0:
        return

    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / (
        f"aed_data_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.csv"
    )
    shutil.copy2(cache_file, backup_path)

    backups = sorted(
        backup_dir.glob("aed_data_*.csv"),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for old_backup in backups[max(1, int(max_backups)):]:
        old_backup.unlink(missing_ok=True)


def sync_excel_to_cache(
    *,
    force: bool = False,
    excel_file: str | Path = EXCEL_FILE,
    excel_sheet: str = EXCEL_SHEET,
    cache_file: str | Path = AED_CACHE_FILE,
    state_file: str | Path = SYNC_STATE_FILE,
    temp_dir: str | Path = TEMP_DIR,
    lock_file: str | Path = SYNC_LOCK_FILE,
    backup_dir: str | Path = CACHE_BACKUP_DIR,
    preserve_cache_only_units: bool = PRESERVE_CACHE_ONLY_UNITS,
    max_backups: int = MAX_CACHE_BACKUPS,
    acquire_lock: bool = True,
    lock_metadata: dict[str, Any] | None = None,
) -> SyncResult:
    """Refresh the CSV mirror when the external workbook has changed."""

    ensure_project_directories()
    source = Path(excel_file)
    cache = Path(cache_file)
    signature = get_excel_signature(source)

    if signature is None:
        result = SyncResult(
            status="csv_fallback",
            message=(
                f"{source.name} is not present. The website is using "
                f"{cache.name} as a temporary local source."
            ),
            source_exists=False,
            changed=False,
            row_count=_safe_cache_row_count(cache),
        )
        previous = load_sync_state(state_file)
        if (
            previous.get("sync_status") != "csv_fallback"
            or previous.get("row_count") != result.row_count
        ):
            _record_result(
                result,
                signature=None,
                state_file=state_file,
                excel_file=source,
                excel_sheet=excel_sheet,
            )
        return result

    state = load_sync_state(state_file)
    if (
        not force
        and state.get("last_successful_signature") == _signature_dict(signature)
        and cache.exists()
        and cache.stat().st_size > 0
    ):
        return SyncResult(
            status="up_to_date",
            message="The website CSV mirror already matches the latest Excel version.",
            source_exists=True,
            changed=False,
            row_count=_safe_cache_row_count(cache),
            synced_at=str(state.get("last_sync_time", "")),
            warnings=tuple(state.get("warnings", []) or []),
        )

    snapshot: Path | None = None
    resolved_lock = _normalise_lock_path(lock_file, state_file)

    try:
        lock_context = (
            _acquire_sync_lock(resolved_lock)
            if acquire_lock
            else nullcontext()
        )
        with lock_context:
            # Another session may have completed the same refresh while this one
            # was waiting to acquire the lock, so compare signatures again.
            signature = get_excel_signature(source)
            state = load_sync_state(state_file)
            if (
                not force
                and signature is not None
                and state.get("last_successful_signature")
                == _signature_dict(signature)
                and cache.exists()
                and cache.stat().st_size > 0
            ):
                return SyncResult(
                    status="up_to_date",
                    message=(
                        "The website CSV mirror already matches the latest Excel "
                        "version."
                    ),
                    source_exists=True,
                    changed=False,
                    row_count=_safe_cache_row_count(cache),
                    synced_at=str(state.get("last_sync_time", "")),
                    warnings=tuple(state.get("warnings", []) or []),
                )

            snapshot, stable_signature = _copy_stable_snapshot(source, Path(temp_dir))
            try:
                raw = pd.read_excel(
                    snapshot,
                    sheet_name=excel_sheet,
                    dtype=object,
                    header=0,
                )
            except ValueError as error:
                with pd.ExcelFile(snapshot) as workbook:
                    available = ", ".join(workbook.sheet_names)
                raise ValueError(
                    f"Worksheet '{excel_sheet}' was not found. "
                    f"Available sheets: {available}."
                ) from error

            dataframe, parse_warnings = _normalise_excel_dataframe(raw)
            _validate_excel_dataframe(dataframe)
            dataframe, merge_warnings = _merge_excel_with_cache(
                dataframe,
                cache,
                preserve_cache_only_units=preserve_cache_only_units,
            )
            _validate_excel_dataframe(dataframe)

            _backup_cache(cache, Path(backup_dir), max_backups)
            save_aed_data(dataframe, cache)

            synced_at = _now_text()
            warnings = tuple(dict.fromkeys([*parse_warnings, *merge_warnings]))
            result = SyncResult(
                status="synced",
                message=(
                    f"Imported {len(dataframe)} AED unit(s) from "
                    f"{source.name} [{excel_sheet}]."
                ),
                source_exists=True,
                changed=True,
                row_count=len(dataframe),
                synced_at=synced_at,
                warnings=warnings,
            )
            _record_result(
                result,
                signature=stable_signature,
                state_file=state_file,
                excel_file=source,
                excel_sheet=excel_sheet,
            )
            return result

    except Exception as error:
        result = SyncResult(
            status="failed",
            message=str(error),
            source_exists=True,
            changed=False,
            row_count=_safe_cache_row_count(cache),
        )
        _record_result(
            result,
            signature=signature,
            state_file=state_file,
            excel_file=source,
            excel_sheet=excel_sheet,
        )
        raise
    finally:
        if snapshot is not None:
            try:
                snapshot.unlink(missing_ok=True)
            except OSError:
                pass


def _safe_cache_row_count(cache_file: str | Path) -> int:
    path = Path(cache_file)
    if not path.exists() or path.stat().st_size == 0:
        return 0
    try:
        dataframe = pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        )
        return len(dataframe)
    except Exception:
        return 0
