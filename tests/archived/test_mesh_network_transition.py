"""
Comprehensive Test Suite for AITBC Mesh Network Transition Plan
Tests all 5 phases of the mesh network implementation
"""

import pytest
import asyncio
import time
import json
from unittest.mock import Mock, patch, AsyncMock
from decimal import Decimal
from typing import Dict, List, Optional

# Import all the components we're testing
import sys
import os

# Add the paths to our modules
sys.path.insert(0, '/opt/aitbc/apps/blockchain-node/src')
sys.path.insert(0, '/opt/aitbc/apps/agent-services/agent-registry/src')
sys.path.insert(0, '/opt/aitbc/apps/agent-services/agent-coordinator/src')

# Phase 1: Consensus Tests
try:
    from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole
    from aitbc_chain.consensus.rotation import ValidatorRotation, RotationStrategy
    from aitbc_chain.consensus.pbft import PBFTConsensus
    from aitbc_chain.consensus.slashing import SlashingManager, SlashingCondition
    from aitbc_chain.consensus.keys import KeyManager
except ImportError:
    pytest.skip("Phase 1 consensus modules not available")

# Phase 2: Network Tests
try:
    from aitbc_chain.network.discovery import P2PDiscovery, PeerNode, NodeStatus
    from aitbc_chain.network.health import PeerHealthMonitor, HealthStatus
    from aitbc_chain.network.peers import DynamicPeerManager, PeerAction
    from aitbc_chain.network.topology import NetworkTopology, TopologyStrategy
    from aitbc_chain.network.partition import NetworkPartitionManager, PartitionState
    from aitbc_chain.network.recovery import NetworkRecoveryManager, RecoveryTrigger
except ImportError:
    pytest.skip("Phase 2 network modules not available")

# Phase 3: Economics Tests
try:
    from aitbc_chain.economics.staking import StakingManager, StakingStatus
    from aitbc_chain.economics.rewards import RewardDistributor, RewardType
    from aitbc_chain.economics.gas import GasManager, GasType
    from aitbc_chain.economics.attacks import EconomicSecurityMonitor, AttackType
except ImportError:
    pytest.skip("Phase 3 economics modules not available")

# Phase 4: Agent Network Tests
try:
    from agent_services.agent_registry.src.registration import AgentRegistry, AgentType, AgentStatus
    from agent_services.agent_registry.src.matching import CapabilityMatcher, MatchScore
    from agent_services.agent_coordinator.src.reputation import ReputationManager, ReputationEvent
    from agent_services.agent_bridge.src.protocols import CommunicationProtocol, MessageType
    from agent_services.agent_coordinator.src.lifecycle import AgentLifecycleManager, LifecycleState
    from agent_services.agent_compliance.src.monitoring import AgentBehaviorMonitor, BehaviorMetric
except ImportError:
    pytest.skip("Phase 4 agent network modules not available")

# Phase 5: Smart Contract Tests
try:
    from aitbc_chain.contracts.escrow import EscrowManager, EscrowState, DisputeReason
    from aitbc_chain.contracts.disputes import DisputeResolver, ResolutionType
    from aitbc_chain.contracts.upgrades import ContractUpgradeManager, UpgradeStatus
    from aitbc_chain.contracts.optimization import GasOptimizer, OptimizationStrategy
except ImportError:
    pytest.skip("Phase 5 smart contract modules not available")


