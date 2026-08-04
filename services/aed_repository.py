"""Single read/write gateway for AED master data used by every Streamlit page."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from config import (
    AED_CACHE_FILE,
    EXCEL_FILE,
    EXCEL_SHEET,
    SYNC_STATE_FILE,
)
from services.aed_service import load_aed_data
from services.excel_sync_service import (
    SyncResult,
    get_excel_signature,
    load_sync_state,
    sync_excel_to_cache,
)
from services.excel_transaction_service import (
    OperationResult,
    execute_add_unit,
    execute_batch_updates,
    execute_deactivate_unit,
    execute_unit_update,
    load_latest_lifecycle_status,
)
from services.onedrive_excel_service import (
    OneDriveError,
    download_workbook,
    is_cloud_onedrive_enabled,
    load_onedrive_state,
    preserve_pending_local_copy,
    upload_workbook,
)
from utils.text_utils import clean_text

_last_result: SyncResult | None = None
_last_cloud_message = ""


def _prepare_workbook(*, force: bool) -> str:
    """Refresh the private local cache from OneDrive and return its eTag."""
    global _last_cloud_message
    if not is_cloud_onedrive_enabled():
        return ""
    result = download_workbook(force=force)
    _last_cloud_message = result.message
    return result.etag


def ensure_cache_current(*, force: bool = False) -> SyncResult:
    global _last_result
    try:
        cloud_mode = is_cloud_onedrive_enabled()
        _prepare_workbook(force=force)
        _last_result = sync_excel_to_cache(
            force=force,
            preserve_cache_only_units=not cloud_mode,
        )
    except Exception as error:
        _last_result = SyncResult(
            status="failed",
            message=str(error),
            source_exists=Path(EXCEL_FILE).exists(),
            changed=False,
            row_count=0,
        )
    return _last_result


def get_all_units(*, refresh: bool = True, include_inactive: bool = False) -> pd.DataFrame:
    """Return the latest validated AED table, hiding inactive units by default."""
    if refresh:
        sync_result = ensure_cache_current(force=False)
        if is_cloud_onedrive_enabled() and sync_result.status not in {"synced", "up_to_date"}:
            raise RuntimeError(
                "The official OneDrive Excel could not be loaded; stale local AED data "
                "will not be displayed. " + (sync_result.message or "")
            )
    try:
        dataframe = load_aed_data(AED_CACHE_FILE)
    except Exception:
        if refresh and Path(EXCEL_FILE).exists():
            retry = ensure_cache_current(force=True)
            if is_cloud_onedrive_enabled() and retry.status not in {"synced", "up_to_date"}:
                raise RuntimeError(
                    "The official OneDrive Excel could not be reloaded. "
                    + (retry.message or "")
                )
            dataframe = load_aed_data(AED_CACHE_FILE)
        else:
            raise

    if include_inactive or dataframe.empty:
        return dataframe
    lifecycle = load_latest_lifecycle_status()
    if not lifecycle:
        return dataframe
    inactive = {serial for serial, status in lifecycle.items() if status.casefold() != "active"}
    if not inactive:
        return dataframe
    return dataframe[
        ~dataframe["Serial Number"].astype(str).str.strip().str.casefold().isin(inactive)
    ].copy()


def get_unit_by_serial(serial_number: str, *, refresh: bool = True, include_inactive: bool = True) -> pd.Series | None:
    serial = clean_text(serial_number).casefold()
    if not serial:
        return None
    dataframe = get_all_units(refresh=refresh, include_inactive=include_inactive)
    matches = dataframe[dataframe["Serial Number"].astype(str).str.strip().str.casefold().eq(serial)]
    return None if matches.empty else matches.iloc[0].copy()


def refresh_from_excel() -> SyncResult:
    return ensure_cache_current(force=True)


def get_sync_status() -> dict[str, Any]:
    state = load_sync_state(SYNC_STATE_FILE)
    result = _last_result
    signature = get_excel_signature(EXCEL_FILE)
    signature_dict = (
        {"modified_time_ns": signature.modified_time_ns, "size": signature.size}
        if signature is not None else None
    )
    update_available = bool(signature_dict and signature_dict != state.get("last_successful_signature"))
    excel_last_modified = ""
    if signature is not None:
        excel_last_modified = datetime.fromtimestamp(
            signature.modified_time_ns / 1_000_000_000
        ).astimezone().strftime("%d-%m-%Y %H:%M:%S")
    cloud_enabled = is_cloud_onedrive_enabled()
    cloud_state = load_onedrive_state() if cloud_enabled else {}
    return {
        "excel_file": str(EXCEL_FILE),
        "excel_sheet": EXCEL_SHEET,
        "cache_file": str(AED_CACHE_FILE),
        "source_exists": Path(EXCEL_FILE).exists(),
        "status": result.status if result is not None else state.get("sync_status", "not_checked"),
        "message": result.message if result is not None else state.get("sync_message", ""),
        "last_sync_time": state.get("last_sync_time", ""),
        "excel_last_modified": excel_last_modified,
        "update_available": update_available,
        "row_count": state.get("row_count", 0),
        "warnings": list(result.warnings) if result is not None else list(state.get("warnings", []) or []),
        "signature": signature_dict,
        "onedrive_enabled": bool(cloud_enabled),
        "onedrive_remote_path": str(cloud_state.get("remote_path", "")),
        "onedrive_etag": str(cloud_state.get("etag", "")),
        "onedrive_last_download": str(cloud_state.get("last_download_time", "")),
        "onedrive_last_upload": str(cloud_state.get("last_upload_time", "")),
        "onedrive_web_url": str(cloud_state.get("web_url", "")),
        "onedrive_message": _last_cloud_message,
    }


def _restore_remote_after_failed_upload() -> None:
    try:
        download_workbook(force=True)
        sync_excel_to_cache(force=True)
    except Exception:
        pass


def _run_operation(operation: Callable[[], OperationResult]) -> OperationResult:
    """Run an existing safe Excel transaction and mirror it back to OneDrive."""
    if not is_cloud_onedrive_enabled():
        return operation()

    try:
        expected_etag = _prepare_workbook(force=True)
        # The forced download may have changed the local source, so refresh the
        # website cache before the transaction performs its field-level checks.
        sync_excel_to_cache(force=True)
    except Exception as error:
        return OperationResult("failed", f"Could not load the latest OneDrive Excel: {error}")

    result = operation()
    if not result.excel_updated:
        return result

    try:
        upload = upload_workbook(expected_etag=expected_etag)
        return replace(
            result,
            message="OneDrive Excel updated and the website synchronised successfully.",
            warnings=tuple(result.warnings) + ((upload.message,) if upload.message else tuple()),
        )
    except OneDriveError as error:
        pending = preserve_pending_local_copy("upload_failed")
        _restore_remote_after_failed_upload()
        pending_note = f" A recovery copy was saved at {pending}." if pending else ""
        return replace(
            result,
            status="failed",
            message=(
                f"The local transaction passed, but OneDrive was not overwritten: {error}."
                f"{pending_note} Refresh AED Data before trying again."
            ),
        )


def update_unit(
    *, serial_number: str, changes: Mapping[str, Any], original_values: Mapping[str, Any],
    user: str, source_page: str, session_id: str = "unknown-session",
) -> OperationResult:
    return _run_operation(lambda: execute_unit_update(
        serial_number=serial_number,
        desired_values=changes,
        original_values=original_values,
        user=user,
        session_id=session_id,
        source_page=source_page,
    ))


def batch_update_units(
    *, updates: Sequence[Mapping[str, Any]], user: str, source_page: str,
    session_id: str = "unknown-session",
) -> OperationResult:
    return _run_operation(lambda: execute_batch_updates(
        updates=updates,
        user=user,
        session_id=session_id,
        source_page=source_page,
    ))


def add_unit(*, values: Mapping[str, Any], user: str, source_page: str, session_id: str = "unknown-session") -> OperationResult:
    return _run_operation(lambda: execute_add_unit(
        values=values,
        user=user,
        session_id=session_id,
        source_page=source_page,
    ))


def deactivate_unit(*, serial_number: str, user: str, reason: str, source_page: str, session_id: str = "unknown-session") -> OperationResult:
    return _run_operation(lambda: execute_deactivate_unit(
        serial_number=serial_number,
        user=user,
        session_id=session_id,
        source_page=source_page,
        reason=reason,
    ))
