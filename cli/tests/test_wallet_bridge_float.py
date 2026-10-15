"""Tests for ``aitbc wallet bridge float`` and ``status --today/--24h``
(CLI-5) — read-only float view + release-window aggregates over
GET /v1/bridge/float. The HTTP client is mocked; the tests pin argument
parsing (exactly-one-of validation) and the output contract.
"""

import json
from unittest import mock

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.wallet.bridge as bridge_mod
from aitbc_cli.commands.wallet.bridge import float_cmd, status


@pytest.fixture
def runner():
    return CliRunner()


_FLOAT_DOC = {
    "eth_address": "0x" + "aa" * 20,
    "balance_eth": "1.5",
    "balance_error": None,
    "pending_reserve_eth": "0.09",
    "available_eth": "1.41",
    "windows": {
        "today": {
            "since": "2026-10-16T00:00:00",
            "withdrawals_eth": "0.01",
            "sell_eth": "0.02",
            "exchange_eth": "0.03",
            "total_eth": "0.06",
        },
        "last_24h": {
            "since": "2026-10-15T10:00:00",
            "withdrawals_eth": "0.04",
            "sell_eth": "0.05",
            "exchange_eth": "0.06",
            "total_eth": "0.15",
        },
    },
    "sell_daily_cap": {
        "max_eth_per_day": "0.03",
        "committed_24h": "0.05",
        "remaining": "0",
        "window": "rolling 24h",
    },
}


def _fake_client(doc=_FLOAT_DOC):
    client = mock.Mock()
    client.get.return_value = doc
    return client


class TestFloat:
    def test_float_calls_route_and_prints(self, runner):
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_hub_bridge_client", return_value=client):
            result = runner.invoke(float_cmd, obj={"output_format": "json"}, args=[])
        assert result.exit_code == 0, result.output
        client.get.assert_called_once_with("/v1/bridge/float")
        body = json.loads(result.output)
        assert body["balance_eth"] == "1.5"
        assert body["pending_reserve_eth"] == "0.09"
        assert body["windows"]["today"]["total_eth"] == "0.06"

    def test_float_http_error_aborts(self, runner):
        client = mock.Mock()
        client.get.side_effect = RuntimeError("connection refused")
        with mock.patch.object(bridge_mod, "_hub_bridge_client", return_value=client):
            result = runner.invoke(float_cmd, obj={"output_format": "table"}, args=[])
        assert result.exit_code != 0
        assert "Failed to read bridge float" in result.output


class TestStatusWindows:
    def test_no_flag_rejected(self, runner):
        result = runner.invoke(status, obj={"output_format": "table"}, args=[])
        assert result.exit_code != 0
        assert "exactly one" in result.output

    def test_today_and_24h_mutually_exclusive(self, runner):
        result = runner.invoke(status, obj={"output_format": "table"}, args=["--today", "--24h"])
        assert result.exit_code != 0
        assert "exactly one" in result.output

    def test_hash_and_today_mutually_exclusive(self, runner):
        result = runner.invoke(status, obj={"output_format": "table"}, args=["--ait-tx-hash", "0xabc", "--today"])
        assert result.exit_code != 0
        assert "exactly one" in result.output

    def test_today_window_output(self, runner):
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_hub_bridge_client", return_value=client):
            result = runner.invoke(status, obj={"output_format": "json"}, args=["--today"])
        assert result.exit_code == 0, result.output
        client.get.assert_called_once_with("/v1/bridge/float")
        body = json.loads(result.output)
        assert "today" in body["window"]
        assert body["since"] == "2026-10-16T00:00:00"
        assert body["total_eth"] == "0.06"
        assert body["sell_daily_cap"]["remaining"] == "0"

    def test_24h_window_output(self, runner):
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_hub_bridge_client", return_value=client):
            result = runner.invoke(status, obj={"output_format": "json"}, args=["--24h"])
        assert result.exit_code == 0, result.output
        body = json.loads(result.output)
        assert "24h" in body["window"]
        assert body["since"] == "2026-10-15T10:00:00"
        assert body["total_eth"] == "0.15"

    def test_hash_path_uses_withdraw_route(self, runner):
        client = mock.Mock()
        client.get.return_value = {"status": "pending"}
        with mock.patch.object(bridge_mod, "get_wallet_client", return_value=client):
            result = runner.invoke(status, obj={"output_format": "json"}, args=["--ait-tx-hash", "0xabc"])
        assert result.exit_code == 0, result.output
        client.get.assert_called_once_with("/v1/bridge/withdraw/0xabc")


_SELL_DOC = {
    "enabled": False,
    "reason": "sell escrow disabled",
    "feature_enabled": False,
    "flags": {"bridge_enabled": True, "sell_escrow_enabled": False},
    "config": {
        "chain_id": "ait-testnet",
        "escrow_address": "0x" + "11" * 20,
        "treasury_address": "0x" + "22" * 20,
        "max_eth_per_day": "0.03",
        "escrow_wallet_configured": True,
        "escrow_credential_configured": True,
    },
}


class TestSellAdminStatus:
    def test_status_calls_route_and_prints(self, runner):
        from aitbc_cli.commands.exchange.sell_admin import status as sa_status

        client = _fake_client(_SELL_DOC)
        with mock.patch("aitbc_cli.commands.exchange.sell_admin._hub_bridge_client", return_value=client):
            result = runner.invoke(sa_status, obj={"output_format": "json"}, args=[])
        assert result.exit_code == 0, result.output
        client.get.assert_called_once_with("/v1/bridge/sell/config-status")
        body = json.loads(result.output)
        assert body["enabled"] is False
        assert body["reason"] == "sell escrow disabled"
        assert body["config"]["max_eth_per_day"] == "0.03"

    def test_status_http_error_aborts(self, runner):
        from aitbc_cli.commands.exchange.sell_admin import status as sa_status

        client = mock.Mock()
        client.get.side_effect = RuntimeError("connection refused")
        with mock.patch("aitbc_cli.commands.exchange.sell_admin._hub_bridge_client", return_value=client):
            result = runner.invoke(sa_status, obj={"output_format": "table"}, args=[])
        assert result.exit_code != 0
        assert "Failed to read sell config status" in result.output
