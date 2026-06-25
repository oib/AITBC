"""
Tests for multi-chain test fixtures and multi-node harness (v0.5.17).

These are "meta-tests" that verify the test infrastructure itself works correctly
before it's used by the v0.5.16 regression tests, bridge tests, and future releases.
"""

from __future__ import annotations

import sys
from pathlib import Path


# Ensure blockchain-node src is on path
_BLOCKCHAIN_SRC = str(Path(__file__).resolve().parent.parent / "apps" / "blockchain-node" / "src")
if _BLOCKCHAIN_SRC not in sys.path:
    sys.path.insert(0, _BLOCKCHAIN_SRC)


# ---------------------------------------------------------------------------
# Multi-Chain Fixture Tests
# ---------------------------------------------------------------------------


class TestMultiChainFixture:
    """Verify the multi_chain_setup fixture works correctly."""

    def test_fixture_creates_two_chains(self, multi_chain_setup) -> None:
        """Fixture should create 2 chains: ait-hub and ait-island1."""
        assert "ait-hub" in multi_chain_setup.chains
        assert "ait-island1" in multi_chain_setup.chains
        assert len(multi_chain_setup.chains) == 2

    def test_hub_chain_is_marked_as_hub(self, multi_chain_setup) -> None:
        """Hub chain should have is_hub=True."""
        assert multi_chain_setup.hub.is_hub is True
        assert multi_chain_setup.hub_chain_id == "ait-hub"

    def test_island_chain_is_not_hub(self, multi_chain_setup) -> None:
        """Island chain should have is_hub=False."""
        island = multi_chain_setup.get("ait-island1")
        assert island.is_hub is False

    def test_chains_have_separate_databases(self, multi_chain_setup) -> None:
        """Each chain should have its own database path."""
        hub_path = multi_chain_setup.hub.db_path
        island_path = multi_chain_setup.get("ait-island1").db_path
        assert hub_path != island_path
        assert "ait-hub" in hub_path
        assert "ait-island1" in island_path

    def test_chains_have_separate_engines(self, multi_chain_setup) -> None:
        """Each chain should have its own SQLAlchemy engine."""
        hub_engine = multi_chain_setup.hub.engine
        island_engine = multi_chain_setup.get("ait-island1").engine
        assert hub_engine is not island_engine

    def test_session_factory_works(self, multi_chain_setup) -> None:
        """Session factory should yield a working session."""
        with multi_chain_setup.hub.session() as session:
            assert session is not None

    def test_island_has_sync_source_to_hub(self, multi_chain_setup) -> None:
        """Island chain should have sync source pointing to hub."""
        island = multi_chain_setup.get("ait-island1")
        assert "ait-hub" in island.sync_sources
        assert island.sync_sources["ait-hub"] == "http://localhost:8006"

    def test_seed_account_function(self, multi_chain_setup) -> None:
        """seed_account should create an account in the chain's database."""
        from tests.fixtures.multi_chain import seed_account
        from aitbc_chain.models import Account

        seed_account(multi_chain_setup.hub, "0xtest123", balance=5000)
        with multi_chain_setup.hub.session() as session:
            account = session.get(Account, ("ait-hub", "0xtest123"))
            assert account is not None
            assert account.balance == 5000

    def test_seed_accounts_multi_chain(self, multi_chain_setup) -> None:
        """seed_accounts_multi_chain should create accounts on all chains."""
        from tests.fixtures.multi_chain import seed_accounts_multi_chain
        from aitbc_chain.models import Account

        seed_accounts_multi_chain(multi_chain_setup, "0xmulti", balance=9999)
        for chain_id in multi_chain_setup.chain_ids:
            ctx = multi_chain_setup.get(chain_id)
            with ctx.session() as session:
                account = session.get(Account, (chain_id, "0xmulti"))
                assert account is not None
                assert account.balance == 9999

    def test_three_chain_setup_creates_three_chains(self, three_chain_setup) -> None:
        """three_chain_setup fixture should create 3 chains."""
        assert len(three_chain_setup.chains) == 3
        assert "ait-hub" in three_chain_setup.chains
        assert "ait-island1" in three_chain_setup.chains
        assert "ait-island2" in three_chain_setup.chains