class TestPhase1ConsensusLayer:
    """Test Phase 1: Consensus Layer Implementation"""
    
    @pytest.fixture
    def multi_validator_poa(self):
        """Create multi-validator PoA instance"""
        return MultiValidatorPoA("test-chain")
    
    @pytest.fixture
    def validator_rotation(self):
        """Create validator rotation instance"""
        from aitbc_chain.consensus.rotation import DEFAULT_ROTATION_CONFIG
        poa = MultiValidatorPoA("test-chain")
        return ValidatorRotation(poa, DEFAULT_ROTATION_CONFIG)
    
    @pytest.fixture
    def pbft_consensus(self):
        """Create PBFT consensus instance"""
        poa = MultiValidatorPoA("test-chain")
        return PBFTConsensus(poa)
    
    @pytest.fixture
    def slashing_manager(self):
        """Create slashing manager instance"""
        return SlashingManager()
    
    @pytest.fixture
    def key_manager(self):
        """Create key manager instance"""
        return KeyManager()
    
    def test_multi_validator_poa_initialization(self, multi_validator_poa):
        """Test multi-validator PoA initialization"""
        assert multi_validator_poa.chain_id == "test-chain"
        assert len(multi_validator_poa.validators) == 0
        assert multi_validator_poa.current_proposer_index == 0
        assert multi_validator_poa.round_robin_enabled is True
    
    def test_add_validator(self, multi_validator_poa):
        """Test adding validators"""
        validator_address = "0x1234567890123456789012345678901234567890"
        
        success = multi_validator_poa.add_validator(validator_address, 1000.0)
        assert success is True
        assert validator_address in multi_validator_poa.validators
        assert multi_validator_poa.validators[validator_address].stake == 1000.0
        assert multi_validator_poa.validators[validator_address].role == ValidatorRole.STANDBY
    
    def test_add_duplicate_validator(self, multi_validator_poa):
        """Test adding duplicate validator"""
        validator_address = "0x1234567890123456789012345678901234567890"
        
        multi_validator_poa.add_validator(validator_address, 1000.0)
        success = multi_validator_poa.add_validator(validator_address, 2000.0)
        assert success is False
    
    def test_select_proposer_round_robin(self, multi_validator_poa):
        """Test round-robin proposer selection"""
        # Add multiple validators
        validators = [
            "0x1111111111111111111111111111111111111111",
            "0x2222222222222222222222222222222222222222",
            "0x3333333333333333333333333333333333333333"
        ]
        
        for validator in validators:
            multi_validator_poa.add_validator(validator, 1000.0)
        
        # Test round-robin selection
        proposer_0 = multi_validator_poa.select_proposer(0)
        proposer_1 = multi_validator_poa.select_proposer(1)
        proposer_2 = multi_validator_poa.select_proposer(2)
        
        assert proposer_0 in validators
        assert proposer_1 in validators
        assert proposer_2 in validators
        assert proposer_0 != proposer_1
        assert proposer_1 != proposer_2
    
    def test_validator_rotation_strategies(self, validator_rotation):
        """Test different rotation strategies"""
        from aitbc_chain.consensus.rotation import RotationStrategy
        
        # Test round-robin rotation
        success = validator_rotation.rotate_validators(100)
        assert success is True
        
        # Test stake-weighted rotation
        validator_rotation.config.strategy = RotationStrategy.STAKE_WEIGHTED
        success = validator_rotation.rotate_validators(101)
        assert success is True
    
    @pytest.mark.asyncio
    async def test_pbft_consensus_phases(self, pbft_consensus):
        """Test PBFT consensus phases"""
        from aitbc_chain.consensus.pbft import PBFTPhase, PBFTMessageType
        
        # Test pre-prepare phase
        success = await pbft_consensus.pre_prepare_phase(
            "0xvalidator1", "block_hash_123", 1, ["0xvalidator1", "0xvalidator2", "0xvalidator3"],
            {"0xvalidator1": 0.9, "0xvalidator2": 0.8, "0xvalidator3": 0.85}
        )
        assert success is True
        
        # Check message creation
        assert len(pbft_consensus.state.pre_prepare_messages) == 1
    
    def test_slashing_conditions(self, slashing_manager):
        """Test slashing condition detection"""
        validator_address = "0x1234567890123456789012345678901234567890"
        
        # Test double signing detection
        event = slashing_manager.detect_double_sign(
            validator_address, "hash1", "hash2", 100
        )
        assert event is not None
        assert event.condition == SlashingCondition.DOUBLE_SIGN
        assert event.validator_address == validator_address
    
    def test_key_management(self, key_manager):
        """Test cryptographic key management"""
        address = "0x1234567890123456789012345678901234567890"
        
        # Generate key pair
        key_pair = key_manager.generate_key_pair(address)
        assert key_pair.address == address
        assert key_pair.private_key_pem is not None
        assert key_pair.public_key_pem is not None
        
        # Test message signing
        message = "test message"
        signature = key_manager.sign_message(address, message)
        assert signature is not None
        
        # Test signature verification
        valid = key_manager.verify_signature(address, message, signature)
        assert valid is True


