"""
Pytest Configuration and Fixtures for AITBC Mesh Network Tests
Shared test configuration and utilities
"""

import pytest
import asyncio
import os
import sys
import json
import time
from unittest.mock import Mock, AsyncMock
from decimal import Decimal

# Add project paths
sys.path.insert(0, '/opt/aitbc/apps/blockchain-node/src')
sys.path.insert(0, '/opt/aitbc/apps/agent-services/agent-registry/src')
sys.path.insert(0, '/opt/aitbc/apps/agent-services/agent-coordinator/src')
sys.path.insert(0, '/opt/aitbc/apps/agent-services/agent-bridge/src')
sys.path.insert(0, '/opt/aitbc/apps/agent-services/agent-compliance/src')

# Test configuration
pytest_plugins = []

# Global test configuration
TEST_CONFIG = {
    "network_timeout": 30.0,
    "consensus_timeout": 10.0,
    "transaction_timeout": 5.0,
    "mock_mode": True,  # Use mocks by default for faster tests
    "integration_mode": False,  # Set to True for integration tests
    "performance_mode": False,  # Set to True for performance tests
}

# Test data
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

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
def test_config():
    """Provide test configuration"""
    return TEST_CONFIG

@pytest.fixture
def mock_consensus():
    """Mock consensus layer components"""
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
    """Mock network layer components"""
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
            
        def get_peer_list(self):
            return [self.peers[pid] for pid in self.connected_peers if pid in self.peers]
    
    return MockNetwork()

@pytest.fixture
def mock_economics():
    """Mock economic layer components"""
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
            
        def update_gas_price(self, new_price):
            self.gas_prices[int(time.time())] = new_price
            return True
    
    return MockEconomics()

@pytest.fixture
def mock_agents():
    """Mock agent network components"""
    class MockAgents:
        def __init__(self):
            self.agents = {}
            self.capabilities = {}
            self.reputations = {}
            
        def register_agent(self, agent_id, agent_type, capabilities):
            self.agents[agent_id] = Mock(
                agent_id=agent_id,
                agent_type=agent_type,
                capabilities=capabilities
            )
            self.capabilities[agent_id] = capabilities
            self.reputations[agent_id] = 1.0
            return True, "registered"
            
        def find_agents(self, capability_type, limit=10):
            matching_agents = []
            for agent_id, caps in self.capabilities.items():
                if capability_type in caps:
                    matching_agents.append(self.agents[agent_id])
                    if len(matching_agents) >= limit:
                        break
            return matching_agents
            
        def update_reputation(self, agent_id, delta):
            if agent_id in self.reputations:
                self.reputations[agent_id] = max(0.0, min(1.0, self.reputations[agent_id] + delta))
                return True
            return False
            
        def get_reputation(self, agent_id):
            return self.reputations.get(agent_id, 0.0)
    
    return MockAgents()

@pytest.fixture
def mock_contracts():
    """Mock smart contract components"""
    class MockContracts:
        def __init__(self):
            self.contracts = {}
            self.disputes = {}
            
        def create_escrow(self, job_id, client, agent, amount):
            contract_id = f"contract_{int(time.time())}"
            self.contracts[contract_id] = Mock(
                contract_id=contract_id,
                job_id=job_id,
                client=client,
                agent=agent,
                amount=amount,
                status="created"
            )
            return True, "created", contract_id
            
        def fund_contract(self, contract_id):
            if contract_id in self.contracts:
                self.contracts[contract_id].status = "funded"
                return True, "funded"
            return False, "not found"
            
        def create_dispute(self, contract_id, reason):
            dispute_id = f"dispute_{int(time.time())}"
            self.disputes[dispute_id] = Mock(
                dispute_id=dispute_id,
                contract_id=contract_id,
                reason=reason,
                status="open"
            )
            return True, "created", dispute_id
            
        def resolve_dispute(self, dispute_id, resolution):
            if dispute_id in self.disputes:
                self.disputes[dispute_id].status = "resolved"
                self.disputes[dispute_id].resolution = resolution
                return True, "resolved"
            return False, "not found"
    
    return MockContracts()

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
        {
            "tx_id": "tx_003",
            "type": "job_create",
            "from": TEST_ADDRESSES["client_2"],
            "to": TEST_ADDRESSES["agent_2"],
            "amount": Decimal('50.0'),
            "gas_limit": 100000,
            "gas_price": DEFAULT_GAS_PRICE
        }
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
        {
            "agent_id": "agent_003",
            "agent_type": "VALIDATOR",
            "capabilities": ["validation", "verification"],
            "cost_per_use": Decimal('0.0005'),
            "reputation": 0.95
        }
    ]

