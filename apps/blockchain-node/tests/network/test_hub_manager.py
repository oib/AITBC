"""
Tests for Hub Manager with Redis persistence
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from aitbc_chain.network.hub_manager import HubManager, HubInfo, HubStatus, PeerInfo


class TestHubManager:
    """Test cases for Hub Manager with Redis persistence"""

    @pytest.fixture
    def hub_manager(self):
        """Create a HubManager instance for testing"""
        return HubManager(
            local_node_id="test-node-id",
            local_address="127.0.0.1",
            local_port=7070,
            island_id="test-island-id",
            island_name="test-island",
            redis_url="redis://localhost:6379"
        )

    @pytest.mark.asyncio
    async def test_connect_redis_success(self, hub_manager):
        """Test successful Redis connection"""
        with patch('aitbc_chain.network.hub_manager.redis.asyncio') as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_redis.from_url.return_value = mock_client

            result = await hub_manager._connect_redis()

            assert result is True
            assert hub_manager._redis is not None
            mock_redis.from_url.assert_called_once_with("redis://localhost:6379")
            mock_client.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_redis_failure(self, hub_manager):
        """Test Redis connection failure"""
        with patch('aitbc_chain.network.hub_manager.redis.asyncio') as mock_redis:
            mock_redis.from_url.side_effect = Exception("Connection failed")

            result = await hub_manager._connect_redis()

            assert result is False
            assert hub_manager._redis is None

    @pytest.mark.asyncio
    async def test_persist_hub_registration_success(self, hub_manager):
        """Test successful hub registration persistence to Redis"""
        hub_info = HubInfo(
            node_id="test-node-id",
            address="127.0.0.1",
            port=7070,
            island_id="test-island-id",
            island_name="test-island",
            public_address="1.2.3.4",
            public_port=7070,
            registered_at=1234567890.0,
            last_seen=1234567890.0
        )

        with patch('aitbc_chain.network.hub_manager.redis.asyncio') as mock_redis:
            mock_client = AsyncMock()
            mock_client.setex = AsyncMock(return_value=True)
            mock_redis.from_url.return_value = mock_client

            result = await hub_manager._persist_hub_registration(hub_info)

            assert result is True
            mock_client.setex.assert_called_once()
            key = mock_client.setex.call_args[0][0]
            assert key == "hub:test-node-id"

    @pytest.mark.asyncio
    async def test_persist_hub_registration_no_redis(self, hub_manager):
        """Test hub registration persistence when Redis is unavailable"""
        hub_info = HubInfo(
            node_id="test-node-id",
            address="127.0.0.1",
            port=7070,
            island_id="test-island-id",
            island_name="test-island"
        )

        with patch.object(hub_manager, '_connect_redis', return_value=False):
            result = await hub_manager._persist_hub_registration(hub_info)

            assert result is False

    @pytest.mark.asyncio
    async def test_remove_hub_registration_success(self, hub_manager):
        """Test successful hub registration removal from Redis"""
        with patch('aitbc_chain.network.hub_manager.redis.asyncio') as mock_redis:
            mock_client = AsyncMock()
            mock_client.delete = AsyncMock(return_value=True)
            mock_redis.from_url.return_value = mock_client

            result = await hub_manager._remove_hub_registration("test-node-id")

            assert result is True
            mock_client.delete.assert_called_once_with("hub:test-node-id")

    @pytest.mark.asyncio
    async def test_load_hub_registration_success(self, hub_manager):
        """Test successful hub registration loading from Redis"""
        with patch('aitbc_chain.network.hub_manager.redis.asyncio') as mock_redis:
            mock_client = AsyncMock()
            hub_data = {
                "node_id": "test-node-id",
                "address": "127.0.0.1",
                "port": 7070,
                "island_id": "test-island-id",
                "island_name": "test-island"
            }
            mock_client.get = AsyncMock(return_value='{"node_id": "test-node-id", "address": "127.0.0.1", "port": 7070, "island_id": "test-island-id", "island_name": "test-island"}')
            mock_redis.from_url.return_value = mock_client

            result = await hub_manager._load_hub_registration()

            assert result is not None
            assert result.node_id == "test-node-id"
            mock_client.get.assert_called_once_with("hub:test-node-id")

    @pytest.mark.asyncio
    async def test_load_hub_registration_not_found(self, hub_manager):
        """Test hub registration loading when not found in Redis"""
        with patch('aitbc_chain.network.hub_manager.redis.asyncio') as mock_redis:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=None)
            mock_redis.from_url.return_value = mock_client

            result = await hub_manager._load_hub_registration()

            assert result is None

    @pytest.mark.asyncio
    async def test_register_as_hub_success(self, hub_manager):
        """Test successful hub registration"""
        with patch.object(hub_manager, '_persist_hub_registration', return_value=True):
            result = await hub_manager.register_as_hub(public_address="1.2.3.4", public_port=7070)

            assert result is True
            assert hub_manager.is_hub is True
            assert hub_manager.hub_status == HubStatus.REGISTERED
            assert hub_manager.registered_at is not None
            assert hub_manager.local_node_id in hub_manager.known_hubs

    @pytest.mark.asyncio
    async def test_register_as_hub_already_registered(self, hub_manager):
        """Test hub registration when already registered"""
        hub_manager.is_hub = True
        hub_manager.hub_status = HubStatus.REGISTERED

        result = await hub_manager.register_as_hub()

        assert result is False
        assert hub_manager.is_hub is True

    @pytest.mark.asyncio
    async def test_unregister_as_hub_success(self, hub_manager):
        """Test successful hub unregistration"""
        hub_manager.is_hub = True
        hub_manager.hub_status = HubStatus.REGISTERED
        hub_manager.known_hubs["test-node-id"] = HubInfo(
            node_id="test-node-id",
            address="127.0.0.1",
            port=7070,
            island_id="test-island-id",
            island_name="test-island"
        )

        with patch.object(hub_manager, '_remove_hub_registration', return_value=True):
            result = await hub_manager.unregister_as_hub()

            assert result is True
            assert hub_manager.is_hub is False
            assert hub_manager.hub_status == HubStatus.UNREGISTERED
            assert hub_manager.registered_at is None
            assert hub_manager.local_node_id not in hub_manager.known_hubs

    @pytest.mark.asyncio
    async def test_unregister_as_hub_not_registered(self, hub_manager):
        """Test hub unregistration when not registered"""
        result = await hub_manager.unregister_as_hub()

        assert result is False
        assert hub_manager.is_hub is False

    def test_register_peer(self, hub_manager):
        """Test peer registration"""
        peer_info = PeerInfo(
            node_id="peer-1",
            address="192.168.1.1",
            port=7071,
            island_id="test-island-id",
            is_hub=False
        )

        result = hub_manager.register_peer(peer_info)

        assert result is True
        assert "peer-1" in hub_manager.peer_registry
        assert "peer-1" in hub_manager.island_peers["test-island-id"]

    def test_unregister_peer(self, hub_manager):
        """Test peer unregistration"""
        peer_info = PeerInfo(
            node_id="peer-1",
            address="192.168.1.1",
            port=7071,
            island_id="test-island-id",
            is_hub=False
        )
        hub_manager.register_peer(peer_info)

        result = hub_manager.unregister_peer("peer-1")

        assert result is True
        assert "peer-1" not in hub_manager.peer_registry
        assert "peer-1" not in hub_manager.island_peers["test-island-id"]

    def test_add_known_hub(self, hub_manager):
        """Test adding a known hub"""
        hub_info = HubInfo(
            node_id="hub-1",
            address="10.1.1.1",
            port=7070,
            island_id="test-island-id",
            island_name="test-island"
        )

        hub_manager.add_known_hub(hub_info)

        assert "hub-1" in hub_manager.known_hubs
        assert hub_manager.known_hubs["hub-1"] == hub_info

    def test_remove_known_hub(self, hub_manager):
        """Test removing a known hub"""
        hub_info = HubInfo(
            node_id="hub-1",
            address="10.1.1.1",
            port=7070,
            island_id="test-island-id",
            island_name="test-island"
        )
        hub_manager.add_known_hub(hub_info)

        result = hub_manager.remove_known_hub("hub-1")

        assert result is True
        assert "hub-1" not in hub_manager.known_hubs

    def test_get_peer_list(self, hub_manager):
        """Test getting peer list for an island"""
        peer_info1 = PeerInfo(
            node_id="peer-1",
            address="192.168.1.1",
            port=7071,
            island_id="test-island-id",
            is_hub=False
        )
        peer_info2 = PeerInfo(
            node_id="peer-2",
            address="192.168.1.2",
            port=7072,
            island_id="other-island-id",
            is_hub=False
        )
        hub_manager.register_peer(peer_info1)
        hub_manager.register_peer(peer_info2)

        peers = hub_manager.get_peer_list("test-island-id")

        assert len(peers) == 1
        assert peers[0].node_id == "peer-1"

    def test_get_hub_list(self, hub_manager):
        """Test getting hub list"""
        hub_info1 = HubInfo(
            node_id="hub-1",
            address="10.1.1.1",
            port=7070,
            island_id="test-island-id",
            island_name="test-island"
        )
        hub_info2 = HubInfo(
            node_id="hub-2",
            address="10.1.1.2",
            port=7070,
            island_id="other-island-id",
            island_name="other-island"
        )
        hub_manager.add_known_hub(hub_info1)
        hub_manager.add_known_hub(hub_info2)

        hubs = hub_manager.get_hub_list("test-island-id")

        assert len(hubs) == 1
        assert hubs[0].node_id == "hub-1"

    def test_update_peer_last_seen(self, hub_manager):
        """Test updating peer last seen time"""
        peer_info = PeerInfo(
            node_id="peer-1",
            address="192.168.1.1",
            port=7071,
            island_id="test-island-id",
            is_hub=False,
            last_seen=100.0
        )
        hub_manager.register_peer(peer_info)

        hub_manager.update_peer_last_seen("peer-1")

        assert hub_manager.peer_registry["peer-1"].last_seen > 100.0


if __name__ == "__main__":
    pytest.main([__file__])
