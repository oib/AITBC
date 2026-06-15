"""
Core Config Tests
Tests for multi-chain configuration management
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import yaml

import pytest


class TestNodeConfig:
    """Test NodeConfig class"""

    def test_node_config_creation(self):
        """Test NodeConfig creation with all fields"""
        from aitbc_cli.core.config import NodeConfig

        config = NodeConfig(id="node1", endpoint="http://localhost:8202", timeout=30, retry_count=3, max_connections=10)

        assert config.id == "node1"
        assert config.endpoint == "http://localhost:8202"
        assert config.timeout == 30
        assert config.retry_count == 3
        assert config.max_connections == 10

    def test_node_config_defaults(self):
        """Test NodeConfig with default values"""
        from aitbc_cli.core.config import NodeConfig

        config = NodeConfig(id="node1", endpoint="http://localhost:8202")

        assert config.timeout == 30
        assert config.retry_count == 3
        assert config.max_connections == 10


class TestChainConfig:
    """Test ChainConfig class"""

    def test_chain_config_defaults(self):
        """Test ChainConfig with default values"""
        from aitbc_cli.core.config import ChainConfig

        config = ChainConfig()

        assert config.default_gas_limit == 10000000
        assert config.default_gas_price == 20000000000
        assert config.max_block_size == 1048576
        assert config.max_concurrent_chains == 100


class TestMultiChainConfig:
    """Test MultiChainConfig class"""

    def test_multichain_config_defaults(self):
        """Test MultiChainConfig with default values"""
        from aitbc_cli.core.config import MultiChainConfig

        config = MultiChainConfig()

        assert config.logging_level == "INFO"
        assert config.enable_caching is True
        assert config.cache_ttl == 300
        assert config.nodes == {}

    def test_multichain_config_with_nodes(self):
        """Test MultiChainConfig with nodes"""
        from aitbc_cli.core.config import MultiChainConfig, NodeConfig

        node = NodeConfig(id="node1", endpoint="http://localhost:8202")
        config = MultiChainConfig(nodes={"node1": node})

        assert "node1" in config.nodes
        assert config.nodes["node1"].id == "node1"


class TestLoadMultichainConfig:
    """Test load_multichain_config function"""

    def test_load_config_default_path(self):
        """Test loading config with default path when file doesn't exist"""
        from aitbc_cli.core.config import load_multichain_config

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"

            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                config = load_multichain_config(str(config_path))

            assert config is not None
            assert config.logging_level == "INFO"

    def test_load_config_from_file(self):
        """Test loading config from existing file"""
        from aitbc_cli.core.config import load_multichain_config

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_data = {
                "nodes": {},
                "chains": {
                    "default_gas_limit": 10000000,
                    "default_gas_price": 20000000000,
                    "max_block_size": 1048576,
                    "backup_path": "./backups",
                    "max_concurrent_chains": 100,
                },
                "logging_level": "DEBUG",
                "enable_caching": False,
                "cache_ttl": 600,
            }

            with open(config_path, "w") as f:
                yaml.dump(config_data, f)

            config = load_multichain_config(str(config_path))

            assert config.logging_level == "DEBUG"
            assert config.enable_caching is False
            assert config.cache_ttl == 600


class TestSaveMultichainConfig:
    """Test save_multichain_config function"""

    def test_save_config(self):
        """Test saving config to file"""
        from aitbc_cli.core.config import MultiChainConfig, save_multichain_config

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config = MultiChainConfig(logging_level="DEBUG")

            save_multichain_config(config, str(config_path))

            assert config_path.exists()

            with open(config_path) as f:
                loaded_data = yaml.safe_load(f)

            assert loaded_data["logging_level"] == "DEBUG"


class TestGetDefaultNodeConfig:
    """Test get_default_node_config function"""

    def test_get_default_node_config(self):
        """Test getting default node configuration"""
        from aitbc_cli.core.config import get_default_node_config

        config = get_default_node_config()

        assert config.id == "default-node"
        assert config.endpoint == "http://localhost:8202"
        assert config.timeout == 30


class TestAddNodeConfig:
    """Test add_node_config function"""

    def test_add_node_config(self):
        """Test adding a node configuration"""
        from aitbc_cli.core.config import MultiChainConfig, NodeConfig, add_node_config

        config = MultiChainConfig()
        node = NodeConfig(id="node1", endpoint="http://localhost:8202")

        updated_config = add_node_config(config, node)

        assert "node1" in updated_config.nodes
        assert updated_config.nodes["node1"].id == "node1"


class TestRemoveNodeConfig:
    """Test remove_node_config function"""

    def test_remove_node_config(self):
        """Test removing a node configuration"""
        from aitbc_cli.core.config import MultiChainConfig, NodeConfig, remove_node_config

        node = NodeConfig(id="node1", endpoint="http://localhost:8202")
        config = MultiChainConfig(nodes={"node1": node})

        updated_config = remove_node_config(config, "node1")

        assert "node1" not in updated_config.nodes

    def test_remove_nonexistent_node(self):
        """Test removing non-existent node"""
        from aitbc_cli.core.config import MultiChainConfig, remove_node_config

        config = MultiChainConfig()

        updated_config = remove_node_config(config, "nonexistent")

        assert "nonexistent" not in updated_config.nodes


class TestGetNodeConfig:
    """Test get_node_config function"""

    def test_get_node_config_exists(self):
        """Test getting existing node configuration"""
        from aitbc_cli.core.config import MultiChainConfig, NodeConfig, get_node_config

        node = NodeConfig(id="node1", endpoint="http://localhost:8202")
        config = MultiChainConfig(nodes={"node1": node})

        result = get_node_config(config, "node1")

        assert result is not None
        assert result.id == "node1"

    def test_get_node_config_not_exists(self):
        """Test getting non-existent node configuration"""
        from aitbc_cli.core.config import MultiChainConfig, get_node_config

        config = MultiChainConfig()

        result = get_node_config(config, "nonexistent")

        assert result is None


class TestListNodeConfigs:
    """Test list_node_configs function"""

    def test_list_node_configs(self):
        """Test listing all node configurations"""
        from aitbc_cli.core.config import MultiChainConfig, NodeConfig, list_node_configs

        node1 = NodeConfig(id="node1", endpoint="http://localhost:8202")
        node2 = NodeConfig(id="node2", endpoint="http://localhost:8203")
        config = MultiChainConfig(nodes={"node1": node1, "node2": node2})

        result = list_node_configs(config)

        assert len(result) == 2
        assert "node1" in result
        assert "node2" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
