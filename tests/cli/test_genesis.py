"""Tests for genesis block management CLI commands"""

import os
import json
import yaml
import pytest
from pathlib import Path
from click.testing import CliRunner
from unittest.mock import Mock, patch, MagicMock
from aitbc_cli.commands.genesis import genesis

@pytest.fixture
def runner():
    """Create CLI runner"""
    return CliRunner()

@pytest.fixture
def mock_genesis_generator():
    """Mock GenesisGenerator"""
    with patch('aitbc_cli.commands.genesis.GenesisGenerator') as mock:
        yield mock.return_value

@pytest.fixture
def mock_config():
    """Mock configuration loader"""
    with patch('aitbc_cli.commands.genesis.load_multichain_config') as mock:
        yield mock

@pytest.fixture
def sample_config_yaml(tmp_path):
    """Create a sample config file for testing"""
    config_path = tmp_path / "config.yaml"
    config_data = {
        "genesis": {
            "chain_type": "topic",
            "purpose": "test",
            "name": "Test Chain",
            "consensus": {
                "algorithm": "pos"
            },
            "privacy": {
                "visibility": "public"
            }
        }
    }
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)
    return str(config_path)

@pytest.fixture
def mock_genesis_block():
    """Create a mock genesis block"""
    block = MagicMock()
    block.chain_id = "test-chain-123"
    block.chain_type.value = "topic"
    block.purpose = "test"
    block.name = "Test Chain"
    block.hash = "0xabcdef123456"
    block.privacy.visibility = "public"
    block.dict.return_value = {"chain_id": "test-chain-123", "hash": "0xabcdef123456"}
    return block

@pytest.fixture
def mock_genesis_config():
    """Mock GenesisConfig"""
    with patch('aitbc_cli.commands.genesis.GenesisConfig') as mock:
        yield mock.return_value

class TestGenesisCreateCommand:
    """Test genesis create command"""
    
    def test_create_from_config(self, runner, mock_config, mock_genesis_generator, mock_genesis_config, sample_config_yaml, mock_genesis_block, tmp_path):
        """Test successful genesis creation from config file"""
        # Setup mock
        mock_genesis_generator.create_genesis.return_value = mock_genesis_block
        output_file = str(tmp_path / "genesis.json")
        
        # Run command
        result = runner.invoke(genesis, ['create', sample_config_yaml, '--output', output_file], obj={})
        
        # Assertions
        assert result.exit_code == 0
        assert "Genesis block created successfully" in result.output
        mock_genesis_generator.create_genesis.assert_called_once()
        
        # Check output file exists and is valid JSON
        assert os.path.exists(output_file)
        with open(output_file, 'r') as f:
            data = json.load(f)
            assert data["chain_id"] == "test-chain-123"

    def test_create_from_template(self, runner, mock_config, mock_genesis_generator, mock_genesis_config, sample_config_yaml, mock_genesis_block, tmp_path):
        """Test successful genesis creation using a template"""
        # Setup mock
        mock_genesis_generator.create_from_template.return_value = mock_genesis_block
        output_file = str(tmp_path / "genesis.yaml")
        
        # Run command
        result = runner.invoke(genesis, ['create', sample_config_yaml, '--template', 'default', '--output', output_file, '--format', 'yaml'], obj={})
        
        # Assertions
        assert result.exit_code == 0
        assert "Genesis block created successfully" in result.output
        mock_genesis_generator.create_from_template.assert_called_once_with('default', sample_config_yaml)
        
        # Check output file exists and is valid YAML
        assert os.path.exists(output_file)
        with open(output_file, 'r') as f:
            data = yaml.safe_load(f)
            assert data["chain_id"] == "test-chain-123"

    def test_create_validation_error(self, runner, mock_config, mock_genesis_generator, mock_genesis_config, sample_config_yaml):
        """Test handling of GenesisValidationError"""
        # Setup mock
        from aitbc_cli.core.genesis_generator import GenesisValidationError
        mock_genesis_generator.create_genesis.side_effect = GenesisValidationError("Invalid configuration")
        
        # Run command
        result = runner.invoke(genesis, ['create', sample_config_yaml])
        
        # Assertions
        assert result.exit_code != 0
        assert "Genesis validation error: Invalid configuration" in result.output

    def test_create_general_error(self, runner, mock_config, mock_genesis_generator, mock_genesis_config, sample_config_yaml):
        """Test handling of general exceptions"""
        # Setup mock
        mock_genesis_generator.create_genesis.side_effect = Exception("Unexpected error")
        
        # Run command
        result = runner.invoke(genesis, ['create', sample_config_yaml])
        
        # Assertions
        assert result.exit_code != 0
        assert "Error creating genesis block: Unexpected error" in result.output

    def test_create_missing_config_file(self, runner):
        """Test running command with missing config file"""
        # Run command
        result = runner.invoke(genesis, ['create', 'non_existent_config.yaml'])
        
        # Assertions
        assert result.exit_code != 0
        assert "does not exist" in result.output.lower()
