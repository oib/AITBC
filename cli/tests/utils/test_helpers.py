"""
Test utilities and helpers for AITBC CLI testing
"""

import os
import sys
import tempfile
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import Dict, Any, Optional


class MockConfig:
    """Mock configuration for testing"""
    
    def __init__(self, coordinator_url: str = "http://localhost:8000", 
                 api_key: str = "test-key"):
        self.coordinator_url = coordinator_url
        self.api_key = api_key
        self.timeout = 30
        self.blockchain_rpc_url = "http://localhost:8006"
        self.wallet_url = "http://localhost:8002"
        self.role = None
        self.config_dir = Path(tempfile.mkdtemp()) / ".aitbc"
        self.config_file = None


class MockApiResponse:
    """Mock API response for testing"""
    
    @staticmethod
    def success_response(data: Dict[str, Any]) -> MagicMock:
        """Create a successful API response mock"""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = data
        response.text = json.dumps(data)
        return response
    
    @staticmethod
    def error_response(status_code: int, message: str) -> MagicMock:
        """Create an error API response mock"""
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = {"error": message}
        response.text = message
        return response


class TestEnvironment:
    """Test environment manager"""
    
    def __init__(self):
        self.temp_dirs = []
        self.mock_patches = []
    
    def create_temp_dir(self, prefix: str = "aitbc_test_") -> Path:
        """Create a temporary directory"""
        temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
        self.temp_dirs.append(temp_dir)
        return temp_dir
    
    def create_mock_wallet_dir(self) -> Path:
        """Create a mock wallet directory"""
        wallet_dir = self.create_temp_dir("wallet_")
        (wallet_dir / "wallets").mkdir(exist_ok=True)
        return wallet_dir
    
    def create_mock_config_dir(self) -> Path:
        """Create a mock config directory"""
        config_dir = self.create_temp_dir("config_")
        config_dir.mkdir(exist_ok=True)
        return config_dir
    
    def add_patch(self, patch_obj):
        """Add a patch to be cleaned up later"""
        self.mock_patches.append(patch_obj)
    
    def cleanup(self):
        """Clean up all temporary resources"""
        # Stop all patches
        for patch_obj in self.mock_patches:
            try:
                patch_obj.stop()
            except:
                pass
        
        # Remove temp directories
        for temp_dir in self.temp_dirs:
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except:
                pass
        
        self.temp_dirs.clear()
        self.mock_patches.clear()


def create_test_wallet(wallet_dir: Path, name: str, address: str = "test-address") -> Dict[str, Any]:
    """Create a test wallet file"""
    wallet_data = {
        "name": name,
        "address": address,
        "balance": 1000.0,
        "created_at": "2026-01-01T00:00:00Z",
        "encrypted": False
    }
    
    wallet_file = wallet_dir / "wallets" / f"{name}.json"
    wallet_file.parent.mkdir(exist_ok=True)
    
    with open(wallet_file, 'w') as f:
        json.dump(wallet_data, f, indent=2)
    
    return wallet_data


def create_test_config(config_dir: Path, coordinator_url: str = "http://localhost:8000") -> Dict[str, Any]:
    """Create a test configuration file"""
    config_data = {
        "coordinator_url": coordinator_url,
        "api_key": "test-api-key",
        "timeout": 30,
        "blockchain_rpc_url": "http://localhost:8006",
        "wallet_url": "http://localhost:8002"
    }
    
    config_file = config_dir / "config.yaml"
    with open(config_file, 'w') as f:
        import yaml
        yaml.dump(config_data, f, default_flow_style=False)
    
    return config_data


def mock_api_responses():
    """Common mock API responses for testing"""
    return {
        'blockchain_info': {
            'chain_id': 'ait-devnet',
            'height': 1000,
            'hash': '0x1234567890abcdef',
            'timestamp': '2026-01-01T00:00:00Z'
        },
        'blockchain_status': {
            'status': 'syncing',
            'height': 1000,
            'peers': 5,
            'sync_progress': 85.5
        },
        'wallet_balance': {
            'address': 'test-address',
            'balance': 1000.0,
            'unlocked': 800.0,
            'staked': 200.0
        },
        'node_info': {
            'id': 'test-node',
            'address': 'localhost:8006',
            'status': 'active',
            'chains': ['ait-devnet']
        }
    }


def setup_test_mocks(test_env: TestEnvironment):
    """Setup common test mocks"""
    mocks = {}
    
    # Mock home directory
    mock_home = patch('aitbc_cli.commands.wallet.Path.home')
    mocks['home'] = mock_home.start()
    mocks['home'].return_value = test_env.create_temp_dir("home_")
    test_env.add_patch(mock_home)
    
    # Mock config loading
    mock_config_load = patch('aitbc_cli.config.Config.load_from_file')
    mocks['config_load'] = mock_config_load.start()
    mocks['config_load'].return_value = MockConfig()
    test_env.add_patch(mock_config_load)
    
    # Mock API calls
    mock_httpx = patch('httpx.get')
    mocks['httpx'] = mock_httpx.start()
    test_env.add_patch(mock_httpx)
    
    # Mock authentication
    mock_auth = patch('aitbc_cli.auth.AuthManager')
    mocks['auth'] = mock_auth.start()
    test_env.add_patch(mock_auth)
    
    return mocks


class CommandTestResult:
    """Result of a command test"""
    
    def __init__(self, command: str, exit_code: int, output: str, 
                 error: str = None, duration: float = 0.0):
        self.command = command
        self.exit_code = exit_code
        self.output = output
        self.error = error
        self.duration = duration
        self.success = exit_code == 0
    
    def __str__(self):
        status = "✅ PASS" if self.success else "❌ FAIL"
        return f"{status} [{self.exit_code}] {self.command}"
    
    def contains(self, text: str) -> bool:
        """Check if output contains text"""
        return text in self.output
    
    def contains_any(self, texts: list) -> bool:
        """Check if output contains any of the texts"""
        return any(text in self.output for text in texts)


def run_command_test(runner, command_args: list, 
                    expected_exit_code: int = 0,
                    expected_text: str = None,
                    timeout: int = 30) -> CommandTestResult:
    """Run a command test with validation"""
    import time
    
    start_time = time.time()
    result = runner.invoke(command_args)
    duration = time.time() - start_time
    
    test_result = CommandTestResult(
        command=' '.join(command_args),
        exit_code=result.exit_code,
        output=result.output,
        error=result.stderr,
        duration=duration
    )
    
    # Validate expected exit code
    if result.exit_code != expected_exit_code:
        print(f"⚠️  Expected exit code {expected_exit_code}, got {result.exit_code}")
    
    # Validate expected text
    if expected_text and expected_text not in result.output:
        print(f"⚠️  Expected text '{expected_text}' not found in output")
    
    return test_result


def print_test_header(title: str):
    """Print a test header"""
    print(f"\n{'='*60}")
    print(f"🧪 {title}")
    print('='*60)


def print_test_footer(title: str, passed: int, failed: int, total: int):
    """Print a test footer"""
    print(f"\n{'-'*60}")
    print(f"📊 {title} Results: {passed}/{total} passed ({passed/total*100:.1f}%)")
    if failed > 0:
        print(f"❌ {failed} test(s) failed")
    else:
        print("🎉 All tests passed!")
    print('-'*60)