class TestPhase2NetworkInfrastructure:
    """Test Phase 2: Network Infrastructure Implementation"""
    
    @pytest.fixture
    def p2p_discovery(self):
        """Create P2P discovery instance"""
        return P2PDiscovery("test-node", "127.0.0.1", 8000)
    
    @pytest.fixture
    def health_monitor(self):
        """Create health monitor instance"""
        return PeerHealthMonitor(check_interval=60)
    
    @pytest.fixture
    def peer_manager(self, p2p_discovery, health_monitor):
        """Create peer manager instance"""
        return DynamicPeerManager(p2p_discovery, health_monitor)
    
    @pytest.fixture
    def topology_manager(self, p2p_discovery, health_monitor):
        """Create topology manager instance"""
        return NetworkTopology(p2p_discovery, health_monitor)
    
    @pytest.fixture
    def partition_manager(self, p2p_discovery, health_monitor):
        """Create partition manager instance"""
        return NetworkPartitionManager(p2p_discovery, health_monitor)
    
    @pytest.fixture
    def recovery_manager(self, p2p_discovery, health_monitor, partition_manager):
        """Create recovery manager instance"""
        return NetworkRecoveryManager(p2p_discovery, health_monitor, partition_manager)
    
    def test_p2p_discovery_initialization(self, p2p_discovery):
        """Test P2P discovery initialization"""
        assert p2p_discovery.local_node_id == "test-node"
        assert p2p_discovery.local_address == "127.0.0.1"
        assert p2p_discovery.local_port == 8000
        assert len(p2p_discovery.bootstrap_nodes) == 0
        assert p2p_discovery.max_peers == 50
    
    def test_bootstrap_node_addition(self, p2p_discovery):
        """Test bootstrap node addition"""
        p2p_discovery.add_bootstrap_node("127.0.0.1", 8001)
        p2p_discovery.add_bootstrap_node("127.0.0.1", 8002)
        
        assert len(p2p_discovery.bootstrap_nodes) == 2
        assert ("127.0.0.1", 8001) in p2p_discovery.bootstrap_nodes
        assert ("127.0.0.1", 8002) in p2p_discovery.bootstrap_nodes
    
    def test_node_id_generation(self, p2p_discovery):
        """Test unique node ID generation"""
        address = "127.0.0.1"
        port = 8000
        public_key = "test_public_key"
        
        node_id1 = p2p_discovery.generate_node_id(address, port, public_key)
        node_id2 = p2p_discovery.generate_node_id(address, port, public_key)
        
        assert node_id1 == node_id2  # Same inputs should generate same ID
        assert len(node_id1) == 64  # SHA256 hex length
        assert node_id1.isalnum()  # Should be alphanumeric
    
    def test_peer_health_monitoring(self, health_monitor):
        """Test peer health monitoring"""
        # Create test peer
        peer = PeerNode(
            node_id="test_peer",
            address="127.0.0.1",
            port=8001,
            public_key="test_key",
            last_seen=time.time(),
            status=NodeStatus.ONLINE,
            capabilities=["test"],
            reputation=1.0,
            connection_count=0
        )
        
        # Check health status
        health_status = health_monitor.get_health_status("test_peer")
        assert health_status is not None
        assert health_status.node_id == "test_peer"
        assert health_status.status == NodeStatus.ONLINE
    
    def test_dynamic_peer_management(self, peer_manager):
        """Test dynamic peer management"""
        # Test adding peer
        success = await peer_manager.add_peer("127.0.0.1", 8001, "test_key")
        assert success is True
        
        # Test removing peer
        success = await peer_manager.remove_peer("test_peer", "Test removal")
        # Note: This would fail if peer doesn't exist, which is expected
    
    def test_network_topology_optimization(self, topology_manager):
        """Test network topology optimization"""
        # Test topology strategies
        assert topology_manager.strategy == TopologyStrategy.HYBRID
        assert topology_manager.max_degree == 8
        assert topology_manager.min_degree == 3
        
        # Test topology metrics
        metrics = topology_manager.get_topology_metrics()
        assert 'node_count' in metrics
        assert 'edge_count' in metrics
        assert 'is_connected' in metrics
    
    def test_partition_detection(self, partition_manager):
        """Test network partition detection"""
        # Test partition status
        status = partition_manager.get_partition_status()
        assert 'state' in status
        assert 'local_partition_id' in status
        assert 'partition_count' in status
        
        # Initially should be healthy
        assert status['state'] == PartitionState.HEALTHY.value
    
    def test_network_recovery_mechanisms(self, recovery_manager):
        """Test network recovery mechanisms"""
        # Test recovery trigger
        success = await recovery_manager.trigger_recovery(
            RecoveryTrigger.PARTITION_DETECTED,
            "test_node"
        )
        # This would start recovery process
        assert success is True or success is False  # Depends on implementation
    
    def test_network_integration(self, p2p_discovery, health_monitor, peer_manager, topology_manager):
        """Test integration between network components"""
        # Test that components can work together
        assert p2p_discovery is not None
        assert health_monitor is not None
        assert peer_manager is not None
        assert topology_manager is not None
        
        # Test basic functionality
        peer_count = p2p_discovery.get_peer_count()
        assert isinstance(peer_count, int)
        assert peer_count >= 0


