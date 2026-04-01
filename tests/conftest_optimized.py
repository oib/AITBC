"""
Optimized Pytest Configuration and Fixtures for AITBC Mesh Network Tests
Provides session-scoped fixtures for improved test performance
"""

import pytest
import asyncio
import os
import sys
import json
import time
from unittest.mock import Mock, AsyncMock
from decimal import Decimal
from typing import Dict, List, Any

# Add project paths
sys.path.insert(0, '/opt/aitbc/apps/blockchain-node/src')
sys.path.insert(0, '/opt/aitbc/apps/agent-services/agent-registry/src')
sys.path.insert(0, '/opt/aitbc/apps/agent-services/agent-coordinator/src')
sys.path.insert(0, '/opt/aitbc/apps/agent-services/agent-bridge/src')
sys.path.insert(0, '/opt/aitbc/apps/agent-services/agent-compliance/src')

# Global test configuration
TEST_CONFIG = {
    "network_timeout": 30.0,
    "consensus_timeout": 10.0,
    "transaction_timeout": 5.0,
    "mock_mode": True,
    "integration_mode": False,
    "performance_mode": False,
}

# Test data constants
TEST_ADDRESSES = {
    "validator_1": "0x1111111111111111111111111111111111111111",
    "validator_2": "0x2222222222222222222222222222222222222222",
    "validator_3": "0x3333333333333333333333333333333333333333",
    "validator_4": "0x4444444444444444444444444444444444444444",
    "validator_5": "0x5555555555555555555555555555555555555555",
    "client_1": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "client_2": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "agent_1": "0xcccccccccccccccccccccccccccccccccccccccccc",
    "agent_2": "0xdddddddddddddddddddddddddddddddddddddddddd",
}

TEST_KEYS = {
    "private_key_1": "0x1111111111111111111111111111111111111111111111111111111111111111",
    "private_key_2": "0x2222222222222222222222222222222222222222222222222222222222222222",
    "public_key_1": "0x031111111111111111111111111111111111111111111111111111111111111111",
    "public_key_2": "0x032222222222222222222222222222222222222222222222222222222222222222",
}

# Test constants
MIN_STAKE_AMOUNT = 1000.0
DEFAULT_GAS_PRICE = 0.001
DEFAULT_BLOCK_TIME = 30
NETWORK_SIZE = 50
AGENT_COUNT = 100

# ============================================================================
# Session-Scoped Fixtures (Created once per test session)
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
def test_config():
    """Provide test configuration - session scoped for consistency"""
    return TEST_CONFIG.copy()

@pytest.fixture(scope="session")
def test_addresses():
    """Provide test addresses - session scoped for consistency"""
    return TEST_ADDRESSES.copy()

@pytest.fixture(scope="session")
def test_keys():
    """Provide test keys - session scoped for consistency"""
    return TEST_KEYS.copy()

# ============================================================================
# Phase 1: Consensus Layer - Session Scoped Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def consensus_instances():
    """
    Create shared consensus instances for all tests.
    Session-scoped to avoid recreating for each test.
    """
    try:
        from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA
        from aitbc_chain.consensus.rotation import ValidatorRotation, DEFAULT_ROTATION_CONFIG
        from aitbc_chain.consensus.pbft import PBFTConsensus
        from aitbc_chain.consensus.slashing import SlashingManager
        from aitbc_chain.consensus.keys import KeyManager
        
        poa = MultiValidatorPoA("test-chain")
        
        # Add default validators
        default_validators = [
            ("0x1111111111111111111111111111111111111111", 1000.0),
            ("0x2222222222222222222222222222222222222222", 1000.0),
            ("0x3333333333333333333333333333333333333333", 1000.0),
        ]
        
        for address, stake in default_validators:
            poa.add_validator(address, stake)
        
        instances = {
            'poa': poa,
            'rotation': ValidatorRotation(poa, DEFAULT_ROTATION_CONFIG),
            'pbft': PBFTConsensus(poa),
            'slashing': SlashingManager(),
            'keys': KeyManager(),
        }
        
        yield instances
        
        # Cleanup if needed
        instances.clear()
        
    except ImportError:
        pytest.skip("Consensus modules not available", allow_module_level=True)

@pytest.fixture(scope="function")
def fresh_poa(consensus_instances):
    """
    Provide a fresh PoA instance for each test.
    Uses session-scoped base but creates fresh copy.
    """
    from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA
    return MultiValidatorPoA("test-chain")

# ============================================================================
# Phase 2: Network Layer - Session Scoped Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def network_instances():
    """
    Create shared network instances for all tests.
    Session-scoped to avoid recreating for each test.
    """
    try:
        from aitbc_chain.network.discovery import P2PDiscovery
        from aitbc_chain.network.health import PeerHealthMonitor
        from aitbc_chain.network.peers import DynamicPeerManager
        from aitbc_chain.network.topology import NetworkTopology
        
        discovery = P2PDiscovery("test-node", "127.0.0.1", 8000)
        health = PeerHealthMonitor(check_interval=60)
        peers = DynamicPeerManager(discovery, health)
        topology = NetworkTopology(discovery, health)
        
        instances = {
            'discovery': discovery,
            'health': health,
            'peers': peers,
            'topology': topology,
        }
        
        yield instances
        
    except ImportError:
        pytest.skip("Network modules not available", allow_module_level=True)

