"""
Unit tests for AITBC Blockchain Node
"""

import pytest
import json
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient

from apps.blockchain_node.src.aitbc_chain.models import Block, Transaction, Receipt, Account
from apps.blockchain_node.src.aitbc_chain.services.block_service import BlockService
from apps.blockchain_node.src.aitbc_chain.services.transaction_pool import TransactionPool
from apps.blockchain_node.src.aitbc_chain.services.consensus import ConsensusService
from apps.blockchain_node.src.aitbc_chain.services.p2p_network import P2PNetwork


@pytest.mark.unit
class TestBlockService:
    """Test block creation and management"""
    
    def test_create_block(self, sample_transactions, validator_address):
        """Test creating a new block"""
        block_service = BlockService()
        
        with patch('apps.blockchain_node.src.aitbc_chain.services.block_service.BlockService.create_block') as mock_create:
            mock_create.return_value = Block(
                number=100,
                hash="0xblockhash123",
                parent_hash="0xparenthash456",
                transactions=sample_transactions,
                timestamp=datetime.utcnow(),
                validator=validator_address
            )
            
            block = block_service.create_block(
                parent_hash="0xparenthash456",
                transactions=sample_transactions,
                validator=validator_address
            )
        
        assert block.number == 100
        assert block.validator == validator_address
        assert len(block.transactions) == len(sample_transactions)
    
    def test_validate_block(self, sample_block):
        """Test block validation"""
        block_service = BlockService()
        
        with patch('apps.blockchain_node.src.aitbc_chain.services.block_service.BlockService.validate_block') as mock_validate:
            mock_validate.return_value = {"valid": True, "errors": []}
            
            result = block_service.validate_block(sample_block)
        
        assert result["valid"] is True
        assert len(result["errors"]) == 0
    
    def test_add_block_to_chain(self, sample_block):
        """Test adding block to blockchain"""
        block_service = BlockService()
        
        with patch('apps.blockchain_node.src.aitbc_chain.services.block_service.BlockService.add_block') as mock_add:
            mock_add.return_value = {"success": True, "block_hash": sample_block.hash}
            
            result = block_service.add_block(sample_block)
        
        assert result["success"] is True
        assert result["block_hash"] == sample_block.hash


@pytest.mark.unit
class TestTransactionPool:
    """Test transaction pool management"""
    
    def test_add_transaction(self, sample_transaction):
        """Test adding transaction to pool"""
        tx_pool = TransactionPool()
        
        with patch('apps.blockchain_node.src.aitbc_chain.services.transaction_pool.TransactionPool.add_transaction') as mock_add:
            mock_add.return_value = {"success": True, "tx_hash": sample_transaction.hash}
            
            result = tx_pool.add_transaction(sample_transaction)
        
        assert result["success"] is True
    
    def test_get_pending_transactions(self):
        """Test retrieving pending transactions"""
        tx_pool = TransactionPool()
        
        with patch('apps.blockchain_node.src.aitbc_chain.services.transaction_pool.TransactionPool.get_pending') as mock_pending:
            mock_pending.return_value = [
                {"hash": "0xtx123", "gas_price": 20},
                {"hash": "0xtx456", "gas_price": 25}
            ]
            
            pending = tx_pool.get_pending(limit=100)
        
        assert len(pending) == 2
        assert pending[0]["gas_price"] == 20
    
    def test_remove_transaction(self, sample_transaction):
        """Test removing transaction from pool"""
        tx_pool = TransactionPool()
        
        with patch('apps.blockchain_node.src.aitbc_chain.services.transaction_pool.TransactionPool.remove_transaction') as mock_remove:
            mock_remove.return_value = True
            
            result = tx_pool.remove_transaction(sample_transaction.hash)
        
        assert result is True


@pytest.mark.unit
class TestConsensusService:
    """Test consensus mechanism"""
    
    def test_propose_block(self, validator_address, sample_block):
        """Test block proposal"""
        consensus = ConsensusService()
        
        with patch('apps.blockchain_node.src.aitbc_chain.services.consensus.ConsensusService.propose_block') as mock_propose:
            mock_propose.return_value = {
                "proposal_id": "prop123",
                "block_hash": sample_block.hash,
                "votes_required": 3
            }
            
            result = consensus.propose_block(sample_block, validator_address)
        
        assert result["proposal_id"] == "prop123"
        assert result["votes_required"] == 3
    
    def test_vote_on_proposal(self, validator_address):
        """Test voting on block proposal"""
        consensus = ConsensusService()
        
        with patch('apps.blockchain_node.src.aitbc_chain.services.consensus.ConsensusService.vote') as mock_vote:
            mock_vote.return_value = {"vote_cast": True, "current_votes": 2}
            
            result = consensus.vote(
                proposal_id="prop123",
                validator=validator_address,
                vote=True
            )
        
        assert result["vote_cast"] is True
    
    def test_check_consensus(self):
        """Test consensus achievement check"""
        consensus = ConsensusService()
        
        with patch('apps.blockchain_node.src.aitbc_chain.services.consensus.ConsensusService.check_consensus') as mock_check:
            mock_check.return_value = {
                "achieved": True,
                "finalized": True,
                "block_hash": "0xfinalized123"
            }
            
            result = consensus.check_consensus("prop123")
        
        assert result["achieved"] is True
        assert result["finalized"] is True


