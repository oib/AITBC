"""
Genesis Generator Tests
Tests for genesis block generator
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestGenesisValidationError:
    """Test GenesisValidationError exception"""

    def test_genesis_validation_error(self):
        """Test GenesisValidationError can be raised"""
        from aitbc_cli.core.genesis_generator import GenesisValidationError

        with pytest.raises(GenesisValidationError):
            raise GenesisValidationError("Genesis validation failed")


class TestGenesisGenerator:
    """Test GenesisGenerator class"""

    @patch('aitbc_cli.core.genesis_generator.MultiChainConfig')
    def test_init(self, mock_config):
        """Test GenesisGenerator initialization"""
        from aitbc_cli.core.genesis_generator import GenesisGenerator

        config = Mock()
        generator = GenesisGenerator(config)

        assert generator.config == config
        assert generator.templates_dir is not None

    @patch('aitbc_cli.core.genesis_generator.MultiChainConfig')
    def test_templates_dir_path(self, mock_config):
        """Test templates directory path"""
        from aitbc_cli.core.genesis_generator import GenesisGenerator

        config = Mock()
        generator = GenesisGenerator(config)

        assert "templates" in str(generator.templates_dir)
        assert "genesis" in str(generator.templates_dir)

    @patch('aitbc_cli.core.genesis_generator.MultiChainConfig')
    def test_merge_configs(self, mock_config):
        """Test config merging"""
        from aitbc_cli.core.genesis_generator import GenesisGenerator

        config = Mock()
        generator = GenesisGenerator(config)

        template = {"genesis": {"chain_id": "template-chain", "name": "Template"}}
        custom = {"genesis": {"name": "Custom", "description": "Custom chain"}}

        merged = generator._merge_configs(template, custom)

        assert merged["genesis"]["chain_id"] == "template-chain"
        assert merged["genesis"]["name"] == "Custom"
        assert merged["genesis"]["description"] == "Custom chain"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
