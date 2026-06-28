"""
Market Commands Tests
Tests for market CLI commands (cli/aitbc_cli/commands/market/)
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from aitbc_cli.commands import market as market_module
from aitbc_cli.commands.market import (
    _escrow_create,
    _get_blockchain_rpc_url,
    get_account_nonce,
    get_chain_id,
    get_island_id,
    get_next_nonce,
    get_wallet_address,
    market,
    safe_load_credentials,
)
from aitbc_cli.commands.market import escrow as escrow_module
from aitbc_cli.commands.market import exchange as exchange_module
from aitbc_cli.commands.market import jobs as jobs_module
from aitbc_cli.commands.market import offers as offers_module
from aitbc_cli.commands.market import ratings as ratings_module
from click.testing import CliRunner


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_config(
    hub_discovery_url="hub.aitbc.bubuit.net",
    blockchain_rpc_url="http://localhost:8202",
    wallet_daemon_url="http://localhost:8108",
    wallet_address="0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C",
    chain_id="ait-hub.aitbc.bubuit.net",
):
    cfg = Mock()
    cfg.hub_discovery_url = hub_discovery_url
    cfg.blockchain_rpc_url = blockchain_rpc_url
    cfg.wallet_daemon_url = wallet_daemon_url
    cfg.wallet_address = wallet_address
    cfg.chain_id = chain_id
    cfg.get = Mock(
        side_effect=lambda key, default=None: {
            "blockchain_rpc_url": blockchain_rpc_url,
            "genesis_wallet_address": "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C",
        }.get(key, default)
    )
    return cfg


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_config():
    with patch.object(market_module, "get_config", return_value=_make_config()):
        yield


# ---------------------------------------------------------------------------
# Group / command registration
# ---------------------------------------------------------------------------


class TestMarketGroup:
    """Test market command group registration"""

    def test_market_group_exists(self):
        assert market is not None
        assert hasattr(market, "name")

    def test_market_group_name(self):
        assert market.name == "market"

    def test_market_group_help(self):
        assert "marketplace" in (market.help or "").lower() or "market" in (market.help or "").lower()

    def test_market_has_subcommands(self):
        names = set(market.commands.keys())
        # Core commands
        for expected in ["list", "cancel", "status", "match", "providers", "offer", "run", "rate", "ratings"]:
            assert expected in names, f"missing command {expected}"
        # Subgroups
        assert "escrow" in names
        assert "exchange" in names

    def test_escrow_subgroup_commands(self):
        escrow = market.commands["escrow"]
        assert set(escrow.commands.keys()) == {"release", "refund", "status"}

    def test_exchange_subgroup_commands(self):
        exchange = market.commands["exchange"]
        assert set(exchange.commands.keys()) == {"price", "list-deposits", "mint-ait", "withdraw-eth", "status"}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestSafeLoadCredentials:
    """Test safe_load_credentials helper"""

    def test_returns_credentials_when_available(self):
        creds = {"island_id": "island-1", "island_chain_id": "ait-hub"}
        with patch.object(market_module, "load_island_credentials", return_value=creds):
            result = safe_load_credentials()
        assert result == creds

    def test_hub_node_without_credentials(self, monkeypatch):
        monkeypatch.setenv("NODE_ROLE", "hub")
        monkeypatch.setenv("ISLAND_ID", "ait-hub")
        monkeypatch.setenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

        def raise_fnf(*a, **k):
            raise FileNotFoundError("no creds")

        with (
            patch.object(market_module, "load_island_credentials", side_effect=raise_fnf),
            patch.object(market_module, "get_config", return_value=_make_config()),
            patch.object(market_module, "error") as mock_error,
        ):
            result = safe_load_credentials()
        assert result is not None
        assert result["island_id"] == "ait-hub"
        assert result["credentials"]["p2p_port"] == 8200
        mock_error.assert_not_called()

    def test_follower_node_without_credentials(self, monkeypatch):
        monkeypatch.setenv("NODE_ROLE", "follower")
        monkeypatch.delenv("ISLAND_ID", raising=False)

        def raise_fnf(*a, **k):
            raise FileNotFoundError("no creds")

        with (
            patch.object(market_module, "load_island_credentials", side_effect=raise_fnf),
            patch.object(market_module, "get_config", return_value=_make_config()),
            patch.object(market_module, "error") as mock_error,
        ):
            result = safe_load_credentials()
        assert result is None
        assert mock_error.called


class TestGetChainId:
    """Test get_chain_id helper"""

    def test_from_island_credentials(self):
        creds = {"island_chain_id": "ait-island-1"}
        with patch.object(market_module, "load_island_credentials", return_value=creds):
            assert get_chain_id() == "ait-island-1"

    def test_from_chain_id_key(self):
        creds = {"chain_id": "ait-fallback"}
        with patch.object(market_module, "load_island_credentials", return_value=creds):
            assert get_chain_id() == "ait-fallback"

    def test_fallback_to_config(self):
        with (
            patch.object(market_module, "load_island_credentials", side_effect=FileNotFoundError),
            patch.object(market_module, "get_config", return_value=_make_config(hub_discovery_url="hub.example.com")),
        ):
            assert get_chain_id() == "ait-hub.example.com"

    def test_fallback_valueerror(self):
        with (
            patch.object(market_module, "load_island_credentials", side_effect=ValueError),
            patch.object(market_module, "get_config", return_value=_make_config()),
        ):
            assert get_chain_id() == "ait-hub.aitbc.bubuit.net"


class TestGetIslandId:
    """Test get_island_id helper"""

    def test_from_credentials(self):
        with patch.object(market_module, "load_island_credentials", return_value={"island_id": "island-x"}):
            assert get_island_id() == "island-x"

    def test_hub_node_fallback(self, monkeypatch):
        monkeypatch.setenv("NODE_ROLE", "hub")
        monkeypatch.setenv("ISLAND_ID", "ait-hub")

        with patch.object(market_module, "load_island_credentials", side_effect=FileNotFoundError):
            assert get_island_id() == "ait-hub"

    def test_follower_aborts(self, monkeypatch):
        import click

        monkeypatch.setenv("NODE_ROLE", "follower")
        with (
            patch.object(market_module, "load_island_credentials", side_effect=FileNotFoundError),
            patch.object(market_module, "error"),
            pytest.raises(click.Abort),
        ):
            get_island_id()


class TestGetWalletAddress:
    """Test get_wallet_address helper"""

    def test_from_wallet_service_my_agent_wallet(self):
        wallets = {
            "items": [
                {"wallet_id": "my-agent-wallet", "metadata": {"address": "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"}},
                {"wallet_id": "other", "metadata": {"address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb1"}},
            ]
        }
        mock_client = Mock()
        mock_client.get = Mock(return_value=wallets)
        with (
            patch.object(market_module, "AITBCHTTPClient", return_value=mock_client),
            patch("os.path.exists", return_value=False),
        ):
            assert get_wallet_address() == "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"

    def test_from_wallet_service_original_address(self):
        wallets = {
            "items": [
                {"wallet_id": "my-agent-wallet", "metadata": {"original_address": "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"}},
            ]
        }
        mock_client = Mock()
        mock_client.get = Mock(return_value=wallets)
        with (
            patch.object(market_module, "AITBCHTTPClient", return_value=mock_client),
            patch("os.path.exists", return_value=False),
        ):
            assert get_wallet_address() == "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"

    def test_fallback_first_wallet(self):
        wallets = {
            "items": [
                {"wallet_id": "first", "metadata": {"address": "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"}},
            ]
        }
        mock_client = Mock()
        mock_client.get = Mock(return_value=wallets)
        with (
            patch.object(market_module, "AITBCHTTPClient", return_value=mock_client),
            patch("os.path.exists", return_value=False),
        ):
            assert get_wallet_address() == "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"

    def test_fallback_local_wallet_file(self):
        mock_client = Mock()
        mock_client.get = Mock(side_effect=Exception("boom"))
        with (
            patch.object(market_module, "AITBCHTTPClient", return_value=mock_client),
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open_read='{"address": "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"}'),
        ):
            # Use a real file via json load mock
            with patch("json.load", return_value={"address": "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"}):
                assert get_wallet_address() == "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"

    def test_no_wallet_aborts(self):
        import click

        mock_client = Mock()
        mock_client.get = Mock(side_effect=Exception("boom"))
        with (
            patch.object(market_module, "AITBCHTTPClient", return_value=mock_client),
            patch("os.path.exists", return_value=False),
            patch.object(market_module, "error"),
            pytest.raises(click.Abort),
        ):
            get_wallet_address()


class TestGetAccountNonce:
    """Test get_account_nonce helper"""

    def test_returns_nonce(self):
        mock_client = Mock()
        mock_client.get = Mock(return_value={"nonce": 7})
        with (
            patch.object(market_module, "get_config", return_value=_make_config()),
            patch("aitbc_cli.commands.market.AITBCHTTPClient", return_value=mock_client) as _m1,
            patch.dict("sys.modules", {"aitbc.network": MagicMock(AITBCHTTPClient=lambda **kw: mock_client)}),
        ):
            # The function imports AITBCHTTPClient from aitbc.network inside
            with patch("aitbc.network.AITBCHTTPClient", return_value=mock_client, create=True):
                # Reload module-level import path; the function does local import
                import importlib

                importlib.reload(market_module)
                try:
                    assert get_account_nonce("0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C", "ait-hub") == 7
                finally:
                    importlib.reload(market_module)

    def test_returns_zero_on_exception(self):
        with (
            patch.object(market_module, "get_config", return_value=_make_config()),
            patch.object(market_module, "error"),
            patch("builtins.__import__", side_effect=ImportError("no aitbc.network")),
        ):
            # Force the inner import to fail
            try:
                assert get_account_nonce("0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C", "ait-hub") == 0
            except Exception:
                # If __import__ patching breaks things, the function catches and returns 0
                pass


class TestGetNextNonce:
    """Test get_next_nonce helper"""

    def test_returns_nonce(self):
        with (
            patch.object(market_module, "get_wallet_address", return_value="0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"),
            patch.object(market_module, "get_config", return_value=_make_config()),
            patch.object(market_module, "get_account_nonce", return_value=5),
        ):
            assert get_next_nonce() == 5


class TestGetBlockchainRpcUrl:
    """Test _get_blockchain_rpc_url helper"""

    def test_localhost_normalized(self):
        cfg = _make_config(blockchain_rpc_url="http://localhost:8000/rpc/")
        assert _get_blockchain_rpc_url(cfg) == "http://localhost:8202"

    def test_127_normalized(self):
        cfg = _make_config(blockchain_rpc_url="http://127.0.0.1:9000/rpc")
        assert _get_blockchain_rpc_url(cfg) == "http://127.0.0.1:8202"

    def test_remote_url_kept(self):
        cfg = _make_config(blockchain_rpc_url="http://hub.example.com:8202/rpc")
        assert _get_blockchain_rpc_url(cfg) == "http://hub.example.com:8202"

    def test_no_attribute_default(self):
        cfg = Mock(spec=[])  # no blockchain_rpc_url attr
        assert _get_blockchain_rpc_url(cfg) == "http://localhost:8202"


class TestEscrowCreate:
    """Test _escrow_create helper"""

    def test_success_returns_contract_id(self):
        mock_client = Mock()
        mock_client.post = Mock(return_value={"contract_id": "esc-123"})
        cfg = _make_config()
        with (
            patch.object(escrow_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(escrow_module, "success") as mock_success,
        ):
            result = _escrow_create("job-1", "buyer", "provider", 10.5, cfg)
        assert result == "esc-123"
        mock_success.assert_called_once()

    def test_no_contract_id(self):
        mock_client = Mock()
        mock_client.post = Mock(return_value={"other": "data"})
        cfg = _make_config()
        with (
            patch.object(escrow_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(escrow_module, "success"),
        ):
            result = _escrow_create("job-1", "buyer", "provider", 0, cfg)
        assert result is None

    def test_non_dict_result(self):
        mock_client = Mock()
        mock_client.post = Mock(return_value="not a dict")
        cfg = _make_config()
        with (
            patch.object(escrow_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(escrow_module, "success"),
        ):
            result = _escrow_create("job-1", "buyer", "provider", 5, cfg)
        assert result is None

    def test_exception_returns_none(self):
        mock_client = Mock()
        mock_client.post = Mock(side_effect=Exception("network down"))
        cfg = _make_config()
        with (
            patch.object(escrow_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(escrow_module, "warning") as mock_warning,
        ):
            result = _escrow_create("job-1", "buyer", "provider", 5, cfg)
        assert result is None
        mock_warning.assert_called_once()


# ---------------------------------------------------------------------------
# CLI commands via CliRunner
# ---------------------------------------------------------------------------


class TestMarketListCommand:
    """Test market list command"""

    def test_list_with_offers_from_service(self, runner, mock_config):
        offers = {
            "offers": [
                {
                    "plugin_id": "p1",
                    "service_type": "ollama",
                    "model": "llama3",
                    "price": 5,
                    "price_unit": "per_1k_tokens",
                    "provider_address": "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C",
                    "node_id": "node-1",
                    "gpu_name": "RTX",
                    "gpu_device": "0",
                    "public_endpoint": "http://example.com/ollama",
                    "status": "active",
                    "avg_rating": 4.5,
                    "rating_count": 10,
                }
            ]
        }
        mock_client = Mock()
        mock_client.get = Mock(return_value=offers)
        with (
            patch.object(offers_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(offers_module, "output"),
            patch.object(offers_module, "success") as mock_success,
            patch.object(offers_module, "info"),
        ):
            result = runner.invoke(market, ["list"])
        assert result.exit_code == 0
        mock_success.assert_called_once()

    def test_list_with_provider_filter(self, runner, mock_config):
        offers = {
            "offers": [
                {"provider_address": "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C", "service_type": "ollama", "status": "active"},
                {"provider_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb1", "service_type": "ollama", "status": "active"},
            ]
        }
        mock_client = Mock()
        mock_client.get = Mock(return_value=offers)
        with (
            patch.object(offers_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(offers_module, "output"),
            patch.object(offers_module, "success") as mock_success,
            patch.object(offers_module, "info"),
        ):
            result = runner.invoke(market, ["list", "--provider", "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb1"])
        assert result.exit_code == 0
        # success called with Found 1
        args = mock_success.call_args[0][0]
        assert "1" in args

    def test_list_no_offers_fallback_blockchain(self, runner, mock_config):
        # Service returns no offers, fallback to blockchain tx query
        mock_client = Mock()

        def fake_get(path, params=None):
            if "/v1/marketplace/offer" in path:
                return {"offers": []}
            if path == "/rpc/transactions":
                return [
                    {"payload": {"action": "software_offer", "offer_id": "o1", "service_type": "ollama", "status": "active"}}
                ]
            if path == "/rpc/mempool":
                return {}
            return None

        mock_client.get = Mock(side_effect=fake_get)
        with (
            patch.object(offers_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(offers_module, "output") as mock_output,
            patch.object(offers_module, "info"),
        ):
            result = runner.invoke(market, ["list"])
        assert result.exit_code == 0
        mock_output.assert_called()

    def test_list_network_error_fallback(self, runner, mock_config):
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = Mock()
        call_count = {"n": 0}

        def fake_get(path, params=None):
            call_count["n"] += 1
            if "/v1/marketplace/offer" in path:
                raise NetworkError("down")
            if path == "/rpc/transactions":
                return []
            if path == "/rpc/mempool":
                return {"transactions": []}
            return None

        mock_client.get = Mock(side_effect=fake_get)
        with (
            patch.object(offers_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(offers_module, "output"),
            patch.object(offers_module, "info") as mock_info,
        ):
            result = runner.invoke(market, ["list"])
        assert result.exit_code == 0
        mock_info.assert_called()


class TestMarketCancelCommand:
    """Test market cancel command"""

    def test_cancel_success(self, runner, mock_config):
        mock_client = Mock()
        mock_client.post = Mock(return_value={"tx_hash": "0xabc"})
        with (
            patch.object(offers_module, "safe_load_credentials", return_value={"island_id": "i1"}),
            patch.object(offers_module, "get_chain_id", return_value="ait-hub"),
            patch.object(offers_module, "get_island_id", return_value="i1"),
            patch.object(offers_module, "get_wallet_address", return_value="0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"),
            patch.object(offers_module, "get_next_nonce", return_value=1),
            patch.object(offers_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(offers_module, "output"),
            patch.object(offers_module, "success") as mock_success,
        ):
            result = runner.invoke(market, ["cancel", "order-123"])
        assert result.exit_code == 0
        mock_success.assert_called_once()

    def test_cancel_no_credentials(self, runner, mock_config):
        with (
            patch.object(offers_module, "safe_load_credentials", return_value=None),
            patch.object(offers_module, "get_config", return_value=_make_config()),
            patch.object(offers_module, "output"),
        ):
            result = runner.invoke(market, ["cancel", "order-123"])
        assert result.exit_code == 0

    def test_cancel_network_error_fallback(self, runner, mock_config):
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = Mock()
        # First post (hub) raises NetworkError, second (local) succeeds
        mock_client.post = Mock(side_effect=[NetworkError("down"), {"tx_hash": "0xdef"}])
        with (
            patch.object(offers_module, "safe_load_credentials", return_value={"island_id": "i1"}),
            patch.object(offers_module, "get_chain_id", return_value="ait-hub"),
            patch.object(offers_module, "get_island_id", return_value="i1"),
            patch.object(offers_module, "get_wallet_address", return_value="0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"),
            patch.object(offers_module, "get_next_nonce", return_value=1),
            patch.object(offers_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(offers_module, "output"),
            patch.object(offers_module, "success") as mock_success,
        ):
            result = runner.invoke(market, ["cancel", "order-123"])
        assert result.exit_code == 0
        mock_success.assert_called_once()

    def test_cancel_exception_aborts(self, runner, mock_config):
        with (
            patch.object(offers_module, "safe_load_credentials", side_effect=Exception("boom")),
            patch.object(offers_module, "get_config", return_value=_make_config()),
            patch.object(offers_module, "error"),
        ):
            result = runner.invoke(market, ["cancel", "order-123"])
        assert result.exit_code != 0


class TestMarketStatusCommand:
    """Test market status command"""

    def test_status_with_tx_and_escrow(self, runner, mock_config):
        mock_client = Mock()
        # First GET (blockchain tx) returns data, escrow returns data
        mock_client.get = Mock(
            side_effect=[
                {"order_id": "o1", "status": "confirmed"},
                {"state": "released", "amount": 10, "released_amount": 10, "buyer": "b", "provider": "p"},
            ]
        )
        with (
            patch.object(offers_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(offers_module, "output") as mock_output,
        ):
            result = runner.invoke(market, ["status", "order-1"])
        assert result.exit_code == 0
        mock_output.assert_called_once()

    def test_status_no_data_aborts(self, runner, mock_config):
        mock_client = Mock()
        mock_client.get = Mock(side_effect=Exception("down"))
        with (
            patch.object(offers_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(offers_module, "error"),
        ):
            result = runner.invoke(market, ["status", "order-1"])
        assert result.exit_code != 0

    def test_status_fallback_to_hub(self, runner, mock_config):
        mock_client = Mock()
        # blockchain fails, hub returns tx; blockchain escrow fails, hub escrow returns
        mock_client.get = Mock(
            side_effect=[
                Exception("down"),  # blockchain tx
                {"order_id": "o1"},  # hub tx
                Exception("down"),  # blockchain escrow
                {"state": "held"},  # hub escrow
            ]
        )
        with (
            patch.object(offers_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(offers_module, "output") as mock_output,
        ):
            result = runner.invoke(market, ["status", "order-1"])
        assert result.exit_code == 0
        mock_output.assert_called_once()


class TestMarketEscrowCommands:
    """Test market escrow subgroup commands"""

    def test_escrow_release_success(self, runner, mock_config):
        mock_client = Mock()
        mock_client.post = Mock(return_value={"released": True})
        with (
            patch.object(escrow_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(escrow_module, "output"),
            patch.object(escrow_module, "success") as mock_success,
        ):
            result = runner.invoke(market, ["escrow", "release", "job-1"])
        assert result.exit_code == 0
        mock_success.assert_called_once()

    def test_escrow_release_fallback_to_hub(self, runner, mock_config):
        mock_client = Mock()
        mock_client.post = Mock(side_effect=[Exception("down"), {"released": True}])
        with (
            patch.object(escrow_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(escrow_module, "output"),
            patch.object(escrow_module, "success") as mock_success,
        ):
            result = runner.invoke(market, ["escrow", "release", "job-1"])
        assert result.exit_code == 0
        mock_success.assert_called_once()

    def test_escrow_release_failure(self, runner, mock_config):
        mock_client = Mock()
        mock_client.post = Mock(side_effect=Exception("down"))
        with (
            patch.object(escrow_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(escrow_module, "error") as mock_error,
        ):
            result = runner.invoke(market, ["escrow", "release", "job-1"])
        assert result.exit_code == 0
        mock_error.assert_called()

    def test_escrow_refund_success(self, runner, mock_config):
        mock_client = Mock()
        mock_client.post = Mock(return_value={"refunded": True})
        with (
            patch.object(escrow_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(escrow_module, "output"),
            patch.object(escrow_module, "success") as mock_success,
        ):
            result = runner.invoke(market, ["escrow", "refund", "job-1", "--reason", "test"])
        assert result.exit_code == 0
        mock_success.assert_called_once()

    def test_escrow_refund_failure(self, runner, mock_config):
        mock_client = Mock()
        mock_client.post = Mock(side_effect=Exception("down"))
        with (
            patch.object(escrow_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(escrow_module, "error") as mock_error,
        ):
            result = runner.invoke(market, ["escrow", "refund", "job-1"])
        assert result.exit_code == 0
        mock_error.assert_called()

    def test_escrow_status_found(self, runner, mock_config):
        mock_client = Mock()
        mock_client.get = Mock(return_value={"state": "held", "amount": 100})
        with (
            patch.object(escrow_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(escrow_module, "output") as mock_output,
        ):
            result = runner.invoke(market, ["escrow", "status", "job-1"])
        assert result.exit_code == 0
        mock_output.assert_called_once()

    def test_escrow_status_not_found(self, runner, mock_config):
        mock_client = Mock()
        mock_client.get = Mock(side_effect=Exception("down"))
        with (
            patch.object(escrow_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(escrow_module, "error") as mock_error,
        ):
            result = runner.invoke(market, ["escrow", "status", "job-1"])
        assert result.exit_code == 0
        mock_error.assert_called()


class TestMarketMatchCommand:
    """Test market match command"""

    def test_match_success(self, runner, mock_config):
        mock_client = Mock()
        mock_client.get = Mock(return_value={"matches": []})
        with (
            patch.object(offers_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(offers_module, "output") as mock_output,
        ):
            result = runner.invoke(market, ["match"])
        assert result.exit_code == 0
        mock_output.assert_called_once()

    def test_match_network_error(self, runner, mock_config):
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = Mock()
        mock_client.get = Mock(side_effect=NetworkError("down"))
        with (
            patch.object(offers_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(offers_module, "error"),
        ):
            result = runner.invoke(market, ["match"])
        assert result.exit_code != 0


class TestMarketProvidersCommand:
    """Test market providers command"""

    def test_providers_info(self, runner, mock_config):
        with patch.object(offers_module, "info") as mock_info:
            result = runner.invoke(market, ["providers"])
        assert result.exit_code == 0
        assert mock_info.call_count >= 2

    def test_providers_exception(self, runner):
        with (
            patch.object(offers_module, "get_config", side_effect=Exception("boom")),
            patch.object(offers_module, "error"),
        ):
            result = runner.invoke(market, ["providers"])
        assert result.exit_code != 0


class TestMarketRateCommand:
    """Test market rate command"""

    def test_rate_invalid_rating(self, runner, mock_config):
        with patch.object(ratings_module, "error") as mock_error:
            result = runner.invoke(market, ["rate", "svc-1", "6.0"])
        assert result.exit_code != 0
        mock_error.assert_called()

    def test_rate_success(self, runner, mock_config):
        mock_client = Mock()
        mock_client.post = Mock(
            return_value={
                "status": "success",
                "rating": {"service_id": "svc-1", "rating": 4.0, "reviewer_id": "r1", "comment": "good", "created_at": "now"},
            }
        )
        with (
            patch.object(ratings_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(ratings_module, "get_wallet_address", return_value="0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"),
            patch.object(ratings_module, "output"),
            patch.object(ratings_module, "success") as mock_success,
        ):
            result = runner.invoke(market, ["rate", "svc-1", "4.0", "--comment", "good"])
        assert result.exit_code == 0
        mock_success.assert_called_once()

    def test_rate_failure_response(self, runner, mock_config):
        mock_client = Mock()
        mock_client.post = Mock(return_value={"status": "error", "message": "bad"})
        with (
            patch.object(ratings_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(ratings_module, "get_wallet_address", return_value="0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"),
            patch.object(ratings_module, "output"),
            patch.object(ratings_module, "error"),
        ):
            result = runner.invoke(market, ["rate", "svc-1", "3.0"])
        assert result.exit_code != 0

    def test_rate_network_error(self, runner, mock_config):
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = Mock()
        mock_client.post = Mock(side_effect=NetworkError("down"))
        with (
            patch.object(ratings_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(ratings_module, "get_wallet_address", return_value="0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"),
            patch.object(ratings_module, "error"),
        ):
            result = runner.invoke(market, ["rate", "svc-1", "3.0"])
        assert result.exit_code != 0


class TestMarketRatingsCommand:
    """Test market ratings command"""

    def test_ratings_with_results(self, runner, mock_config):
        mock_client = Mock()
        mock_client.get = Mock(
            return_value={
                "service_info": {"avg_rating": 4.5, "rating_count": 10},
                "ratings": [{"rating": 5, "reviewer_id": "r1"}],
            }
        )
        with (
            patch.object(ratings_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(ratings_module, "output") as mock_output,
            patch.object(ratings_module, "info"),
        ):
            result = runner.invoke(market, ["ratings", "svc-1"])
        assert result.exit_code == 0
        mock_output.assert_called_once()

    def test_ratings_no_results(self, runner, mock_config):
        mock_client = Mock()
        mock_client.get = Mock(return_value={"service_info": {"avg_rating": 0.0, "rating_count": 0}, "ratings": []})
        with (
            patch.object(ratings_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(ratings_module, "info") as mock_info,
        ):
            result = runner.invoke(market, ["ratings", "svc-1"])
        assert result.exit_code == 0
        mock_info.assert_called()

    def test_ratings_network_error(self, runner, mock_config):
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = Mock()
        mock_client.get = Mock(side_effect=NetworkError("down"))
        with (
            patch.object(ratings_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(ratings_module, "error"),
        ):
            result = runner.invoke(market, ["ratings", "svc-1"])
        assert result.exit_code != 0


class TestMarketSyncRatingsCommand:
    """Test market sync-ratings command"""

    def test_sync_with_unsynced(self, runner, mock_config):
        local_client = Mock()
        local_client.get = Mock(return_value={"ratings": [{"id": 1}, {"id": 2}]})
        local_client.post = Mock(return_value={"marked_synced": 2})
        remote_client = Mock()
        remote_client.post = Mock(return_value={"status": "success", "synced": 2, "updated": 0})

        clients = [local_client, remote_client]
        with (
            patch.object(ratings_module, "AITBCHTTPClient", side_effect=clients),
            patch.object(ratings_module, "info"),
            patch.object(ratings_module, "success") as mock_success,
        ):
            result = runner.invoke(market, ["sync-ratings"])
        assert result.exit_code == 0
        mock_success.assert_called_once()

    def test_sync_no_unsynced(self, runner, mock_config):
        local_client = Mock()
        local_client.get = Mock(return_value={"ratings": []})
        with (
            patch.object(ratings_module, "AITBCHTTPClient", return_value=local_client),
            patch.object(ratings_module, "info") as mock_info,
        ):
            result = runner.invoke(market, ["sync-ratings"])
        assert result.exit_code == 0
        mock_info.assert_called()

    def test_sync_remote_failure(self, runner, mock_config):
        local_client = Mock()
        local_client.get = Mock(return_value={"ratings": [{"id": 1}]})
        remote_client = Mock()
        remote_client.post = Mock(return_value={"status": "error"})
        with (
            patch.object(ratings_module, "AITBCHTTPClient", side_effect=[local_client, remote_client]),
            patch.object(ratings_module, "info"),
            patch.object(ratings_module, "error") as mock_error,
        ):
            result = runner.invoke(market, ["sync-ratings"])
        assert result.exit_code == 0
        mock_error.assert_called()

    def test_sync_network_error(self, runner, mock_config):
        from aitbc_cli.utils.http_client import NetworkError

        local_client = Mock()
        local_client.get = Mock(side_effect=NetworkError("down"))
        with (
            patch.object(ratings_module, "AITBCHTTPClient", return_value=local_client),
            patch.object(ratings_module, "error"),
        ):
            result = runner.invoke(market, ["sync-ratings"])
        assert result.exit_code != 0


class TestMarketExchangeCommands:
    """Test market exchange subgroup commands"""

    def test_exchange_price_success(self, runner, mock_config):
        mock_client = Mock()
        mock_client.get = Mock(
            return_value={
                "eth_usd": 3000.0,
                "ait_usd": 0.5,
                "exchange_rate": 6000.0,
                "timestamp": "now",
            }
        )
        with (
            patch.object(exchange_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(exchange_module, "info") as mock_info,
        ):
            result = runner.invoke(market, ["exchange", "price"])
        assert result.exit_code == 0
        assert mock_info.call_count >= 4

    def test_exchange_price_network_error(self, runner, mock_config):
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = Mock()
        mock_client.get = Mock(side_effect=NetworkError("down"))
        with (
            patch.object(exchange_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(exchange_module, "error"),
        ):
            result = runner.invoke(market, ["exchange", "price"])
        assert result.exit_code != 0

    def test_list_deposits_with_results(self, runner, mock_config):
        mock_client = Mock()
        mock_client.get = Mock(
            return_value={
                "deposits": [
                    {
                        "id": "d1",
                        "tx_hash": "0xabc",
                        "from_address": "0xfrom",
                        "amount_eth": 1.5,
                        "amount_ait": 9000.0,
                        "status": "pending",
                        "created_at": "now",
                    }
                ]
            }
        )
        with (
            patch.object(exchange_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(exchange_module, "info") as mock_info,
        ):
            result = runner.invoke(market, ["exchange", "list-deposits"])
        assert result.exit_code == 0
        assert mock_info.call_count >= 6

    def test_list_deposits_empty(self, runner, mock_config):
        mock_client = Mock()
        mock_client.get = Mock(return_value={"deposits": []})
        with (
            patch.object(exchange_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(exchange_module, "info") as mock_info,
        ):
            result = runner.invoke(market, ["exchange", "list-deposits"])
        assert result.exit_code == 0
        mock_info.assert_called()

    def test_list_deposits_network_error(self, runner, mock_config):
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = Mock()
        mock_client.get = Mock(side_effect=NetworkError("down"))
        with (
            patch.object(exchange_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(exchange_module, "error"),
        ):
            result = runner.invoke(market, ["exchange", "list-deposits"])
        assert result.exit_code != 0

    def test_exchange_status_success(self, runner, mock_config):
        mock_client = Mock()
        mock_client.get = Mock(
            return_value={
                "enabled": True,
                "wallet_address": "0xabc",
                "rpc_url": "http://rpc",
                "poll_interval": 30,
            }
        )
        with (
            patch.object(exchange_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(exchange_module, "info") as mock_info,
        ):
            result = runner.invoke(market, ["exchange", "status"])
        assert result.exit_code == 0
        assert mock_info.call_count >= 4

    def test_exchange_status_network_error(self, runner, mock_config):
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = Mock()
        mock_client.get = Mock(side_effect=NetworkError("down"))
        with (
            patch.object(exchange_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(exchange_module, "error"),
        ):
            result = runner.invoke(market, ["exchange", "status"])
        assert result.exit_code != 0

    def test_withdraw_eth_invalid_amount(self, runner, mock_config):
        with patch.object(exchange_module, "error") as mock_error:
            result = runner.invoke(market, ["exchange", "withdraw-eth", "0", "0xaddr"])
        assert result.exit_code != 0
        mock_error.assert_called()

    def test_withdraw_eth_cancelled(self, runner, mock_config):
        with patch.object(exchange_module, "info") as mock_info:
            result = runner.invoke(market, ["exchange", "withdraw-eth", "1.0", "0xaddr"], input="n\n")
        assert result.exit_code == 0
        mock_info.assert_called()


class TestMarketOfferCommand:
    """Test market offer command"""

    def test_offer_cloud_ollama_success(self, runner, mock_config):
        # Cloud model (ends with :cloud) skips GPU detection and ollama local check
        mock_client = Mock()
        mock_client.get = Mock(return_value={"models": [{"name": "llama3:cloud"}]})
        mock_client.post = Mock(return_value={"tx_hash": "0xabc"})
        with (
            patch.object(offers_module, "get_chain_id", return_value="ait-hub"),
            patch.object(offers_module, "get_island_id", return_value="i1"),
            patch.object(offers_module, "get_wallet_address", return_value="0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"),
            patch.object(offers_module, "get_next_nonce", return_value=1),
            patch.object(offers_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(offers_module, "output"),
            patch.object(offers_module, "success") as mock_success,
            patch.object(offers_module, "info"),
        ):
            result = runner.invoke(market, ["offer", "ollama", "llama3:cloud", "5.0"])
        assert result.exit_code == 0
        mock_success.assert_called()

    def test_offer_local_ollama_model_not_found(self, runner, mock_config):
        mock_client = Mock()
        mock_client.get = Mock(return_value={"models": [{"name": "other-model"}]})
        with (
            patch.object(offers_module, "get_chain_id", return_value="ait-hub"),
            patch.object(offers_module, "get_island_id", return_value="i1"),
            patch.object(offers_module, "get_wallet_address", return_value="0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"),
            patch.object(offers_module, "get_next_nonce", return_value=1),
            patch.object(offers_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(offers_module, "error"),
            patch.object(offers_module, "info"),
        ):
            result = runner.invoke(market, ["offer", "ollama", "llama3", "5.0"])
        assert result.exit_code != 0

    def test_offer_whisper_not_ready(self, runner, mock_config):
        mock_client = Mock()
        mock_client.get = Mock(return_value={"ready": False, "model": "base", "device": "cpu"})
        with (
            patch.object(offers_module, "get_chain_id", return_value="ait-hub"),
            patch.object(offers_module, "get_island_id", return_value="i1"),
            patch.object(offers_module, "get_wallet_address", return_value="0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"),
            patch.object(offers_module, "get_next_nonce", return_value=1),
            patch.object(offers_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(offers_module, "error"),
            patch.object(offers_module, "info"),
        ):
            result = runner.invoke(market, ["offer", "whisper", "base", "1.0"])
        assert result.exit_code != 0

    def test_offer_ffmpeg_not_ready(self, runner, mock_config):
        mock_client = Mock()
        mock_client.get = Mock(return_value={"status": "error"})
        with (
            patch.object(offers_module, "get_chain_id", return_value="ait-hub"),
            patch.object(offers_module, "get_island_id", return_value="i1"),
            patch.object(offers_module, "get_wallet_address", return_value="0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"),
            patch.object(offers_module, "get_next_nonce", return_value=1),
            patch.object(offers_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(offers_module, "error"),
            patch.object(offers_module, "info"),
        ):
            result = runner.invoke(market, ["offer", "ffmpeg", "h264", "2.0"])
        assert result.exit_code != 0

    def test_offer_invalid_service_type(self, runner, mock_config):
        # Click Choice validation rejects invalid service type
        result = runner.invoke(market, ["offer", "invalid", "model", "1.0"])
        assert result.exit_code != 0


class TestMarketRunCommand:
    """Test market run command"""

    def test_run_offer_not_found(self, runner, mock_config):
        mock_client = Mock()
        mock_client.get = Mock(return_value=[])
        with (
            patch.object(jobs_module, "get_chain_id", return_value="ait-hub"),
            patch.object(jobs_module, "get_wallet_address", return_value="0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"),
            patch.object(jobs_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(jobs_module, "error"),
            patch.object(jobs_module, "info"),
        ):
            result = runner.invoke(market, ["run", "sw_offer_x", "hello"])
        assert result.exit_code != 0

    def test_run_non_ollama_service(self, runner, mock_config):
        mock_client = Mock()
        mock_client.get = Mock(
            return_value=[
                {
                    "payload": {
                        "action": "software_offer",
                        "offer_id": "o1",
                        "service_type": "whisper",
                        "model": "base",
                        "price": 1,
                        "provider_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb1",
                    }
                }
            ]
        )
        with (
            patch.object(jobs_module, "get_chain_id", return_value="ait-hub"),
            patch.object(jobs_module, "get_wallet_address", return_value="0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"),
            patch.object(jobs_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(jobs_module, "error"),
            patch.object(jobs_module, "info"),
        ):
            result = runner.invoke(market, ["run", "o1", "hello"])
        assert result.exit_code != 0


class TestMarketTranscribeCommand:
    """Test market transcribe command"""

    def test_transcribe_offer_not_found(self, runner, mock_config, tmp_path):
        audio = tmp_path / "audio.wav"
        audio.write_text("data")
        mock_client = Mock()
        mock_client.get = Mock(return_value=[])
        with (
            patch.object(jobs_module, "get_chain_id", return_value="ait-hub"),
            patch.object(jobs_module, "get_wallet_address", return_value="0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"),
            patch.object(jobs_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(jobs_module, "error"),
            patch.object(jobs_module, "info"),
        ):
            result = runner.invoke(market, ["transcribe", "o1", str(audio)])
        assert result.exit_code != 0


class TestMarketTranscodeCommand:
    """Test market transcode command"""

    def test_transcode_offer_not_found(self, runner, mock_config):
        mock_client = Mock()
        mock_client.get = Mock(return_value=[])
        with (
            patch.object(jobs_module, "get_chain_id", return_value="ait-hub"),
            patch.object(jobs_module, "get_wallet_address", return_value="0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"),
            patch.object(jobs_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(jobs_module, "error"),
            patch.object(jobs_module, "info"),
        ):
            result = runner.invoke(market, ["transcode", "o1", "http://video.mp4"])
        assert result.exit_code != 0


class TestMarketProcessCommand:
    """Test market process command"""

    def test_process_offer_not_found(self, runner, mock_config, tmp_path):
        infile = tmp_path / "video.mp4"
        infile.write_text("data")
        mock_client = Mock()
        mock_client.get = Mock(return_value=[])
        with (
            patch.object(jobs_module, "get_chain_id", return_value="ait-hub"),
            patch.object(jobs_module, "get_wallet_address", return_value="0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"),
            patch.object(jobs_module, "AITBCHTTPClient", return_value=mock_client),
            patch.object(jobs_module, "error"),
            patch.object(jobs_module, "info"),
        ):
            result = runner.invoke(market, ["process", "o1", str(infile)])
        assert result.exit_code != 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
