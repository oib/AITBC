"""Integration tests for v0.8.0 inter-chain trading (B1-B8).

Tests cover:
- B1: Trading service Settings class
- B2: InterChainTrade + IslandRegistryEntry model creation
- B3: BlockchainClient + BridgeClient (mocked)
- B4: Chain discovery (register, list, health)
- B5: Inter-chain trade lifecycle (create, list, get, status, history)
- B6: Matching engine (price-time priority, cross-chain matching)
- B7: CLI trade commands
- B8: This test file
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================================
# B1: Trading Service Settings
# ============================================================================


class TestTradingSettings:
    """Test the trading service Settings class (B1)."""

    def test_settings_defaults(self):
        from trading_service.config import Settings

        s = Settings()
        assert s.blockchain_rpc_url == "http://localhost:8202"
        assert s.bridge_rpc_url == "http://localhost:8202"
        assert s.default_chain_id == "ait-hub"
        assert s.matching_enabled is True
        assert s.execution_timeout == 300
        assert s.island_registry_sync_interval == 300
        assert s.bind_port == 8104

    def test_settings_env_override(self, monkeypatch):
        from trading_service.config import Settings

        monkeypatch.setenv("TRADING_BLOCKCHAIN_RPC_URL", "http://node:8202")
        monkeypatch.setenv("TRADING_DEFAULT_CHAIN_ID", "test-chain")
        monkeypatch.setenv("TRADING_MATCHING_ENABLED", "false")
        s = Settings()
        assert s.blockchain_rpc_url == "http://node:8202"
        assert s.default_chain_id == "test-chain"
        assert s.matching_enabled is False

    def test_settings_not_8006(self):
        """Verify the stale port 8006 is NOT used."""
        from trading_service.config import Settings

        s = Settings()
        assert "8006" not in s.blockchain_rpc_url
        assert "8202" in s.blockchain_rpc_url


# ============================================================================
# B2: Domain Models
# ============================================================================


class TestInterChainModels:
    """Test InterChainTrade and IslandRegistryEntry models (B2)."""

    def test_inter_chain_trade_defaults(self):
        from trading_service.domain.inter_chain import InterChainTrade

        trade = InterChainTrade(
            source_chain="ait-hub",
            dest_chain="ait-island-1",
            sender="0xabc",
            recipient="0xdef",
            amount=1000,
        )
        assert trade.status == "pending"
        assert trade.price == 0.0
        assert trade.quantity == 0
        assert trade.source_tx_hash is None
        assert trade.dest_tx_hash is None
        assert trade.matched_trade_id is None
        assert trade.trade_id.startswith("trade_")

    def test_inter_chain_trade_with_offer(self):
        from trading_service.domain.inter_chain import InterChainTrade

        trade = InterChainTrade(
            source_chain="ait-hub",
            dest_chain="ait-island-1",
            sender="0xabc",
            recipient="0xdef",
            amount=1000,
            offer_id="offer_123",
            price=50.5,
            quantity=10,
        )
        assert trade.offer_id == "offer_123"
        assert trade.price == 50.5
        assert trade.quantity == 10

    def test_island_registry_entry_defaults(self):
        from trading_service.domain.inter_chain import IslandRegistryEntry

        entry = IslandRegistryEntry(
            chain_id="ait-hub",
            endpoint="http://localhost:8202",
        )
        assert entry.status == "active"
        assert entry.block_height == 0
        assert entry.offers_count == 0


# ============================================================================
# B3: Blockchain/Bridge Clients (mocked)
# ============================================================================


class TestBlockchainClient:
    """Test the BlockchainClient for trading service (B3)."""

    def test_client_init(self):
        from trading_service.clients.blockchain import BlockchainClient

        client = BlockchainClient(rpc_url="http://localhost:8202")
        assert client.rpc_url == "http://localhost:8202"

    def test_client_strips_trailing_slash(self):
        from trading_service.clients.blockchain import BlockchainClient

        client = BlockchainClient(rpc_url="http://localhost:8202/")
        assert client.rpc_url == "http://localhost:8202"

    @pytest.mark.asyncio
    async def test_get_block_height(self):
        from trading_service.clients.blockchain import BlockchainClient

        client = BlockchainClient(rpc_url="http://localhost:8202")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"height": 12345}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_c = AsyncMock()
            mock_c.get = AsyncMock(return_value=mock_resp)
            mock_c.__aenter__ = AsyncMock(return_value=mock_c)
            mock_c.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_c
            height = await client.get_block_height("ait-hub")
            assert height == 12345

    @pytest.mark.asyncio
    async def test_get_account_balance_404(self):
        from trading_service.clients.blockchain import BlockchainClient

        client = BlockchainClient(rpc_url="http://localhost:8202")
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("httpx.AsyncClient") as mock_cls:
            mock_c = AsyncMock()
            mock_c.get = AsyncMock(return_value=mock_resp)
            mock_c.__aenter__ = AsyncMock(return_value=mock_c)
            mock_c.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_c
            balance = await client.get_account_balance("0xnew")
            assert balance == 0


class TestBridgeClient:
    """Test the BridgeClient wrapper (B3)."""

    def test_client_init(self):
        from trading_service.clients.bridge import BridgeClient

        client = BridgeClient(bridge_rpc_url="http://localhost:8202")
        assert client is not None

    @pytest.mark.asyncio
    async def test_check_health(self):
        from trading_service.clients.bridge import BridgeClient

        client = BridgeClient(bridge_rpc_url="http://localhost:8202")
        with patch.object(client._bridge, "check_health", new=AsyncMock(return_value={"status": "healthy"})):
            result = await client.check_health()
            assert result["status"] == "healthy"


# ============================================================================
# B4 + B5: Chain Discovery + Trade Lifecycle (in-memory SQLite)
# ============================================================================


@pytest.fixture
async def db_session():
    """Create an in-memory SQLite async session for testing."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlmodel import SQLModel

    # Import all models to ensure they're registered with SQLModel.metadata
    from trading_service.domain.inter_chain import (  # noqa: F401 — ensure registered
        InterChainTrade,
        IslandRegistryEntry,
    )
    from trading_service.domain.trading import (  # noqa: F401 — ensure registered
        TradeAgreement,
        TradeMatch,
        TradeNegotiation,
        TradeRequest,
        TradeSettlement,
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session

    await engine.dispose()


class TestChainDiscovery:
    """Test chain discovery service (B4)."""

    @pytest.mark.asyncio
    async def test_register_and_list_chain(self, db_session):
        from trading_service.services.chain_discovery import ChainDiscoveryService

        svc = ChainDiscoveryService(db_session)
        await svc.register_chain("ait-hub", "http://localhost:8202")
        await svc.register_chain("ait-island-1", "http://node1:8202")

        chains = await svc.list_chains()
        assert len(chains) == 2
        assert any(c.chain_id == "ait-hub" for c in chains)
        assert any(c.chain_id == "ait-island-1" for c in chains)

    @pytest.mark.asyncio
    async def test_register_duplicate_updates(self, db_session):
        from trading_service.services.chain_discovery import ChainDiscoveryService

        svc = ChainDiscoveryService(db_session)
        await svc.register_chain("ait-hub", "http://old:8202")
        await svc.register_chain("ait-hub", "http://new:8202")

        chains = await svc.list_chains()
        assert len(chains) == 1
        assert chains[0].endpoint == "http://new:8202"

    @pytest.mark.asyncio
    async def test_get_chain(self, db_session):
        from trading_service.services.chain_discovery import ChainDiscoveryService

        svc = ChainDiscoveryService(db_session)
        await svc.register_chain("ait-hub", "http://localhost:8202")

        chain = await svc.get_chain("ait-hub")
        assert chain is not None
        assert chain.endpoint == "http://localhost:8202"

        missing = await svc.get_chain("nonexistent")
        assert missing is None


class TestInterChainTradeLifecycle:
    """Test inter-chain trade lifecycle (B5)."""

    @pytest.mark.asyncio
    async def test_create_and_get_trade(self, db_session):
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        trade = await svc.create_trade(
            source_chain="ait-hub",
            dest_chain="ait-island-1",
            sender="0xabc",
            recipient="0xdef",
            amount=1000,
        )
        assert trade.status == "pending"
        assert trade.source_chain == "ait-hub"
        assert trade.dest_chain == "ait-island-1"

        fetched = await svc.get_trade(trade.trade_id)
        assert fetched is not None
        assert fetched.trade_id == trade.trade_id

    @pytest.mark.asyncio
    async def test_list_trades_with_filter(self, db_session):
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        await svc.create_trade("ait-hub", "ait-island-1", "0xa", "0xb", 100)
        await svc.create_trade("ait-hub", "ait-island-2", "0xc", "0xd", 200)
        await svc.create_trade("ait-island-1", "ait-hub", "0xe", "0xf", 300)

        all_trades = await svc.list_trades()
        assert len(all_trades) == 3

        hub_to_island1 = await svc.list_trades(source_chain="ait-hub", dest_chain="ait-island-1")
        assert len(hub_to_island1) == 1
        assert hub_to_island1[0].amount == 100

    @pytest.mark.asyncio
    async def test_get_trade_status(self, db_session):
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        trade = await svc.create_trade("ait-hub", "ait-island-1", "0xa", "0xb", 100)

        status = await svc.get_trade_status(trade.trade_id)
        assert status is not None
        assert status["status"] == "pending"
        assert status["source_chain"] == "ait-hub"

    @pytest.mark.asyncio
    async def test_update_trade_status(self, db_session):
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        trade = await svc.create_trade("ait-hub", "ait-island-1", "0xa", "0xb", 100)

        updated = await svc.update_trade_status(trade.trade_id, "matched", matched_trade_id="trade_other")
        assert updated is not None
        assert updated.status == "matched"
        assert updated.matched_trade_id == "trade_other"

    @pytest.mark.asyncio
    async def test_trade_history(self, db_session):
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        trade1 = await svc.create_trade("ait-hub", "ait-island-1", "0xa", "0xb", 100)
        trade2 = await svc.create_trade("ait-hub", "ait-island-2", "0xc", "0xd", 200)

        # History only includes completed/cancelled/failed
        await svc.update_trade_status(trade1.trade_id, "completed")
        await svc.update_trade_status(trade2.trade_id, "cancelled")

        history = await svc.get_trade_history()
        assert len(history) == 2


# ============================================================================
# B6: Matching Engine
# ============================================================================


class TestMatchingEngine:
    """Test the matching engine (B6)."""

    @pytest.mark.asyncio
    async def test_match_trade_finds_counterparty(self, db_session):
        from trading_service.services.inter_chain_service import InterChainTradeService
        from trading_service.services.matching_engine import MatchingEngine

        trade_svc = InterChainTradeService(db_session)
        match_svc = MatchingEngine(db_session)

        # Create trade A: hub → island-1
        trade_a = await trade_svc.create_trade("ait-hub", "ait-island-1", "0xa", "0xb", 1000)
        # Create trade B: island-1 → hub (counterparty)
        trade_b = await trade_svc.create_trade("ait-island-1", "ait-hub", "0xb", "0xa", 1000)

        # Match trade A
        result = await match_svc.match_trade(trade_a.trade_id)
        assert result is not None
        assert result["matched"] is True
        assert result["matched_trade_id"] == trade_b.trade_id

        # Both should be "matched"
        status_a = await trade_svc.get_trade_status(trade_a.trade_id)
        status_b = await trade_svc.get_trade_status(trade_b.trade_id)
        assert status_a["status"] == "matched"
        assert status_b["status"] == "matched"

    @pytest.mark.asyncio
    async def test_match_trade_no_match(self, db_session):
        from trading_service.services.inter_chain_service import InterChainTradeService
        from trading_service.services.matching_engine import MatchingEngine

        trade_svc = InterChainTradeService(db_session)
        match_svc = MatchingEngine(db_session)

        # Create a trade with no counterparty
        trade = await trade_svc.create_trade("ait-hub", "ait-island-1", "0xa", "0xb", 1000)

        result = await match_svc.match_trade(trade.trade_id)
        assert result is not None
        assert result["matched"] is False
        assert "no matching" in result.get("reason", "")

    @pytest.mark.asyncio
    async def test_match_trade_wrong_amount(self, db_session):
        from trading_service.services.inter_chain_service import InterChainTradeService
        from trading_service.services.matching_engine import MatchingEngine

        trade_svc = InterChainTradeService(db_session)
        match_svc = MatchingEngine(db_session)

        trade_a = await trade_svc.create_trade("ait-hub", "ait-island-1", "0xa", "0xb", 1000)
        # Different amount — should not match
        await trade_svc.create_trade("ait-island-1", "ait-hub", "0xb", "0xa", 500)

        result = await match_svc.match_trade(trade_a.trade_id)
        assert result["matched"] is False

    @pytest.mark.asyncio
    async def test_match_all_pending(self, db_session):
        from trading_service.services.inter_chain_service import InterChainTradeService
        from trading_service.services.matching_engine import MatchingEngine

        trade_svc = InterChainTradeService(db_session)
        match_svc = MatchingEngine(db_session)

        # Create 2 matching pairs
        await trade_svc.create_trade("ait-hub", "ait-island-1", "0xa", "0xb", 100)
        await trade_svc.create_trade("ait-island-1", "ait-hub", "0xb", "0xa", 100)
        await trade_svc.create_trade("ait-hub", "ait-island-2", "0xc", "0xd", 200)
        await trade_svc.create_trade("ait-island-2", "ait-hub", "0xd", "0xc", 200)

        results = await match_svc.match_all_pending()
        matched = [r for r in results if r.get("matched")]
        assert len(matched) == 2


# ============================================================================
# B7: CLI Trade Commands
# ============================================================================


class TestCLITradeCommands:
    """Test the trade CLI command group (B7)."""

    def test_trade_group_exists(self):
        from aitbc_cli.commands.trade import trade

        assert trade is not None
        assert trade.name == "trade"

    def test_trade_has_subcommands(self):
        from aitbc_cli.commands.trade import trade

        subcommands = list(trade.commands.keys())
        assert "create" in subcommands
        assert "list" in subcommands
        assert "chains" in subcommands
        assert "get" in subcommands
        assert "status" in subcommands
        assert "register-chain" in subcommands
        assert "health" in subcommands
        assert "history" in subcommands
        assert "match" in subcommands
        assert "match-all" in subcommands

    def test_create_command_params(self):
        from aitbc_cli.commands.trade import trade

        cmd = trade.commands["create"]
        param_names = {p.name for p in cmd.params}
        assert "source_chain" in param_names
        assert "dest_chain" in param_names
        assert "sender" in param_names
        assert "recipient" in param_names
        assert "amount" in param_names


# ============================================================================
# Alembic Migration
# ============================================================================


class TestAlembicMigration:
    """Test that the v0.8.0 Alembic migration exists."""

    def test_migration_file_exists(self):
        import importlib.util
        from pathlib import Path

        path = Path(__file__).parent.parent / "alembic" / "versions" / "001_v080_inter_chain_trading.py"
        assert path.exists()
        spec = importlib.util.spec_from_file_location("migration_001", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.revision == "001"
        assert mod.down_revision is None

    def test_migration_has_upgrade_downgrade(self):
        import importlib.util
        from pathlib import Path

        path = Path(__file__).parent.parent / "alembic" / "versions" / "001_v080_inter_chain_trading.py"
        spec = importlib.util.spec_from_file_location("migration_001b", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert callable(mod.upgrade)
        assert callable(mod.downgrade)
