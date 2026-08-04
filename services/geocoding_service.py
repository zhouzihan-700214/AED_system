from __future__ import annotations

from dataclasses import dataclass
import os
import time
from typing import Any

import requests


ONEMAP_BASE_URL = "https://www.onemap.gov.sg"
ONEMAP_AUTH_URL = f"{ONEMAP_BASE_URL}/api/auth/post/getToken"
ONEMAP_SEARCH_URL = f"{ONEMAP_BASE_URL}/api/common/elastic/search"

_TOKEN_CACHE: dict[str, Any] = {
    "access_token": "",
    "expiry_timestamp": 0,
}


@dataclass(frozen=True)
class GeocodingResult:
    latitude: str = ""
    longitude: str = ""
    address: str = ""
    status: str = ""

    @property
    def success(self) -> bool:
        return self.status == "Success"


def clean_postal_code(value: Any) -> str:
    """Return a six-digit Singapore postal code, or an empty string."""

    if value is None:
        return ""

    text = str(value).strip()

    if text.endswith(".0"):
        text = text[:-2]

    digits = "".join(character for character in text if character.isdigit())

    if len(digits) != 6:
        return ""

    return digits


def _read_streamlit_secret(name: str) -> str:
    """Read either a top-level or [onemap] Streamlit secret."""

    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name]).strip()

        short_name = name.removeprefix("ONEMAP_").lower()

        if "onemap" in st.secrets and short_name in st.secrets["onemap"]:
            return str(st.secrets["onemap"][short_name]).strip()

    except Exception:
        # The service can also be used outside Streamlit.
        return ""

    return ""


def _read_setting(name: str) -> str:
    value = os.getenv(name, "").strip()

    if value:
        return value

    return _read_streamlit_secret(name)


def _credentials_available() -> bool:
    return bool(
        _read_setting("ONEMAP_EMAIL")
        and _read_setting("ONEMAP_PASSWORD")
    )


def _request_new_access_token() -> str:
    email = _read_setting("ONEMAP_EMAIL")
    password = _read_setting("ONEMAP_PASSWORD")

    if not email or not password:
        raise RuntimeError(
            "OneMap credentials are missing. Add ONEMAP_EMAIL and "
            "ONEMAP_PASSWORD to .streamlit/secrets.toml."
        )

    response = requests.post(
        ONEMAP_AUTH_URL,
        json={
            "email": email,
            "password": password,
        },
        timeout=20,
    )
    response.raise_for_status()

    data = response.json()
    access_token = str(data.get("access_token", "")).strip()

    if not access_token:
        raise RuntimeError(
            str(data.get("error", "OneMap did not return an access token."))
        )

    try:
        expiry_timestamp = int(data.get("expiry_timestamp", 0))
    except (TypeError, ValueError):
        expiry_timestamp = int(time.time()) + (72 * 60 * 60)

    _TOKEN_CACHE["access_token"] = access_token
    _TOKEN_CACHE["expiry_timestamp"] = expiry_timestamp

    return access_token


def get_access_token(force_refresh: bool = False) -> str:
    """
    Return a usable OneMap token.

    Preferred setup:
    - ONEMAP_EMAIL and ONEMAP_PASSWORD in Streamlit secrets, so the
      application can obtain a fresh token automatically.

    Alternative:
    - ONEMAP_ACCESS_TOKEN in Streamlit secrets. This token must be replaced
      manually when it expires.
    """

    now = int(time.time())
    cached_token = str(_TOKEN_CACHE.get("access_token", "")).strip()
    cached_expiry = int(_TOKEN_CACHE.get("expiry_timestamp", 0) or 0)

    if (
        not force_refresh
        and cached_token
        and cached_expiry > now + 60
    ):
        return cached_token

    if not force_refresh:
        configured_token = _read_setting("ONEMAP_ACCESS_TOKEN")

        if configured_token:
            return configured_token

    return _request_new_access_token()


def _search_postal_code(
    postal_code: str,
    access_token: str,
) -> dict[str, Any]:
    response = requests.get(
        ONEMAP_SEARCH_URL,
        params={
            "searchVal": postal_code,
            "returnGeom": "Y",
            "getAddrDetails": "Y",
            "pageNum": 1,
        },
        headers={
            "Authorization": access_token,
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def geocode_postal_code(value: Any) -> GeocodingResult:
    """Query OneMap and return an exact postal-code match."""

    postal_code = clean_postal_code(value)

    if not postal_code:
        return GeocodingResult(
            status="Invalid Postal Code"
        )

    try:
        access_token = get_access_token()
        data = _search_postal_code(postal_code, access_token)

        # OneMap can return HTTP 200 with an "error" property for token errors.
        token_error = str(data.get("error", "")).strip()

        if token_error and _credentials_available():
            access_token = get_access_token(force_refresh=True)
            data = _search_postal_code(postal_code, access_token)
            token_error = str(data.get("error", "")).strip()

        if token_error:
            return GeocodingResult(
                status=f"OneMap Error: {token_error}"
            )

        results = data.get("results", [])

        exact_match = None

        for result in results:
            if clean_postal_code(result.get("POSTAL", "")) == postal_code:
                exact_match = result
                break

        if exact_match is None:
            return GeocodingResult(
                status="Postal Code Not Found"
            )

        latitude = str(exact_match.get("LATITUDE", "")).strip()
        longitude = str(
            exact_match.get(
                "LONGITUDE",
                exact_match.get("LONGTITUDE", ""),
            )
        ).strip()
        address = str(exact_match.get("ADDRESS", "")).strip()

        if not latitude or not longitude:
            return GeocodingResult(
                address=address,
                status="Coordinates Missing in OneMap Response",
            )

        # Validate that both coordinate values are numeric.
        float(latitude)
        float(longitude)

        return GeocodingResult(
            latitude=latitude,
            longitude=longitude,
            address=address,
            status="Success",
        )

    except requests.HTTPError as error:
        status_code = error.response.status_code if error.response else ""
        return GeocodingResult(
            status=f"OneMap HTTP Error {status_code}".strip()
        )

    except requests.RequestException as error:
        return GeocodingResult(
            status=f"OneMap Network Error: {error}"
        )

    except (RuntimeError, TypeError, ValueError) as error:
        return GeocodingResult(
            status=f"OneMap Configuration Error: {error}"
        )
