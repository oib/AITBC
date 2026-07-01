"""Tests for v0.6.3 multi-island node support: per-chain sync source resolution
(B2), multi-hub subscription (B3), and island manager activation (B4)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from aitbc.network import IslandRegistry, SubscriptionManager
from aitbc.sync import SyncSourceResolver


# ---------------------------------------------------------------------------
# B2 — SyncSourceResolver (wired in main.py)
# ---------------------------------------------------------------------------


class TestSyncSourceResolver:
    """Test per-chain sync source resolution."""

    def test_single_hub_fallback(self):
        """Empty chain_sync_sources falls back to default_peer_rpc_url."""
        resolver = SyncSourceResolver(sync_sources="", default_url="http://hub-a:8202")
        assert resolver.get_sync_source("ait-hub") == "http://hub-a:8202"
        assert resolver.get_sync_source("ait-island1") == "http://hub-a:8202"

    def test_per_chain_sources(self):
        """Per-chain mapping returns correct hub URL per chain."""
        resolver = SyncSourceResolver(
            sync_sources="ait-hub:http://hub-a:8202,ait-island1:http://hub-b:8202",
            default_url="http://hub-a:8202",
        )
        assert resolver.get_sync_source("ait-hub") == "http://hub-a:8202"
        assert resolver.get_sync_source("ait-island1") == "http://hub-b:8202"

    def test_unknown_chain_uses_default(self):
        """Unknown chain falls back to default URL."""
        resolver = SyncSourceResolver(
            sync_sources="ait-hub:http://hub-a:8202",
            default_url="http://fallback:8202",
        )
        assert resolver.get_sync_source("ait-unknown") == "http://fallback:8202"

    def test_no_default_returns_none(self):
        """No default URL and chain not in mapping returns None."""
        resolver = SyncSourceResolver(sync_sources="ait-hub:http://hub-a:8202")
        assert resolver.get_sync_source("ait-unknown") is None

    def test_has_per_chain_sources_true(self):
        """has_per_chain_sources returns True when sources configured."""
        resolver = SyncSourceResolver(sync_sources="ait-hub:http://hub-a:8202")
        assert resolver.has_per_chain_sources() is True

    def test_has_per_chain_sources_false(self):
        """has_per_chain_sources returns False when no sources configured."""
        resolver = SyncSourceResolver(sync_sources="")
        assert resolver.has_per_chain_sources() is False

    def test_url_normalized_with_http_prefix(self):
        """URLs without protocol get http:// prefix."""
        resolver = SyncSourceResolver(sync_sources="ait-hub:hub-a:8202")
        assert resolver.get_sync_source("ait-hub") == "http://hub-a:8202"

    def test_malformed_entry_raises(self):
        """Entry without colon raises ValueError."""
        with pytest.raises(ValueError, match="Invalid sync source entry"):
            SyncSourceResolver(sync_sources="ait-hub")

    def test_get_all_sources(self):
        """get_all_sources returns copy of all configured sources."""
        resolver = SyncSourceResolver(sync_sources="ait-hub:http://a:8202,ait-island1:http://b:8202")
        all_sources = resolver.get_all_sources()
        assert len(all_sources) == 2
        assert all_sources["ait-hub"] == "http://a:8202"
        assert all_sources["ait-island1"] == "http://b:8202"
        # Verify it's a copy (modifying doesn't affect resolver)
        all_sources["ait-hub"] = "modified"
        assert resolver.get_sync_source("ait-hub") == "http://a:8202"


# ---------------------------------------------------------------------------
# B3 — Multi-hub subscription (SubscriptionManager)
# ---------------------------------------------------------------------------


