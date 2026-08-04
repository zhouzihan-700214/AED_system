"""Runtime-only Microsoft OneDrive configuration.

This module is the single source of truth for cloud settings.  It intentionally
reads ``st.secrets`` at runtime instead of copying values from ``config.py`` at
module import time.  That prevents a Streamlit process from keeping stale empty
credentials after an app reboot or a mixed deployment.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
from typing import Any, Iterable
import os
import re


_DEFAULT_AUTHORITY = "https://login.microsoftonline.com/consumers"
_DEFAULT_WORKBOOK = "/AED System/IB_list_TEST.xlsx"
_DEFAULT_STATE = "/AED System/AED_System_State.zip"


def _normalise_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _plain_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    try:
        return {str(key): item for key, item in dict(value).items()}
    except (TypeError, ValueError):
        return {}


def _normalised_mapping(value: Any) -> dict[str, Any]:
    return {_normalise_key(key): item for key, item in _plain_mapping(value).items()}


def _walk_mappings(value: Any, *, depth: int = 0) -> Iterable[tuple[str, dict[str, Any]]]:
    """Yield nested secret mappings without exposing their values."""

    if depth > 4:
        return
    mapping = _plain_mapping(value)
    if not mapping:
        return
    yield ("root" if depth == 0 else "nested", mapping)
    for key, child in mapping.items():
        child_map = _plain_mapping(child)
        if child_map:
            for _, nested in _walk_mappings(child_map, depth=depth + 1):
                yield str(key), nested


def _streamlit_root() -> dict[str, Any]:
    try:
        import streamlit as st

        return _plain_mapping(st.secrets)
    except Exception:
        return {}


def _request_redirect_uri() -> str:
    """Best-effort fallback for the current Streamlit app URL."""

    try:
        import streamlit as st

        context = getattr(st, "context", None)
        url = str(getattr(context, "url", "") or "").strip()
        if url.startswith(("https://", "http://")):
            return url.split("?", 1)[0].rstrip("/") + "/"

        headers = _plain_mapping(getattr(context, "headers", {}))
        normalised = {_normalise_key(key): str(value or "") for key, value in headers.items()}
        host = normalised.get("xforwardedhost") or normalised.get("host")
        protocol = normalised.get("xforwardedproto") or "https"
        if host:
            return f"{protocol}://{host.strip().rstrip('/')}/"
    except Exception:
        pass
    return ""


def _first_value(mappings: Iterable[dict[str, Any]], aliases: tuple[str, ...]) -> str:
    normalised_aliases = tuple(_normalise_key(alias) for alias in aliases)
    for mapping in mappings:
        normalised = _normalised_mapping(mapping)
        for alias in normalised_aliases:
            value = normalised.get(alias)
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""


@dataclass(frozen=True)
class CloudSettings:
    client_id: str
    client_secret: str
    authority: str
    redirect_uri: str
    onedrive_file_path: str
    system_state_path: str
    source: str = ""

    @property
    def missing_keys(self) -> tuple[str, ...]:
        required = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
        }
        return tuple(key for key, value in required.items() if not str(value or "").strip())

    @property
    def configured(self) -> bool:
        return not self.missing_keys

    def as_dict(self) -> dict[str, str]:
        return {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "authority": self.authority,
            "redirect_uri": self.redirect_uri,
            "onedrive_file_path": self.onedrive_file_path,
            "system_state_path": self.system_state_path,
        }


def load_cloud_settings(secret_root: Any | None = None) -> CloudSettings:
    """Read Microsoft settings directly from the current runtime.

    The preferred format is ``[microsoft]``.  For resilience, key matching is
    case-insensitive and ignores underscores, spaces and hyphens.  A nested
    section is accepted when it contains Microsoft credential keys.
    """

    root = _plain_mapping(secret_root) if secret_root is not None else _streamlit_root()
    candidates: list[dict[str, Any]] = []
    source = "Streamlit Secrets"

    preferred_names = {
        "microsoft", "microsoftconfig", "azure", "azuread", "onedrive"
    }
    for key, value in root.items():
        child = _plain_mapping(value)
        if child and _normalise_key(key) in preferred_names:
            candidates.append(child)
            source = f"[{key}]"

    # Also locate a Microsoft-like nested mapping.  This covers Secrets copied
    # from older builds where the section name was changed but the keys remain.
    for key, mapping in _walk_mappings(root):
        keys = set(_normalised_mapping(mapping))
        if keys.intersection({"clientid", "microsoftclientid", "applicationclientid"}):
            if mapping not in candidates:
                candidates.append(mapping)
                source = f"[{key}]"

    candidates.append(root)

    aliases = {
        "client_id": (
            "client_id", "clientId", "microsoft_client_id",
            "MICROSOFT_CLIENT_ID", "application_client_id", "app_client_id",
        ),
        "client_secret": (
            "client_secret", "clientSecret", "microsoft_client_secret",
            "MICROSOFT_CLIENT_SECRET", "client_secret_value", "secret_value",
        ),
        "authority": (
            "authority", "microsoft_authority", "tenant_authority", "login_authority",
        ),
        "redirect_uri": (
            "redirect_uri", "redirectUri", "microsoft_redirect_uri",
            "reply_url", "callback_url", "redirect_url",
        ),
        "onedrive_file_path": (
            "onedrive_file_path", "onedriveFilePath", "workbook_path",
            "excel_file_path", "ib_list_path",
        ),
        "system_state_path": (
            "system_state_path", "systemStatePath", "state_zip_path",
            "onedrive_state_path",
        ),
    }
    env_aliases = {
        "client_id": ("MICROSOFT_CLIENT_ID", "AZURE_CLIENT_ID"),
        "client_secret": ("MICROSOFT_CLIENT_SECRET", "AZURE_CLIENT_SECRET"),
        "authority": ("MICROSOFT_AUTHORITY",),
        "redirect_uri": ("MICROSOFT_REDIRECT_URI",),
        "onedrive_file_path": ("MICROSOFT_ONEDRIVE_FILE_PATH",),
        "system_state_path": ("MICROSOFT_SYSTEM_STATE_PATH",),
    }

    values: dict[str, str] = {}
    for field, field_aliases in aliases.items():
        values[field] = _first_value(candidates, field_aliases)
        if not values[field]:
            for env_name in env_aliases[field]:
                env_value = str(os.getenv(env_name, "") or "").strip()
                if env_value:
                    values[field] = env_value
                    source = f"environment variable {env_name}"
                    break

    values["authority"] = values["authority"] or _DEFAULT_AUTHORITY
    values["redirect_uri"] = values["redirect_uri"] or _request_redirect_uri()
    values["onedrive_file_path"] = values["onedrive_file_path"] or _DEFAULT_WORKBOOK
    values["system_state_path"] = values["system_state_path"] or _DEFAULT_STATE

    return CloudSettings(source=source, **values)


def apply_to_config(config_module: Any, settings: CloudSettings | None = None) -> CloudSettings:
    """Publish runtime settings to legacy modules without making them authoritative."""

    resolved = settings or load_cloud_settings()
    config_module.MICROSOFT_CONFIG = resolved.as_dict()
    config_module.MICROSOFT_SECRET_SOURCE = resolved.source
    config_module.MICROSOFT_MISSING_KEYS = resolved.missing_keys
    config_module.ONEDRIVE_CLOUD_ENABLED = resolved.configured
    config_module.ALLOW_LOCAL_DATA_MODE = False
    config_module.REQUIRE_ONEDRIVE_SIGN_IN = True

    if resolved.configured:
        cache_dir = Path(getattr(config_module, "ONEDRIVE_CACHE_DIR"))
        file_name = Path(resolved.onedrive_file_path).name or "IB_list_TEST.xlsx"
        config_module.EXCEL_FILE = cache_dir / file_name
        config_module.LOCK_FILE = config_module.EXCEL_FILE.with_suffix(
            config_module.EXCEL_FILE.suffix + ".lock"
        )
    return resolved
