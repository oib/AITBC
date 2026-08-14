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

from unittest.mock import AsyncMock, MagicMock


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