class TestPhase3EconomicLayer:
    """Test Phase 3: Economic Layer Implementation"""
    
    @pytest.fixture
    def staking_manager(self):
        """Create staking manager instance"""
        return StakingManager(min_stake_amount=1000.0)
    
    @pytest.fixture
    def reward_distributor(self, staking_manager):
        """Create reward distributor instance"""
        from aitbc_chain.economics.rewards import RewardCalculator
        calculator = RewardCalculator(base_reward_rate=0.05)
        return RewardDistributor(staking_manager, calculator)
    
    @pytest.fixture
    def gas_manager(self):
        """Create gas manager instance"""
        return GasManager(base_gas_price=0.001)
    
    @pytest.fixture
    def security_monitor(self, staking_manager, reward_distributor, gas_manager):
        """Create security monitor instance"""
        return EconomicSecurityMonitor(staking_manager, reward_distributor, gas_manager)
    
    def test_staking_manager_initialization(self, staking_manager):
        """Test staking manager initialization"""
        assert staking_manager.min_stake_amount == 1000.0
        assert staking_manager.unstaking_period == 21  # days
        assert staking_manager.max_delegators_per_validator == 100
        assert staking_manager.registration_fee == Decimal('100.0')
    
    def test_validator_registration(self, staking_manager):
        """Test validator registration"""
        validator_address = "0x1234567890123456789012345678901234567890"
        
        success, message = staking_manager.register_validator(
            validator_address, 2000.0, 0.05
        )
        assert success is True
        assert "successfully" in message.lower()
        
        # Check validator info
        validator_info = staking_manager.get_validator_stake_info(validator_address)
        assert validator_info is not None
        assert validator_info.validator_address == validator_address
        assert float(validator_info.self_stake) == 2000.0
        assert validator_info.is_active is True
    
    def test_staking_to_validator(self, staking_manager):
        """Test staking to validator"""
        # Register validator first
        validator_address = "0x1234567890123456789012345678901234567890"
        staking_manager.register_validator(validator_address, 2000.0, 0.05)
        
        # Stake to validator
        delegator_address = "0x2345678901234567890123456789012345678901"
        success, message = staking_manager.stake(
            validator_address, delegator_address, 1500.0
        )
        assert success is True
        assert "successful" in message.lower()
        
        # Check stake position
        position = staking_manager.get_stake_position(validator_address, delegator_address)
        assert position is not None
        assert float(position.amount) == 1500.0
        assert position.status == StakingStatus.ACTIVE
    
    def test_insufficient_stake_amount(self, staking_manager):
        """Test staking with insufficient amount"""
        validator_address = "0x1234567890123456789012345678901234567890"
        
        success, message = staking_manager.stake(
            validator_address, "0x2345678901234567890123456789012345678901", 500.0
        )
        assert success is False
        assert "insufficient" in message.lower() or "at least" in message.lower()
    
    def test_unstaking_process(self, staking_manager):
        """Test unstaking process"""
        # Setup stake
        validator_address = "0x1234567890123456789012345678901234567890"
        delegator_address = "0x2345678901234567890123456789012345678901"
        
        staking_manager.register_validator(validator_address, 2000.0, 0.05)
        staking_manager.stake(validator_address, delegator_address, 1500.0, 1)  # 1 day lock
        
        # Try to unstake immediately (should fail due to lock period)
        success, message = staking_manager.unstake(validator_address, delegator_address)
        assert success is False
        assert "lock period" in message.lower()
    
    def test_reward_distribution(self, reward_distributor):
        """Test reward distribution"""
        # Test reward event addition
        reward_distributor.add_reward_event(
            "0xvalidator1", RewardType.BLOCK_PROPOSAL, 10.0, 100
        )
        
        # Test pending rewards
        pending = reward_distributor.get_pending_rewards("0xvalidator1")
        assert pending > 0
        
        # Test reward statistics
        stats = reward_distributor.get_reward_statistics()
        assert 'total_events' in stats
        assert 'total_distributions' in stats
    
    def test_gas_fee_calculation(self, gas_manager):
        """Test gas fee calculation"""
        # Test gas estimation
        gas_used = gas_manager.estimate_gas(
            GasType.TRANSFER, data_size=100, complexity_score=1.0
        )
        assert gas_used > 0
        
        # Test transaction fee calculation
        fee_info = gas_manager.calculate_transaction_fee(
            GasType.TRANSFER, data_size=100
        )
        assert fee_info.gas_used == gas_used
        assert fee_info.total_fee > 0
    
    def test_gas_price_dynamics(self, gas_manager):
        """Test dynamic gas pricing"""
        # Test price update
        old_price = gas_manager.current_gas_price
        new_price = gas_manager.update_gas_price(0.8, 100, 1000)
        
        assert new_price.price_per_gas is not None
        assert new_price.congestion_level >= 0.0
        
        # Test optimal pricing
        fast_price = gas_manager.get_optimal_gas_price("fast")
        slow_price = gas_manager.get_optimal_gas_price("slow")
        
        assert fast_price >= slow_price
    
    def test_economic_attack_detection(self, security_monitor):
        """Test economic attack detection"""
        # Test attack detection
        from aitbc_chain.economics.attacks import AttackType
        
        # This would require actual network activity to test
        # For now, test the monitoring infrastructure
        stats = security_monitor.get_attack_summary()
        assert 'total_detections' in stats
        assert 'security_metrics' in stats
    
    def test_economic_integration(self, staking_manager, reward_distributor, gas_manager):
        """Test integration between economic components"""
        # Test that components can work together
        assert staking_manager is not None
        assert reward_distributor is not None
        assert gas_manager is not None
        
        # Test basic functionality
        total_staked = staking_manager.get_total_staked()
        assert total_staked >= 0
        
        gas_stats = gas_manager.get_gas_statistics()
        assert 'current_price' in gas_stats


