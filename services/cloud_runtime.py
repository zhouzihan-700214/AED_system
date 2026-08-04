"""Runtime-only Microsoft OneDrive configuration.

This module is the single source of truth for cloud settings. It reads
``st.secrets`` directly at runtime instead of copying values from ``config.py``
or first converting Streamlit's secrets proxy into a plain ``dict``.

Some Streamlit runtimes expose ``st.secrets`` as a lazy dict-like proxy. Direct
item access is supported by Streamlit, while eager conversion can omit nested
sections in some environments. The loader therefore walks the proxy through
its public mapping interface and only falls back to plain mappings and
environment variables when necessary.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
from typing import Any, Iterable, Iterator
import os
import re


_DEFAULT_AUTHORITY = "https://login.microsoftonline.com/consumers"
_DEFAULT_WORKBOOK = "/AED System/IB_list_TEST.xlsx"
_DEFAULT_STATE = "/AED System/AED_System_State.zip"
_MISSING = object()


def _normalise_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _plain_mapping(value: Any) -> dict[str, Any]:
    """Best-effort conversion used only as a compatibility fallback."""

    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            converted = to_dict()
            if isinstance(converted, Mapping):
                return {str(key): item for key, item in converted.items()}
        except Exception:
            pass
    try:
        return {str(key): item for key, item in dict(value).items()}
    except Exception:
        return {}


def _direct_get(container: Any, key: str, default: Any = _MISSING) -> Any:
    """Read one key from a mapping/proxy without converting the whole object."""

    try:
        return container[key]
    except Exception:
        pass

    getter = getattr(container, "get", None)
    if callable(getter):
        try:
            value = getter(key, _MISSING)
            if value is not _MISSING:
                return value
        except Exception:
            pass

    # Attribute access is officially supported by st.secrets for TOML keys that
    # are valid Python identifiers.
    if str(key).isidentifier():
        try:
            return getattr(container, key)
        except Exception:
            pass

    return default


def _direct_keys(container: Any) -> list[str]:
    """Return secret key names only; credential values are never exposed."""

    keys_method = getattr(container, "keys", None)
    if callable(keys_method):
        try:
            return [str(key) for key in keys_method()]
        except Exception:
            pass

    mapping = _plain_mapping(container)
    return [str(key) for key in mapping.keys()]


def _is_container(value: Any) -> bool:
    if isinstance(value, (str, bytes, int, float, bool, type(None))):
        return False
    return bool(_direct_keys(value))


def _walk_secret_nodes(
    root: Any,
    *,
    label: str = "Streamlit Secrets",
    depth: int = 0,
    seen: set[int] | None = None,
) -> Iterator[tuple[str, Any]]:
    """Yield root and nested secret sections through direct proxy access."""

    if depth > 5 or root is None:
        return
    if seen is None:
        seen = set()
    object_id = id(root)
    if object_id in seen:
        return
    seen.add(object_id)

    yield label, root
    for key in _direct_keys(root):
        child = _direct_get(root, key)
        if child is not _MISSING and _is_container(child):
            if label == "Streamlit Secrets":
                child_label = f"[{key}]"
            elif label.startswith("[") and label.endswith("]"):
                child_label = f"[{label[1:-1]}.{key}]"
            else:
                child_label = f"[{key}]"
            yield from _walk_secret_nodes(
                child,
                label=child_label,
                depth=depth + 1,
                seen=seen,
            )


def _streamlit_root() -> Any:
    try:
        import streamlit as st

        # Return the live proxy. Do not eagerly call dict(st.secrets).
        return st.secrets
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


def _value_from_node(node: Any, aliases: tuple[str, ...]) -> str:
    """Read a field from one section using exact and normalised key matching."""

    # First use direct exact access for the canonical aliases.
    for alias in aliases:
        value = _direct_get(node, alias)
        if value is not _MISSING and str(value or "").strip():
            return str(value).strip()

    # Then compare the actual key names after normalisation. This supports
    # client-id, CLIENT ID, ClientId, and similar TOML names.
    aliases_normalised = {_normalise_key(alias) for alias in aliases}
    for actual_key in _direct_keys(node):
        if _normalise_key(actual_key) not in aliases_normalised:
            continue
        value = _direct_get(node, actual_key)
        if value is not _MISSING and str(value or "").strip():
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
    """Read Microsoft settings directly from the current Streamlit runtime.

    Preferred TOML format::

        [microsoft]
        client_id = "..."
        client_secret = "..."
        redirect_uri = "https://example.streamlit.app/"

    Matching is case-insensitive and ignores underscores, spaces and hyphens.
    Nested sections and root-level legacy keys are supported.
    """

    root = secret_root if secret_root is not None else _streamlit_root()
    nodes = list(_walk_secret_nodes(root))
    if not nodes:
        nodes = [("Streamlit Secrets", root)]

    preferred_names = {"microsoft", "microsoftconfig", "azure", "azuread", "onedrive"}

    # Prefer a [microsoft]-like section, then any section containing client ID,
    # then all remaining nodes including the root.
    preferred_nodes: list[tuple[str, Any]] = []
    credential_nodes: list[tuple[str, Any]] = []
    other_nodes: list[tuple[str, Any]] = []
    for label, node in nodes:
        leaf_text = label.strip("[]").rsplit(".", 1)[-1]
        leaf = _normalise_key(leaf_text)
        normalised_keys = {_normalise_key(key) for key in _direct_keys(node)}
        if leaf in preferred_names:
            preferred_nodes.append((label, node))
        elif normalised_keys.intersection(
            {"clientid", "microsoftclientid", "applicationclientid", "appclientid"}
        ):
            credential_nodes.append((label, node))
        else:
            other_nodes.append((label, node))

    ordered_nodes = preferred_nodes + credential_nodes + other_nodes

    aliases = {
        "client_id": (
            "client_id", "client-id", "client id", "clientId",
            "microsoft_client_id", "MICROSOFT_CLIENT_ID",
            "application_client_id", "app_client_id",
        ),
        "client_secret": (
            "client_secret", "client-secret", "client secret", "clientSecret",
            "microsoft_client_secret", "MICROSOFT_CLIENT_SECRET",
            "client_secret_value", "client secret value", "secret_value",
        ),
        "authority": (
            "authority", "microsoft_authority", "tenant_authority", "login_authority",
        ),
        "redirect_uri": (
            "redirect_uri", "redirect-uri", "redirect uri", "redirectUri",
            "microsoft_redirect_uri", "reply_url", "reply url",
            "callback_url", "redirect_url",
        ),
        "onedrive_file_path": (
            "onedrive_file_path", "onedrive-file-path", "onedrive file path",
            "onedriveFilePath", "workbook_path", "excel_file_path", "ib_list_path",
        ),
        "system_state_path": (
            "system_state_path", "system-state-path", "system state path",
            "systemStatePath", "state_zip_path", "onedrive_state_path",
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
    source = "Streamlit Secrets"
    client_source = ""
    for field, field_aliases in aliases.items():
        values[field] = ""
        for label, node in ordered_nodes:
            found = _value_from_node(node, field_aliases)
            if found:
                values[field] = found
                if field == "client_id":
                    client_source = label
                break
        if not values[field]:
            for env_name in env_aliases[field]:
                env_value = str(os.getenv(env_name, "") or "").strip()
                if env_value:
                    values[field] = env_value
                    if field == "client_id":
                        client_source = f"environment variable {env_name}"
                    break

    if client_source:
        source = client_source

    values["authority"] = values["authority"] or _DEFAULT_AUTHORITY
    values["redirect_uri"] = values["redirect_uri"] or _request_redirect_uri()
    values["onedrive_file_path"] = values["onedrive_file_path"] or _DEFAULT_WORKBOOK
    values["system_state_path"] = values["system_state_path"] or _DEFAULT_STATE

    return CloudSettings(source=source, **values)


def detected_secret_keys(secret_root: Any | None = None) -> tuple[str, ...]:
    """Return non-sensitive key names for troubleshooting only."""

    root = secret_root if secret_root is not None else _streamlit_root()
    names: list[str] = []
    for label, node in _walk_secret_nodes(root):
        for key in _direct_keys(node):
            full_name = f"{label}.{key}" if label else key
            names.append(full_name)
    return tuple(dict.fromkeys(names))


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
