"""Tests for island join functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from aitbc_chain.network.island_manager import IslandManager
from aitbc_chain.rpc.islands import JoinIslandRequest, JoinIslandResponse, join_island


class TestIslandManagerJoin:
    """Test cases for IslandManager join operations."""

    @pytest.fixture
    def island_manager(self):
        """Create an IslandManager instance for testing."""
        return IslandManager("test-node", "test-island-id", "ait-test")

    def test_join_island_registers_new_island(self, island_manager):
        """join_island adds a new island membership."""
        result = island_manager.join_island("island-uuid-1", "island1", "ait-island1", is_hub=False)
        assert result is True
        assert island_manager.is_member_of_island("island-uuid-1")

    def test_join_island_duplicate_returns_false(self, island_manager):
        """Joining an island already a member of returns False."""
        island_manager.join_island("island-uuid-1", "island1", "ait-island1")
        result = island_manager.join_island("island-uuid-1", "island1", "ait-island1")
        assert result is False


class TestJoinIslandRpc:
    """Test cases for the HTTP /islands/join RPC endpoint."""

    @pytest.fixture
    def mock_island_manager(self):
        """Return a mock island manager with a default island."""
        manager = MagicMock()
        island = MagicMock()
        island.island_id = "ait-hub.aitbc.bubuit.net-island"
        island.island_name = "default"
        island.chain_id = "ait-hub.aitbc.bubuit.net"
        island.island_chain_id = "ait-hub.aitbc.bubuit.net"
        island.is_hub = True
        manager.get_island_info.return_value = island
        manager.join_island.return_value = True
        manager.island_peers = {}
        manager.local_node_id = "hub-node"
        return manager

    @pytest.mark.asyncio
    async def test_join_island_returns_full_response(self, mock_island_manager):
        """join_island returns the island credentials and metadata."""
        with patch(
            "aitbc_chain.rpc.islands.get_island_manager",
            return_value=mock_island_manager,
        ):
            request = JoinIslandRequest(
                island_id="ait-hub.aitbc.bubuit.net-island",
                island_name="default",
                chain_id="ait-hub.aitbc.bubuit.net",
                is_hub=True,
            )
            response = await join_island(request)

        assert isinstance(response, JoinIslandResponse)
        assert response.success is True
        assert response.island_id == "ait-hub.aitbc.bubuit.net-island"
        assert response.island_name == "default"
        assert response.island_chain_id == "ait-hub.aitbc.bubuit.net"
        assert response.status == "joined"
        assert "rpc_endpoint" in response.credentials
        assert response.members

    @pytest.mark.asyncio
    async def test_join_island_idempotent(self, mock_island_manager):
        """join_island succeeds even when the node is already a member."""
        mock_island_manager.join_island.return_value = False
        with patch(
            "aitbc_chain.rpc.islands.get_island_manager",
            return_value=mock_island_manager,
        ):
            request = JoinIslandRequest(
                island_id="ait-hub.aitbc.bubuit.net-island",
                island_name="default",
                chain_id="ait-hub.aitbc.bubuit.net",
            )
            response = await join_island(request)

        assert response.success is True
        assert response.status == "already_member"

    @pytest.mark.asyncio
    async def test_join_island_unknown_island_returns_failure(self):
        """join_island returns failure when the island is not known."""
        manager = MagicMock()
        manager.join_island.return_value = False
        manager.get_island_info.return_value = None
        with patch("aitbc_chain.rpc.islands.get_island_manager", return_value=manager):
            request = JoinIslandRequest(
                island_id="unknown-island",
                island_name="unknown",
                chain_id="ait-unknown",
            )
            response = await join_island(request)

        assert response.success is False
        assert response.status == "failed"


if __name__ == "__main__":
    pytest.main([__file__])
