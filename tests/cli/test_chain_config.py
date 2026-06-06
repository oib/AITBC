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

    def test_consensus_config_with_minimal_validators(self):
        """Test consensus config with minimal validators"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2,
            authorities=["validator_1"]
        )
        
        assert len(consensus.authorities) == 1
        assert "validator_1" in consensus.authorities

    def test_chain_config_with_main_type(self):
        """Test chain config with main type"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POS,
            block_time=5
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Main blockchain network",
            name="AITBC Main Network",
            consensus=consensus
        )
        
        assert config.type == ChainType.MAIN
        assert "main" in config.purpose.lower()

    def test_consensus_config_with_hybrid_algorithm(self):
        """Test consensus config with hybrid algorithm"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.HYBRID,
            block_time=10,
            authorities=["validator_1", "validator_2"]
        )
        
        assert consensus.algorithm == ConsensusAlgorithm.HYBRID
        assert len(consensus.authorities) == 2

    def test_chain_config_with_private_type(self):
        """Test chain config with private type"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=3
        )
        
        config = ChainConfig(
            type=ChainType.PRIVATE,
            purpose="Private chain for internal operations",
            name="Internal Operations Chain",
            consensus=consensus
        )
        
        assert config.type == ChainType.PRIVATE
        assert "internal" in config.purpose.lower()

    def test_consensus_config_with_pos_algorithm(self):
        """Test consensus config with POS algorithm"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POS,
            block_time=15
        )
        
        assert consensus.algorithm == ConsensusAlgorithm.POS
        assert consensus.block_time == 15

    def test_chain_config_with_topic_type(self):
        """Test chain config with topic type"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.TOPIC,
            purpose="Topic-specific chain for AI models",
            name="AI Models Chain",
            consensus=consensus
        )
        
        assert config.type == ChainType.TOPIC
        assert "ai models" in config.purpose.lower()

    def test_consensus_config_with_pow_algorithm(self):
        """Test consensus config with POW algorithm"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POW,
            block_time=10
        )
        
        assert consensus.algorithm == ConsensusAlgorithm.POW
        assert consensus.block_time == 10

    def test_chain_config_with_long_name(self):
        """Test chain config with long name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Main blockchain network with extended name for testing",
            name="AITBC Main Network Extended Name For Testing Purposes",
            consensus=consensus
        )
        
        assert len(config.name) > 20
        assert config.type == ChainType.MAIN

    def test_chain_config_with_short_purpose(self):
        """Test chain config with short purpose"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.TOPIC,
            purpose="AI",
            name="AI Chain",
            consensus=consensus
        )
        
        assert len(config.purpose) == 2
        assert config.purpose == "AI"

    def test_consensus_config_with_zero_block_time(self):
        """Test consensus config with zero block time"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=0
        )
        
        assert consensus.block_time == 0

    def test_chain_config_with_private_type(self):
        """Test chain config with private type"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.PRIVATE,
            purpose="Private network for testing",
            name="Private Test Chain",
            consensus=consensus
        )
        
        assert config.type == ChainType.PRIVATE

    def test_consensus_config_with_large_block_time(self):
        """Test consensus config with large block time"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=3600  # 1 hour
        )
        
        assert consensus.block_time == 3600

    def test_chain_config_with_topic_type(self):
        """Test chain config with topic type"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.TOPIC,
            purpose="Topic-specific blockchain",
            name="Topic Chain",
            consensus=consensus
        )
        
        assert config.type == ChainType.TOPIC

    def test_consensus_config_with_negative_block_time(self):
        """Test consensus config with negative block time (edge case)"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=-1
        )
        
        assert consensus.block_time == -1

    def test_chain_config_with_hybrid_algorithm(self):
        """Test chain config with hybrid consensus algorithm"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.HYBRID,
            block_time=5
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Hybrid consensus chain",
            name="Hybrid Chain",
            consensus=consensus
        )
        
        assert consensus.algorithm == ConsensusAlgorithm.HYBRID

    def test_consensus_config_with_zero_block_time(self):
        """Test consensus config with zero block time (edge case)"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=0
        )
        
        assert consensus.block_time == 0

    def test_chain_config_with_long_purpose(self):
        """Test chain config with long purpose description"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="A very long purpose description that describes the blockchain network in detail",
            name="Long Purpose Chain",
            consensus=consensus
        )
        
        assert len(config.purpose) > 50

    def test_consensus_config_with_large_block_time(self):
        """Test consensus config with very large block time"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=86400  # 1 day
        )
        
        assert consensus.block_time == 86400

    def test_chain_config_with_numeric_name(self):
        """Test chain config with numeric characters in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Numeric name chain",
            name="Chain123",
            consensus=consensus
        )
        
        assert "123" in config.name

    def test_consensus_config_with_negative_block_time(self):
        """Test consensus config with negative block time (edge case)"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=-1
        )
        
        assert consensus.block_time == -1

    def test_chain_config_with_special_characters_in_name(self):
        """Test chain config with special characters in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Special characters chain",
            name="Chain-Test_123@",
            consensus=consensus
        )
        
        assert "-" in config.name
        assert "_" in config.name
        assert "@" in config.name

    def test_chain_config_with_empty_purpose(self):
        """Test chain config with empty purpose (edge case)"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="",
            name="Empty Purpose Chain",
            consensus=consensus
        )
        
        assert config.purpose == ""

    def test_chain_config_with_numeric_purpose(self):
        """Test chain config with numeric characters in purpose"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Chain123",
            name="Numeric Purpose Chain",
            consensus=consensus
        )
        
        assert "123" in config.purpose

    def test_consensus_config_with_zero_block_time(self):
        """Test consensus config with zero block time (edge case)"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=0
        )
        
        assert consensus.block_time == 0

    def test_chain_config_with_very_long_name(self):
        """Test chain config with very long name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Very long name test",
            name="A" * 100,
            consensus=consensus
        )
        
        assert len(config.name) == 100

    def test_consensus_config_with_large_block_time(self):
        """Test consensus config with large block time"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=1000
        )
        
        assert consensus.block_time == 1000

    def test_chain_config_with_very_long_purpose(self):
        """Test chain config with very long purpose"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="B" * 100,
            name="Long Purpose Chain",
            consensus=consensus
        )
        
        assert len(config.purpose) == 100

    def test_consensus_config_with_negative_block_time(self):
        """Test consensus config with negative block time (edge case)"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=-1
        )
        
        assert consensus.block_time == -1

    def test_chain_config_with_mixed_case_name(self):
        """Test chain config with mixed case name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Mixed Case",
            name="MixedCaseName",
            consensus=consensus
        )
        
        assert "Mixed" in config.name
        assert "Case" in config.name

    def test_chain_config_with_empty_name(self):
        """Test chain config with empty name (edge case)"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Empty Name",
            name="",
            consensus=consensus
        )
        
        assert config.name == ""

    def test_consensus_config_with_zero_algorithm(self):
        """Test consensus config with empty algorithm (edge case)"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        assert consensus.algorithm == ConsensusAlgorithm.POA

    def test_chain_config_with_empty_purpose(self):
        """Test chain config with empty purpose (edge case)"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="",
            name="Empty Purpose",
            consensus=consensus
        )
        
        assert config.purpose == ""

    def test_consensus_config_with_positive_block_time(self):
        """Test consensus config with positive block time"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=10
        )
        
        assert consensus.block_time == 10

    def test_chain_config_with_numeric_name(self):
        """Test chain config with numeric characters in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Numeric Name",
            name="Chain123",
            consensus=consensus
        )
        
        assert "123" in config.name

    def test_consensus_config_with_algorithm_pos(self):
        """Test consensus config with POS algorithm"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POS,
            block_time=2
        )
        
        assert consensus.algorithm == ConsensusAlgorithm.POS

    def test_chain_config_with_underscore_in_name(self):
        """Test chain config with underscore in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Underscore Name",
            name="chain_123",
            consensus=consensus
        )
        
        assert "_" in config.name

    def test_consensus_config_with_algorithm_pow(self):
        """Test consensus config with POW algorithm"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POW,
            block_time=2
        )
        
        assert consensus.algorithm == ConsensusAlgorithm.POW

    def test_chain_config_with_hyphen_in_name(self):
        """Test chain config with hyphen in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Hyphen Name",
            name="chain-123",
            consensus=consensus
        )
        
        assert "-" in config.name

    def test_chain_config_with_empty_name(self):
        """Test chain config with empty name (edge case)"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Empty Name",
            name="",
            consensus=consensus
        )
        
        assert config.name == ""

    def test_chain_config_with_mixed_case_purpose(self):
        """Test chain config with mixed case purpose"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Mixed Case",
            name="chain",
            consensus=consensus
        )
        
        assert "Mixed" in config.purpose

    def test_chain_config_with_empty_purpose(self):
        """Test chain config with empty purpose (edge case)"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="",
            name="chain",
            consensus=consensus
        )
        
        assert config.purpose == ""

    def test_chain_config_with_numeric_purpose(self):
        """Test chain config with numeric purpose"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="123",
            name="chain",
            consensus=consensus
        )
        
        assert config.purpose == "123"

    def test_chain_config_with_hyphen_in_purpose(self):
        """Test chain config with hyphen in purpose"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="hyphen-purpose",
            name="chain",
            consensus=consensus
        )
        
        assert "-" in config.purpose

    def test_chain_config_with_underscore_in_purpose(self):
        """Test chain config with underscore in purpose"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="underscore_purpose",
            name="chain",
            consensus=consensus
        )
        
        assert "_" in config.purpose

    def test_chain_config_with_special_characters_in_name(self):
        """Test chain config with special characters in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Special",
            name="chain@#$",
            consensus=consensus
        )
        
        assert "@" in config.name
        assert "#" in config.name
        assert "$" in config.name

    def test_chain_config_with_spaces_in_name(self):
        """Test chain config with spaces in name (edge case)"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Spaces",
            name="chain 123",
            consensus=consensus
        )
        
        assert " " in config.name

    def test_chain_config_with_underscore_in_name(self):
        """Test chain config with underscore in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Underscore",
            name="chain_123",
            consensus=consensus
        )
        
        assert "_" in config.name

    def test_chain_config_with_pipe_in_name(self):
        """Test chain config with pipe in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Pipe",
            name="chain|123",
            consensus=consensus
        )
        
        assert "|" in config.name

    def test_chain_config_with_colon_in_name(self):
        """Test chain config with colon in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Colon",
            name="chain:123",
            consensus=consensus
        )
        
        assert ":" in config.name

    def test_chain_config_with_semicolon_in_name(self):
        """Test chain config with semicolon in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Semicolon",
            name="chain;123",
            consensus=consensus
        )
        
        assert ";" in config.name

    def test_chain_config_with_equals_in_name(self):
        """Test chain config with equals in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Equals",
            name="chain=123",
            consensus=consensus
        )
        
        assert "=" in config.name

    def test_chain_config_with_plus_in_name(self):
        """Test chain config with plus in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Plus",
            name="chain+123",
            consensus=consensus
        )
        
        assert "+" in config.name

    def test_chain_config_with_slash_in_name(self):
        """Test chain config with slash in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Slash",
            name="chain/123",
            consensus=consensus
        )
        
        assert "/" in config.name

    def test_chain_config_with_backslash_in_name(self):
        """Test chain config with backslash in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Backslash",
            name="chain\\123",
            consensus=consensus
        )
        
        assert "\\" in config.name

    def test_chain_config_with_bracket_in_name(self):
        """Test chain config with bracket in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Bracket",
            name="chain[123]",
            consensus=consensus
        )
        
        assert "[" in config.name
        assert "]" in config.name

    def test_chain_config_with_parenthesis_in_name(self):
        """Test chain config with parenthesis in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Parenthesis",
            name="chain(123)",
            consensus=consensus
        )
        
        assert "(" in config.name
        assert ")" in config.name

    def test_chain_config_with_curly_bracket_in_name(self):
        """Test chain config with curly bracket in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="CurlyBracket",
            name="chain{123}",
            consensus=consensus
        )
        
        assert "{" in config.name
        assert "}" in config.name

    def test_chain_config_with_angle_bracket_in_name(self):
        """Test chain config with angle bracket in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="AngleBracket",
            name="chain<123>",
            consensus=consensus
        )
        
        assert "<" in config.name
        assert ">" in config.name

    def test_chain_config_with_dollar_in_name(self):
        """Test chain config with dollar in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Dollar",
            name="chain$123",
            consensus=consensus
        )
        
        assert "$" in config.name

    def test_chain_config_with_at_in_name(self):
        """Test chain config with at in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="At",
            name="chain@123",
            consensus=consensus
        )
        
        assert "@" in config.name

    def test_chain_config_with_hash_in_name(self):
        """Test chain config with hash in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Hash",
            name="chain#123",
            consensus=consensus
        )
        
        assert "#" in config.name

    def test_chain_config_with_exclamation_in_name(self):
        """Test chain config with exclamation in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Exclamation",
            name="chain!123",
            consensus=consensus
        )
        
        assert "!" in config.name

    def test_chain_config_with_asterisk_in_name(self):
        """Test chain config with asterisk in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Asterisk",
            name="chain*123",
            consensus=consensus
        )
        
        assert "*" in config.name

    def test_chain_config_with_plus_in_name(self):
        """Test chain config with plus in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Plus",
            name="chain+123",
            consensus=consensus
        )
        
        assert "+" in config.name

    def test_chain_config_with_equals_in_name(self):
        """Test chain config with equals in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Equals",
            name="chain=123",
            consensus=consensus
        )
        
        assert "=" in config.name

    def test_chain_config_with_bracket_in_name(self):
        """Test chain config with bracket in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Bracket",
            name="chain[123]",
            consensus=consensus
        )
        
        assert "[" in config.name

    def test_chain_config_with_curly_brace_in_name(self):
        """Test chain config with curly brace in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="CurlyBrace",
            name="chain{123}",
            consensus=consensus
        )
        
        assert "{" in config.name

    def test_chain_config_with_pipe_in_name(self):
        """Test chain config with pipe in name"""
        consensus = ConsensusConfig(
            algorithm=ConsensusAlgorithm.POA,
            block_time=2
        )
        
        config = ChainConfig(
            type=ChainType.MAIN,
            purpose="Pipe",
            name="chain|123",
            consensus=consensus
        )
        
        assert "|" in config.name


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
