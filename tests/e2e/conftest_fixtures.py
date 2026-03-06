"""
E2E Test Fixtures Configuration

Extended pytest configuration for home directory fixtures
and test data management for end-to-end testing.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional
import json
import yaml


@pytest.fixture(scope="session")
def fixture_base_path():
    """Base path for all test fixtures"""
    return Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def test_home_dirs(fixture_base_path):
    """Access to test home directories"""
    home_path = fixture_base_path / "home"
    
    if not home_path.exists():
        pytest.skip("Test home directories not found")
    
    return home_path


@pytest.fixture
def temp_home_dirs():
    """Create temporary home directories for testing"""
    with tempfile.TemporaryDirectory() as temp_dir:
        base_path = Path(temp_dir)
        
        # Create standard AITBC home structure
        agents = {}
        
        for agent_name in ["test_client", "test_miner", "test_agent"]:
            agent_path = base_path / agent_name
            agent_path.mkdir(exist_ok=True)
            
            # Create AITBC directory structure
            aitbc_dir = agent_path / ".aitbc"
            aitbc_dir.mkdir(exist_ok=True)
            
            (aitbc_dir / "wallets").mkdir(exist_ok=True)
            (aitbc_dir / "config").mkdir(exist_ok=True)
            (aitbc_dir / "cache").mkdir(exist_ok=True)
            
            # Create default configuration
            config_data = {
                "agent": {
                    "name": agent_name,
                    "type": "client" if "client" in agent_name else "miner" if "miner" in agent_name else "agent",
                    "wallet_path": f"~/.aitbc/wallets/{agent_name}_wallet.json"
                },
                "node": {
                    "endpoint": "http://localhost:8082",
                    "timeout": 30
                },
                "coordinator": {
                    "url": "http://localhost:8000",
                    "api_key": None
                }
            }
            
            config_file = aitbc_dir / "config.yaml"
            with open(config_file, 'w') as f:
                yaml.dump(config_data, f, default_flow_style=False)
            
            agents[agent_name] = agent_path
        
        yield agents
        
        # Cleanup is handled by tempfile


@pytest.fixture
def mock_agent_wallet(temp_home_dirs):
    """Create a mock agent wallet for testing"""
    agent_path = temp_home_dirs["test_client"]
    wallet_path = agent_path / ".aitbc" / "wallets" / "test_client_wallet.json"
    
    wallet_data = {
        "address": "aitbc1testclient",
        "balance": 1000,
        "transactions": [],
        "created_at": "2026-03-03T00:00:00Z"
    }
    
    with open(wallet_path, 'w') as f:
        json.dump(wallet_data, f, indent=2)
    
    return wallet_data


@pytest.fixture
def mock_miner_wallet(temp_home_dirs):
    """Create a mock miner wallet for testing"""
    agent_path = temp_home_dirs["test_miner"]
    wallet_path = agent_path / ".aitbc" / "wallets" / "test_miner_wallet.json"
    
    wallet_data = {
        "address": "aitbc1testminer",
        "balance": 5000,
        "transactions": [],
        "created_at": "2026-03-03T00:00:00Z",
        "mining_rewards": 2000
    }
    
    with open(wallet_path, 'w') as f:
        json.dump(wallet_data, f, indent=2)
    
    return wallet_data


class HomeDirFixture:
    """Helper class for managing home directory fixtures"""
    
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.created_dirs: List[Path] = []
    
    def create_agent_home(self, 
                         agent_name: str, 
                         agent_type: str = "agent",
                         initial_balance: int = 0) -> Path:
        """Create a new agent home directory with AITBC structure"""
        agent_path = self.base_path / agent_name
        agent_path.mkdir(exist_ok=True)
        
        # Create AITBC directory structure
        aitbc_dir = agent_path / ".aitbc"
        aitbc_dir.mkdir(exist_ok=True)
        
        (aitbc_dir / "wallets").mkdir(exist_ok=True)
        (aitbc_dir / "config").mkdir(exist_ok=True)
        (aitbc_dir / "cache").mkdir(exist_ok=True)
        
        # Create configuration
        config_data = {
            "agent": {
                "name": agent_name,
                "type": agent_type,
                "wallet_path": f"~/.aitbc/wallets/{agent_name}_wallet.json"
            },
            "node": {
                "endpoint": "http://localhost:8082",
                "timeout": 30
            },
            "coordinator": {
                "url": "http://localhost:8000",
                "api_key": None
            }
        }
        
        config_file = aitbc_dir / "config.yaml"
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f, default_flow_style=False)
        
        # Create wallet
        wallet_data = {
            "address": f"aitbc1{agent_name}",
            "balance": initial_balance,
            "transactions": [],
            "created_at": "2026-03-03T00:00:00Z"
        }
        
        wallet_file = aitbc_dir / "wallets" / f"{agent_name}_wallet.json"
        with open(wallet_file, 'w') as f:
            json.dump(wallet_data, f, indent=2)
        
        self.created_dirs.append(agent_path)
        return agent_path
    
    def create_multi_agent_setup(self, agent_configs: List[Dict]) -> Dict[str, Path]:
        """Create multiple agent homes from configuration"""
        agents = {}
        
        for config in agent_configs:
            agent_path = self.create_agent_home(
                agent_name=config["name"],
                agent_type=config["type"],
                initial_balance=config.get("initial_balance", 0)
            )
            agents[config["name"]] = agent_path
        
        return agents
    
    def get_agent_config(self, agent_name: str) -> Optional[Dict]:
        """Get configuration for an agent"""
        agent_path = self.base_path / agent_name
        config_file = agent_path / ".aitbc" / "config.yaml"
        
        if config_file.exists():
            with open(config_file, 'r') as f:
                return yaml.safe_load(f)
        
        return None
    
    def get_agent_wallet(self, agent_name: str) -> Optional[Dict]:
        """Get wallet data for an agent"""
        agent_path = self.base_path / agent_name
        wallet_file = agent_path / ".aitbc" / "wallets" / f"{agent_name}_wallet.json"
        
        if wallet_file.exists():
            with open(wallet_file, 'r') as f:
                return json.load(f)
        
        return None
    
    def cleanup(self):
        """Clean up all created directories"""
        for dir_path in self.created_dirs:
            if dir_path.exists():
                shutil.rmtree(dir_path)
        self.created_dirs.clear()


@pytest.fixture
def home_dir_fixture(tmp_path):
    """Create a home directory fixture manager"""
    fixture = HomeDirFixture(tmp_path)
    yield fixture
    fixture.cleanup()


@pytest.fixture
def standard_test_agents(home_dir_fixture):
    """Create standard test agents for E2E testing"""
    agent_configs = [
        {"name": "client1", "type": "client", "initial_balance": 1000},
        {"name": "client2", "type": "client", "initial_balance": 500},
        {"name": "miner1", "type": "miner", "initial_balance": 2000},
        {"name": "miner2", "type": "miner", "initial_balance": 1500},
        {"name": "agent1", "type": "agent", "initial_balance": 800},
        {"name": "agent2", "type": "agent", "initial_balance": 1200}
    ]
    
    return home_dir_fixture.create_multi_agent_setup(agent_configs)


@pytest.fixture
def cross_container_test_setup(home_dir_fixture):
    """Create test setup for cross-container E2E tests"""
    # Create agents for different containers/sites
    agent_configs = [
        {"name": "localhost_client", "type": "client", "initial_balance": 1000},
        {"name": "aitbc_client", "type": "client", "initial_balance": 2000},
        {"name": "aitbc1_client", "type": "client", "initial_balance": 1500},
        {"name": "localhost_miner", "type": "miner", "initial_balance": 3000},
        {"name": "aitbc_miner", "type": "miner", "initial_balance": 2500},
        {"name": "aitbc1_miner", "type": "miner", "initial_balance": 2800}
    ]
    
    return home_dir_fixture.create_multi_agent_setup(agent_configs)


# Helper functions for test development
def create_test_transaction(from_addr: str, to_addr: str, amount: int, tx_hash: str = None) -> Dict:
    """Create a test transaction for wallet testing"""
    import hashlib
    
    if tx_hash is None:
        tx_hash = hashlib.sha256(f"{from_addr}{to_addr}{amount}".encode()).hexdigest()
    
    return {
        "hash": tx_hash,
        "from": from_addr,
        "to": to_addr,
        "amount": amount,
        "timestamp": "2026-03-03T12:00:00Z",
        "type": "transfer",
        "status": "confirmed"
    }


def add_transaction_to_wallet(wallet_path: Path, transaction: Dict):
    """Add a transaction to a wallet file"""
    with open(wallet_path, 'r') as f:
        wallet_data = json.load(f)
    
    wallet_data["transactions"].append(transaction)
    
    # Update balance for outgoing transactions
    if transaction["from"] == wallet_data["address"]:
        wallet_data["balance"] -= transaction["amount"]
    # Update balance for incoming transactions
    elif transaction["to"] == wallet_data["address"]:
        wallet_data["balance"] += transaction["amount"]
    
    with open(wallet_path, 'w') as f:
        json.dump(wallet_data, f, indent=2)


def verify_wallet_state(wallet_path: Path, expected_balance: int, min_transactions: int = 0) -> bool:
    """Verify wallet state matches expectations"""
    with open(wallet_path, 'r') as f:
        wallet_data = json.load(f)
    
    return (
        wallet_data["balance"] == expected_balance and
        len(wallet_data["transactions"]) >= min_transactions
    )


# Pytest markers for categorizing E2E tests
pytest.mark.e2e_home_dirs = pytest.mark.e2e_home_dirs("Tests that use home directory fixtures")
pytest.mark.cross_container = pytest.mark.cross_container("Tests that span multiple containers")
pytest.mark.agent_simulation = pytest.mark.agent_simulation("Tests that simulate agent behavior")
pytest.mark.wallet_management = pytest.mark.wallet_management("Tests that focus on wallet operations")
