import sys
import yaml
from click.testing import CliRunner
from unittest.mock import Mock, patch, MagicMock
from aitbc_cli.commands.genesis import genesis

runner = CliRunner()
with patch('aitbc_cli.commands.genesis.GenesisGenerator') as mock_generator_class:
    with patch('aitbc_cli.commands.genesis.load_multichain_config') as mock_config:
        with patch('aitbc_cli.commands.genesis.GenesisConfig') as mock_genesis_config:
            mock_generator = mock_generator_class.return_value
            
            block = MagicMock()
            block.chain_id = "test-chain-123"
            block.chain_type.value = "topic"
            block.purpose = "test"
            block.name = "Test Chain"
            block.hash = "0xabcdef123456"
            block.privacy.visibility = "public"
            block.dict.return_value = {"chain_id": "test-chain-123", "hash": "0xabcdef123456"}
            mock_generator.create_genesis.return_value = block
            
            # Create a full config
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
            with open("dummy.yaml", "w") as f:
                yaml.dump(config_data, f)
                
            result = runner.invoke(genesis, ['create', 'dummy.yaml', '--output', 'test_out.json'], obj={})
            print(f"Exit code: {result.exit_code}")
            print(f"Output: {result.output}")
            if result.exception:
                print(f"Exception: {result.exception}")
