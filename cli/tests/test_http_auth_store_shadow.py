"""#2271: ``aitbc http call --auth rpc`` / ``--auth miner`` must send the
configured service key, not a stored ``aitbc auth login`` credential.

The fleet RPC key-gated reads (``/chains``, escrow state, AI job lists, ...)
only accept ``X-API-Key``; a stored client JWT used to shadow
``BLOCKCHAIN_RPC_API_KEY`` inside ``auth_client_kwargs`` and surface as a
403 "missing or invalid API key" on every typed MCP read that passed
``--auth rpc``.
"""

from __future__ import annotations

import pytest

from aitbc_cli.auth import AuthManager
from aitbc_cli.commands import http as http_module


@pytest.fixture
def stored_credential(monkeypatch):
    monkeypatch.setattr(
        AuthManager, "get_credential", lambda self, name, environment="default", quiet=False: "stored-client-cred"
    )


def _client(auth_kind: str, resolved_key: str | None):
    return http_module._auth_client(
        base_url="http://127.0.0.1:8202",
        timeout=10,
        url=None,
        api_key=None,
        resolved_key=resolved_key,
        auth_kind=auth_kind,
        path="chains",
    )


@pytest.mark.parametrize("auth_kind", ["rpc", "miner"])
def test_service_key_kinds_skip_credential_store(stored_credential, auth_kind):
    client = _client(auth_kind, "service-key-123")
    assert client.headers.get("X-API-Key") == "service-key-123"
    assert "Authorization" not in client.headers
    client.close()


def test_none_kind_still_uses_credential_store(stored_credential):
    """Plain ``http call`` keeps the stored client credential — that is how
    coordinator-api JWT auth works today."""
    client = _client("none", None)
    assert client.headers.get("X-API-Key") == "stored-client-cred"
    client.close()


def test_explicit_api_key_wins_over_everything(stored_credential):
    client = http_module._auth_client(
        base_url="http://127.0.0.1:8202",
        timeout=10,
        url=None,
        api_key="explicit-key",
        resolved_key="service-key-123",
        auth_kind="rpc",
        path="chains",
    )
    assert client.headers.get("X-API-Key") == "explicit-key"
    client.close()