# ============================================================================
# Phase 3: Economic Layer - Session Scoped Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def economic_instances():
    """
    Create shared economic instances for all tests.
    Session-scoped to avoid recreating for each test.
    """
    try:
        from aitbc_chain.economics.staking import StakingManager
        from aitbc_chain.economics.rewards import RewardDistributor, RewardCalculator
        from aitbc_chain.economics.gas import GasManager
        
        staking = StakingManager(min_stake_amount=MIN_STAKE_AMOUNT)
        calculator = RewardCalculator(base_reward_rate=0.05)
        rewards = RewardDistributor(staking, calculator)
        gas = GasManager(base_gas_price=DEFAULT_GAS_PRICE)
        
        instances = {
            'staking': staking,
            'rewards': rewards,
            'calculator': calculator,
            'gas': gas,
        }
        
        yield instances
        
    except ImportError:
        pytest.skip("Economic modules not available", allow_module_level=True)

# ============================================================================
# Phase 4: Agent Network - Session Scoped Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def agent_instances():
    """
    Create shared agent instances for all tests.
    Session-scoped to avoid recreating for each test.
    """
    try:
        from agent_services.agent_registry.src.registration import AgentRegistry
        from agent_services.agent_registry.src.matching import CapabilityMatcher
        from agent_services.agent_coordinator.src.reputation import ReputationManager
        
        registry = AgentRegistry()
        matcher = CapabilityMatcher(registry)
        reputation = ReputationManager()
        
        instances = {
            'registry': registry,
            'matcher': matcher,
            'reputation': reputation,
        }
        
        yield instances
        
    except ImportError:
        pytest.skip("Agent modules not available", allow_module_level=True)

# ============================================================================
# Phase 5: Smart Contract - Session Scoped Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def contract_instances():
    """
    Create shared contract instances for all tests.
    Session-scoped to avoid recreating for each test.
    """
    try:
        from aitbc_chain.contracts.escrow import EscrowManager
        from aitbc_chain.contracts.disputes import DisputeResolver
        
        escrow = EscrowManager()
        disputes = DisputeResolver()
        
        instances = {
            'escrow': escrow,
            'disputes': disputes,
        }
        
        yield instances
        
    except ImportError:
        pytest.skip("Contract modules not available", allow_module_level=True)

# ============================================================================
# Mock Fixtures - Function Scoped (Fresh for each test)
# ============================================================================

@pytest.fixture
def mock_consensus():
    """Mock consensus layer components - fresh for each test"""
    class MockConsensus:
        def __init__(self):
            self.validators = {}
            self.current_proposer = None
            self.block_height = 100
            self.round_robin_index = 0
            
        def add_validator(self, address, stake):
            self.validators[address] = Mock(address=address, stake=stake)
            return True
            
        def select_proposer(self, round_number=None):
            if not self.validators:
                return None
            validator_list = list(self.validators.keys())
            index = (round_number or self.round_robin_index) % len(validator_list)
            self.round_robin_index = index + 1
            self.current_proposer = validator_list[index]
            return self.current_proposer
            
        def validate_transaction(self, tx):
            return True, "valid"
            
        def process_block(self, block):
            return True, "processed"
    
    return MockConsensus()

@pytest.fixture
def mock_network():
    """Mock network layer components - fresh for each test"""
    class MockNetwork:
        def __init__(self):
            self.peers = {}
            self.connected_peers = set()
            self.message_handler = Mock()
            
        def add_peer(self, peer_id, address, port):
            self.peers[peer_id] = Mock(peer_id=peer_id, address=address, port=port)
            self.connected_peers.add(peer_id)
            return True
            
        def remove_peer(self, peer_id):
            self.connected_peers.discard(peer_id)
            if peer_id in self.peers:
                del self.peers[peer_id]
            return True
            
        def send_message(self, recipient, message_type, payload):
            return True, "sent", f"msg_{int(time.time())}"
            
        def broadcast_message(self, message_type, payload):
            return True, "broadcasted"
            
        def get_peer_count(self):
            return len(self.connected_peers)
    
    return MockNetwork()

@pytest.fixture
def mock_economics():
    """Mock economic layer components - fresh for each test"""
    class MockEconomics:
        def __init__(self):
            self.stakes = {}
            self.rewards = {}
            self.gas_prices = {}
            
        def stake_tokens(self, address, amount):
            self.stakes[address] = self.stakes.get(address, 0) + amount
            return True, "staked"
            
        def unstake_tokens(self, address, amount):
            if address in self.stakes and self.stakes[address] >= amount:
                self.stakes[address] -= amount
                return True, "unstaked"
            return False, "insufficient stake"
            
        def calculate_reward(self, address, block_height):
            return Decimal('10.0')
            
        def get_gas_price(self):
            return Decimal(DEFAULT_GAS_PRICE)
    
    return MockEconomics()

