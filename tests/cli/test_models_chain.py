"""
Models Chain Tests
Tests for chain data models
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestChainType:
    """Test ChainType enum"""

    def test_chain_type_values(self):
        """Test ChainType enum values"""
        from aitbc_cli.models.chain import ChainType

        assert ChainType.MAIN == "main"
        assert ChainType.TOPIC == "topic"
        assert ChainType.PRIVATE == "private"
        assert ChainType.TEMPORARY == "temporary"


class TestChainStatus:
    """Test ChainStatus enum"""

    def test_chain_status_values(self):
        """Test ChainStatus enum values"""
        from aitbc_cli.models.chain import ChainStatus

        assert ChainStatus.ACTIVE == "active"
        assert ChainStatus.INACTIVE == "inactive"
        assert ChainStatus.SYNCING == "syncing"
        assert ChainStatus.ERROR == "error"
        assert ChainStatus.MAINTENANCE == "maintenance"


class TestConsensusAlgorithm:
    """Test ConsensusAlgorithm enum"""

    def test_consensus_algorithm_values(self):
        """Test ConsensusAlgorithm enum values"""
        from aitbc_cli.models.chain import ConsensusAlgorithm

        assert ConsensusAlgorithm.POW == "pow"
        assert ConsensusAlgorithm.POS == "pos"
        assert ConsensusAlgorithm.POA == "poa"
        assert ConsensusAlgorithm.HYBRID == "hybrid"


class TestGenesisAccount:
    """Test GenesisAccount model"""

    def test_genesis_account_creation(self):
        """Test GenesisAccount creation"""
        from aitbc_cli.models.chain import GenesisAccount

        account = GenesisAccount(address="0xabc123", balance="1000000000000000000", type="regular")

        assert account.address == "0xabc123"
        assert account.balance == "1000000000000000000"
        assert account.type == "regular"

    def test_genesis_account_defaults(self):
        """Test GenesisAccount with defaults"""
        from aitbc_cli.models.chain import GenesisAccount

        account = GenesisAccount(address="0xabc123", balance="1000000000000000000")

        assert account.type == "regular"


class TestGenesisContract:
    """Test GenesisContract model"""

    def test_genesis_contract_creation(self):
        """Test GenesisContract creation"""
        from aitbc_cli.models.chain import GenesisContract

        contract = GenesisContract(name="TestContract", address="0xdef456", bytecode="0x606060", abi={"name": "test"})

        assert contract.name == "TestContract"
        assert contract.address == "0xdef456"
        assert contract.bytecode == "0x606060"


class TestPrivacyConfig:
    """Test PrivacyConfig model"""

    def test_privacy_config_defaults(self):
        """Test PrivacyConfig with defaults"""
        from aitbc_cli.models.chain import PrivacyConfig

        config = PrivacyConfig()

        assert config.visibility == "public"
        assert config.access_control == "open"
        assert config.require_invitation is False
        assert config.encryption_enabled is False


class TestConsensusConfig:
    """Test ConsensusConfig model"""

    def test_consensus_config_creation(self):
        """Test ConsensusConfig creation"""
        from aitbc_cli.models.chain import ConsensusAlgorithm, ConsensusConfig

        config = ConsensusConfig(algorithm=ConsensusAlgorithm.POS, block_time=10, max_validators=50)

        assert config.algorithm == ConsensusAlgorithm.POS
        assert config.block_time == 10
        assert config.max_validators == 50

    def test_consensus_config_defaults(self):
        """Test ConsensusConfig with defaults"""
        from aitbc_cli.models.chain import ConsensusAlgorithm, ConsensusConfig

        config = ConsensusConfig(algorithm=ConsensusAlgorithm.POW)

        assert config.block_time == 5
        assert config.max_validators == 100


class TestChainParameters:
    """Test ChainParameters model"""

    def test_chain_parameters_defaults(self):
        """Test ChainParameters with defaults"""
        from aitbc_cli.models.chain import ChainParameters

        params = ChainParameters()

        assert params.max_block_size == 1048576
        assert params.max_gas_per_block == 10000000
        assert params.min_gas_price == 1000000000


class TestChainLimits:
    """Test ChainLimits model"""

    def test_chain_limits_defaults(self):
        """Test ChainLimits with defaults"""
        from aitbc_cli.models.chain import ChainLimits

        limits = ChainLimits()

        assert limits.max_participants == 1000
        assert limits.max_contracts == 100
        assert limits.max_transactions_per_block == 500


class TestGenesisConfig:
    """Test GenesisConfig model"""

    def test_genesis_config_creation(self):
        """Test GenesisConfig creation"""
        from aitbc_cli.models.chain import ChainType, ConsensusAlgorithm, ConsensusConfig, GenesisConfig

        config = GenesisConfig(
            chain_type=ChainType.MAIN,
            purpose="test",
            name="TestChain",
            consensus=ConsensusConfig(algorithm=ConsensusAlgorithm.POW),
        )

        assert config.chain_type == ChainType.MAIN
        assert config.purpose == "test"
        assert config.name == "TestChain"

    def test_genesis_config_defaults(self):
        """Test GenesisConfig with defaults"""
        from aitbc_cli.models.chain import ChainType, ConsensusAlgorithm, ConsensusConfig, GenesisConfig

        config = GenesisConfig(
            chain_type=ChainType.TOPIC,
            purpose="test",
            name="TestChain",
            consensus=ConsensusConfig(algorithm=ConsensusAlgorithm.POS),
        )

        assert config.parent_hash == "0x0000000000000000000000000000000000000000000000000000000000000000"
        assert config.gas_limit == 10000000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
