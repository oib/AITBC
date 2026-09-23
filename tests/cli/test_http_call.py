"""Tests for the aitbc http call generic pivot — per-service auth selection."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from pydantic import SecretStr


@pytest.fixture
def runner():
    return CliRunner()


class TestHttpCallAuth:
    """The trading service authenticates on X-Trading-Api-Key, not X-API-Key —
    ``--auth trading`` must produce the trading header, while the existing
    rpc/miner modes keep emitting X-API-Key.
    """

    @patch("aitbc_cli.commands.http.AITBCHTTPClient")
    @patch("aitbc_cli.commands.http.get_config")
    def test_auth_trading_sends_trading_header(self, mock_get_config, mock_http_class, runner):
        from aitbc_cli.commands.http import http

        mock_get_config.return_value = SimpleNamespace(trading_api_key=SecretStr("trading-key-9"))
        client = mock_http_class.return_value
        client.get.return_value = {"ok": True}

        result = runner.invoke(http, ["call", "trading", "v1/trading/inter-chain", "--auth", "trading"])

        assert result.exit_code == 0
        kwargs = mock_http_class.call_args.kwargs
        assert kwargs["headers"] == {"X-Trading-Api-Key": "trading-key-9"}
        assert "api_key" not in kwargs

    @patch("aitbc_cli.auth.AuthManager")
    @patch("aitbc_cli.commands.http.AITBCHTTPClient")
    @patch("aitbc_cli.commands.http.get_config")
    def test_auth_rpc_keeps_api_key_header(self, mock_get_config, mock_http_class, mock_auth_manager, runner):
        from aitbc_cli.commands.http import http

        mock_get_config.return_value = SimpleNamespace(blockchain_rpc_api_key="rpc-key", api_key=None)
        mock_auth_manager.return_value.get_credential.return_value = None
        client = mock_http_class.return_value
        client.get.return_value = {"height": 1}

        result = runner.invoke(http, ["call", "blockchain-rpc", "height", "--auth", "rpc"])

        assert result.exit_code == 0
        kwargs = mock_http_class.call_args.kwargs
        # api_key kwarg becomes the X-API-Key header inside AITBCHTTPClient.
        assert kwargs["api_key"] == "rpc-key"
        assert "X-Trading-Api-Key" not in (kwargs.get("headers") or {})

    @patch("aitbc_cli.commands.http.AITBCHTTPClient")
    @patch("aitbc_cli.commands.http.get_config")
    def test_auth_trading_explicit_api_key_uses_trading_header(self, mock_get_config, mock_http_class, runner):
        """--auth trading --api-key K sends K as X-Trading-Api-Key — the only
        sensible reading of an explicit key with an explicit trading auth."""
        from aitbc_cli.commands.http import http

        client = mock_http_class.return_value
        client.get.return_value = {"ok": True}

        result = runner.invoke(
            http,
            ["call", "trading", "v1/trading/inter-chain", "--auth", "trading", "--api-key", "explicit-1"],
        )

        assert result.exit_code == 0
        kwargs = mock_http_class.call_args.kwargs
        assert kwargs["headers"] == {"X-Trading-Api-Key": "explicit-1"}

    @patch("aitbc_cli.commands.http.AITBCHTTPClient")
    @patch("aitbc_cli.commands.http.get_config")
    def test_auth_trading_without_key_fails_loudly(self, mock_get_config, mock_http_class, runner):
        """--auth trading with no resolvable key fails before sending — the
        trading gate reads only X-Trading-Api-Key, so falling back to a stored
        JWT Bearer would surface as a misleading "Missing API key" 401."""
        from aitbc_cli.commands.http import http

        mock_get_config.return_value = SimpleNamespace(trading_api_key=None)

        result = runner.invoke(http, ["call", "trading", "v1/trading/inter-chain", "--auth", "trading"])

        assert result.exit_code != 0
        assert "trading API key" in result.output
        mock_http_class.assert_not_called()


class TestHttpCallIdempotencyKey:
    """--idempotency-key flows into the client's write methods so ambiguous
    post-send failures may be retried against a deduplicating upstream."""

    @patch("aitbc_cli.commands.http.AITBCHTTPClient")
    @patch("aitbc_cli.commands.http.get_config")
    def test_post_passes_idempotency_key(self, mock_get_config, mock_http_class, runner):
        from aitbc_cli.commands.http import http

        mock_get_config.return_value = SimpleNamespace(api_key=None)
        client = mock_http_class.return_value
        client.post.return_value = {"ok": True}

        result = runner.invoke(
            http,
            [
                "call",
                "wallet",
                "v1/wallets",
                "--method",
                "POST",
                "--body",
                '{"wallet_id": "genesis"}',
                "--idempotency-key",
                "op-123",
            ],
        )

        assert result.exit_code == 0
        assert client.post.call_args.kwargs["idempotency_key"] == "op-123"

    @patch("aitbc_cli.commands.http.AITBCHTTPClient")
    @patch("aitbc_cli.commands.http.get_config")
    def test_post_without_key_passes_none(self, mock_get_config, mock_http_class, runner):
        from aitbc_cli.commands.http import http

        mock_get_config.return_value = SimpleNamespace(api_key=None)
        client = mock_http_class.return_value
        client.post.return_value = {"ok": True}

        result = runner.invoke(
            http,
            ["call", "wallet", "v1/wallets", "--method", "POST", "--body", '{"wallet_id": "genesis"}'],
        )

        assert result.exit_code == 0
        assert client.post.call_args.kwargs["idempotency_key"] is None
