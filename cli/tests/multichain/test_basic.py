"""
Basic test for multi-chain CLI functionality
"""

import pytest
import asyncio
import tempfile
import yaml
from pathlib import Path
from aitbc_cli.core.config import MultiChainConfig, load_multichain_config
from aitbc_cli.core.chain_manager import ChainManager
from aitbc_cli.core.genesis_generator import GenesisGenerator
from aitbc_cli.models.chain import ChainConfig, ChainType, ConsensusAlgorithm, ConsensusConfig, PrivacyConfig

def test_multichain_config():
    """Test multi-chain configuration"""
    config = MultiChainConfig()
    
    assert config.chains.default_gas_limit == 10000000
    assert config.chains.default_gas_price == 20000000000
    assert config.logging_level == "INFO"
    assert config.enable_caching is True

def test_chain_config():
    """Test chain configuration model"""
    consensus_config = ConsensusConfig(
        algorithm=ConsensusAlgorithm.POS,
        block_time=5,
        max_validators=21
    )
    
    privacy_config = PrivacyConfig(
        visibility="private",
        access_control="invite_only"
    )
    
    chain_config = ChainConfig(
        type=ChainType.PRIVATE,
        purpose="test",
        name="Test Chain",
        consensus=consensus_config,
        privacy=privacy_config
    )
    
    assert chain_config.type == ChainType.PRIVATE
    assert chain_config.purpose == "test"
    assert chain_config.consensus.algorithm == ConsensusAlgorithm.POS
    assert chain_config.privacy.visibility == "private"

def test_genesis_generator():
    """Test genesis generator"""
    config = MultiChainConfig()
    generator = GenesisGenerator(config)
    
    # Test template listing
    templates = generator.list_templates()
    assert isinstance(templates, dict)
    assert "private" in templates
    assert "topic" in templates
    assert "research" in templates

async def test_chain_manager():
    """Test chain manager"""
    config = MultiChainConfig()
    chain_manager = ChainManager(config)
    
    # Test listing chains (should return empty list initially)
    chains = await chain_manager.list_chains()
    assert isinstance(chains, list)

def test_config_file_operations():
    """Test configuration file operations"""
    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = Path(temp_dir) / "test_config.yaml"
        
        # Create test config
        config = MultiChainConfig()
        config.chains.default_gas_limit = 20000000
        
        # Save config
        from aitbc_cli.core.config import save_multichain_config
        save_multichain_config(config, str(config_path))
        
        # Load config
        loaded_config = load_multichain_config(str(config_path))
        assert loaded_config.chains.default_gas_limit == 20000000

def test_chain_config_file():
    """Test chain configuration from file"""
    chain_config_data = {
        "chain": {
            "type": "topic",
            "purpose": "healthcare",
            "name": "Healthcare Chain",
            "consensus": {
                "algorithm": "pos",
                "block_time": 5
            },
            "privacy": {
                "visibility": "public",
                "access_control": "open"
            }
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(chain_config_data, f)
        config_file = f.name
    
    try:
        # Load and validate
        with open(config_file, 'r') as f:
            data = yaml.safe_load(f)
        
        chain_config = ChainConfig(**data['chain'])
        assert chain_config.type == ChainType.TOPIC
        assert chain_config.purpose == "healthcare"
        assert chain_config.consensus.algorithm == ConsensusAlgorithm.POS
        
    finally:
        Path(config_file).unlink()

if __name__ == "__main__":
    # Run basic tests
    test_multichain_config()
    test_chain_config()
    test_genesis_generator()
    asyncio.run(test_chain_manager())
    test_config_file_operations()
    test_chain_config_file()
    
    print("✅ All basic tests passed!")
