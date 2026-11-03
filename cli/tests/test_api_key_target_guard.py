"""Pin for MCP-URL-PARAM-CREDENTIAL-FORWARD-1 (#850).

Read-only MCP tools pass caller-chosen service URLs to the CLI; the CLI
then attached the node's stored API key to whatever URL it was given — a
credential-forward to a foreign host. ``get_config()`` now registers the
configured service hosts, and ``AITBCHTTPClient`` refuses to attach a key
to a host that is not configured. Service processes that never register
behave exactly as before (no restriction).
"""

import pytest

from aitbc.network.client import AITBCHTTPClient, AsyncAITBCHTTPClient, set_trusted_api_key_hosts
from aitbc_cli.config import get_config


@pytest.fixture(autouse=True)
def _reset_trusted():
    set_trusted_api_key_hosts.__globals__["_trusted_api_key_hosts"] = None
    yield
    set_trusted_api_key_hosts.__globals__["_trusted_api_key_hosts"] = None


def test_foreign_hub_url_never_gets_the_key():
    set_trusted_api_key_hosts(frozenset({"hub.aitbc.example", "localhost", "127.0.0.1"}))
    with pytest.raises(ValueError, match="unconfigured host"):
        AITBCHTTPClient(base_url="https://collector.evil.example", api_key="deadbeef")


def test_configured_host_still_gets_the_key():
    set_trusted_api_key_hosts(frozenset({"hub.aitbc.example", "localhost"}))
    client = AITBCHTTPClient(base_url="https://hub.aitbc.example/api", api_key="deadbeef")
    assert client.headers["X-API-Key"] == "deadbeef"


def test_no_key_no_restriction():
    set_trusted_api_key_hosts(frozenset({"localhost"}))
    client = AITBCHTTPClient(base_url="https://public.example")
    assert "X-API-Key" not in client.headers


def test_unregistered_process_behaves_as_before():
    client = AITBCHTTPClient(base_url="https://anything.example", api_key="deadbeef")
    assert client.headers["X-API-Key"] == "deadbeef"


def test_async_client_is_guarded_too():
    set_trusted_api_key_hosts(frozenset({"localhost"}))
    with pytest.raises(ValueError, match="unconfigured host"):
        AsyncAITBCHTTPClient(base_url="https://collector.evil.example", api_key="deadbeef")


def test_get_config_registers_every_configured_url(monkeypatch):
    monkeypatch.delenv("AITBC_CONFIG", raising=False)
    config = get_config("/nonexistent.yaml")
    import aitbc.network.client as client_mod

    trusted = client_mod._trusted_api_key_hosts
    assert trusted is not None
    # the configured defaults are loopback — trusted
    for name in ("wallet_daemon_url", "blockchain_rpc_url", "market_service_url"):
        from urllib.parse import urlparse

        host = urlparse(getattr(config, name)).hostname
        assert host in trusted, name


def test_bridge_client_refuses_foreign_hub_url(monkeypatch):
    monkeypatch.setenv("WALLET_API_KEY", "deadbeef")
    get_config("/nonexistent.yaml")
    from aitbc_cli.commands.wallet.bridge import _hub_bridge_client

    with pytest.raises(ValueError, match="unconfigured host"):
        _hub_bridge_client("http://collector.evil.example")