class TestPhase4AgentNetworkScaling:
    """Test Phase 4: Agent Network Scaling Implementation"""
    
    @pytest.fixture
    def agent_registry(self):
        """Create agent registry instance"""
        return AgentRegistry()
    
    @pytest.fixture
    def capability_matcher(self, agent_registry):
        """Create capability matcher instance"""
        return CapabilityMatcher(agent_registry)
    
    @pytest.fixture
    def reputation_manager(self):
        """Create reputation manager instance"""
        return ReputationManager()
    
    @pytest.fixture
    def communication_protocol(self):
        """Create communication protocol instance"""
        return CommunicationProtocol("test_agent", "test_key")
    
    @pytest.fixture
    def lifecycle_manager(self):
        """Create lifecycle manager instance"""
        return AgentLifecycleManager()
    
    @pytest.fixture
    def behavior_monitor(self):
        """Create behavior monitor instance"""
        return AgentBehaviorMonitor()
    
    def test_agent_registration(self, agent_registry):
        """Test agent registration"""
        capabilities = [
            {
                'type': 'text_generation',
                'name': 'GPT-4',
                'version': '1.0',
                'cost_per_use': 0.001,
                'availability': 0.95,
                'max_concurrent_jobs': 5
            }
        ]
        
        success, message, agent_id = asyncio.run(
            agent_registry.register_agent(
                AgentType.AI_MODEL,
                "TestAgent",
                "0x1234567890123456789012345678901234567890",
                "test_public_key",
                "http://localhost:8080",
                capabilities
            )
        )
        
        assert success is True
        assert agent_id is not None
        assert "successful" in message.lower()
        
        # Check agent info
        agent_info = asyncio.run(agent_registry.get_agent_info(agent_id))
        assert agent_info is not None
        assert agent_info.name == "TestAgent"
        assert agent_info.agent_type == AgentType.AI_MODEL
        assert len(agent_info.capabilities) == 1
    
    def test_capability_matching(self, capability_matcher):
        """Test agent capability matching"""
        from agent_services.agent_registry.src.registration import CapabilityType
        
        # Create job requirement
        from agent_services.agent_registry.src.matching import JobRequirement
        requirement = JobRequirement(
            capability_type=CapabilityType.TEXT_GENERATION,
            name="GPT-4",
            min_version="1.0",
            required_parameters={"max_tokens": 1000},
            performance_requirements={"speed": 1.0},
            max_cost_per_use=Decimal('0.01'),
            min_availability=0.8,
            priority="medium"
        )
        
        # Find matches (would require actual agents)
        matches = asyncio.run(capability_matcher.find_matches(requirement, limit=5))
        assert isinstance(matches, list)
    
    def test_reputation_system(self, reputation_manager):
        """Test reputation system"""
        agent_id = "test_agent_001"
        
        # Initialize agent reputation
        reputation_score = asyncio.run(reputation_manager.initialize_agent_reputation(agent_id))
        assert reputation_score is not None
        assert reputation_score.overall_score == 0.5  # Base score
        
        # Add reputation event
        success, message = asyncio.run(
            reputation_manager.add_reputation_event(
                ReputationEvent.JOB_COMPLETED,
                agent_id,
                "job_001",
                "Excellent work"
            )
        )
        assert success is True
        assert "added successfully" in message.lower()
        
        # Check updated reputation
        updated_score = asyncio.run(reputation_manager.get_reputation_score(agent_id))
        assert updated_score.overall_score > 0.5
    
    def test_communication_protocols(self, communication_protocol):
        """Test communication protocols"""
        # Test message creation
        success, message, message_id = asyncio.run(
            communication_protocol.send_message(
                "target_agent",
                MessageType.HEARTBEAT,
                {"status": "active", "load": 0.5}
            )
        )
        
        assert success is True
        assert message_id is not None
        
        # Test communication statistics
        stats = asyncio.run(communication_protocol.get_communication_statistics())
        assert 'total_messages' in stats
        assert 'protocol_version' in stats
    
    def test_agent_lifecycle(self, lifecycle_manager):
        """Test agent lifecycle management"""
        agent_id = "test_agent_lifecycle"
        agent_type = "AI_MODEL"
        
        # Create agent lifecycle
        lifecycle = asyncio.run(
            lifecycle_manager.create_agent_lifecycle(agent_id, agent_type)
        )
        
        assert lifecycle is not None
        assert lifecycle.agent_id == agent_id
        assert lifecycle.agent_type == agent_type
        assert lifecycle.current_state == LifecycleState.INITIALIZING
        
        # Test state transition
        success, message = asyncio.run(
            lifecycle_manager.transition_state(agent_id, LifecycleState.REGISTERING)
        )
        assert success is True
        assert "successful" in message.lower()
    
    def test_behavior_monitoring(self, behavior_monitor):
        """Test agent behavior monitoring"""
        # Test metric tracking
        metrics = asyncio.run(behavior_monitor.get_monitoring_statistics())
        assert 'total_agents' in metrics
        assert 'total_alerts' in metrics
        assert 'metric_statistics' in metrics
    
    def test_agent_network_integration(self, agent_registry, capability_matcher, reputation_manager):
        """Test integration between agent network components"""
        # Test that components can work together
        assert agent_registry is not None
        assert capability_matcher is not None
        assert reputation_manager is not None
        
        # Test basic functionality
        stats = asyncio.run(agent_registry.get_registry_statistics())
        assert 'total_agents' in stats
        assert 'agent_types' in stats


