"""Tests for _resolve_market_api_key and the market client's X-Api-Key header."""

from __future__ import annotations

from unittest.mock import patch

from aitbc_cli.commands.ipfs import _hub_market_client
from aitbc_cli.config import CLIConfig, _resolve_market_api_key


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
