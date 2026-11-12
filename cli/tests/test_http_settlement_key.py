"""#1917: ``aitbc http call --auth rpc`` attaches ``X-Settlement-Key`` only
on the chain escrow settlement routes (release/refund), from the CLI
config's ``blockchain_rpc_settlement_api_key`` — never on other paths and
never to a ``--url`` retarget.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from aitbc_cli.commands import http as http_module


@pytest.fixture
def settlement_key(monkeypatch):
    cfg = SimpleNamespace(blockchain_rpc_settlement_api_key="settle-test-key")
    monkeypatch.setattr(http_module, "get_config", lambda: cfg)
    return "settle-test-key"


def _client(path: str, *, url: str | None = None):
    return http_module._auth_client(
        base_url="http://127.0.0.1:8202",
        timeout=10,
        url=url,
        api_key="explicit-key",
        resolved_key="explicit-key",
        auth_kind="rpc",
        path=path,
    )


@pytest.mark.parametrize(
    "path",
    ["escrow/job-1/release", "escrow/job-1/refund", "rpc/escrow/job-1/release", "escrow/job-1/release/"],
)
def test_settlement_routes_get_settlement_key(settlement_key, path):
    client = _client(path)
    assert client.headers.get("X-API-Key") == "explicit-key"
    assert client.headers.get("X-Settlement-Key") == "settle-test-key"
    client.close()


@pytest.mark.parametrize(
    "path",
    ["escrow/create", "escrow/job-1", "escrow/job-1/release/extra", "transactions", "health"],
)
def test_other_paths_do_not_get_settlement_key(settlement_key, path):
    client = _client(path)
    assert "X-Settlement-Key" not in client.headers
    client.close()


def test_url_retarget_suppresses_settlement_key(settlement_key):
    """--url points at an arbitrary host: the stored settlement credential
    must not ride along (same rule as the RPC key)."""
    client = _client("escrow/job-1/release", url="http://evil.example")
    assert "X-Settlement-Key" not in client.headers
    client.close()


def test_no_configured_key_sends_no_header(monkeypatch):
    monkeypatch.setattr(
        http_module,
        "get_config",
        lambda: SimpleNamespace(blockchain_rpc_settlement_api_key=None),
    )
    client = _client("escrow/job-1/release")
    assert "X-Settlement-Key" not in client.headers
    client.close()