# ============================================================================
# Sample Data Fixtures
# ============================================================================

@pytest.fixture
def sample_transactions():
    """Sample transaction data for testing"""
    return [
        {
            "tx_id": "tx_001",
            "type": "transfer",
            "from": TEST_ADDRESSES["client_1"],
            "to": TEST_ADDRESSES["agent_1"],
            "amount": Decimal('100.0'),
            "gas_limit": 21000,
            "gas_price": DEFAULT_GAS_PRICE
        },
        {
            "tx_id": "tx_002",
            "type": "stake",
            "from": TEST_ADDRESSES["validator_1"],
            "amount": Decimal('1000.0'),
            "gas_limit": 50000,
            "gas_price": DEFAULT_GAS_PRICE
        },
    ]

@pytest.fixture
def sample_agents():
    """Sample agent data for testing"""
    return [
        {
            "agent_id": "agent_001",
            "agent_type": "AI_MODEL",
            "capabilities": ["text_generation", "summarization"],
            "cost_per_use": Decimal('0.001'),
            "reputation": 0.9
        },
        {
            "agent_id": "agent_002",
            "agent_type": "DATA_PROVIDER",
            "capabilities": ["data_analysis", "prediction"],
            "cost_per_use": Decimal('0.002'),
            "reputation": 0.85
        },
    ]

# ============================================================================
# Test Configuration Fixtures
# ============================================================================

@pytest.fixture
def test_network_config():
    """Test network configuration"""
    return {
        "bootstrap_nodes": ["10.1.223.93:8000", "10.1.223.40:8000"],
        "discovery_interval": 30,
        "max_peers": 50,
        "heartbeat_interval": 60
    }

@pytest.fixture
def test_consensus_config():
    """Test consensus configuration"""
    return {
        "min_validators": 3,
        "max_validators": 100,
        "block_time": DEFAULT_BLOCK_TIME,
        "consensus_timeout": 10,
        "slashing_threshold": 0.1
    }

@pytest.fixture
def test_economics_config():
    """Test economics configuration"""
    return {
        "min_stake": MIN_STAKE_AMOUNT,
        "reward_rate": 0.05,
        "gas_price": DEFAULT_GAS_PRICE,
        "escrow_fee": 0.025,
        "dispute_timeout": 604800
    }

# ============================================================================
# Pytest Configuration Hooks
# ============================================================================

def pytest_configure(config):
    """Pytest configuration hook - add custom markers"""
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "performance: mark test as a performance test")
    config.addinivalue_line("markers", "security: mark test as a security test")
    config.addinivalue_line("markers", "slow: mark test as slow running")

def pytest_collection_modifyitems(config, items):
    """Modify test collection - add markers based on test location"""
    for item in items:
        if "performance" in str(item.fspath):
            item.add_marker(pytest.mark.performance)
        elif "security" in str(item.fspath):
            item.add_marker(pytest.mark.security)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        else:
            item.add_marker(pytest.mark.unit)

def pytest_ignore_collect(path, config):
    """Ignore certain files during test collection"""
    if "__pycache__" in str(path):
        return True
    if path.name.endswith(".bak") or path.name.endswith("~"):
        return True
    return False

# ============================================================================
# Test Helper Functions
# ============================================================================

def create_test_validator(address, stake=1000.0):
    """Create a test validator"""
    return Mock(
        address=address,
        stake=stake,
        public_key=f"0x03{address[2:]}",
        last_seen=time.time(),
        status="active"
    )

def create_test_agent(agent_id, agent_type="AI_MODEL", reputation=1.0):
    """Create a test agent"""
    return Mock(
        agent_id=agent_id,
        agent_type=agent_type,
        reputation=reputation,
        capabilities=["test_capability"],
        endpoint=f"http://localhost:8000/{agent_id}",
        created_at=time.time()
    )

def assert_performance_metric(actual, expected, tolerance=0.1, metric_name="metric"):
    """Assert performance metric within tolerance"""
    lower_bound = expected * (1 - tolerance)
    upper_bound = expected * (1 + tolerance)
    
    assert lower_bound <= actual <= upper_bound, (
        f"{metric_name} {actual} not within tolerance of expected {expected} "
        f"(range: {lower_bound} - {upper_bound})"
    )

async def async_wait_for_condition(condition, timeout=10.0, interval=0.1, description="condition"):
    """Wait for async condition to be true"""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        if condition():
            return True
        
        await asyncio.sleep(interval)
    
    raise AssertionError(f"Timeout waiting for {description}")

# ============================================================================
# Environment Setup
# ============================================================================

os.environ.setdefault('AITBC_TEST_MODE', 'true')
os.environ.setdefault('AITBC_MOCK_MODE', 'true')
os.environ.setdefault('AITBC_LOG_LEVEL', 'DEBUG')
