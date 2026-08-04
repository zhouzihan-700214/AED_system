from __future__ import annotations

from services import cloud_runtime


class LazySecretsProxy:
    """Mimic a Streamlit proxy that supports direct access but not dict()."""

    def __init__(self, values):
        self._values = values

    def __getitem__(self, key):
        value = self._values[key]
        if isinstance(value, dict):
            return LazySecretsProxy(value)
        return value

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self):
        return self._values.keys()

    def __iter__(self):
        raise TypeError("This lazy proxy must not be converted with dict()")


def test_direct_streamlit_proxy_section_is_read_without_dict_conversion() -> None:
    proxy = LazySecretsProxy(
        {
            "microsoft": {
                "client_id": "proxy-client",
                "client_secret": "proxy-secret",
                "redirect_uri": "https://zollaed.streamlit.app/",
                "onedrive_file_path": "/AED System/IB_list_TEST.xlsx",
            }
        }
    )

    settings = cloud_runtime.load_cloud_settings(proxy)

    assert settings.configured is True
    assert settings.client_id == "proxy-client"
    assert settings.client_secret == "proxy-secret"
    assert settings.source == "[microsoft]"


def test_direct_proxy_accepts_hyphenated_credential_names() -> None:
    proxy = LazySecretsProxy(
        {
            "Microsoft": {
                "client-id": "hyphen-client",
                "client-secret": "hyphen-secret",
                "redirect-uri": "https://zollaed.streamlit.app/",
            }
        }
    )

    settings = cloud_runtime.load_cloud_settings(proxy)

    assert settings.configured is True
    assert settings.client_id == "hyphen-client"
    assert settings.client_secret == "hyphen-secret"


def test_detected_secret_keys_never_returns_values() -> None:
    proxy = LazySecretsProxy(
        {"microsoft": {"client_id": "DO-NOT-LEAK", "client_secret": "SECRET"}}
    )

    keys = cloud_runtime.detected_secret_keys(proxy)
    joined = "\n".join(keys)

    assert "client_id" in joined
    assert "client_secret" in joined
    assert "DO-NOT-LEAK" not in joined
    assert "SECRET" not in joined
