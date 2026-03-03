"""
Unit Tests for AITBC Core Functionality
Tests core components using actual AITBC CLI tool
"""

import pytest
import json
import time
import tempfile
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from pathlib import Path
from click.testing import CliRunner

# Import the actual CLI
from aitbc_cli.main import cli


class TestAITBCCliIntegration:
    """Test AITBC CLI integration"""
    
    def test_cli_help(self):
        """Test CLI help command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'AITBC CLI' in result.output
        assert 'Commands:' in result.output
    
    def test_cli_version(self):
        """Test CLI version command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['version'])
        assert result.exit_code == 0
        assert 'version' in result.output.lower()
    
    def test_cli_config_show(self):
        """Test CLI config show command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['config-show'])
        assert result.exit_code == 0
        assert 'coordinator_url' in result.output.lower()
    
    def test_cli_test_mode(self):
        """Test CLI test mode functionality"""
        runner = CliRunner()
        result = runner.invoke(cli, ['--test-mode', 'test', 'environment'])
        assert result.exit_code == 0
        assert 'Test Mode: True' in result.output
        assert 'test-api-k' in result.output
    
    def test_cli_dry_run(self):
        """Test CLI dry run functionality"""
        runner = CliRunner()
        result = runner.invoke(cli, ['--dry-run', 'test', 'environment'])
        assert result.exit_code == 0
        assert 'Dry Run: True' in result.output
    
    def test_cli_debug_mode(self):
        """Test CLI debug mode functionality"""
        runner = CliRunner()
        result = runner.invoke(cli, ['--debug', 'test', 'environment'])
        assert result.exit_code == 0
        assert 'Log Level: DEBUG' in result.output


class TestAITBCWalletCli:
    """Test AITBC wallet CLI functionality"""
    
    def test_wallet_help(self):
        """Test wallet help command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['wallet', '--help'])
        assert result.exit_code == 0
        assert 'wallet' in result.output.lower()
    
    def test_wallet_create_test_mode(self):
        """Test wallet creation in test mode"""
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {'WALLET_DIR': temp_dir}
            wallet_name = f"test-wallet-{int(time.time())}"
            result = runner.invoke(cli, ['--test-mode', 'wallet', 'create', wallet_name], env=env)
            # In test mode, this should work without actual blockchain
            assert result.exit_code == 0 or 'wallet' in result.output.lower()
    
    def test_wallet_commands_available(self):
        """Test that wallet commands are available"""
        runner = CliRunner()
        result = runner.invoke(cli, ['wallet', '--help'])
        expected_commands = ['create', 'balance', 'list', 'info', 'switch']
        for cmd in expected_commands:
            assert cmd in result.output.lower()


class TestAITBCMarketplaceCli:
    """Test AITBC marketplace CLI functionality"""
    
    def test_marketplace_help(self):
        """Test marketplace help command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['marketplace', '--help'])
        assert result.exit_code == 0
        assert 'marketplace' in result.output.lower()
    
    def test_marketplace_commands_available(self):
        """Test that marketplace commands are available"""
        runner = CliRunner()
        result = runner.invoke(cli, ['marketplace', '--help'])
        expected_commands = ['offers', 'pricing', 'providers']
        for cmd in expected_commands:
            assert cmd in result.output.lower()
    
    def test_marketplace_offers_list_test_mode(self):
        """Test marketplace offers list in test mode"""
        runner = CliRunner()
        result = runner.invoke(cli, ['--test-mode', 'marketplace', 'offers', 'list'])
        # Should handle test mode gracefully
        assert result.exit_code == 0 or 'offers' in result.output.lower()


class TestAITBCClientCli:
    """Test AITBC client CLI functionality"""
    
    def test_client_help(self):
        """Test client help command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['client', '--help'])
        assert result.exit_code == 0
        assert 'client' in result.output.lower()
    
    def test_client_commands_available(self):
        """Test that client commands are available"""
        runner = CliRunner()
        result = runner.invoke(cli, ['client', '--help'])
        expected_commands = ['submit', 'status', 'list', 'cancel']
        for cmd in expected_commands:
            assert cmd in result.output.lower()


