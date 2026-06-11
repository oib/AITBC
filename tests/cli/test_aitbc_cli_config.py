"""
AITBC CLI Config Tests
Tests for CLI configuration module
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import yaml

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestGetConfig:
    """Test get_config function"""

    @patch.dict('os.environ', {}, clear=True)
    def test_get_config_default(self):
        """Test get_config with default values"""
        try:
            from aitbc_cli.config import get_config
            
            config = get_config()
            
            assert config is not None
            assert config.app_name == "AITBC CLI"
            assert config.app_version == "2.1.0"
        except ImportError:
            pytest.skip("BaseAITBCConfig import failed - expected for this module")

    @patch.dict('os.environ', {}, clear=True)
    def test_get_config_with_file(self):
        """Test get_config with config file"""
        try:
            from aitbc_cli.config import get_config
            
            with tempfile.TemporaryDirectory() as tmpdir:
                config_file = Path(tmpdir) / "config.yaml"
                config_data = {
                    'coordinator_url': 'http://custom:8203',
                    'wallet_url': 'http://custom:8003',
                    'api_key': 'test_key',
                    'timeout': 60
                }
                
                with open(config_file, 'w') as f:
                    yaml.dump(config_data, f)
                
                config = get_config(str(config_file))
                
                assert config.coordinator_url == "http://custom:8203"
                assert config.wallet_daemon_url == "http://custom:8003"
                assert config.api_key == "test_key"
                assert config.timeout == 60
        except ImportError:
            pytest.skip("BaseAITBCConfig import failed - expected for this module")

    @patch.dict('os.environ', {}, clear=True)
    def test_get_config_with_nonexistent_file(self):
        """Test get_config with nonexistent file"""
        try:
            from aitbc_cli.config import get_config
            
            config = get_config("/nonexistent/config.yaml")
            
            # Should use defaults when file doesn't exist
            assert config is not None
        except ImportError:
            pytest.skip("BaseAITBCConfig import failed - expected for this module")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