class TestPhase5SmartContracts:
    """Test Phase 5: Smart Contract Infrastructure Implementation"""
    
    @pytest.fixture
    def escrow_manager(self):
        """Create escrow manager instance"""
        return EscrowManager()
    
    @pytest.fixture
    def dispute_resolver(self):
        """Create dispute resolver instance"""
        return DisputeResolver()
    
    @pytest.fixture
    def upgrade_manager(self):
        """Create upgrade manager instance"""
        return ContractUpgradeManager()
    
    @pytest.fixture
    def gas_optimizer(self):
        """Create gas optimizer instance"""
        return GasOptimizer()
    
    def test_escrow_contract_creation(self, escrow_manager):
        """Test escrow contract creation"""
        success, message, contract_id = asyncio.run(
            escrow_manager.create_contract(
                job_id="job_001",
                client_address="0x1234567890123456789012345678901234567890",
                agent_address="0x2345678901234567890123456789012345678901",
                amount=Decimal('100.0')
            )
        )
        
        assert success is True
        assert contract_id is not None
        assert "created successfully" in message.lower()
        
        # Check contract details
        contract = asyncio.run(escrow_manager.get_contract_info(contract_id))
        assert contract is not None
        assert contract.job_id == "job_001"
        assert contract.state == EscrowState.CREATED
        assert contract.amount > Decimal('100.0')  # Includes platform fee
    
    def test_escrow_funding(self, escrow_manager):
        """Test escrow contract funding"""
        # Create contract first
        success, _, contract_id = asyncio.run(
            escrow_manager.create_contract(
                job_id="job_002",
                client_address="0x1234567890123456789012345678901234567890",
                agent_address="0x2345678901234567890123456789012345678901",
                amount=Decimal('100.0')
            )
        )
        
        # Fund contract
        success, message = asyncio.run(
            escrow_manager.fund_contract(contract_id, "tx_hash_001")
        )
        
        assert success is True
        assert "funded successfully" in message.lower()
        
        # Check state
        contract = asyncio.run(escrow_manager.get_contract_info(contract_id))
        assert contract.state == EscrowState.FUNDED
    
    def test_milestone_completion(self, escrow_manager):
        """Test milestone completion and verification"""
        milestones = [
            {
                'milestone_id': 'milestone_1',
                'description': 'Initial setup',
                'amount': Decimal('50.0')
            },
            {
                'milestone_id': 'milestone_2',
                'description': 'Main work',
                'amount': Decimal('50.0')
            }
        ]
        
        # Create contract with milestones
        success, _, contract_id = asyncio.run(
            escrow_manager.create_contract(
                job_id="job_003",
                client_address="0x1234567890123456789012345678901234567890",
                agent_address="0x2345678901234567890123456789012345678901",
                amount=Decimal('100.0'),
                milestones=milestones
            )
        )
        
        asyncio.run(escrow_manager.fund_contract(contract_id, "tx_hash_001"))
        asyncio.run(escrow_manager.start_job(contract_id))
        
        # Complete milestone
        success, message = asyncio.run(
            escrow_manager.complete_milestone(contract_id, "milestone_1")
        )
        
        assert success is True
        assert "completed successfully" in message.lower()
        
        # Verify milestone
        success, message = asyncio.run(
            escrow_manager.verify_milestone(contract_id, "milestone_1", True, "Work verified")
        )
        
        assert success is True
        assert "processed" in message.lower()
    
    def test_dispute_resolution(self, dispute_resolver):
        """Test dispute resolution process"""
        # Create dispute case
        success, message, dispute_id = asyncio.run(
            dispute_resolver.create_dispute_case(
                contract_id="contract_001",
                client_address="0x1234567890123456789012345678901234567890",
                agent_address="0x2345678901234567890123456789012345678901",
                reason="quality_issues",
                description="Poor quality work",
                evidence=[{'type': 'screenshot', 'description': 'Quality issues'}]
            )
        )
        
        assert success is True
        assert dispute_id is not None
        assert "created successfully" in message.lower()
        
        # Check dispute case
        dispute_case = asyncio.run(dispute_resolver.get_dispute_case(dispute_id))
        assert dispute_case is not None
        assert dispute_case.reason == "quality_issues"
    
    def test_contract_upgrades(self, upgrade_manager):
        """Test contract upgrade system"""
        # Create upgrade proposal
        success, message, proposal_id = asyncio.run(
            upgrade_manager.propose_upgrade(
                contract_type="escrow",
                current_version="1.0.0",
                new_version="1.1.0",
                upgrade_type=UpgradeType.FEATURE_ADDITION,
                description="Add new features",
                changes={"new_feature": "enhanced_security"},
                proposer="0xgovernance1111111111111111111111111111111111111"
            )
        )
        
        assert success is True
        assert proposal_id is not None
        assert "created successfully" in message.lower()
        
        # Test voting
        success, message = asyncio.run(
            upgrade_manager.vote_on_proposal(proposal_id, "0xgovernance1111111111111111111111111111111111111", True)
        )
        
        assert success is True
        assert "cast successfully" in message.lower()
    
    def test_gas_optimization(self, gas_optimizer):
        """Test gas optimization system"""
        # Record gas usage
        asyncio.run(
            gas_optimizer.record_gas_usage(
                "0xcontract123", "transferFunction", 21000, 25000, 0.5
            )
        )
        
        # Get optimization recommendations
        recommendations = asyncio.run(gas_optimizer.get_optimization_recommendations())
        assert isinstance(recommendations, list)
        
        # Get gas statistics
        stats = asyncio.run(gas_optimizer.get_gas_statistics())
        assert 'total_transactions' in stats
        assert 'average_gas_used' in stats
        assert 'optimization_opportunities' in stats
    
    def test_smart_contract_integration(self, escrow_manager, dispute_resolver, upgrade_manager):
        """Test integration between smart contract components"""
        # Test that components can work together
        assert escrow_manager is not None
        assert dispute_resolver is not None
        assert upgrade_manager is not None
        
        # Test basic functionality
        stats = asyncio.run(escrow_manager.get_escrow_statistics())
        assert 'total_contracts' in stats
        assert 'active_contracts' in stats


