"""
CLI Command Tests
Tests for CLI command models and utilities
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest

from aitbc_cli.models.chain import (
    ChainType,
    ChainStatus,
    ConsensusAlgorithm,
    ConsensusConfig,
    ChainConfig,
    ChainInfo,
)


class TestChainEnums:
    """Test chain enumeration models"""

    def test_chain_type_values(self):
        """Test chain type enum values"""
        assert ChainType.MAIN.value == "main"
        assert ChainType.TOPIC.value == "topic"
        assert ChainType.PRIVATE.value == "private"
        assert ChainType.TEMPORARY.value == "temporary"

    def test_chain_status_values(self):
        """Test chain status enum values"""
        assert ChainStatus.ACTIVE.value == "active"
        assert ChainStatus.INACTIVE.value == "inactive"
        assert ChainStatus.SYNCING.value == "syncing"
        assert ChainStatus.ERROR.value == "error"
        assert ChainStatus.MAINTENANCE.value == "maintenance"

    def test_consensus_algorithm_values(self):
        """Test consensus algorithm enum values"""
        assert ConsensusAlgorithm.POW.value == "pow"
        assert ConsensusAlgorithm.POS.value == "pos"
        assert ConsensusAlgorithm.POA.value == "poa"
        assert ConsensusAlgorithm.HYBRID.value == "hybrid"


class TestConsensusConfig:
    """Test consensus configuration model"""

    def test_consensus_config_creation(self):
        """Test creating a consensus configuration"""
        config = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POS,
            block_time=5,
            max_validators=100
        )
        
        assert config.algorithm == ConsensusAlgorithm.POS
        assert config.block_time == 5
        assert config.max_validators == 100

    def test_consensus_config_defaults(self):
        """Test consensus configuration with defaults"""
        config = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POW
        )
        
        assert config.algorithm == ConsensusAlgorithm.POW
        assert config.block_time == 5  # default
        assert config.max_validators == 100  # default


class TestChainConfig:
    """Test chain configuration model"""

    def test_chain_config_creation(self):
        """Test creating a chain configuration"""
        consensus = ConsensusConfig(algorithm=ConsensusAlgorithm.POS)
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Main production chain",
            name="AITBC Mainnet",
            consensus=consensus
        )
        
        assert config.type == ChainType.MAIN
        assert config.purpose == "Main production chain"
        assert config.name == "AITBC Mainnet"
        assert config.consensus.algorithm == ConsensusAlgorithm.POS

    def test_chain_config_with_description(self):
        """Test chain configuration with description"""
        consensus = ConsensusConfig(algorithm=ConsensusAlgorithm.POA)
        config = ChainConfig(
            type=ChainType.PRIVATE,
            purpose="Private testing chain",
            name="AITBC Testnet",
            description="Private chain for testing",
            consensus=consensus
        )
        
        assert config.description == "Private chain for testing"
        assert config.type == ChainType.PRIVATE

    def test_chain_config_hybrid_consensus(self):
        """Test chain configuration with hybrid consensus"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.HYBRID,
            block_time=10,
            max_validators=50
        )
        config = ChainConfig(
            type=ChainType.TOPIC,
            purpose="Topic-specific chain",
            name="AITBC Topic Chain",
            consensus=consensus
        )
        
        assert config.type == ChainType.TOPIC
        assert config.consensus.algorithm == ConsensusAlgorithm.HYBRID
        assert config.consensus.block_time == 10
        assert config.consensus.max_validators == 50

    def test_chain_config_temporary_chain(self):
        """Test chain configuration for temporary chain"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POW,
            block_time=15,
            authorities=["validator1", "validator2"]
        )
        config = ChainConfig(
            type=ChainType.TEMPORARY,
            purpose="Temporary task chain",
            name="AITBC Task Chain",
            consensus=consensus
        )
        
        assert config.type == ChainType.TEMPORARY
        assert config.purpose == "Temporary task chain"
        assert len(config.consensus.authorities) == 2

    def test_chain_config_with_genesis(self):
        """Test chain configuration with genesis settings"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POS,
            block_time=5,
            max_validators=100
        )
        config = ChainConfig(
            type=ChainType.TOPIC,
            purpose="Topic chain with genesis",
            name="AITBC Topic Chain",
            consensus=consensus
        )
        
        assert config.type == ChainType.TOPIC
        assert config.consensus.algorithm == ConsensusAlgorithm.POS
        assert config.consensus.block_time == 5

    def test_chain_status_values(self):
        """Test chain status enum values"""
        statuses = [
            ChainStatus.ACTIVE,
            ChainStatus.INACTIVE,
            ChainStatus.SYNCING,
            ChainStatus.ERROR,
            ChainStatus.MAINTENANCE
        ]
        
        for status in statuses:
            assert isinstance(status.value, str)

    def test_consensus_algorithm_values(self):
        """Test consensus algorithm enum values"""
        algorithms = [
            ConsensusAlgorithm.POW,
            ConsensusAlgorithm.POS,
            ConsensusAlgorithm.POA,
            ConsensusAlgorithm.HYBRID
        ]
        
        for algo in algorithms:
            assert isinstance(algo.value, str)

    def test_chain_type_values(self):
        """Test chain type enum values"""
        types = [
            ChainType.MAIN,
            ChainType.TOPIC,
            ChainType.PRIVATE,
            ChainType.TEMPORARY
        ]
        
        for chain_type in types:
            assert isinstance(chain_type.value, str)

    def test_consensus_config_with_all_fields(self):
        """Test consensus config with all fields"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POS,
            block_time=10,
            max_validators=50,
            authorities=["validator1", "validator2", "validator3"]
        )
        
        assert consensus.algorithm == ConsensusAlgorithm.POS
        assert consensus.block_time == 10
        assert consensus.max_validators == 50
        assert len(consensus.authorities) == 3

    def test_consensus_config_minimal(self):
        """Test consensus config with minimal fields"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POW,
            block_time=15
        )
        
        assert consensus.algorithm == ConsensusAlgorithm.POW
        assert consensus.block_time == 15
        assert len(consensus.authorities) == 0

    def test_chain_config_with_multiple_steps(self):
        """Test chain config with multiple genesis steps"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POS,
            block_time=5,
            max_validators=100
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Main chain with multi-step genesis",
            name="AITBC Main Chain",
            consensus=consensus
        )
        
        assert config.type == ChainType.MAIN
        assert config.consensus.algorithm == ConsensusAlgorithm.POS
        assert config.name == "AITBC Main Chain"

    def test_chain_config_purpose_validation(self):
        """Test chain config purpose field"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.TOPIC,
            purpose="Topic-specific chain for GPU marketplace",
            name="GPU Marketplace Chain",
            consensus=consensus
        )
        
        assert "gpu marketplace" in config.purpose.lower()
        assert config.type == ChainType.TOPIC


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