@pytest.fixture
def sample_jobs():
    """Sample job data for testing"""
    return [
        {
            "job_id": "job_001",
            "client_address": TEST_ADDRESSES["client_1"],
            "capability_required": "text_generation",
            "parameters": {"max_tokens": 1000, "temperature": 0.7},
            "payment": Decimal('10.0')
        },
        {
            "job_id": "job_002",
            "client_address": TEST_ADDRESSES["client_2"],
            "capability_required": "data_analysis",
            "parameters": {"dataset_size": 1000, "algorithm": "linear_regression"},
            "payment": Decimal('20.0')
        }
    ]

@pytest.fixture
def test_network_config():
    """Test network configuration"""
    return {
        "bootstrap_nodes": [
            "10.1.223.93:8000",
            "10.1.223.40:8000"
        ],
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

@pytest.fixture
def temp_config_files(tmp_path):
    """Create temporary configuration files for testing"""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    
    configs = {
        "consensus_test.json": test_consensus_config(),
        "network_test.json": test_network_config(),
        "economics_test.json": test_economics_config(),
        "agent_network_test.json": {"max_agents": AGENT_COUNT},
        "smart_contracts_test.json": {"escrow_fee": 0.025}
    }
    
    created_files = {}
    for filename, config_data in configs.items():
        config_path = config_dir / filename
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        created_files[filename] = config_path
    
    return created_files

@pytest.fixture
def mock_blockchain_state():
    """Mock blockchain state for testing"""
    return {
        "block_height": 1000,
        "total_supply": Decimal('1000000'),
        "active_validators": 10,
        "total_staked": Decimal('100000'),
        "gas_price": DEFAULT_GAS_PRICE,
        "network_hashrate": 1000000,
        "difficulty": 1000
    }

@pytest.fixture
def performance_metrics():
    """Performance metrics for testing"""
    return {
        "block_propagation_time": 2.5,  # seconds
        "transaction_throughput": 1000,  # tx/s
        "consensus_latency": 0.5,  # seconds
        "network_latency": 0.1,  # seconds
        "memory_usage": 512,  # MB
        "cpu_usage": 0.3,  # 30%
        "disk_io": 100,  # MB/s
    }

# Test markers
pytest.mark.unit = pytest.mark.unit
pytest.mark.integration = pytest.mark.integration
pytest.mark.performance = pytest.mark.performance
pytest.mark.security = pytest.mark.security
pytest.mark.slow = pytest.mark.slow

# Custom test helpers
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

def create_test_transaction(tx_type="transfer", amount=100.0):
    """Create a test transaction"""
    return Mock(
        tx_id=f"tx_{int(time.time())}",
        type=tx_type,
        from_address=TEST_ADDRESSES["client_1"],
        to_address=TEST_ADDRESSES["agent_1"],
        amount=Decimal(str(amount)),
        gas_limit=21000,
        gas_price=DEFAULT_GAS_PRICE,
        timestamp=time.time()
    )

def assert_performance_metric(actual, expected, tolerance=0.1, metric_name="metric"):
    """Assert performance metric within tolerance"""
    lower_bound = expected * (1 - tolerance)
    upper_bound = expected * (1 + tolerance)
    
    assert lower_bound <= actual <= upper_bound, (
        f"{metric_name} {actual} not within tolerance of expected {expected} "
        f"(range: {lower_bound} - {upper_bound})"
    )

def wait_for_condition(condition, timeout=10.0, interval=0.1, description="condition"):
    """Wait for a condition to be true"""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        if condition():
            return True
        
        time.sleep(interval)
    
    raise AssertionError(f"Timeout waiting for {description}")

# Test data generators
def generate_test_transactions(count=100):
    """Generate test transactions"""
    transactions = []
    for i in range(count):
        tx = create_test_transaction(
            tx_type=["transfer", "stake", "unstake", "job_create"][i % 4],
            amount=100.0 + (i % 10) * 10
        )
        transactions.append(tx)
    return transactions

def generate_test_agents(count=50):
    """Generate test agents"""
    agents = []
    agent_types = ["AI_MODEL", "DATA_PROVIDER", "VALIDATOR", "ORACLE"]
    
    for i in range(count):
        agent = create_test_agent(
            f"agent_{i:03d}",
            agent_type=agent_types[i % len(agent_types)],
            reputation=0.5 + (i % 50) / 100
        )
        agents.append(agent)
    return agents

# Async test helpers
async def async_wait_for_condition(condition, timeout=10.0, interval=0.1, description="condition"):
    """Async version of wait_for_condition"""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        if condition():
            return True
        
        await asyncio.sleep(interval)
    
    raise AssertionError(f"Timeout waiting for {description}")

# Mock decorators
def mock_integration_test(func):
    """Decorator for integration tests that require mocking"""
    return pytest.mark.integration(func)

def mock_performance_test(func):
    """Decorator for performance tests"""
    return pytest.mark.performance(func)

def mock_security_test(func):
    """Decorator for security tests"""
    return pytest.mark.security(func)

# Environment setup
def setup_test_environment():
    """Setup test environment"""
    # Set environment variables
    os.environ.setdefault('AITBC_TEST_MODE', 'true')
    os.environ.setdefault('AITBC_MOCK_MODE', 'true')
    os.environ.setdefault('AITBC_LOG_LEVEL', 'DEBUG')
    
    # Create test directories if they don't exist
    test_dirs = [
        '/opt/aitbc/tests/tmp',
        '/opt/aitbc/tests/logs',
        '/opt/aitbc/tests/data'
    ]
    
    for test_dir in test_dirs:
        os.makedirs(test_dir, exist_ok=True)

def cleanup_test_environment():
    """Cleanup test environment"""
    # Remove test environment variables
    test_env_vars = ['AITBC_TEST_MODE', 'AITBC_MOCK_MODE', 'AITBC_LOG_LEVEL']
    for var in test_env_vars:
        os.environ.pop(var, None)

# Setup and cleanup hooks
def pytest_configure(config):
    """Pytest configuration hook"""
    setup_test_environment()
    
    # Add custom markers
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "performance: mark test as a performance test"
    )
    config.addinivalue_line(
        "markers", "security: mark test as a security test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )

def pytest_unconfigure(config):
    """Pytest cleanup hook"""
    cleanup_test_environment()

# Test collection hooks
def pytest_collection_modifyitems(config, items):
    """Modify test collection"""
    # Add markers based on test location
    for item in items:
        # Mark tests in performance directory
        if "performance" in str(item.fspath):
            item.add_marker(pytest.mark.performance)
        
        # Mark tests in security directory
        elif "security" in str(item.fspath):
            item.add_marker(pytest.mark.security)
        
        # Mark integration tests
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        
        # Default to unit tests
        else:
            item.add_marker(pytest.mark.unit)

# Test reporting
def pytest_html_report_title(report):
    """Custom HTML report title"""
    report.title = "AITBC Mesh Network Test Report"

# Test discovery
def pytest_ignore_collect(path, config):
    """Ignore certain files during test collection"""
    # Skip __pycache__ directories
    if "__pycache__" in str(path):
        return True
    
    # Skip backup files
    if path.name.endswith(".bak") or path.name.endswith("~"):
        return True
    
    return False
