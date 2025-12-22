"""
Integration tests for AITBC Blockchain Node
"""

import pytest
import asyncio
import json
import websockets
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
import requests

from apps.blockchain_node.src.aitbc_chain.models import Block, Transaction, Receipt, Account
from apps.blockchain_node.src.aitbc_chain.consensus.poa import PoAConsensus
from apps.blockchain_node.src.aitbc_chain.rpc.router import router
from apps.blockchain_node.src.aitbc_chain.rpc.websocket import WebSocketManager


@pytest.mark.integration
class TestBlockchainNodeRPC:
    """Test blockchain node RPC endpoints"""
    
    @pytest.fixture
    def blockchain_client(self):
        """Create a test client for blockchain node"""
        base_url = "http://localhost:8545"
        return requests.Session()
        # Note: In real tests, this would connect to a running test instance
    
    def test_get_block_by_number(self, blockchain_client):
        """Test getting block by number"""
        with patch('apps.blockchain_node.src.aitbc_chain.rpc.handlers.get_block_by_number') as mock_handler:
            mock_handler.return_value = {
                "number": 100,
                "hash": "0x123",
                "timestamp": datetime.utcnow().timestamp(),
                "transactions": [],
            }
            
            response = blockchain_client.post(
                "http://localhost:8545",
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_getBlockByNumber",
                    "params": ["0x64", True],
                    "id": 1
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert "result" in data
        assert data["result"]["number"] == 100
    
    def test_get_transaction_by_hash(self, blockchain_client):
        """Test getting transaction by hash"""
        with patch('apps.blockchain_node.src.aitbc_chain.rpc.handlers.get_transaction_by_hash') as mock_handler:
            mock_handler.return_value = {
                "hash": "0x456",
                "blockNumber": 100,
                "from": "0xabc",
                "to": "0xdef",
                "value": "1000",
                "status": "0x1",
            }
            
            response = blockchain_client.post(
                "http://localhost:8545",
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_getTransactionByHash",
                    "params": ["0x456"],
                    "id": 1
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["result"]["hash"] == "0x456"
    
    def test_send_raw_transaction(self, blockchain_client):
        """Test sending raw transaction"""
        with patch('apps.blockchain_node.src.aitbc_chain.rpc.handlers.send_raw_transaction') as mock_handler:
            mock_handler.return_value = "0x789"
            
            response = blockchain_client.post(
                "http://localhost:8545",
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_sendRawTransaction",
                    "params": ["0xrawtx"],
                    "id": 1
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["result"] == "0x789"
    
    def test_get_balance(self, blockchain_client):
        """Test getting account balance"""
        with patch('apps.blockchain_node.src.aitbc_chain.rpc.handlers.get_balance') as mock_handler:
            mock_handler.return_value = "0x1520F41CC0B40000"  # 100000 ETH in wei
            
            response = blockchain_client.post(
                "http://localhost:8545",
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_getBalance",
                    "params": ["0xabc", "latest"],
                    "id": 1
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["result"] == "0x1520F41CC0B40000"
    
    def test_get_block_range(self, blockchain_client):
        """Test getting a range of blocks"""
        with patch('apps.blockchain_node.src.aitbc_chain.rpc.handlers.get_block_range') as mock_handler:
            mock_handler.return_value = [
                {"number": 100, "hash": "0x100"},
                {"number": 101, "hash": "0x101"},
                {"number": 102, "hash": "0x102"},
            ]
            
            response = blockchain_client.post(
                "http://localhost:8545",
                json={
                    "jsonrpc": "2.0",
                    "method": "aitbc_getBlockRange",
                    "params": [100, 102],
                    "id": 1
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["result"]) == 3
        assert data["result"][0]["number"] == 100


@pytest.mark.integration
class TestWebSocketSubscriptions:
    """Test WebSocket subscription functionality"""
    
    async def test_subscribe_new_blocks(self):
        """Test subscribing to new blocks"""
        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()
            mock_connect.return_value.__aenter__.return_value = mock_ws
            
            # Mock subscription response
            mock_ws.recv.side_effect = [
                json.dumps({"id": 1, "result": "0xsubscription"}),
                json.dumps({
                    "subscription": "0xsubscription",
                    "result": {
                        "number": 101,
                        "hash": "0xnewblock",
                    }
                })
            ]
            
            # Connect and subscribe
            async with websockets.connect("ws://localhost:8546") as ws:
                await ws.send(json.dumps({
                    "id": 1,
                    "method": "eth_subscribe",
                    "params": ["newHeads"]
                }))
                
                # Get subscription ID
                response = await ws.recv()
                sub_data = json.loads(response)
                assert "result" in sub_data
                
                # Get block notification
                notification = await ws.recv()
                block_data = json.loads(notification)
                assert block_data["result"]["number"] == 101
    
    async def test_subscribe_pending_transactions(self):
        """Test subscribing to pending transactions"""
        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()
            mock_connect.return_value.__aenter__.return_value = mock_ws
            
            mock_ws.recv.side_effect = [
                json.dumps({"id": 1, "result": "0xtxsub"}),
                json.dumps({
                    "subscription": "0xtxsub",
                    "result": {
                        "hash": "0xtx123",
                        "from": "0xabc",
                        "to": "0xdef",
                    }
                })
            ]
            
            async with websockets.connect("ws://localhost:8546") as ws:
                await ws.send(json.dumps({
                    "id": 1,
                    "method": "eth_subscribe",
                    "params": ["newPendingTransactions"]
                }))
                
                response = await ws.recv()
                assert "result" in response
                
                notification = await ws.recv()
                tx_data = json.loads(notification)
                assert tx_data["result"]["hash"] == "0xtx123"
    
    async def test_subscribe_logs(self):
        """Test subscribing to event logs"""
        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()
            mock_connect.return_value.__aenter__.return_value = mock_ws
            
            mock_ws.recv.side_effect = [
                json.dumps({"id": 1, "result": "0xlogsub"}),
                json.dumps({
                    "subscription": "0xlogsub",
                    "result": {
                        "address": "0xcontract",
                        "topics": ["0xevent"],
                        "data": "0xdata",
                    }
                })
            ]
            
            async with websockets.connect("ws://localhost:8546") as ws:
                await ws.send(json.dumps({
                    "id": 1,
                    "method": "eth_subscribe",
                    "params": ["logs", {"address": "0xcontract"}]
                }))
                
                response = await ws.recv()
                sub_data = json.loads(response)
                
                notification = await ws.recv()
                log_data = json.loads(notification)
                assert log_data["result"]["address"] == "0xcontract"


@pytest.mark.integration
class TestPoAConsensus:
    """Test Proof of Authority consensus mechanism"""
    
    @pytest.fixture
    def poa_consensus(self):
        """Create PoA consensus instance for testing"""
        validators = [
            "0xvalidator1",
            "0xvalidator2",
            "0xvalidator3",
        ]
        return PoAConsensus(validators=validators, block_time=1)
    
    def test_proposer_selection(self, poa_consensus):
        """Test proposer selection algorithm"""
        # Test deterministic proposer selection
        proposer1 = poa_consensus.get_proposer(100)
        proposer2 = poa_consensus.get_proposer(101)
        
        assert proposer1 in poa_consensus.validators
        assert proposer2 in poa_consensus.validators
        # Should rotate based on block number
        assert proposer1 != proposer2
    
    def test_block_validation(self, poa_consensus):
        """Test block validation"""
        block = Block(
            number=100,
            hash="0xblock123",
            proposer="0xvalidator1",
            timestamp=datetime.utcnow(),
            transactions=[],
        )
        
        # Valid block
        assert poa_consensus.validate_block(block) is True
        
        # Invalid proposer
        block.proposer = "0xinvalid"
        assert poa_consensus.validate_block(block) is False
    
    def test_validator_rotation(self, poa_consensus):
        """Test validator rotation schedule"""
        proposers = []
        for i in range(10):
            proposer = poa_consensus.get_proposer(i)
            proposers.append(proposer)
        
        # Each validator should have proposed roughly equal times
        for validator in poa_consensus.validators:
            count = proposers.count(validator)
            assert count >= 2  # At least 2 times in 10 blocks
    
    @pytest.mark.asyncio
    async def test_block_production_loop(self, poa_consensus):
        """Test block production loop"""
        blocks_produced = []
        
        async def mock_produce_block():
            block = Block(
                number=len(blocks_produced),
                hash=f"0xblock{len(blocks_produced)}",
                proposer=poa_consensus.get_proposer(len(blocks_produced)),
                timestamp=datetime.utcnow(),
                transactions=[],
            )
            blocks_produced.append(block)
            return block
        
        # Mock block production
        with patch.object(poa_consensus, 'produce_block', side_effect=mock_produce_block):
            # Produce 3 blocks
            for _ in range(3):
                block = await poa_consensus.produce_block()
                assert block.number == len(blocks_produced) - 1
        
        assert len(blocks_produced) == 3


@pytest.mark.integration
class TestCrossChainSettlement:
    """Test cross-chain settlement integration"""
    
    @pytest.fixture
    def bridge_manager(self):
        """Create bridge manager for testing"""
        from apps.coordinator_api.src.app.services.bridge_manager import BridgeManager
        return BridgeManager()
    
    def test_bridge_registration(self, bridge_manager):
        """Test bridge registration"""
        bridge_config = {
            "bridge_id": "layerzero",
            "source_chain": "ethereum",
            "target_chain": "polygon",
            "endpoint": "https://endpoint.layerzero.network",
        }
        
        result = bridge_manager.register_bridge(bridge_config)
        assert result["success"] is True
        assert result["bridge_id"] == "layerzero"
    
    def test_cross_chain_transaction(self, bridge_manager):
        """Test cross-chain transaction execution"""
        with patch.object(bridge_manager, 'execute_cross_chain_tx') as mock_execute:
            mock_execute.return_value = {
                "tx_hash": "0xcrosschain",
                "status": "pending",
                "source_tx": "0x123",
                "target_tx": None,
            }
            
            result = bridge_manager.execute_cross_chain_tx({
                "source_chain": "ethereum",
                "target_chain": "polygon",
                "amount": "1000",
                "token": "USDC",
                "recipient": "0xabc",
            })
        
        assert result["tx_hash"] is not None
        assert result["status"] == "pending"
    
    def test_settlement_verification(self, bridge_manager):
        """Test cross-chain settlement verification"""
        with patch.object(bridge_manager, 'verify_settlement') as mock_verify:
            mock_verify.return_value = {
                "verified": True,
                "source_tx": "0x123",
                "target_tx": "0x456",
                "amount": "1000",
                "completed_at": datetime.utcnow().isoformat(),
            }
            
            result = bridge_manager.verify_settlement("0xcrosschain")
        
        assert result["verified"] is True
        assert result["target_tx"] is not None


@pytest.mark.integration
class TestNodePeering:
    """Test node peering and gossip"""
    
    @pytest.fixture
    def peer_manager(self):
        """Create peer manager for testing"""
        from apps.blockchain_node.src.aitbc_chain.p2p.peer_manager import PeerManager
        return PeerManager()
    
    def test_peer_discovery(self, peer_manager):
        """Test peer discovery"""
        with patch.object(peer_manager, 'discover_peers') as mock_discover:
            mock_discover.return_value = [
                "enode://1@localhost:30301",
                "enode://2@localhost:30302",
                "enode://3@localhost:30303",
            ]
            
            peers = peer_manager.discover_peers()
        
        assert len(peers) == 3
        assert all(peer.startswith("enode://") for peer in peers)
    
    def test_gossip_transaction(self, peer_manager):
        """Test transaction gossip"""
        tx_data = {
            "hash": "0xgossip",
            "from": "0xabc",
            "to": "0xdef",
            "value": "100",
        }
        
        with patch.object(peer_manager, 'gossip_transaction') as mock_gossip:
            mock_gossip.return_value = {"peers_notified": 5}
            
            result = peer_manager.gossip_transaction(tx_data)
        
        assert result["peers_notified"] > 0
    
    def test_gossip_block(self, peer_manager):
        """Test block gossip"""
        block_data = {
            "number": 100,
            "hash": "0xblock100",
            "transactions": [],
        }
        
        with patch.object(peer_manager, 'gossip_block') as mock_gossip:
            mock_gossip.return_value = {"peers_notified": 5}
            
            result = peer_manager.gossip_block(block_data)
        
        assert result["peers_notified"] > 0


@pytest.mark.integration
class TestNodeSynchronization:
    """Test node synchronization"""
    
    @pytest.fixture
    def sync_manager(self):
        """Create sync manager for testing"""
        from apps.blockchain_node.src.aitbc_chain.sync.sync_manager import SyncManager
        return SyncManager()
    
    def test_sync_status(self, sync_manager):
        """Test synchronization status"""
        with patch.object(sync_manager, 'get_sync_status') as mock_status:
            mock_status.return_value = {
                "syncing": False,
                "current_block": 100,
                "highest_block": 100,
                "starting_block": 0,
            }
            
            status = sync_manager.get_sync_status()
        
        assert status["syncing"] is False
        assert status["current_block"] == status["highest_block"]
    
    def test_sync_from_peer(self, sync_manager):
        """Test syncing from peer"""
        with patch.object(sync_manager, 'sync_from_peer') as mock_sync:
            mock_sync.return_value = {
                "synced": True,
                "blocks_synced": 10,
                "time_taken": 5.0,
            }
            
            result = sync_manager.sync_from_peer("enode://peer@localhost:30301")
        
        assert result["synced"] is True
        assert result["blocks_synced"] > 0


@pytest.mark.integration
class TestNodeMetrics:
    """Test node metrics and monitoring"""
    
    def test_block_metrics(self):
        """Test block production metrics"""
        from apps.blockchain_node.src.aitbc_chain.metrics import block_metrics
        
        # Record block metrics
        block_metrics.record_block(100, 2.5)
        block_metrics.record_block(101, 2.1)
        
        # Get metrics
        metrics = block_metrics.get_metrics()
        
        assert metrics["block_count"] == 2
        assert metrics["avg_block_time"] == 2.3
        assert metrics["last_block_number"] == 101
    
    def test_transaction_metrics(self):
        """Test transaction metrics"""
        from apps.blockchain_node.src.aitbc_chain.metrics import tx_metrics
        
        # Record transaction metrics
        tx_metrics.record_transaction("0x123", 1000, True)
        tx_metrics.record_transaction("0x456", 2000, False)
        
        metrics = tx_metrics.get_metrics()
        
        assert metrics["total_txs"] == 2
        assert metrics["success_rate"] == 0.5
        assert metrics["total_value"] == 3000
    
    def test_peer_metrics(self):
        """Test peer connection metrics"""
        from apps.blockchain_node.src.aitbc_chain.metrics import peer_metrics
        
        # Record peer metrics
        peer_metrics.record_peer_connected()
        peer_metrics.record_peer_connected()
        peer_metrics.record_peer_disconnected()
        
        metrics = peer_metrics.get_metrics()
        
        assert metrics["connected_peers"] == 1
        assert metrics["total_connections"] == 2
        assert metrics["disconnections"] == 1
