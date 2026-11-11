"""Tests for _resolve_market_api_key and the market client's X-Api-Key header."""

from __future__ import annotations

from unittest.mock import patch

from aitbc_cli.commands.ipfs import _hub_market_client
import pytest

from aitbc.network.client import set_trusted_api_key_hosts
from aitbc_cli.config import CLIConfig, _resolve_market_api_key


@pytest.fixture(autouse=True)
def _trusted_hosts():
    set_trusted_api_key_hosts(frozenset({"market.example", "localhost", "127.0.0.1", "hub.aitbc.invalid"}))
    yield
    set_trusted_api_key_hosts(None)


def _cfg(api_key: str | None = None) -> CLIConfig:
    return CLIConfig(api_key=api_key, market_service_url="http://market.example:8102", _env_file=[])


def test_market_env_var_wins(monkeypatch):
    monkeypatch.setenv("MARKET_API_KEY", "market-key")
    monkeypatch.delenv("AITBC_API_KEY", raising=False)
    assert _resolve_market_api_key(_cfg(api_key="generic")) == "market-key"


def test_generic_config_key_used_when_no_market_env(monkeypatch):
    monkeypatch.delenv("MARKET_API_KEY", raising=False)
    assert _resolve_market_api_key(_cfg(api_key="generic")) == "generic"


def test_falls_back_to_market_service_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("MARKET_API_KEY", raising=False)
    env_file = tmp_path / "aitbc-market.env"
    env_file.write_text("API_KEY=node-key\n")
    with patch("aitbc_cli.config.Path") as mock_path:
        mock_path.return_value = env_file
        assert _resolve_market_api_key(_cfg()) == "node-key"


def test_none_when_nothing_configured(monkeypatch):
    monkeypatch.delenv("MARKET_API_KEY", raising=False)
    monkeypatch.delenv("AITBC_API_KEY", raising=False)
    with patch("aitbc_cli.config._parse_env_file", return_value={}):
        assert _resolve_market_api_key(_cfg()) is None


def test_hub_market_client_sends_key_header(monkeypatch):
    monkeypatch.setenv("MARKET_API_KEY", "market-key")
    monkeypatch.delenv("AITBC_API_KEY", raising=False)
    with patch("aitbc_cli.commands.ipfs.get_config", return_value=_cfg()):
        client = _hub_market_client()
    assert client.headers.get("X-API-Key") == "market-key"
    assert client.base_url == "http://market.example:8102"


# --- OPS-PROMWATCH-EACCES-1 (#1781): unreadable/empty env files must not crash ---


def test_parse_env_file_unreadable_returns_empty(tmp_path, monkeypatch):
    """A root:aitbc 0600 env file read as aitbc raises PermissionError on
    open() — config load must skip it, not crash (node2 prometheus-watch)."""
    from aitbc_cli.config import _parse_env_file

    env_file = tmp_path / "aitbc-coordinator-api.env"
    env_file.write_text("AITBC_API_KEY=secret\n")
    env_file.chmod(0o000)

    def _deny(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("builtins.open", _deny)
    assert _parse_env_file(env_file) == {}


def test_parse_env_file_empty_returns_empty(tmp_path):
    from aitbc_cli.config import _parse_env_file

    env_file = tmp_path / "empty.env"
    env_file.write_text("")
    assert _parse_env_file(env_file) == {}


def test_resolve_api_key_survives_unreadable_env_file(tmp_path, monkeypatch):
    """End-to-end: an unreadable file in the search path is skipped instead
    of crashing config load (the node2 prometheus-watch failure)."""
    from aitbc_cli.config import _resolve_api_key

    monkeypatch.delenv("AITBC_API_KEY", raising=False)
    monkeypatch.setattr("aitbc_cli.config.Path.home", classmethod(lambda cls: tmp_path / "nohome"))

    denied = {"/etc/aitbc/aitbc-cli.env", "/etc/aitbc/aitbc-coordinator-api.env"}
    real_open = open

    def _maybe_deny(file, *args, **kwargs):
        if str(file) in denied:
            raise PermissionError(13, "Permission denied")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", _maybe_deny)
    result = _resolve_api_key({})  # must not raise PermissionError
    assert result is None