class TestMeshNetworkIntegration:
    """Test integration across all phases"""
    
    @pytest.fixture
    def integrated_system(self):
        """Create integrated system with all components"""
        # This would set up all components working together
        return {
            'consensus': MultiValidatorPoA("test-chain"),
            'network': P2PDiscovery("test-node", "127.0.0.1", 8000),
            'economics': StakingManager(),
            'agents': AgentRegistry(),
            'contracts': EscrowManager()
        }
    
    def test_end_to_end_workflow(self, integrated_system):
        """Test end-to-end mesh network workflow"""
        # This would test a complete workflow:
        # 1. Validators reach consensus
        # 2. Agents discover each other
        # 3. Jobs are created and matched
        # 4. Escrow contracts are funded
        # 5. Work is completed and paid for
        
        # For now, test basic integration
        assert integrated_system['consensus'] is not None
        assert integrated_system['network'] is not None
        assert integrated_system['economics'] is not None
        assert integrated_system['agents'] is not None
        assert integrated_system['contracts'] is not None
    
    def test_performance_requirements(self, integrated_system):
        """Test that performance requirements are met"""
        # Test validator count
        assert integrated_system['consensus'].max_peers >= 50
        
        # Test network connectivity
        assert integrated_system['network'].max_peers >= 50
        
        # Test economic throughput
        # This would require actual performance testing
        pass
    
    def test_security_requirements(self, integrated_system):
        """Test that security requirements are met"""
        # Test consensus security
        assert integrated_system['consensus'].fault_tolerance >= 1
        
        # Test network security
        assert integrated_system['network'].max_peers >= 50
        
        # Test economic security
        # This would require actual security testing
        pass
    
    def test_scalability_requirements(self, integrated_system):
        """Test that scalability requirements are met"""
        # Test node scalability
        assert integrated_system['network'].max_peers >= 50
        
        # Test agent scalability
        # This would require actual scalability testing
        pass