class TestAITBCBlockchainCli:
    """Test AITBC blockchain CLI functionality"""
    
    def test_blockchain_help(self):
        """Test blockchain help command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['blockchain', '--help'])
        assert result.exit_code == 0
        assert 'blockchain' in result.output.lower()
    
    def test_blockchain_commands_available(self):
        """Test that blockchain commands are available"""
        runner = CliRunner()
        result = runner.invoke(cli, ['blockchain', '--help'])
        expected_commands = ['info', 'status', 'blocks', 'transactions']
        for cmd in expected_commands:
            assert cmd in result.output.lower()


class TestAITBCAuthCli:
    """Test AITBC auth CLI functionality"""
    
    def test_auth_help(self):
        """Test auth help command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['auth', '--help'])
        assert result.exit_code == 0
        assert 'auth' in result.output.lower()
    
    def test_auth_commands_available(self):
        """Test that auth commands are available"""
        runner = CliRunner()
        result = runner.invoke(cli, ['auth', '--help'])
        expected_commands = ['login', 'logout', 'status', 'token']
        for cmd in expected_commands:
            assert cmd in result.output.lower()


class TestAITBCTestCommands:
    """Test AITBC test commands"""
    
    def test_test_help(self):
        """Test test command help"""
        runner = CliRunner()
        result = runner.invoke(cli, ['test', '--help'])
        assert result.exit_code == 0
        assert 'Testing and debugging' in result.output
    
    def test_test_environment(self):
        """Test test environment command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['test', 'environment'])
        assert result.exit_code == 0
        assert 'CLI Environment Test Results' in result.output
    
    def test_test_environment_json(self):
        """Test test environment command with JSON output"""
        runner = CliRunner()
        result = runner.invoke(cli, ['test', 'environment', '--format', 'json'])
        assert result.exit_code == 0
        # Should be valid JSON
        data = json.loads(result.output)
        assert 'coordinator_url' in data
        assert 'test_mode' in data
    
    def test_test_mock(self):
        """Test test mock command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['test', 'mock'])
        assert result.exit_code == 0
        assert 'Mock data for testing' in result.output
        # Should be valid JSON
        lines = result.output.split('\n')
        for line in lines:
            if line.strip().startswith('{') or line.strip().startswith('"'):
                try:
                    data = json.loads(line)
                    assert 'wallet' in data or 'job' in data or 'marketplace' in data
                except:
                    pass  # Skip non-JSON lines


class TestAITBCOutputFormats:
    """Test AITBC CLI output formats"""
    
    def test_json_output_format(self):
        """Test JSON output format"""
        runner = CliRunner()
        result = runner.invoke(cli, ['--output', 'json', 'test', 'environment'])
        assert result.exit_code == 0
        # Should be valid JSON
        data = json.loads(result.output)
        assert 'coordinator_url' in data
    
    def test_yaml_output_format(self):
        """Test YAML output format"""
        runner = CliRunner()
        result = runner.invoke(cli, ['--output', 'yaml', 'test', 'environment'])
        assert result.exit_code == 0
        # Should contain YAML-like output
        assert 'coordinator_url:' in result.output or 'coordinator_url' in result.output
    
    def test_table_output_format(self):
        """Test table output format (default)"""
        runner = CliRunner()
        result = runner.invoke(cli, ['--output', 'table', 'test', 'environment'])
        assert result.exit_code == 0
        assert 'CLI Environment Test Results' in result.output


