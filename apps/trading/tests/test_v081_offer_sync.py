"""Integration tests for v0.8.1 cross-chain offer sync (B1-B6).

Tests cover:
- B1: Offer sync config in Settings
- B2: OfferSyncService — sync_chain, sync_all_chains, discover_offers, staleness
- B3: Offer discovery endpoint
- B4: Offer sync endpoints
- B5: CLI discover, sync, sync-status commands
- B6: This test file
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest


# ============================================================================
# B1: Offer Sync Config
# ============================================================================


class TestOfferSyncConfig:
    """Test offer sync settings (B1)."""

    def test_offer_sync_defaults(self):
        from trading_service.config import Settings

        s = Settings()
        assert s.offer_sync_enabled is True
        assert s.offer_sync_interval_seconds == 60
        assert s.offer_staleness_threshold_seconds == 300
        assert s.offer_cache_ttl_seconds == 300
        assert s.offer_sync_max_bandwidth_kbps == 100
        assert s.offer_per_chain_staleness == {}

    def test_offer_sync_env_override(self, monkeypatch):
        from trading_service.config import Settings

        monkeypatch.setenv("TRADING_OFFER_SYNC_ENABLED", "false")
        monkeypatch.setenv("TRADING_OFFER_SYNC_INTERVAL_SECONDS", "120")
        monkeypatch.setenv("TRADING_OFFER_STALENESS_THRESHOLD_SECONDS", "600")
        s = Settings()
        assert s.offer_sync_enabled is False
        assert s.offer_sync_interval_seconds == 120
        assert s.offer_staleness_threshold_seconds == 600


# ============================================================================
# B2: OfferSyncService
# ============================================================================


class TestOfferSyncService:
    """Test the OfferSyncService (B2)."""

    @pytest.mark.asyncio
    async def test_sync_chain_success(self):
        """Test syncing offers from a single chain."""
        from trading_service.services.offer_sync_service import OfferSyncService

        # Mock the session and cache
        mock_session = AsyncMock()
        cache = MagicMock()
        cache.get_offer.return_value = None
        cache.set_offer = MagicMock()
        cache.set_sync_metadata = MagicMock()
        cache.mark_syncing = MagicMock()
        cache.get_stale_offers.return_value = []

        # Mock BlockchainRPCClient
        mock_blockchain = AsyncMock()
        mock_blockchain.query_offers = AsyncMock(
            return_value=[
                {
                    "gpu_id": "gpu_1",
                    "provider": "0xabc",
                    "price": 10.5,
                    "status": "available",
                    "model": "A100",
                    "region": "us-east",
                },
                {
                    "gpu_id": "gpu_2",
                    "provider": "0xdef",
                    "price": 20.0,
                    "status": "available",
                    "model": "V100",
                    "region": "eu-west",
                },
            ]
        )

        svc = OfferSyncService(mock_session, cache=cache, blockchain_client=mock_blockchain)
        result = await svc.sync_chain("ait-hub")

        assert result["chain_id"] == "ait-hub"
        assert result["synced"] == 2
        assert "last_sync" in result
        assert cache.set_offer.call_count == 2

    @pytest.mark.asyncio
    async def test_sync_chain_error(self):
        """Test sync failure handling."""
        from trading_service.services.offer_sync_service import OfferSyncService

        mock_session = AsyncMock()
        cache = MagicMock()
        cache.mark_syncing = MagicMock()

        mock_blockchain = AsyncMock()
        mock_blockchain.query_offers = AsyncMock(side_effect=Exception("Connection refused"))

        svc = OfferSyncService(mock_session, cache=cache, blockchain_client=mock_blockchain)
        result = await svc.sync_chain("ait-bad")

        assert result["chain_id"] == "ait-bad"
        assert result["synced"] == 0
        assert "error" in result

    @pytest.mark.asyncio
    async def test_sync_chain_source_wins_conflict(self):
        """Test that source-chain-wins conflict resolution works."""
        from trading_service.services.offer_sync_service import OfferSyncService
        from aitbc.trading.offer_types import SyncedOffer

        mock_session = AsyncMock()
        cache = MagicMock()
        # Offer already exists from a different chain
        existing = SyncedOffer(
            offer_id="gpu_1",
            chain_id="ait-island-1",
            provider="0xabc",
            service_type="gpu_marketplace",
            price=10.0,
            quantity=1,
            status="available",
        )
        cache.get_offer.return_value = existing
        cache.set_offer = MagicMock()
        cache.set_sync_metadata = MagicMock()
        cache.mark_syncing = MagicMock()
        cache.get_stale_offers.return_value = []

        mock_blockchain = AsyncMock()
        mock_blockchain.query_offers = AsyncMock(
            return_value=[
                {"gpu_id": "gpu_1", "provider": "0xabc", "price": 15.0, "status": "available"},
            ]
        )

        svc = OfferSyncService(mock_session, cache=cache, blockchain_client=mock_blockchain)
        result = await svc.sync_chain("ait-hub")

        # Should NOT update because offer belongs to ait-island-1 (source wins)
        assert result["synced"] == 0
        cache.set_offer.assert_not_called()

    @pytest.mark.asyncio
    async def test_discover_offers_with_filters(self):
        """Test offer discovery with filters."""
        from trading_service.services.offer_sync_service import OfferSyncService
        from aitbc.trading.offer_types import OfferDiscoveryRequest, SyncedOffer

        mock_session = AsyncMock()
        cache = MagicMock()
        cache.get_stale_offers.return_value = []
        cache._get_known_chains.return_value = ["ait-hub"]

        offers = [
            SyncedOffer(
                offer_id="gpu_1",
                chain_id="ait-hub",
                provider="0xa",
                service_type="gpu_marketplace",
                price=10.0,
                quantity=1,
                status="available",
                attributes={"model": "A100", "region": "us-east"},
            ),
            SyncedOffer(
                offer_id="gpu_2",
                chain_id="ait-hub",
                provider="0xb",
                service_type="gpu_marketplace",
                price=50.0,
                quantity=1,
                status="available",
                attributes={"model": "V100", "region": "eu-west"},
            ),
            SyncedOffer(
                offer_id="gpu_3",
                chain_id="ait-hub",
                provider="0xc",
                service_type="compute",
                price=5.0,
                quantity=1,
                status="available",
                attributes={"model": "A100", "region": "us-east"},
            ),
        ]
        cache.list_offers_by_chain.return_value = offers

        mock_blockchain = AsyncMock()
        svc = OfferSyncService(mock_session, cache=cache, blockchain_client=mock_blockchain)

        # Filter by service_type
        request = OfferDiscoveryRequest(service_type="gpu_marketplace")
        result = await svc.discover_offers(request)
        assert result.total_count == 2
        assert all(o.service_type == "gpu_marketplace" for o in result.offers)

        # Filter by max_price (gpu_3 at 5.0 and gpu_1 at 10.0 both qualify)
        cache.list_offers_by_chain.return_value = offers
        request = OfferDiscoveryRequest(max_price=10.0)
        result = await svc.discover_offers(request)
        assert result.total_count == 2
        assert all(o.price <= 10.0 for o in result.offers)

        # Filter by gpu_model
        cache.list_offers_by_chain.return_value = offers
        request = OfferDiscoveryRequest(gpu_model="A100")
        result = await svc.discover_offers(request)
        assert result.total_count == 2

    @pytest.mark.asyncio
    async def test_discover_triggers_sync_when_stale(self):
        """Test that discovery triggers on-demand sync when offers are stale."""
        from trading_service.services.offer_sync_service import OfferSyncService
        from aitbc.trading.offer_types import OfferDiscoveryRequest, SyncedOffer

        mock_session = AsyncMock()
        cache = MagicMock()
        cache.get_stale_offers.return_value = ["gpu_1"]  # 1 stale offer
        cache.list_offers_by_chain.return_value = [
            SyncedOffer(
                offer_id="gpu_1",
                chain_id="ait-hub",
                provider="0xa",
                service_type="gpu_marketplace",
                price=10.0,
                quantity=1,
                status="available",
            ),
        ]
        cache.set_offer = MagicMock()
        cache.set_sync_metadata = MagicMock()
        cache.mark_syncing = MagicMock()

        mock_blockchain = AsyncMock()
        mock_blockchain.query_offers = AsyncMock(
            return_value=[
                {"gpu_id": "gpu_1", "provider": "0xa", "price": 10.0, "status": "available"},
            ]
        )

        svc = OfferSyncService(mock_session, cache=cache, blockchain_client=mock_blockchain)
        request = OfferDiscoveryRequest(source_chain="ait-hub")
        result = await svc.discover_offers(request)

        assert result.sync_triggered is True
        assert result.total_count == 1

    def test_get_sync_status(self):
        """Test getting sync status."""
        from trading_service.services.offer_sync_service import OfferSyncService
        from aitbc.trading.offer_types import OfferSyncStatusEntry

        mock_session = AsyncMock()
        cache = MagicMock()
        svc = OfferSyncService(mock_session, cache=cache)

        # Manually add a status entry
        svc._sync_status["ait-hub"] = OfferSyncStatusEntry(
            chain_id="ait-hub",
            last_sync="2026-01-01T00:00:00Z",
            offer_count=5,
        )

        status = svc.get_sync_status()
        assert len(status) == 1
        assert status[0].chain_id == "ait-hub"
        assert status[0].offer_count == 5


# ============================================================================
# B3 + B4: Endpoints (using mocked OfferSyncService)
# ============================================================================


class TestOfferSyncEndpoints:
    """Test offer sync endpoints (B3 + B4)."""

    @pytest.mark.asyncio
    async def test_discover_endpoint_exists(self):
        """Test that the discover endpoint is registered."""
        # Just verify the route exists in the app
        from trading_service.main import app

        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/v1/trading/offers/discover" in routes

    @pytest.mark.asyncio
    async def test_sync_endpoint_exists(self):
        """Test that the sync endpoint is registered."""
        from trading_service.main import app

        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/v1/trading/offers/sync" in routes

    @pytest.mark.asyncio
    async def test_sync_status_endpoint_exists(self):
        """Test that the sync-status endpoint is registered."""
        from trading_service.main import app

        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/v1/trading/offers/sync-status" in routes

    @pytest.mark.asyncio
    async def test_cache_endpoint_exists(self):
        """Test that the cache endpoint is registered."""
        from trading_service.main import app

        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/v1/trading/offers/cache" in routes


# ============================================================================
# B5: CLI Commands
# ============================================================================


class TestCLIOfferSyncCommands:
    """Test CLI offer sync commands (B5)."""

    def test_trade_group_has_discover(self):
        from aitbc_cli.commands.trade import trade

        assert "discover" in trade.commands

    def test_trade_group_has_sync(self):
        from aitbc_cli.commands.trade import trade

        assert "sync" in trade.commands

    def test_trade_group_has_sync_status(self):
        from aitbc_cli.commands.trade import trade

        assert "sync-status" in trade.commands

    def test_discover_command_params(self):
        from aitbc_cli.commands.trade import trade

        cmd = trade.commands["discover"]
        param_names = {p.name for p in cmd.params}
        assert "source_chain" in param_names
        assert "service_type" in param_names
        assert "min_price" in param_names
        assert "max_price" in param_names
        assert "gpu_model" in param_names
        assert "region" in param_names

    def test_sync_command_params(self):
        from aitbc_cli.commands.trade import trade

        cmd = trade.commands["sync"]
        param_names = {p.name for p in cmd.params}
        assert "chain_id" in param_names
        assert "force" in param_names


# ============================================================================
# Integration: OfferSyncService with real OfferCache
# ============================================================================


class TestOfferSyncWithRealCache:
    """Test OfferSyncService with a real in-memory OfferCache."""

    @pytest.mark.asyncio
    async def test_sync_and_discover_flow(self):
        """Test the full sync → discover flow with a real cache."""
        from aitbc.trading.offer_cache import OfferCache
        from aitbc.trading.offer_types import OfferDiscoveryRequest
        from trading_service.services.offer_sync_service import OfferSyncService

        cache = OfferCache()
        # Clear any leftover data from previous tests
        cache.clear_chain("ait-hub")

        mock_session = AsyncMock()

        mock_blockchain = AsyncMock()
        mock_blockchain.query_offers = AsyncMock(
            return_value=[
                {"gpu_id": "gpu_1", "provider": "0xabc", "price": 10.0, "status": "available", "model": "A100"},
                {"gpu_id": "gpu_2", "provider": "0xdef", "price": 20.0, "status": "available", "model": "V100"},
            ]
        )

        svc = OfferSyncService(mock_session, cache=cache, blockchain_client=mock_blockchain)

        # Sync
        sync_result = await svc.sync_chain("ait-hub")
        assert sync_result["synced"] == 2

        # Discover
        request = OfferDiscoveryRequest(source_chain="ait-hub")
        result = await svc.discover_offers(request)
        assert result.total_count == 2
        assert all(o.chain_id == "ait-hub" for o in result.offers)

        # Verify cache has the offers
        cached = cache.get_offer("gpu_1")
        assert cached is not None
        assert cached.chain_id == "ait-hub"
        assert cached.price == 10.0

    @pytest.mark.asyncio
    async def test_staleness_detection(self):
        """Test that stale offers are detected based on last_synced timestamp."""
        from aitbc.trading.offer_cache import OfferCache
        from aitbc.trading.offer_types import SyncedOffer

        cache = OfferCache()
        cache.clear_chain("ait-hub")  # Clear leftover data
        # Insert an offer with an old last_synced timestamp (stale)
        old_offer = SyncedOffer(
            offer_id="gpu_old",
            chain_id="ait-hub",
            provider="0xabc",
            service_type="gpu_marketplace",
            price=10.0,
            quantity=1,
            status="available",
            last_synced="2020-01-01T00:00:00Z",  # Very old → stale
        )
        cache.set_offer(old_offer, ttl=3600)  # Long TTL so it stays in cache

        # Insert a fresh offer
        fresh_offer = SyncedOffer(
            offer_id="gpu_fresh",
            chain_id="ait-hub",
            provider="0xdef",
            service_type="gpu_marketplace",
            price=20.0,
            quantity=1,
            status="available",
            last_synced=datetime.now(UTC).isoformat(),  # Now → fresh
        )
        cache.set_offer(fresh_offer, ttl=3600)

        stale = cache.get_stale_offers("ait-hub")
        assert "gpu_old" in stale
        assert "gpu_fresh" not in stale