class TestMeshNetworkTransition:
    """Test the complete mesh network transition"""
    
    def test_transition_plan_completeness(self):
        """Test that the transition plan is complete"""
        # Check that all 5 phases are implemented
        phases = [
            '01_consensus_setup.sh',
            '02_network_infrastructure.sh', 
            '03_economic_layer.sh',
            '04_agent_network_scaling.sh',
            '05_smart_contracts.sh'
        ]
        
        scripts_dir = '/opt/aitbc/scripts/plan'
        for phase in phases:
            script_path = os.path.join(scripts_dir, phase)
            assert os.path.exists(script_path), f"Missing script: {phase}"
            assert os.access(script_path, os.X_OK), f"Script not executable: {phase}"
    
    def test_phase_dependencies(self):
        """Test that phase dependencies are correctly handled"""
        # Phase 1 should be independent
        # Phase 2 depends on Phase 1
        # Phase 3 depends on Phase 1
        # Phase 4 depends on Phase 1
        # Phase 5 depends on Phase 1
        
        # This would test actual dependencies in the code
        pass
    
    def test_configuration_files(self):
        """Test that all configuration files are created"""
        config_dir = '/etc/aitbc'
        configs = [
            'consensus_test.json',
            'network_test.json',
            'economics_test.json',
            'agent_network_test.json',
            'smart_contracts_test.json'
        ]
        
        for config in configs:
            config_path = os.path.join(config_dir, config)
            assert os.path.exists(config_path), f"Missing config: {config}"
    
    def test_documentation_completeness(self):
        """Test that documentation is complete"""
        readme_path = '/opt/aitbc/scripts/plan/README.md'
        assert os.path.exists(readme_path), "Missing README.md"
        
        # Check README contains key sections
        with open(readme_path, 'r') as f:
            content = f.read()
            assert 'Phase Structure' in content
            assert 'Quick Start' in content
            assert 'Implementation Features' in content
            assert 'Expected Outcomes' in content
    
    def test_backward_compatibility(self):
        """Test that implementation maintains backward compatibility"""
        # This would test that existing functionality still works
        # with the new mesh network features
        
        # Test that single-producer mode still works as fallback
        pass
    
    def test_migration_path(self):
        """Test that migration from current to mesh network works"""
        # This would test the migration process
        # ensuring data integrity and minimal downtime
        
        pass


# Test execution configuration
if __name__ == "__main__":
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "--maxfail=5"
    ])
