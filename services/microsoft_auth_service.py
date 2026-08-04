"""Microsoft OAuth sign-in for browser-only OneDrive integration.

This implementation uses the project's existing ``requests`` dependency, so
no additional authentication package is required.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import requests


def _streamlit():
    """Import Streamlit lazily so service tests can run without the UI package."""
    import streamlit as st

    return st

import config
from services import cloud_runtime

GRAPH_SCOPES = ["openid", "profile", "offline_access", "User.Read", "Files.ReadWrite"]
TOKEN_KEY = "microsoft_oauth_token"
ACCOUNT_KEY = "microsoft_account"
AUTH_ERROR_KEY = "microsoft_auth_error"
STATE_MAX_AGE_SECONDS = 15 * 60
REQUEST_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class AuthenticationStatus:
    authenticated: bool
    account_name: str = ""
    message: str = ""


def _required_config() -> dict[str, str]:
    settings = cloud_runtime.apply_to_config(config)
    if not settings.configured:
        missing = ", ".join(settings.missing_keys) or "unknown settings"
        raise RuntimeError(
            "Microsoft OneDrive configuration is incomplete. Missing: " + missing
        )
    return settings.as_dict()


def _authority_endpoint(name: str) -> str:
    authority = _required_config()["authority"].rstrip("/")
    return f"{authority}/oauth2/v2.0/{name}"


def _signed_state() -> str:
    config = _required_config()
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(18)
    payload = f"{timestamp}.{nonce}"
    signature = hmac.new(
        config["client_secret"].encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{signature}"


def _valid_state(value: str) -> bool:
    try:
        timestamp_text, nonce, supplied_signature = value.split(".", 2)
        timestamp = int(timestamp_text)
    except (TypeError, ValueError):
        return False
    if not nonce or abs(int(time.time()) - timestamp) > STATE_MAX_AGE_SECONDS:
        return False
    config = _required_config()
    payload = f"{timestamp_text}.{nonce}"
    expected = hmac.new(
        config["client_secret"].encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, supplied_signature)


def build_sign_in_url() -> str:
    config = _required_config()
    params = {
        "client_id": config["client_id"],
        "response_type": "code",
        "redirect_uri": config["redirect_uri"],
        "response_mode": "query",
        "scope": " ".join(GRAPH_SCOPES),
        "state": _signed_state(),
        "prompt": "select_account",
    }
    return f"{_authority_endpoint('authorize')}?{urlencode(params)}"


def _normalise_query_params() -> dict[str, str]:
    st = _streamlit()
    result: dict[str, str] = {}
    for key in st.query_params:
        value: Any = st.query_params.get(key)
        if isinstance(value, list):
            result[key] = str(value[-1]) if value else ""
        else:
            result[key] = str(value or "")
    return result


def _token_error(response: requests.Response) -> str:
    try:
        payload = response.json()
        return str(
            payload.get("error_description")
            or payload.get("error")
            or response.text[:500]
        )
    except ValueError:
        return response.text[:500] or f"HTTP {response.status_code}"


def _store_token(payload: dict[str, Any], *, previous_refresh_token: str = "") -> None:
    st = _streamlit()
    expires_in = int(payload.get("expires_in", 3600) or 3600)
    stored = dict(payload)
    stored["expires_at"] = int(time.time()) + expires_in
    if not stored.get("refresh_token") and previous_refresh_token:
        stored["refresh_token"] = previous_refresh_token
    st.session_state[TOKEN_KEY] = stored


def _load_account_name(access_token: str) -> str:
    try:
        response = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"$select": "displayName,userPrincipalName,mail"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.ok:
            payload = response.json()
            return str(
                payload.get("mail")
                or payload.get("userPrincipalName")
                or payload.get("displayName")
                or "Microsoft account"
            )
    except requests.RequestException:
        pass
    return "Microsoft account"


def handle_auth_callback() -> bool:
    st = _streamlit()
    """Consume a Microsoft OAuth callback, if one is present in the URL."""
    if not cloud_runtime.apply_to_config(config).configured:
        return False
    params = _normalise_query_params()
    if params.get("error"):
        st.session_state[AUTH_ERROR_KEY] = (
            params.get("error_description") or params["error"]
        )
        st.query_params.clear()
        return False
    code = params.get("code", "")
    if not code:
        return False
    if not _valid_state(params.get("state", "")):
        st.session_state[AUTH_ERROR_KEY] = (
            "The Microsoft sign-in response could not be verified. Please sign in again."
        )
        st.query_params.clear()
        return False

    config = _required_config()
    response = requests.post(
        _authority_endpoint("token"),
        data={
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config["redirect_uri"],
            "scope": " ".join(GRAPH_SCOPES),
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    st.query_params.clear()
    if not response.ok:
        st.session_state[AUTH_ERROR_KEY] = _token_error(response)
        return False
    payload = response.json()
    if not payload.get("access_token"):
        st.session_state[AUTH_ERROR_KEY] = "Microsoft did not return an access token."
        return False
    _store_token(payload)
    st.session_state[ACCOUNT_KEY] = _load_account_name(str(payload["access_token"]))
    st.session_state.pop(AUTH_ERROR_KEY, None)
    return True


def _refresh_access_token(refresh_token: str) -> str | None:
    st = _streamlit()
    config = _required_config()
    response = requests.post(
        _authority_endpoint("token"),
        data={
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "redirect_uri": config["redirect_uri"],
            "scope": " ".join(GRAPH_SCOPES),
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if not response.ok:
        st.session_state[AUTH_ERROR_KEY] = _token_error(response)
        return None
    payload = response.json()
    access_token = str(payload.get("access_token", "") or "")
    if not access_token:
        return None
    _store_token(payload, previous_refresh_token=refresh_token)
    return access_token


def get_access_token() -> str | None:
    st = _streamlit()
    """Return a valid Graph access token, refreshing it when possible."""
    if not cloud_runtime.apply_to_config(config).configured:
        return None
    payload = st.session_state.get(TOKEN_KEY, {})
    if not isinstance(payload, dict):
        return None
    access_token = str(payload.get("access_token", "") or "")
    expires_at = int(payload.get("expires_at", 0) or 0)
    if access_token and expires_at > int(time.time()) + 60:
        return access_token
    refresh_token = str(payload.get("refresh_token", "") or "")
    if refresh_token:
        return _refresh_access_token(refresh_token)
    return None


def get_authentication_status() -> AuthenticationStatus:
    st = _streamlit()
    token = get_access_token()
    if token:
        account = str(st.session_state.get(ACCOUNT_KEY, "") or "")
        if not account:
            account = _load_account_name(token)
            st.session_state[ACCOUNT_KEY] = account
        return AuthenticationStatus(True, account, "Connected to Microsoft OneDrive.")
    return AuthenticationStatus(
        False,
        "",
        str(st.session_state.get(AUTH_ERROR_KEY, "")),
    )


def sign_out() -> None:
    st = _streamlit()
    for key in [TOKEN_KEY, ACCOUNT_KEY, AUTH_ERROR_KEY]:
        st.session_state.pop(key, None)
    st.query_params.clear()