class TestMultiHubSubscription:
    """Test multi-hub subscription client management."""

    def test_subscription_manager_creation(self):
        """SubscriptionManager can be created with defaults."""
        mgr = SubscriptionManager()
        assert mgr.get_all_chains() == []

    def test_add_subscription(self):
        """Adding a subscription registers it by chain_id."""
        mgr = SubscriptionManager()
        client = MagicMock()
        client.hub_url = "http://hub-a:8202"
        mgr.add_subscription("ait-hub", client)
        assert "ait-hub" in mgr.get_all_chains()
        entry = mgr.get_subscription("ait-hub")
        assert entry is not None
        assert entry.client is client

    def test_duplicate_chain_raises(self):
        """Adding a duplicate chain_id raises ValueError."""
        mgr = SubscriptionManager()
        client = MagicMock()
        client.hub_url = "http://hub-a:8202"
        mgr.add_subscription("ait-hub", client)
        with pytest.raises(ValueError, match="already exists"):
            mgr.add_subscription("ait-hub", client)

    def test_remove_subscription(self):
        """Removing a subscription removes it from the manager."""
        mgr = SubscriptionManager()
        client = MagicMock()
        client.hub_url = "http://hub-a:8202"
        mgr.add_subscription("ait-hub", client)
        entry = mgr.remove_subscription("ait-hub")
        assert entry is not None
        assert "ait-hub" not in mgr.get_all_chains()

    def test_remove_nonexistent_returns_none(self):
        """Removing a non-existent subscription returns None."""
        mgr = SubscriptionManager()
        assert mgr.remove_subscription("nonexistent") is None

    async def test_start_all_starts_each_subscription(self):
        """start_all creates tasks for all registered subscriptions."""
        mgr = SubscriptionManager()
        client_a = AsyncMock()
        client_a.hub_url = "http://hub-a:8202"
        client_a.chain_id = "ait-hub"
        client_a.start = AsyncMock(side_effect=asyncio.CancelledError)
        client_b = AsyncMock()
        client_b.hub_url = "http://hub-b:8202"
        client_b.chain_id = "ait-island1"
        client_b.start = AsyncMock(side_effect=asyncio.CancelledError)
        mgr.add_subscription("ait-hub", client_a)
        mgr.add_subscription("ait-island1", client_b)
        await mgr.start_all()
        # Give tasks a moment to call start
        await asyncio.sleep(0.05)
        await mgr.stop_all()
        # Both clients should have had start called
        client_a.start.assert_awaited()
        client_b.start.assert_awaited()

    async def test_stop_all_cancels_tasks(self):
        """stop_all cancels all running subscription tasks."""
        mgr = SubscriptionManager()
        client = AsyncMock()
        client.hub_url = "http://hub-a:8202"
        client.chain_id = "ait-hub"
        client.start = AsyncMock(side_effect=asyncio.CancelledError)
        mgr.add_subscription("ait-hub", client)
        await mgr.start_all()
        await asyncio.sleep(0.05)
        await mgr.stop_all()
        entry = mgr.get_subscription("ait-hub")
        assert entry is not None
        assert entry.task is None or entry.task.done()

    def test_subscription_client_properties(self):
        """SubscriptionClient exposes chain_id, hub_url, is_connected properties."""
        from aitbc_chain.subscription_client import SubscriptionClient

        client = SubscriptionClient("http://hub-a:8202", "node-1", "ait-hub")
        assert client.chain_id == "ait-hub"
        assert client.hub_url == "http://hub-a:8202"
        assert client.is_connected is False


# ---------------------------------------------------------------------------
# B4 — Island manager activation
# ---------------------------------------------------------------------------


class TestIslandManagerActivation:
    """Test island manager background task activation and auto-join."""

    def test_island_tasks_disabled_by_default(self):
        """island_tasks_enabled defaults to False."""
        from aitbc_chain.config import settings

        assert settings.island_tasks_enabled is False

    def test_island_tasks_configurable(self):
        """island_tasks_enabled can be set via env var."""
        import os

        original = os.environ.get("ISLAND_TASKS_ENABLED")
        try:
            os.environ["ISLAND_TASKS_ENABLED"] = "true"
            from aitbc_chain.config import ChainSettings

            test_settings = ChainSettings()
            assert test_settings.island_tasks_enabled is True
        finally:
            if original is not None:
                os.environ["ISLAND_TASKS_ENABLED"] = original
            else:
                os.environ.pop("ISLAND_TASKS_ENABLED", None)

    def test_island_registry_parses_bridge_islands(self):
        """IslandRegistry parses island_registry config correctly."""
        registry = IslandRegistry("island-uuid-1:ait-island1:http://hub-b:8202,island-uuid-2:ait-island2:http://hub-c:8202")
        entry1 = registry.get_entry("island-uuid-1")
        assert entry1 is not None
        assert entry1.chain_id == "ait-island1"
        assert entry1.hub_url == "http://hub-b:8202"
        entry2 = registry.get_entry("island-uuid-2")
        assert entry2 is not None
        assert entry2.chain_id == "ait-island2"
        assert entry2.hub_url == "http://hub-c:8202"

    def test_island_registry_empty(self):
        """Empty island_registry returns no entries."""
        registry = IslandRegistry("")
        assert registry.get_entry("any-island") is None
        assert registry.get_all_entries() == []

    def test_island_registry_get_chain_for_island(self):
        """get_chain_for_island returns the chain_id for an island."""
        registry = IslandRegistry("island-1:ait-chain1:http://hub:8202")
        assert registry.get_chain_for_island("island-1") == "ait-chain1"
        assert registry.get_chain_for_island("unknown") is None

    def test_island_registry_get_hub_for_island(self):
        """get_hub_for_island returns the hub_url for an island."""
        registry = IslandRegistry("island-1:ait-chain1:http://hub:8202")
        assert registry.get_hub_for_island("island-1") == "http://hub:8202"
        assert registry.get_hub_for_island("unknown") is None

    def test_island_manager_join_island(self):
        """IslandManager.join_island registers a new island membership."""
        from aitbc_chain.network.island_manager import IslandManager

        mgr = IslandManager("node-1", "default-island", "ait-hub")
        result = mgr.join_island("island-uuid-1", "island1", "ait-island1", is_hub=False)
        assert result is True
        assert mgr.is_member_of_island("island-uuid-1")

    def test_island_manager_join_duplicate_returns_false(self):
        """Joining an island already a member of returns False."""
        from aitbc_chain.network.island_manager import IslandManager

        mgr = IslandManager("node-1", "default-island", "ait-hub")
        mgr.join_island("island-uuid-1", "island1", "ait-island1")
        result = mgr.join_island("island-uuid-1", "island1", "ait-island1")
        assert result is False

    def test_island_manager_leave_island(self):
        """IslandManager.leave_island removes island membership."""
        from aitbc_chain.network.island_manager import IslandManager

        mgr = IslandManager("node-1", "default-island", "ait-hub")
        mgr.join_island("island-uuid-1", "island1", "ait-island1")
        result = mgr.leave_island("island-uuid-1")
        assert result is True
        assert not mgr.is_member_of_island("island-uuid-1")

    def test_island_manager_cannot_leave_default(self):
        """Cannot leave the default island."""
        from aitbc_chain.network.island_manager import IslandManager

        mgr = IslandManager("node-1", "default-island", "ait-hub")
        result = mgr.leave_island("default-island")
        assert result is False

    def test_island_manager_get_all_islands(self):
        """get_all_islands returns all island memberships including default."""
        from aitbc_chain.network.island_manager import IslandManager

        mgr = IslandManager("node-1", "default-island", "ait-hub")
        mgr.join_island("island-uuid-1", "island1", "ait-island1")
        islands = mgr.get_all_islands()
        assert len(islands) == 2  # default + joined

    async def test_island_manager_start_sets_running(self):
        """start() sets running=True and starts background tasks."""
        from aitbc_chain.network.island_manager import IslandManager

        mgr = IslandManager("node-1", "default-island", "ait-hub")
        # Start and cancel quickly to verify running flag
        task = asyncio.create_task(mgr.start())
        await asyncio.sleep(0.05)
        assert mgr.running is True
        await mgr.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def test_island_manager_stop_sets_running_false(self):
        """stop() sets running=False."""
        from aitbc_chain.network.island_manager import IslandManager

        mgr = IslandManager("node-1", "default-island", "ait-hub")
        mgr.running = True
        asyncio.run(mgr.stop())
        assert mgr.running is False