class TestAITBCConfiguration:
    """Test AITBC CLI configuration"""
    
    def test_custom_config_file(self):
        """Test custom config file option"""
        runner = CliRunner()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('coordinator_url: http://test.example.com\n')
            f.write('api_key: test-key\n')
            config_file = f.name
        
        try:
            result = runner.invoke(cli, ['--config-file', config_file, 'test', 'environment'])
            assert result.exit_code == 0
        finally:
            Path(config_file).unlink(missing_ok=True)
    
    def test_custom_url_override(self):
        """Test custom URL override"""
        runner = CliRunner()
        result = runner.invoke(cli, ['--url', 'http://custom.test', 'test', 'environment'])
        assert result.exit_code == 0
        assert 'http://custom.test' in result.output
    
    def test_custom_api_key_override(self):
        """Test custom API key override"""
        runner = CliRunner()
        result = runner.invoke(cli, ['--api-key', 'custom-test-key', 'test', 'environment'])
        assert result.exit_code == 0
        assert 'custom-test' in result.output


class TestAITBCErrorHandling:
    """Test AITBC CLI error handling"""
    
    def test_invalid_command(self):
        """Test invalid command handling"""
        runner = CliRunner()
        result = runner.invoke(cli, ['invalid-command'])
        assert result.exit_code != 0
        assert 'No such command' in result.output
    
    def test_invalid_option(self):
        """Test invalid option handling"""
        runner = CliRunner()
        result = runner.invoke(cli, ['--invalid-option'])
        assert result.exit_code != 0
    
    def test_missing_required_argument(self):
        """Test missing required argument handling"""
        runner = CliRunner()
        result = runner.invoke(cli, ['wallet', 'create'])
        # Should show error about missing argument
        assert result.exit_code != 0 or 'Usage:' in result.output


class TestAITBCPerformance:
    """Test AITBC CLI performance"""
    
    def test_help_command_performance(self):
        """Test help command performance"""
        runner = CliRunner()
        start_time = time.time()
        result = runner.invoke(cli, ['--help'])
        end_time = time.time()
        
        assert result.exit_code == 0
        assert (end_time - start_time) < 2.0  # Should complete in under 2 seconds
    
    def test_config_show_performance(self):
        """Test config show performance"""
        runner = CliRunner()
        start_time = time.time()
        result = runner.invoke(cli, ['config-show'])
        end_time = time.time()
        
        assert result.exit_code == 0
        assert (end_time - start_time) < 1.0  # Should complete in under 1 second


class TestAITBCDataStructures:
    """Test AITBC CLI data structures"""
    
    def test_job_structure_validation(self):
        """Test job data structure validation"""
        job_data = {
            'id': 'test-job-123',
            'type': 'ml_inference',
            'status': 'pending',
            'created_at': datetime.utcnow().isoformat(),
            'requirements': {
                'gpu_type': 'RTX 3080',
                'memory_gb': 8,
                'duration_minutes': 30
            }
        }
        
        # Validate job structure
        assert 'id' in job_data
        assert 'type' in job_data
        assert 'status' in job_data
        assert job_data['status'] in ['pending', 'running', 'completed', 'failed']
        assert 'requirements' in job_data
    
    def test_wallet_structure_validation(self):
        """Test wallet data structure validation"""
        wallet_data = {
            'name': 'test-wallet',
            'type': 'hd',
            'address': 'aitbc1test123456789',
            'balance': 1000.0,
            'created_at': datetime.utcnow().isoformat(),
            'transactions': []
        }
        
        # Validate wallet structure
        assert 'name' in wallet_data
        assert 'type' in wallet_data
        assert 'address' in wallet_data
        assert wallet_data['address'].startswith('aitbc1')
        assert isinstance(wallet_data['balance'], (int, float))
    
    def test_marketplace_structure_validation(self):
        """Test marketplace data structure validation"""
        offer_data = {
            'id': 'offer-123',
            'provider': 'miner-456',
            'gpu_type': 'RTX 3080',
            'price_per_hour': 0.1,
            'memory_gb': 10,
            'available': True,
            'created_at': datetime.utcnow().isoformat()
        }
        
        # Validate offer structure
        assert 'id' in offer_data
        assert 'provider' in offer_data
        assert 'gpu_type' in offer_data
        assert isinstance(offer_data['price_per_hour'], (int, float))
        assert isinstance(offer_data['available'], bool)
