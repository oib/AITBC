"""
Models Init Tests
Tests for models package initialization
"""


import pytest


class TestModelsInit:
    """Test models package initialization"""

    def test_models_module_exists(self):
        """Test that models module can be imported"""
        from models import chain

        assert chain is not None

    def test_models_chain_module(self):
        """Test that chain module has expected exports"""
        from models.chain import (
            ChainConfig,
            ChainLimits,
            ChainParameters,
            ChainStatus,
            ChainType,
            ConsensusAlgorithm,
            ConsensusConfig,
            GenesisAccount,
            GenesisConfig,
            GenesisContract,
            PrivacyConfig,
        )

        assert ChainType is not None
        assert ChainStatus is not None
        assert ConsensusAlgorithm is not None
        assert GenesisAccount is not None
        assert GenesisContract is not None
        assert PrivacyConfig is not None
        assert ConsensusConfig is not None
        assert ChainParameters is not None
        assert ChainLimits is not None
        assert GenesisConfig is not None
        assert ChainConfig is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
