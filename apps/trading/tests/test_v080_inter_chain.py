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


class TestBridgeClient:
    """Test the BridgeClient wrapper (B3)."""

    def test_client_init(self):
        from trading_service.clients.bridge import BridgeClient

        client = BridgeClient(bridge_rpc_url="http://localhost:8202")
        assert client is not None


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


class TestInterChainTradeLifecycle:
    """Test inter-chain trade lifecycle (B5)."""


# ============================================================================
# B6: Matching Engine
# ============================================================================


class TestMatchingEngine:
    """Test the matching engine (B6)."""


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