class TestSyncSourceMap:
    """Verify the sync_source_map fixture."""

    def test_sync_source_map_has_hub_url(self, sync_source_map) -> None:
        """Sync source map should map ait-hub to its URL."""
        assert "ait-hub" in sync_source_map
        assert sync_source_map["ait-hub"] == "http://localhost:8006"


class TestIslandRegistry:
    """Verify the island_registry fixture."""

    def test_island_registry_has_entries(self, island_registry) -> None:
        """Island registry should have entries for hub and island."""
        assert "island-hub" in island_registry
        assert "island-1" in island_registry

    def test_island_registry_has_chain_ids(self, island_registry) -> None:
        """Each island entry should have a chain_id."""
        for _island_id, info in island_registry.items():
            assert "chain_id" in info
            assert "hub_url" in info
            assert "hub_chain_id" in info


class TestMultiChainMempool:
    """Verify the multi_chain_mempool fixture."""

    def test_mempool_has_transactions_for_each_chain(self, multi_chain_mempool, multi_chain_setup) -> None:
        """Mempool should have at least 1 transaction per chain."""
        for chain_id in multi_chain_setup.chain_ids:
            txs = multi_chain_mempool.get_pending_transactions(chain_id=chain_id, limit=100)
            assert len(txs) >= 1, f"No transactions for chain {chain_id}"

    def test_mempool_separates_chains(self, multi_chain_mempool) -> None:
        """Transactions for one chain should not appear in another chain's listing."""
        hub_txs = multi_chain_mempool.get_pending_transactions(chain_id="ait-hub", limit=100)
        island_txs = multi_chain_mempool.get_pending_transactions(chain_id="ait-island1", limit=100)
        # Each chain's txs should have the correct chain_id
        for tx in hub_txs:
            assert tx.get("chain_id") == "ait-hub", "Cross-chain contamination in mempool"
        for tx in island_txs:
            assert tx.get("chain_id") == "ait-island1", "Cross-chain contamination in mempool"


class TestMockSettings:
    """Verify the mock_settings fixture."""

    def test_mock_settings_has_hub_chain_id(self, mock_settings, multi_chain_setup) -> None:
        """Mock settings should have chain_id set to hub chain."""
        assert mock_settings.chain_id == multi_chain_setup.hub_chain_id

    def test_mock_settings_has_all_chains_supported(self, mock_settings, multi_chain_setup) -> None:
        """Mock settings should have all test chains in supported_chains."""
        from aitbc_chain.rpc.utils import get_supported_chains

        supported = get_supported_chains()
        for chain_id in multi_chain_setup.chain_ids:
            assert chain_id in supported, f"Chain {chain_id} not in supported_chains"


# ---------------------------------------------------------------------------
# Multi-Node Harness Tests
# ---------------------------------------------------------------------------


