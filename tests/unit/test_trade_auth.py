from __future__ import annotations

import os

import click
import httpx
import pytest
from click.testing import CliRunner

from aitbc_cli import config as cli_config
from aitbc_cli.commands import trade as trade_mod
from aitbc_cli.commands.trade import _get_client, trade

SYNTHETIC_TRADING_KEY = "test-trading-key-0000"
SYNTHETIC_RPC_KEY = "test-rpc-key-0000"


@pytest.fixture
def trading_env_file(tmp_path, monkeypatch):
    env_path = tmp_path / "aitbc-trading.env"
    env_path.write_text(f"TRADING_API_KEY={SYNTHETIC_TRADING_KEY}\nTRADING_SERVICE_URL=http://trading.test:8104\n")
    monkeypatch.setattr(cli_config, "_cli_env_files", lambda: [str(env_path)])
    monkeypatch.setenv("AITBC_CONFIG_FILE", str(tmp_path / "no-such-config.yaml"))
    monkeypatch.delenv("TRADING_API_KEY", raising=False)
    monkeypatch.delenv("TRADING_SERVICE_URL", raising=False)
    return env_path


class TestCLIConfigTradingKey:
    def test_trading_key_loaded_from_env_file(self, trading_env_file) -> None:
        config = cli_config.get_config()
        assert config.trading_api_key is not None
        assert config.trading_api_key.get_secret_value() == SYNTHETIC_TRADING_KEY
        assert os.environ.get("TRADING_API_KEY") is None
        assert config.trading_service_url == "http://trading.test:8104"

    def test_secret_never_leaks_in_repr_or_dump(self, trading_env_file) -> None:
        config = cli_config.get_config()
        assert SYNTHETIC_TRADING_KEY not in repr(config)
        assert SYNTHETIC_TRADING_KEY not in str(config)
        assert SYNTHETIC_TRADING_KEY not in config.model_dump_json()

    def test_process_env_beats_env_file(self, trading_env_file, monkeypatch) -> None:
        monkeypatch.setenv("TRADING_API_KEY", "env-override-key")
        config = cli_config.get_config()
        assert config.trading_api_key is not None
        assert config.trading_api_key.get_secret_value() == "env-override-key"

    def test_missing_key_stays_none(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(cli_config, "_cli_env_files", lambda: [])
        monkeypatch.setenv("AITBC_CONFIG_FILE", str(tmp_path / "no-such-config.yaml"))
        monkeypatch.delenv("TRADING_API_KEY", raising=False)
        config = cli_config.get_config()
        assert config.trading_api_key is None


class TestCLIEnvFiles:
    def test_trading_env_included_when_readable(self, monkeypatch) -> None:
        monkeypatch.setattr(os, "access", lambda p, m: True)
        assert "/etc/aitbc/aitbc-trading.env" in cli_config._cli_env_files()

    def test_trading_env_omitted_when_unreadable(self, monkeypatch) -> None:
        real_access = os.access

        def fake_access(path, mode):
            if path == "/etc/aitbc/aitbc-trading.env":
                return False
            return real_access(path, mode)

        monkeypatch.setattr(os, "access", fake_access)
        assert "/etc/aitbc/aitbc-trading.env" not in cli_config._cli_env_files()


class TestGetClient:
    def test_uses_config_key_and_url(self, trading_env_file) -> None:
        client = _get_client()
        assert client.headers["X-Trading-Api-Key"] == SYNTHETIC_TRADING_KEY
        assert "X-API-Key" not in client.headers
        assert "Authorization" not in client.headers
        assert client.base_url == "http://trading.test:8104"
        assert client.timeout == 30

    def test_explicit_url_wins(self, trading_env_file) -> None:
        client = _get_client("http://explicit.test:9999")
        assert client.base_url == "http://explicit.test:9999"
        assert client.headers["X-Trading-Api-Key"] == SYNTHETIC_TRADING_KEY

    def test_ctx_obj_config_wins_over_get_config(self, monkeypatch) -> None:
        config = cli_config.CLIConfig(TRADING_API_KEY="ctx-key-synthetic", _env_file=[])

        def _boom(*args, **kwargs):
            raise RuntimeError("get_config must not be consulted")

        monkeypatch.setattr(cli_config, "get_config", _boom)
        with click.Context(trade, obj={"config": config}):
            client = _get_client()
        assert client.headers["X-Trading-Api-Key"] == "ctx-key-synthetic"

    def test_missing_key_raises_before_client_constructed(self, monkeypatch) -> None:
        monkeypatch.delenv("TRADING_API_KEY", raising=False)
        config = cli_config.CLIConfig(_env_file=[])
        assert config.trading_api_key is None

        def _boom(*args, **kwargs):
            pytest.fail("AITBCHTTPClient must not be constructed without a key")

        monkeypatch.setattr(trade_mod, "AITBCHTTPClient", _boom)
        with click.Context(trade, obj={"config": config}):
            with pytest.raises(click.UsageError, match="Trading API key required"):
                _get_client()


class TestTradeCommands:
    def test_list_sends_trading_header_only(self, trading_env_file, monkeypatch) -> None:
        captured = {}

        def fake_get(self, endpoint, params=None, headers=None):
            captured["base_url"] = self.base_url
            captured["headers"] = dict(self.headers)
            captured["endpoint"] = endpoint
            return [{"trade_id": "t-1"}]

        monkeypatch.setattr(trade_mod.AITBCHTTPClient, "get", fake_get)
        result = CliRunner().invoke(
            trade,
            ["list", "--format", "json"],
            obj={"config": cli_config.get_config()},
        )
        assert result.exit_code == 0, result.output
        assert captured["endpoint"] == "/v1/trading/inter-chain"
        assert captured["base_url"] == "http://trading.test:8104"
        assert captured["headers"]["X-Trading-Api-Key"] == SYNTHETIC_TRADING_KEY
        assert "X-API-Key" not in captured["headers"]
        assert SYNTHETIC_TRADING_KEY not in result.output

    def test_settlement_status_keeps_rpc_key_off_trading_request(self, trading_env_file, monkeypatch) -> None:
        captured = {}

        def fake_get(self, endpoint, params=None, headers=None):
            captured["headers"] = dict(self.headers)
            captured["endpoint"] = endpoint
            return {"trade_id": "t-9", "settlement_phase": "none", "escrow_id": None}

        monkeypatch.setattr(trade_mod.AITBCHTTPClient, "get", fake_get)
        result = CliRunner().invoke(
            trade,
            ["settlement-status", "--trade-id", "t-9", "--api-key", SYNTHETIC_RPC_KEY, "--format", "json"],
            obj={"config": cli_config.get_config()},
        )
        assert result.exit_code == 0, result.output
        assert captured["endpoint"] == "/v1/trading/inter-chain/t-9"
        assert captured["headers"]["X-Trading-Api-Key"] == SYNTHETIC_TRADING_KEY
        assert "X-API-Key" not in captured["headers"]
        assert SYNTHETIC_RPC_KEY not in result.output
        assert SYNTHETIC_TRADING_KEY not in result.output

    def test_settlement_status_uses_separate_credentials(self, trading_env_file, monkeypatch) -> None:
        trading_requests = []
        rpc_requests = []

        def fake_get(self, endpoint, params=None, headers=None):
            trading_requests.append((endpoint, dict(self.headers)))
            return {"trade_id": "t-10", "settlement_phase": "escrow_locked", "escrow_id": "esc-10"}

        def rpc_handler(request):
            rpc_requests.append(request)
            return httpx.Response(200, json={"escrow_id": "esc-10", "status": "locked"})

        real_async_client = httpx.AsyncClient

        def rpc_client(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(rpc_handler)
            return real_async_client(*args, **kwargs)

        monkeypatch.setattr(trade_mod.AITBCHTTPClient, "get", fake_get)
        monkeypatch.setattr(httpx, "AsyncClient", rpc_client)
        result = CliRunner().invoke(
            trade,
            [
                "settlement-status",
                "--trade-id",
                "t-10",
                "--node-url",
                "http://rpc.test:8202",
                "--api-key",
                SYNTHETIC_RPC_KEY,
                "--format",
                "json",
            ],
            obj={"config": cli_config.get_config()},
        )
        assert result.exit_code == 0, result.output
        assert len(trading_requests) == 1
        assert trading_requests[0][0] == "/v1/trading/inter-chain/t-10"
        assert trading_requests[0][1]["X-Trading-Api-Key"] == SYNTHETIC_TRADING_KEY
        assert "X-API-Key" not in trading_requests[0][1]
        assert len(rpc_requests) == 1
        assert str(rpc_requests[0].url) == "http://rpc.test:8202/rpc/bridge/settlement/esc-10"
        assert rpc_requests[0].headers["X-API-Key"] == SYNTHETIC_RPC_KEY
        assert "X-Trading-Api-Key" not in rpc_requests[0].headers
        assert SYNTHETIC_TRADING_KEY not in result.output
        assert SYNTHETIC_RPC_KEY not in result.output

    def test_settlement_status_still_requires_rpc_key(self, trading_env_file, monkeypatch) -> None:
        monkeypatch.delenv("BLOCKCHAIN_RPC_API_KEY", raising=False)

        def fake_get(self, endpoint, params=None, headers=None):
            pytest.fail("trading lookup must not run without the RPC key")

        monkeypatch.setattr(trade_mod.AITBCHTTPClient, "get", fake_get)
        result = CliRunner().invoke(
            trade,
            ["settlement-status", "--trade-id", "t-9"],
            obj={"config": cli_config.get_config()},
        )
        assert "Blockchain RPC API key required" in result.output

    def test_list_without_key_fails_cleanly(self, monkeypatch) -> None:
        monkeypatch.delenv("TRADING_API_KEY", raising=False)
        config = cli_config.CLIConfig(_env_file=[])

        def _boom(*args, **kwargs):
            pytest.fail("AITBCHTTPClient must not be constructed without a key")

        monkeypatch.setattr(trade_mod, "AITBCHTTPClient", _boom)
        result = CliRunner().invoke(trade, ["list"], obj={"config": config})
        assert "Trading API key required" in result.output