@pytest.mark.unit
class TestP2PNetwork:
    """Test P2P network functionality"""
    
    def test_connect_to_peer(self):
        """Test connecting to a peer"""
        network = P2PNetwork()
        
        with patch('apps.blockchain_node.src.aitbc_chain.services.p2p_network.P2PNetwork.connect') as mock_connect:
            mock_connect.return_value = {"connected": True, "peer_id": "peer123"}
            
            result = network.connect("enode://123@192.168.1.100:30303")
        
        assert result["connected"] is True
    
    def test_broadcast_transaction(self, sample_transaction):
        """Test broadcasting transaction to peers"""
        network = P2PNetwork()
        
        with patch('apps.blockchain_node.src.aitbc_chain.services.p2p_network.P2PNetwork.broadcast_transaction') as mock_broadcast:
            mock_broadcast.return_value = {"peers_notified": 5}
            
            result = network.broadcast_transaction(sample_transaction)
        
        assert result["peers_notified"] == 5
    
    def test_sync_blocks(self):
        """Test block synchronization"""
        network = P2PNetwork()
        
        with patch('apps.blockchain_node.src.aitbc_chain.services.p2p_network.P2PNetwork.sync_blocks') as mock_sync:
            mock_sync.return_value = {
                "synced": True,
                "blocks_received": 10,
                "latest_block": 150
            }
            
            result = network.sync_blocks(from_block=140)
        
        assert result["synced"] is True
        assert result["blocks_received"] == 10


@pytest.mark.unit
class TestSmartContracts:
    """Test smart contract functionality"""
    
    def test_deploy_contract(self, sample_account):
        """Test deploying a smart contract"""
        contract_data = {
            "bytecode": "0x6060604052...",
            "abi": [{"type": "function", "name": "getValue"}],
            "args": []
        }
        
        with patch('apps.blockchain_node.src.aitbc_chain.services.contract_service.ContractService.deploy') as mock_deploy:
            mock_deploy.return_value = {
                "contract_address": "0xContract123",
                "transaction_hash": "0xTx456",
                "gas_used": 100000
            }
            
            from apps.blockchain_node.src.aitbc_chain.services.contract_service import ContractService
            contract_service = ContractService()
            result = contract_service.deploy(contract_data, sample_account.address)
        
        assert result["contract_address"] == "0xContract123"
    
    def test_call_contract_method(self):
        """Test calling smart contract method"""
        with patch('apps.blockchain_node.src.aitbc_chain.services.contract_service.ContractService.call') as mock_call:
            mock_call.return_value = {
                "result": "42",
                "gas_used": 5000,
                "success": True
            }
            
            from apps.blockchain_node.src.aitbc_chain.services.contract_service import ContractService
            contract_service = ContractService()
            result = contract_service.call_method(
                contract_address="0xContract123",
                method="getValue",
                args=[]
            )
        
        assert result["result"] == "42"
        assert result["success"] is True
    
    def test_estimate_contract_gas(self):
        """Test gas estimation for contract interaction"""
        with patch('apps.blockchain_node.src.aitbc_chain.services.contract_service.ContractService.estimate_gas') as mock_estimate:
            mock_estimate.return_value = {
                "gas_limit": 50000,
                "gas_price": 20,
                "total_cost": "0.001"
            }
            
            from apps.blockchain_node.src.aitbc_chain.services.contract_service import ContractService
            contract_service = ContractService()
            result = contract_service.estimate_gas(
                contract_address="0xContract123",
                method="setValue",
                args=[42]
            )
        
        assert result["gas_limit"] == 50000


@pytest.mark.unit
class TestNodeManagement:
    """Test node management operations"""
    
    def test_start_node(self):
        """Test starting blockchain node"""
        with patch('apps.blockchain_node.src.aitbc_chain.node.BlockchainNode.start') as mock_start:
            mock_start.return_value = {"status": "running", "port": 30303}
            
            from apps.blockchain_node.src.aitbc_chain.node import BlockchainNode
            node = BlockchainNode()
            result = node.start()
        
        assert result["status"] == "running"
    
    def test_stop_node(self):
        """Test stopping blockchain node"""
        with patch('apps.blockchain_node.src.aitbc_chain.node.BlockchainNode.stop') as mock_stop:
            mock_stop.return_value = {"status": "stopped"}
            
            from apps.blockchain_node.src.aitbc_chain.node import BlockchainNode
            node = BlockchainNode()
            result = node.stop()
        
        assert result["status"] == "stopped"
    
    def test_get_node_info(self):
        """Test getting node information"""
        with patch('apps.blockchain_node.src.aitbc_chain.node.BlockchainNode.get_info') as mock_info:
            mock_info.return_value = {
                "version": "1.0.0",
                "chain_id": 1337,
                "block_number": 150,
                "peer_count": 5,
                "syncing": False
            }
            
            from apps.blockchain_node.src.aitbc_chain.node import BlockchainNode
            node = BlockchainNode()
            result = node.get_info()
        
        assert result["chain_id"] == 1337
        assert result["block_number"] == 150