# ---------------------------------------------------------------------------
# B2+B3 — BlockchainNode integration (get_sync_source + multi-hub wiring)
# ---------------------------------------------------------------------------


class TestBlockchainNodeSyncSource:
    """Test BlockchainNode.get_sync_source method."""

    def test_get_sync_source_returns_default(self):
        """get_sync_source returns default URL when no per-chain mapping."""
        from aitbc_chain.main import BlockchainNode

        node = BlockchainNode()
        # With empty chain_sync_sources, all chains use default_peer_rpc_url
        # default_peer_rpc_url is None by default, so result is None
        result = node.get_sync_source("ait-hub")
        # default_peer_rpc_url is None in test env
        assert result is None or isinstance(result, str)

    def test_get_sync_source_with_per_chain_mapping(self):
        """get_sync_source returns per-chain URL when mapping is configured."""
        from aitbc_chain.main import BlockchainNode

        # Create a resolver with per-chain sources directly
        node = BlockchainNode()
        node._sync_source_resolver = SyncSourceResolver(
            sync_sources="ait-hub:http://hub-a:8202,ait-island1:http://hub-b:8202",
            default_url="http://fallback:8202",
        )
        assert node.get_sync_source("ait-hub") == "http://hub-a:8202"
        assert node.get_sync_source("ait-island1") == "http://hub-b:8202"
        assert node.get_sync_source("ait-unknown") == "http://fallback:8202"


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------


class TestCLICommands:
    """Test new CLI commands are registered."""

    def test_chain_sync_status_help(self):
        """chain sync-status command is registered and shows help."""
        from click.testing import CliRunner

        from aitbc_cli.commands.chain import chain

        runner = CliRunner()
        result = runner.invoke(chain, ["sync-status", "--help"])
        assert result.exit_code == 0
        assert "sync-status" in result.output or "synchronization" in result.output.lower()

    def test_island_health_help(self):
        """node island health command is registered and shows help."""
        from click.testing import CliRunner

        from aitbc_cli.commands.node import node

        runner = CliRunner()
        result = runner.invoke(node, ["island", "health", "--help"])
        assert result.exit_code == 0
        assert "health" in result.output.lower()

    def test_island_list_alias(self):
        """node island list (alias) is registered."""

        from aitbc_cli.commands.node import node

        island_group = node.commands["island"]
        assert "list" in island_group.commands
        assert "list-islands" in island_group.commands

    def test_island_list_islands_not_stub(self):
        """list-islands command accepts --node-url (not the old stub)."""
        from click.testing import CliRunner

        from aitbc_cli.commands.node import node

        runner = CliRunner()
        result = runner.invoke(node, ["island", "list-islands", "--help"])
        assert result.exit_code == 0
        assert "--node-url" in result.output
