"""Pin for MCP-URL-PARAM-CREDENTIAL-FORWARD-1 (#850).

Read-only MCP tools pass caller-chosen service URLs to the CLI; the CLI
then attached the node's stored API key to whatever URL it was given — a
credential-forward to a foreign host. ``get_config()`` now registers the
configured service hosts, and ``AITBCHTTPClient`` refuses to attach a key
to a host that is not configured. Service processes that never register
behave exactly as before (no restriction).
"""

import warnings

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


# --- PI-SDK-01 / PI-SDK-04: credential headers and absolute endpoints -------


def test_bearer_header_to_foreign_host_is_refused():
    """auth_client_kwargs emits JWTs as Authorization: Bearer — the guard must
    cover headers, not only the api_key kwarg (PI-SDK-01)."""
    set_trusted_api_key_hosts(frozenset({"hub.aitbc.example", "localhost"}))
    with pytest.raises(ValueError, match="unconfigured host"):
        AITBCHTTPClient(
            base_url="https://collector.evil.example",
            headers={"Authorization": "Bearer eyJhbGciOi.fake.token"},
        )


def test_trading_key_header_to_foreign_host_is_refused():
    set_trusted_api_key_hosts(frozenset({"localhost"}))
    with pytest.raises(ValueError, match="unconfigured host"):
        AITBCHTTPClient(
            base_url="https://collector.evil.example",
            headers={"X-Trading-Api-Key": "sekrit"},
        )


def test_bearer_header_to_trusted_host_still_works():
    set_trusted_api_key_hosts(frozenset({"hub.aitbc.example"}))
    client = AITBCHTTPClient(
        base_url="https://hub.aitbc.example",
        headers={"Authorization": "Bearer eyJhbGciOi.fake.token"},
    )
    assert client.headers["Authorization"].startswith("Bearer ")


def test_absolute_endpoint_to_foreign_host_cannot_carry_credentials():
    """_build_url returns absolute endpoints verbatim — a request-level
    absolute URL must face the same trust check as base_url (PI-SDK-04)."""
    set_trusted_api_key_hosts(frozenset({"hub.aitbc.example", "localhost"}))
    client = AITBCHTTPClient(
        base_url="https://hub.aitbc.example",
        headers={"Authorization": "Bearer eyJhbGciOi.fake.token"},
    )
    with pytest.raises(ValueError, match="unconfigured host"):
        client._check_request_target("https://collector.evil.example/x", client.headers)


def test_absolute_endpoint_to_trusted_host_is_allowed():
    set_trusted_api_key_hosts(frozenset({"hub.aitbc.example"}))
    client = AITBCHTTPClient(
        base_url="https://hub.aitbc.example",
        headers={"Authorization": "Bearer eyJhbGciOi.fake.token"},
    )
    client._check_request_target("https://hub.aitbc.example/v1/jobs", client.headers)  # no raise


def test_per_request_headers_to_foreign_absolute_url_are_refused():
    """A credential added via per-request headers= must not reach a foreign
    absolute endpoint either."""
    set_trusted_api_key_hosts(frozenset({"hub.aitbc.example"}))
    client = AITBCHTTPClient(base_url="https://hub.aitbc.example")
    req_headers = client._build_headers({"Authorization": "Bearer eyJhbGciOi.fake.token"})
    with pytest.raises(ValueError, match="unconfigured host"):
        client._check_request_target("https://collector.evil.example/x", req_headers)


def test_credential_free_client_is_unrestricted():
    set_trusted_api_key_hosts(frozenset({"localhost"}))
    client = AITBCHTTPClient(base_url="https://hub.aitbc.example")
    client._check_request_target("https://collector.evil.example/x", {})  # no raise


def test_async_client_refuses_bearer_to_foreign_host():
    set_trusted_api_key_hosts(frozenset({"localhost"}))
    with pytest.raises(ValueError, match="unconfigured host"):
        AsyncAITBCHTTPClient(
            base_url="https://collector.evil.example",
            headers={"Authorization": "Bearer eyJhbGciOi.fake.token"},
        )


# --- PI-SDK-01: CWD-planted .aitbc.yaml must be loud -------------------------


def test_cwd_aitbc_yaml_warns_about_ambient_config(tmp_path, monkeypatch):
    """A ./.aitbc.yaml picked up from the working directory can redirect every
    service URL — the CLI must say so on every load (PI-SDK-01)."""
    monkeypatch.delenv("AITBC_CONFIG_FILE", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    (tmp_path / ".aitbc.yaml").write_text("coordinator_api_url: https://hub.example\n")
    monkeypatch.chdir(tmp_path)
    with pytest.warns(UserWarning, match="current directory"):
        get_config()


def test_pinned_config_file_does_not_warn(tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_CONFIG_FILE", str(tmp_path / "pinned.yaml"))
    (tmp_path / "pinned.yaml").write_text("timeout: 5\n")
    monkeypatch.chdir(tmp_path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        get_config()
    assert not any("current directory" in str(w.message) for w in caught)


def test_home_aitbc_yaml_does_not_warn(tmp_path, monkeypatch):
    monkeypatch.delenv("AITBC_CONFIG_FILE", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    (home / ".aitbc.yaml").write_text("timeout: 5\n")
    monkeypatch.setenv("HOME", str(home))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        get_config()
    assert not any("current directory" in str(w.message) for w in caught)
