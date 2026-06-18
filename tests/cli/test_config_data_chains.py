"""
Config Data Chains Tests
Tests for chain registry configuration
"""

from unittest.mock import patch

import pytest


class TestChainConfig:
    """Test ChainConfig dataclass"""

    def test_chain_config_creation(self):
        """Test ChainConfig creation with all fields"""
        from config_data.chains import ChainConfig

        config = ChainConfig(
            chain_id="ait-mainnet",
            name="AITBC Main Network",
            rpc_url="http://localhost:8202",
            explorer_url="http://localhost:8203",
            is_testnet=False,
            native_currency="AITBC",
        )

        assert config.chain_id == "ait-mainnet"
        assert config.name == "AITBC Main Network"
        assert config.rpc_url == "http://localhost:8202"
        assert config.explorer_url == "http://localhost:8203"
        assert config.is_testnet is False
        assert config.native_currency == "AITBC"

    def test_chain_config_defaults(self):
        """Test ChainConfig with default values"""
        from config_data.chains import ChainConfig

        config = ChainConfig(chain_id="ait-test", name="Test Chain", rpc_url="http://localhost:8025")

        assert config.explorer_url is None
        assert config.is_testnet is False
        assert config.native_currency == "AITBC"


class TestChainRegistry:
    """Test ChainRegistry class"""

    def test_registry_initialization(self):
        """Test registry initialization with default chains"""
        from config_data.chains import ChainRegistry

        registry = ChainRegistry()

        assert len(registry.chains) > 0
        assert "ait-devnet" in registry.chains
        assert "ait-hub.aitbc.bubuit.net" in registry.chains

    def test_get_chain_exists(self):
        """Test getting existing chain"""
        from config_data.chains import ChainRegistry

        registry = ChainRegistry()
        chain = registry.get_chain("ait-devnet")

        assert chain is not None
        assert chain.chain_id == "ait-devnet"
        assert chain.is_testnet is True

    def test_get_chain_not_exists(self):
        """Test getting non-existent chain"""
        from config_data.chains import ChainRegistry

        registry = ChainRegistry()
        chain = registry.get_chain("nonexistent")

        assert chain is None

    def test_get_all_chains(self):
        """Test getting all chains"""
        from config_data.chains import ChainRegistry

        registry = ChainRegistry()
        chains = registry.get_all_chains()

        assert isinstance(chains, dict)
        assert len(chains) > 0

    def test_get_chain_ids(self):
        """Test getting chain IDs"""
        from config_data.chains import ChainRegistry

        registry = ChainRegistry()
        chain_ids = registry.get_chain_ids()

        assert isinstance(chain_ids, list)
        assert "ait-devnet" in chain_ids
        assert "ait-hub.aitbc.bubuit.net" in chain_ids

    def test_get_testnet_chains(self):
        """Test getting testnet chains"""
        from config_data.chains import ChainRegistry

        registry = ChainRegistry()
        testnet_chains = registry.get_testnet_chains()

        assert len(testnet_chains) > 0
        assert "ait-devnet" in testnet_chains
        for chain in testnet_chains.values():
            assert chain.is_testnet is True

    def test_get_mainnet_chains(self):
        """Test getting mainnet chains"""
        from config_data.chains import ChainRegistry

        registry = ChainRegistry()
        mainnet_chains = registry.get_mainnet_chains()

        # Default chains are all testnets, so this should be empty
        assert len(mainnet_chains) == 0

    def test_register_chain(self):
        """Test registering a new chain"""
        from config_data.chains import ChainConfig, ChainRegistry

        registry = ChainRegistry()
        new_chain = ChainConfig(chain_id="ait-custom", name="Custom Chain", rpc_url="http://localhost:9000")

        registry.register_chain("ait-custom", new_chain)

        assert "ait-custom" in registry.chains
        assert registry.chains["ait-custom"].name == "Custom Chain"

    def test_unregister_chain_exists(self):
        """Test unregistering existing chain"""
        from config_data.chains import ChainRegistry

        registry = ChainRegistry()
        result = registry.unregister_chain("ait-devnet")

        assert result is True
        assert "ait-devnet" not in registry.chains

    def test_unregister_chain_not_exists(self):
        """Test unregistering non-existent chain"""
        from config_data.chains import ChainRegistry

        registry = ChainRegistry()
        result = registry.unregister_chain("nonexistent")

        assert result is False

    @patch.dict(
        "os.environ",
        {
            "AITBC_CHAIN_CUSTOM_RPC_URL": "http://localhost:9000",
            "AITBC_CHAIN_CUSTOM_NAME": "Custom Chain",
            "AITBC_CHAIN_CUSTOM_IS_TESTNET": "true",
        },
    )
    def test_load_from_env(self):
        """Test loading chains from environment variables"""
        from config_data.chains import ChainRegistry

        registry = ChainRegistry()
        registry.load_from_env()

        assert "custom" in registry.chains
        assert registry.chains["custom"].name == "Custom Chain"
        assert registry.chains["custom"].is_testnet is True


class TestGetChainRegistry:
    """Test get_chain_registry function"""

    def test_get_chain_registry_singleton(self):
        """Test that chain registry is a singleton"""
        from config_data.chains import get_chain_registry

        registry1 = get_chain_registry()
        registry2 = get_chain_registry()

        assert registry1 is registry2

    def test_get_chain_registry_initializes(self):
        """Test that chain registry initializes on first call"""
        from config_data.chains import get_chain_registry

        registry = get_chain_registry()

        assert registry is not None
        assert len(registry.chains) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
