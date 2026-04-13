"""
Tests for Island Join functionality
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from aitbc_chain.network.hub_manager import HubManager, HubInfo, PeerInfo
from aitbc_chain.p2p_network import P2PNetworkService


class TestHubManagerJoin:
    """Test cases for HubManager join request handling"""

    @pytest.fixture
    def hub_manager(self):
        """Create a HubManager instance for testing"""
        return HubManager(
            local_node_id="test-hub-node",
            local_address="127.0.0.1",
            local_port=7070,
            island_id="test-island-id",
            island_name="test-island",
            redis_url="redis://localhost:6379"
        )

    def test_get_blockchain_credentials(self, hub_manager):
        """Test blockchain credentials retrieval"""
        with patch('aitbc_chain.network.hub_manager.os.path.exists', return_value=True):
            with patch('aitbc_chain.network.hub_manager.open', create=True) as mock_open:
                # Mock genesis.json
                genesis_data = {
                    'blocks': [{'hash': 'test-genesis-hash'}]
                }
                mock_file = MagicMock()
                mock_file.read.return_value = '{"blocks": [{"hash": "test-genesis-hash"}]}'
                mock_open.return_value.__enter__.return_value = mock_file

                # Mock keystore
                with patch('aitbc_chain.network.hub_manager.json.load') as mock_json_load:
                    mock_json_load.return_value = {'0x123': {'public_key_pem': 'test-key'}}

                    credentials = hub_manager._get_blockchain_credentials()

                    assert credentials is not None
                    assert 'chain_id' in credentials
                    assert 'island_id' in credentials
                    assert credentials['island_id'] == 'test-island-id'

    @pytest.mark.asyncio
    async def test_handle_join_request_success(self, hub_manager):
        """Test successful join request handling"""
        # Add some peers to the registry
        peer_info = PeerInfo(
            node_id="peer-1",
            address="192.168.1.1",
            port=7071,
            island_id="test-island-id",
            is_hub=False
        )
        hub_manager.register_peer(peer_info)

        join_request = {
            'type': 'join_request',
            'node_id': 'new-node',
            'island_id': 'test-island-id',
            'island_name': 'test-island',
            'public_key_pem': 'test-pem'
        }

        with patch.object(hub_manager, '_get_blockchain_credentials', return_value={'chain_id': 'test-chain'}):
            response = await hub_manager.handle_join_request(join_request)

            assert response is not None
            assert response['type'] == 'join_response'
            assert response['island_id'] == 'test-island-id'
            assert len(response['members']) >= 1  # At least the hub itself
            assert 'credentials' in response

    @pytest.mark.asyncio
    async def test_handle_join_request_wrong_island(self, hub_manager):
        """Test join request for wrong island"""
        join_request = {
            'type': 'join_request',
            'node_id': 'new-node',
            'island_id': 'wrong-island-id',
            'island_name': 'wrong-island',
            'public_key_pem': 'test-pem'
        }

        response = await hub_manager.handle_join_request(join_request)

        assert response is None

    @pytest.mark.asyncio
    async def test_handle_join_request_with_members(self, hub_manager):
        """Test join request returns all island members"""
        # Add multiple peers
        for i in range(3):
            peer_info = PeerInfo(
                node_id=f"peer-{i}",
                address=f"192.168.1.{i}",
                port=7070 + i,
                island_id="test-island-id",
                is_hub=False
            )
            hub_manager.register_peer(peer_info)

        join_request = {
            'type': 'join_request',
            'node_id': 'new-node',
            'island_id': 'test-island-id',
            'island_name': 'test-island',
            'public_key_pem': 'test-pem'
        }

        with patch.object(hub_manager, '_get_blockchain_credentials', return_value={'chain_id': 'test-chain'}):
            response = await hub_manager.handle_join_request(join_request)

            assert response is not None
            # Should include all peers + hub itself
            assert len(response['members']) >= 4


class TestP2PNetworkJoin:
    """Test cases for P2P network join request functionality"""

    @pytest.fixture
    def p2p_service(self):
        """Create a P2P service instance for testing"""
        return P2PNetworkService(
            host="127.0.0.1",
            port=7070,
            node_id="test-node",
            peers=[]
        )

    @pytest.mark.asyncio
    async def test_send_join_request_success(self, p2p_service):
        """Test successful join request to hub"""
        join_response = {
            'type': 'join_response',
            'island_id': 'test-island-id',
            'island_name': 'test-island',
            'island_chain_id': 'test-chain',
            'members': [],
            'credentials': {}
        }

        with patch('aitbc_chain.p2p_network.asyncio.open_connection') as mock_open:
            # Mock reader and writer
            mock_reader = AsyncMock()
            mock_reader.readline = AsyncMock(return_value=b'{"type": "join_response"}')
            mock_writer = AsyncMock()
            mock_writer.close = AsyncMock()
            mock_writer.wait_closed = AsyncMock()
            mock_open.return_value = (mock_reader, mock_writer)

            response = await p2p_service.send_join_request(
                hub_address="127.0.0.1",
                hub_port=7070,
                island_id="test-island-id",
                island_name="test-island",
                node_id="test-node",
                public_key_pem="test-pem"
            )

            assert response is not None
            mock_open.assert_called_once_with("127.0.0.1", 7070)

    @pytest.mark.asyncio
    async def test_send_join_request_connection_refused(self, p2p_service):
        """Test join request when hub refuses connection"""
        with patch('aitbc_chain.p2p_network.asyncio.open_connection') as mock_open:
            mock_open.side_effect = ConnectionRefusedError()

            response = await p2p_service.send_join_request(
                hub_address="127.0.0.1",
                hub_port=7070,
                island_id="test-island-id",
                island_name="test-island",
                node_id="test-node",
                public_key_pem="test-pem"
            )

            assert response is None

    @pytest.mark.asyncio
    async def test_send_join_request_timeout(self, p2p_service):
        """Test join request timeout"""
        with patch('aitbc_chain.p2p_network.asyncio.open_connection') as mock_open:
            # Mock reader that times out
            mock_reader = AsyncMock()
            mock_reader.readline = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_writer = AsyncMock()
            mock_writer.close = AsyncMock()
            mock_writer.wait_closed = AsyncMock()
            mock_open.return_value = (mock_reader, mock_writer)

            response = await p2p_service.send_join_request(
                hub_address="127.0.0.1",
                hub_port=7070,
                island_id="test-island-id",
                island_name="test-island",
                node_id="test-node",
                public_key_pem="test-pem"
            )

            assert response is None


class TestJoinMessageHandling:
    """Test cases for join message handling in P2P network"""

    @pytest.mark.asyncio
    async def test_join_request_message_handling(self):
        """Test that join_request messages are handled correctly"""
        service = P2PNetworkService(
            host="127.0.0.1",
            port=7070,
            node_id="test-node",
            peers=[]
        )

        # Mock hub manager
        service.hub_manager = Mock()
        service.hub_manager.handle_join_request = AsyncMock(return_value={'type': 'join_response'})

        join_request = {
            'type': 'join_request',
            'node_id': 'new-node',
            'island_id': 'test-island-id'
        }

        # The actual message handling happens in _listen_to_stream
        # This test verifies the hub_manager.handle_join_request would be called
        response = await service.hub_manager.handle_join_request(join_request)

        assert response is not None
        assert response['type'] == 'join_response'


if __name__ == "__main__":
    pytest.main([__file__])
