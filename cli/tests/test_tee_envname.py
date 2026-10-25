"""TEE-ENVNAME-1: `tee` resolves credentials through the shared store.

The old `_api_client` checked config.api_key BEFORE the credential store,
so a stale config key beat the `client@default` login and tee status
401'd where ai jobs passed. Stubbed store proves the order.
"""

import pytest

from aitbc_cli.commands import tee as tee_mod


@pytest.fixture
def _stub_config(monkeypatch):
    class _Cfg:
        coordinator_api_url = "http://coordinator.test"
        api_key = "stale-config-key"
        timeout = 5
        tee_attestation_enabled = True

    monkeypatch.setattr(tee_mod, "get_config", lambda: _Cfg())
    monkeypatch.setenv("COORDINATOR_API_URL", "http://coordinator.test")
    return _Cfg


class _Store:
    """Stubbed credential store holding only client@default."""

    def __init__(self):
        self.jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5t_xlZXqKqXwN3p6X5Yd5x0"
        )

    def get_credential(self, name, environment="default", quiet=False):
        return self.jwt if name == "client" else None

    def get_admin_token(self, environment="default"):
        return None


def test_api_client_uses_stored_jwt_over_stale_config(_stub_config, monkeypatch):
    """The stored client@default JWT must beat a stale config.api_key."""

    monkeypatch.setattr("aitbc_cli.auth.AuthManager", _Store)
    client = tee_mod._api_client(ctx=None)
    assert client is not None
    store = _Store()
    assert client.headers.get("Authorization") == f"Bearer {store.jwt}"


def test_api_client_without_login_uses_config(_stub_config, monkeypatch):
    """With no stored credential the config key still flows through."""

    class _Empty:
        def get_credential(self, name, environment="default", quiet=False):
            return None

        def get_admin_token(self, environment="default"):
            return None

    monkeypatch.setattr("aitbc_cli.auth.AuthManager", _Empty)
    client = tee_mod._api_client(ctx=None)
    assert client is not None
    # api_key path (non-JWT token)
    assert getattr(client, "api_key", None) == "stale-config-key" or client.headers.get("X-API-Key") == "stale-config-key"


def test_api_client_no_url_returns_none(monkeypatch):
    class _Cfg:
        coordinator_api_url = ""
        api_key = ""
        timeout = 5

    monkeypatch.setattr(tee_mod, "get_config", lambda: _Cfg())
    monkeypatch.delenv("COORDINATOR_API_URL", raising=False)
    assert tee_mod._api_client(ctx=None) is None
