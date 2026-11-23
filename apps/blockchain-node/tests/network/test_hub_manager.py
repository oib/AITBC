"""
Tests for Hub Manager with Redis persistence
"""

import pytest
from aitbc_chain.network.hub_manager import HubInfo, HubManager, HubStatus, PeerInfo


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
            redis_url="redis://localhost:6379",
        )

    def test_register_peer(self, hub_manager):
        """Test peer registration"""
        peer_info = PeerInfo(node_id="peer-1", address="192.168.1.1", port=7071, island_id="test-island-id", is_hub=False)

        result = hub_manager.register_peer(peer_info)

        assert result is True
        assert "peer-1" in hub_manager.peer_registry
        assert "peer-1" in hub_manager.island_peers["test-island-id"]

    def test_unregister_peer(self, hub_manager):
        """Test peer unregistration"""
        peer_info = PeerInfo(node_id="peer-1", address="192.168.1.1", port=7071, island_id="test-island-id", is_hub=False)
        hub_manager.register_peer(peer_info)

        result = hub_manager.unregister_peer("peer-1")

        assert result is True
        assert "peer-1" not in hub_manager.peer_registry
        assert "peer-1" not in hub_manager.island_peers["test-island-id"]

    def test_add_known_hub(self, hub_manager):
        """Test adding a known hub"""
        hub_info = HubInfo(
            node_id="hub-1", address="10.1.1.1", port=7070, island_id="test-island-id", island_name="test-island"
        )

        hub_manager.add_known_hub(hub_info)

        assert "hub-1" in hub_manager.known_hubs
        assert hub_manager.known_hubs["hub-1"] == hub_info

    def test_remove_known_hub(self, hub_manager):
        """Test removing a known hub"""
        hub_info = HubInfo(
            node_id="hub-1", address="10.1.1.1", port=7070, island_id="test-island-id", island_name="test-island"
        )
        hub_manager.add_known_hub(hub_info)

        result = hub_manager.remove_known_hub("hub-1")

        assert result is True
        assert "hub-1" not in hub_manager.known_hubs

    def test_get_peer_list(self, hub_manager):
        """Test getting peer list for an island"""
        peer_info1 = PeerInfo(node_id="peer-1", address="192.168.1.1", port=7071, island_id="test-island-id", is_hub=False)
        peer_info2 = PeerInfo(node_id="peer-2", address="192.168.1.2", port=7072, island_id="other-island-id", is_hub=False)
        hub_manager.register_peer(peer_info1)
        hub_manager.register_peer(peer_info2)

        peers = hub_manager.get_peer_list("test-island-id")

        assert len(peers) == 1
        assert peers[0].node_id == "peer-1"

    def test_get_hub_list(self, hub_manager):
        """Test getting hub list"""
        hub_info1 = HubInfo(
            node_id="hub-1", address="10.1.1.1", port=7070, island_id="test-island-id", island_name="test-island"
        )
        hub_info2 = HubInfo(
            node_id="hub-2", address="10.1.1.2", port=7070, island_id="other-island-id", island_name="other-island"
        )
        hub_manager.add_known_hub(hub_info1)
        hub_manager.add_known_hub(hub_info2)

        hubs = hub_manager.get_hub_list("test-island-id")

        assert len(hubs) == 1
        assert hubs[0].node_id == "hub-1"

    def test_update_peer_last_seen(self, hub_manager):
        """Test updating peer last seen time"""
        peer_info = PeerInfo(
            node_id="peer-1", address="192.168.1.1", port=7071, island_id="test-island-id", is_hub=False, last_seen=100.0
        )
        hub_manager.register_peer(peer_info)

        hub_manager.update_peer_last_seen("peer-1")

        assert hub_manager.peer_registry["peer-1"].last_seen > 100.0


if __name__ == "__main__":
    pytest.main([__file__])


class TestUnregisterPersisted:
    """#2760 — unregister must consult the persisted hub:<node_id> row; a fresh
    CLI process always has is_hub=False even when the row exists."""

    @pytest.fixture
    def hub_manager(self):
        return HubManager(
            local_node_id="test-node-id",
            local_address="127.0.0.1",
            local_port=7070,
            island_id="test-island-id",
            island_name="test-island",
            redis_url="redis://localhost:6379",
        )

    @pytest.mark.asyncio
    async def test_unregister_removes_persisted_registration(self, hub_manager, monkeypatch):
        persisted = HubInfo(
            node_id="test-node-id",
            address="127.0.0.1",
            port=7070,
            island_id="test-island-id",
            island_name="test-island",
            public_address="1.2.3.4",
            public_port=26656,
        )
        removed: list[str] = []

        async def fake_load():
            return persisted

        async def fake_remove(node_id):
            removed.append(node_id)
            return True

        monkeypatch.setattr(hub_manager, "_load_hub_registration", fake_load)
        monkeypatch.setattr(hub_manager, "_remove_hub_registration", fake_remove)

        assert hub_manager.is_hub is False
        assert await hub_manager.unregister_as_hub() is True
        assert removed == ["test-node-id"]
        assert hub_manager.is_hub is False
        assert hub_manager.hub_status.value == "unregistered"
        assert "test-node-id" not in hub_manager.known_hubs

    @pytest.mark.asyncio
    async def test_unregister_without_any_registration_still_refuses(self, hub_manager, monkeypatch):
        async def fake_load():
            return None

        async def fake_remove(node_id):  # pragma: no cover - must not run
            raise AssertionError("remove called with nothing persisted")

        monkeypatch.setattr(hub_manager, "_load_hub_registration", fake_load)
        monkeypatch.setattr(hub_manager, "_remove_hub_registration", fake_remove)

        assert await hub_manager.unregister_as_hub() is False

    @pytest.mark.asyncio
    async def test_unregister_in_memory_registration_skips_load(self, hub_manager, monkeypatch):
        hub_manager.is_hub = True
        hub_manager.hub_status = HubStatus.REGISTERED
        removed: list[str] = []

        async def fake_load():  # pragma: no cover - must not run
            raise AssertionError("persisted load ran for in-memory registration")

        async def fake_remove(node_id):
            removed.append(node_id)
            return True

        monkeypatch.setattr(hub_manager, "_load_hub_registration", fake_load)
        monkeypatch.setattr(hub_manager, "_remove_hub_registration", fake_remove)

        assert await hub_manager.unregister_as_hub() is True
        assert removed == ["test-node-id"]
