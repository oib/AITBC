"""
E2E Test Fixtures

This package contains fixtures and test data for end-to-end testing,
including mock home directories for agents and users.
"""

import os
from pathlib import Path
from typing import Dict, List
import pytest


@pytest.fixture
def mock_home_dir():
    """Create a temporary mock home directory for testing"""
    import tempfile
    
    with tempfile.TemporaryDirectory() as temp_dir:
        home_path = Path(temp_dir)
        
        # Create standard AITBC home directory structure
        (home_path / ".aitbc").mkdir(exist_ok=True)
        (home_path / ".aitbc" / "wallets").mkdir(exist_ok=True)
        (home_path / ".aitbc" / "config").mkdir(exist_ok=True)
        (home_path / ".aitbc" / "cache").mkdir(exist_ok=True)
        
        yield home_path


@pytest.fixture
def agent_home_dirs():
    """Create mock agent home directories for testing"""
    import tempfile
    
    with tempfile.TemporaryDirectory() as temp_dir:
        base_path = Path(temp_dir)
        
        # Create agent home directories
        agents = {}
        for agent_name in ["client1", "miner1", "agent1", "agent2"]:
            agent_path = base_path / agent_name
            agent_path.mkdir(exist_ok=True)
            
            # Create AITBC structure
            (agent_path / ".aitbc").mkdir(exist_ok=True)
            (agent_path / ".aitbc" / "wallets").mkdir(exist_ok=True)
            (agent_path / ".aitbc" / "config").mkdir(exist_ok=True)
            
            # Create default config
            config_file = agent_path / ".aitbc" / "config.yaml"
            config_file.write_text(f"""
agent:
  name: {agent_name}
  type: {"client" if "client" in agent_name else "miner" if "miner" in agent_name else "agent"}
  wallet_path: ~/.aitbc/wallets/{agent_name}_wallet.json

node:
  endpoint: http://localhost:8082
  timeout: 30

coordinator:
  url: http://localhost:8000
  api_key: null
""")
            
            agents[agent_name] = agent_path
        
        yield agents


@pytest.fixture
def fixture_home_dirs():
    """Access to the actual fixture home directories"""
    fixture_path = Path(__file__).parent / "home"
    
    if not fixture_path.exists():
        pytest.skip("Fixture home directories not found")
    
    return fixture_path


class HomeDirManager:
    """Manager for test home directories"""
    
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.created_dirs: List[Path] = []
    
    def create_agent_home(self, agent_name: str, agent_type: str = "agent") -> Path:
        """Create a new agent home directory"""
        agent_path = self.base_path / agent_name
        agent_path.mkdir(exist_ok=True)
        
        # Create AITBC structure
        (agent_path / ".aitbc").mkdir(exist_ok=True)
        (agent_path / ".aitbc" / "wallets").mkdir(exist_ok=True)
        (agent_path / ".aitbc" / "config").mkdir(exist_ok=True)
        
        # Create default config
        config_file = agent_path / ".aitbc" / "config.yaml"
        config_file.write_text(f"""
agent:
  name: {agent_name}
  type: {agent_type}
  wallet_path: ~/.aitbc/wallets/{agent_name}_wallet.json

node:
  endpoint: http://localhost:8082
  timeout: 30

coordinator:
  url: http://localhost:8000
  api_key: null
""")
        
        self.created_dirs.append(agent_path)
        return agent_path
    
    def create_wallet(self, agent_name: str, address: str, balance: int = 0) -> Path:
        """Create a wallet file for an agent"""
        agent_path = self.base_path / agent_name
        wallet_path = agent_path / ".aitbc" / "wallets" / f"{agent_name}_wallet.json"
        
        wallet_data = {
            "address": address,
            "balance": balance,
            "transactions": [],
            "created_at": "2026-03-03T00:00:00Z"
        }
        
        import json
        wallet_path.write_text(json.dumps(wallet_data, indent=2))
        return wallet_path
    
    def cleanup(self):
        """Clean up created directories"""
        for dir_path in self.created_dirs:
            if dir_path.exists():
                import shutil
                shutil.rmtree(dir_path)
        self.created_dirs.clear()


@pytest.fixture
def home_dir_manager(tmp_path):
    """Create a home directory manager for tests"""
    manager = HomeDirManager(tmp_path)
    yield manager
    manager.cleanup()


# Constants for fixture paths
FIXTURE_HOME_PATH = Path(__file__).parent / "home"
CLIENT1_HOME_PATH = FIXTURE_HOME_PATH / "client1"
MINER1_HOME_PATH = FIXTURE_HOME_PATH / "miner1"


def get_fixture_home_path(agent_name: str) -> Path:
    """Get the path to a fixture home directory"""
    return FIXTURE_HOME_PATH / agent_name


def fixture_home_exists(agent_name: str) -> bool:
    """Check if a fixture home directory exists"""
    return get_fixture_home_path(agent_name).exists()


def create_test_wallet(agent_name: str, address: str, balance: int = 0) -> Dict:
    """Create test wallet data"""
    return {
        "address": address,
        "balance": balance,
        "transactions": [],
        "created_at": "2026-03-03T00:00:00Z",
        "agent_name": agent_name
    }


def setup_fixture_homes():
    """Set up the fixture home directories if they don't exist"""
    fixture_path = FIXTURE_HOME_PATH
    
    if not fixture_path.exists():
        fixture_path.mkdir(parents=True, exist_ok=True)
    
    # Create standard agent homes
    for agent_name, agent_type in [("client1", "client"), ("miner1", "miner")]:
        agent_path = fixture_path / agent_name
        agent_path.mkdir(exist_ok=True)
        
        # Create AITBC structure
        (agent_path / ".aitbc").mkdir(exist_ok=True)
        (agent_path / ".aitbc" / "wallets").mkdir(exist_ok=True)
        (agent_path / ".aitbc" / "config").mkdir(exist_ok=True)
        
        # Create default config
        config_file = agent_path / ".aitbc" / "config.yaml"
        config_file.write_text(f"""
agent:
  name: {agent_name}
  type: {agent_type}
  wallet_path: ~/.aitbc/wallets/{agent_name}_wallet.json

node:
  endpoint: http://localhost:8082
  timeout: 30

coordinator:
  url: http://localhost:8000
  api_key: null
""")
        
        # Create empty wallet
        wallet_file = agent_path / ".aitbc" / "wallets" / f"{agent_name}_wallet.json"
        wallet_data = create_test_wallet(agent_name, f"aitbc1{agent_name}", 1000)
        import json
        wallet_file.write_text(json.dumps(wallet_data, indent=2))


# Ensure fixture homes exist when this module is imported
setup_fixture_homes()