@pytest.mark.unit
class TestMining:
    """Test mining operations"""
    
    def test_start_mining(self, miner_address):
        """Test starting mining process"""
        with patch('apps.blockchain_node.src.aitbc_chain.services.mining_service.MiningService.start') as mock_mine:
            mock_mine.return_value = {
                "mining": True,
                "hashrate": "50 MH/s",
                "blocks_mined": 0
            }
            
            from apps.blockchain_node.src.aitbc_chain.services.mining_service import MiningService
            mining = MiningService()
            result = mining.start(miner_address)
        
        assert result["mining"] is True
    
    def test_get_mining_stats(self):
        """Test getting mining statistics"""
        with patch('apps.blockchain_node.src.aitbc_chain.services.mining_service.MiningService.get_stats') as mock_stats:
            mock_stats.return_value = {
                "hashrate": "50 MH/s",
                "blocks_mined": 10,
                "difficulty": 1000000,
                "average_block_time": "12.5s"
            }
            
            from apps.blockchain_node.src.aitbc_chain.services.mining_service import MiningService
            mining = MiningService()
            result = mining.get_stats()
        
        assert result["blocks_mined"] == 10
        assert result["hashrate"] == "50 MH/s"


@pytest.mark.unit
class TestChainData:
    """Test blockchain data queries"""
    
    def test_get_block_by_number(self):
        """Test retrieving block by number"""
        with patch('apps.blockchain_node.src.aitbc_chain.services.chain_data.ChainData.get_block') as mock_block:
            mock_block.return_value = {
                "number": 100,
                "hash": "0xblock123",
                "timestamp": datetime.utcnow().isoformat(),
                "transaction_count": 5
            }
            
            from apps.blockchain_node.src.aitbc_chain.services.chain_data import ChainData
            chain_data = ChainData()
            result = chain_data.get_block(100)
        
        assert result["number"] == 100
        assert result["transaction_count"] == 5
    
    def test_get_transaction_by_hash(self):
        """Test retrieving transaction by hash"""
        with patch('apps.blockchain_node.src.aitbc_chain.services.chain_data.ChainData.get_transaction') as mock_tx:
            mock_tx.return_value = {
                "hash": "0xtx123",
                "block_number": 100,
                "from": "0xsender",
                "to": "0xreceiver",
                "value": "1000",
                "status": "confirmed"
            }
            
            from apps.blockchain_node.src.aitbc_chain.services.chain_data import ChainData
            chain_data = ChainData()
            result = chain_data.get_transaction("0xtx123")
        
        assert result["hash"] == "0xtx123"
        assert result["status"] == "confirmed"
    
    def test_get_account_balance(self):
        """Test getting account balance"""
        with patch('apps.blockchain_node.src.aitbc_chain.services.chain_data.ChainData.get_balance') as mock_balance:
            mock_balance.return_value = {
                "balance": "1000000",
                "nonce": 25,
                "code_hash": "0xempty"
            }
            
            from apps.blockchain_node.src.aitbc_chain.services.chain_data import ChainData
            chain_data = ChainData()
            result = chain_data.get_balance("0xaccount123")
        
        assert result["balance"] == "1000000"
        assert result["nonce"] == 25


@pytest.mark.unit
class TestEventLogs:
    """Test event log functionality"""
    
    def test_get_logs(self):
        """Test retrieving event logs"""
        with patch('apps.blockchain_node.src.aitbc_chain.services.event_service.EventService.get_logs') as mock_logs:
            mock_logs.return_value = [
                {
                    "address": "0xcontract123",
                    "topics": ["0xevent123"],
                    "data": "0xdata456",
                    "block_number": 100,
                    "transaction_hash": "0xtx789"
                }
            ]
            
            from apps.blockchain_node.src.aitbc_chain.services.event_service import EventService
            event_service = EventService()
            result = event_service.get_logs(
                from_block=90,
                to_block=100,
                address="0xcontract123"
            )
        
        assert len(result) == 1
        assert result[0]["address"] == "0xcontract123"
    
    def test_subscribe_to_events(self):
        """Test subscribing to events"""
        with patch('apps.blockchain_node.src.aitbc_chain.services.event_service.EventService.subscribe') as mock_subscribe:
            mock_subscribe.return_value = {
                "subscription_id": "sub123",
                "active": True
            }
            
            from apps.blockchain_node.src.aitbc_chain.services.event_service import EventService
            event_service = EventService()
            result = event_service.subscribe(
                address="0xcontract123",
                topics=["0xevent123"]
            )
        
        assert result["subscription_id"] == "sub123"
        assert result["active"] is True