class TestMultiNodeHarness:
    """Verify the multi-node harness works correctly."""

    def test_harness_starts_empty(self, multi_node_harness) -> None:
        """Harness should start with no nodes."""
        assert len(multi_node_harness.nodes) == 0

    def test_start_network_creates_hub_and_followers(self, multi_node_harness) -> None:
        """start_network should create 1 hub + N followers."""
        multi_node_harness.start_network(num_nodes=2, num_chains=2)
        assert "hub" in multi_node_harness.nodes
        assert "follower-1" in multi_node_harness.nodes
        assert "follower-2" in multi_node_harness.nodes
        assert len(multi_node_harness.nodes) == 3

    def test_hub_node_is_marked_as_hub(self, multi_node_harness) -> None:
        """Hub node should have is_hub=True."""
        multi_node_harness.start_network(num_nodes=1, num_chains=1)
        assert multi_node_harness.nodes["hub"].config.is_hub is True

    def test_follower_nodes_are_not_hubs(self, multi_node_harness) -> None:
        """Follower nodes should have is_hub=False."""
        multi_node_harness.start_network(num_nodes=2, num_chains=2)
        for nid, node in multi_node_harness.nodes.items():
            if nid != "hub":
                assert node.config.is_hub is False

    def test_nodes_have_separate_databases(self, multi_node_harness) -> None:
        """Each node should have its own database."""
        multi_node_harness.start_network(num_nodes=2, num_chains=2)
        paths = [node.db_path for node in multi_node_harness.nodes.values()]
        assert len(paths) == len(set(paths)), "Nodes share database paths"

    def test_nodes_respond_to_health_check(self, multi_node_harness) -> None:
        """Each node should respond to /health."""
        multi_node_harness.start_network(num_nodes=2, num_chains=2)
        for nid, node in multi_node_harness.nodes.items():
            resp = node.client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["node_id"] == nid

    def test_nodes_respond_to_head(self, multi_node_harness) -> None:
        """Each node should respond to /rpc/head."""
        multi_node_harness.start_network(num_nodes=1, num_chains=1)
        resp = multi_node_harness.nodes["hub"].client.get("/rpc/head")
        assert resp.status_code == 200
        data = resp.json()
        assert "height" in data
        assert "chain_id" in data

    def test_partition_marks_nodes(self, multi_node_harness) -> None:
        """partition() should mark specified nodes as partitioned."""
        multi_node_harness.start_network(num_nodes=2, num_chains=2)
        multi_node_harness.partition(["follower-1"])
        assert multi_node_harness.nodes["follower-1"].is_partitioned()
        assert not multi_node_harness.nodes["follower-2"].is_partitioned()

    def test_heal_clears_partitions(self, multi_node_harness) -> None:
        """heal() should clear all partitions."""
        multi_node_harness.start_network(num_nodes=2, num_chains=2)
        multi_node_harness.partition(["follower-1", "follower-2"])
        multi_node_harness.heal()
        for node in multi_node_harness.nodes.values():
            assert not node.is_partitioned()

    def test_add_byzantine_node(self, multi_node_harness) -> None:
        """add_byzantine_node should create a node marked as byzantine."""
        multi_node_harness.start_network(num_nodes=1, num_chains=1)
        byz_id = multi_node_harness.add_byzantine_node("ait-hub")
        assert byz_id in multi_node_harness.nodes
        assert multi_node_harness.nodes[byz_id].is_byzantine()

    def test_byzantine_node_returns_invalid_head(self, multi_node_harness) -> None:
        """Byzantine node should return invalid block data."""
        multi_node_harness.start_network(num_nodes=1, num_chains=1)
        byz_id = multi_node_harness.add_byzantine_node("ait-hub")
        resp = multi_node_harness.nodes[byz_id].client.get("/rpc/head")
        data = resp.json()
        assert data["hash"] == "0xfake"
        assert data["height"] == 999999

    def test_measure_sync_lag(self, multi_node_harness) -> None:
        """measure_sync_lag should return lag dict for followers."""
        multi_node_harness.start_network(num_nodes=2, num_chains=1)
        lag = multi_node_harness.measure_sync_lag("ait-hub")
        assert "follower-1" in lag
        assert "follower-2" in lag
        # All nodes start at height -1, so lag should be 0
        assert lag["follower-1"] >= 0
        assert lag["follower-2"] >= 0

    def test_three_node_network_fixture(self, three_node_network) -> None:
        """three_node_network fixture should create 3 nodes."""
        assert len(three_node_network.nodes) == 3
        assert "hub" in three_node_network.nodes

    def test_node_url_property(self, multi_node_harness) -> None:
        """Node.url should return the correct URL."""
        multi_node_harness.start_network(num_nodes=1, num_chains=1, base_port=9000)
        hub = multi_node_harness.nodes["hub"]
        assert hub.url == "http://127.0.0.1:9000"
        follower = multi_node_harness.nodes["follower-1"]
        assert follower.url == "http://127.0.0.1:9001"

    def test_get_account_endpoint(self, multi_node_harness) -> None:
        """Node should respond to /rpc/account/{address}."""
        multi_node_harness.start_network(num_nodes=1, num_chains=1)
        resp = multi_node_harness.nodes["hub"].client.get("/rpc/account/0xnonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["balance"] == 0
        assert data["nonce"] == 0

    def test_blocks_range_endpoint(self, multi_node_harness) -> None:
        """Node should respond to /rpc/blocks-range."""
        multi_node_harness.start_network(num_nodes=1, num_chains=1)
        resp = multi_node_harness.nodes["hub"].client.get("/rpc/blocks-range?start=0&end=10")
        assert resp.status_code == 200
        blocks = resp.json()
        assert isinstance(blocks, list)
