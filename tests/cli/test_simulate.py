"""Tests for simulate CLI commands"""

import pytest
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock
from click.testing import CliRunner
from aitbc_cli.commands.simulate import simulate


def extract_json_from_output(output):
    """Extract first JSON object from CLI output that may contain ANSI escape codes and success messages"""
    import re
    clean_output = re.sub(r'\x1b\[[0-9;]*m', '', output)
    lines = clean_output.strip().split('\n')
    
    # Find all lines that contain JSON and join them
    json_lines = []
    in_json = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('{'):
            in_json = True
            json_lines.append(stripped)
        elif in_json:
            json_lines.append(stripped)
            if stripped.endswith('}'):
                break
    
    assert json_lines, "No JSON found in output"
    json_str = '\n'.join(json_lines)
    return json.loads(json_str)


def extract_last_json_from_output(output):
    """Extract the last JSON object from CLI output (for commands that emit multiple JSON objects)"""
    import re
    clean_output = re.sub(r'\x1b\[[0-9;]*m', '', output)
    lines = clean_output.strip().split('\n')
    
    all_objects = []
    json_lines = []
    in_json = False
    brace_depth = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('{') and not in_json:
            in_json = True
            brace_depth = stripped.count('{') - stripped.count('}')
            json_lines = [stripped]
            if brace_depth == 0:
                try:
                    all_objects.append(json.loads('\n'.join(json_lines)))
                except json.JSONDecodeError:
                    pass
                json_lines = []
                in_json = False
        elif in_json:
            json_lines.append(stripped)
            brace_depth += stripped.count('{') - stripped.count('}')
            if brace_depth <= 0:
                try:
                    all_objects.append(json.loads('\n'.join(json_lines)))
                except json.JSONDecodeError:
                    pass
                json_lines = []
                in_json = False
    
    assert all_objects, "No JSON found in output"
    return all_objects[-1]


@pytest.fixture
def runner():
    """Create CLI runner"""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Mock configuration"""
    config = Mock()
    config.coordinator_url = "http://test:8000"
    config.api_key = "test_api_key"
    return config


class TestSimulateCommands:
    """Test simulate command group"""
    
    def test_init_economy(self, runner, mock_config):
        """Test initializing test economy"""
        with runner.isolated_filesystem():
            # Create a temporary home directory
            home_dir = Path("temp_home")
            home_dir.mkdir()
            
            # Patch the hardcoded path
            with patch('aitbc_cli.commands.simulate.Path') as mock_path_class:
                # Make Path return our temp directory
                mock_path_class.return_value = home_dir
                mock_path_class.side_effect = lambda x: home_dir if x == "/home/oib/windsurf/aitbc/home" else Path(x)
                
                # Run command
                result = runner.invoke(simulate, [
                    'init',
                    '--distribute', '5000,2000'
                ], obj={'config': mock_config, 'output_format': 'json'})
                
                # Assertions
                assert result.exit_code == 0
                data = extract_json_from_output(result.output)
                assert data['status'] == 'initialized'
                assert data['distribution']['client'] == 5000.0
                assert data['distribution']['miner'] == 2000.0
    
    def test_init_with_reset(self, runner, mock_config):
        """Test initializing with reset flag"""
        with runner.isolated_filesystem():
            # Create a temporary home directory with existing files
            home_dir = Path("temp_home")
            home_dir.mkdir()
            
            # Create existing wallet files
            (home_dir / "client_wallet.json").write_text("{}")
            (home_dir / "miner_wallet.json").write_text("{}")
            
            # Patch the hardcoded path
            with patch('aitbc_cli.commands.simulate.Path') as mock_path_class:
                mock_path_class.return_value = home_dir
                mock_path_class.side_effect = lambda x: home_dir if x == "/home/oib/windsurf/aitbc/home" else Path(x)
                
                # Run command
                result = runner.invoke(simulate, [
                    'init',
                    '--reset'
                ], obj={'config': mock_config, 'output_format': 'json'})
                
                # Assertions
                assert result.exit_code == 0
                assert 'resetting' in result.output.lower()
    
    def test_create_user(self, runner, mock_config):
        """Test creating a test user"""
        with runner.isolated_filesystem():
            # Create a temporary home directory
            home_dir = Path("temp_home")
            home_dir.mkdir()
            
            # Patch the hardcoded path
            with patch('aitbc_cli.commands.simulate.Path') as mock_path_class:
                mock_path_class.return_value = home_dir
                mock_path_class.side_effect = lambda x: home_dir if x == "/home/oib/windsurf/aitbc/home" else Path(x)
                
                # Run command
                result = runner.invoke(simulate, [
                    'user',
                    'create',
                    '--type', 'client',
                    '--name', 'testuser',
                    '--balance', '1000'
                ], obj={'config': mock_config, 'output_format': 'json'})
                
                # Assertions
                assert result.exit_code == 0
                data = extract_json_from_output(result.output)
                assert data['user_id'] == 'client_testuser'
                assert data['balance'] == 1000
    
    def test_list_users(self, runner, mock_config):
        """Test listing test users"""
        with runner.isolated_filesystem():
            # Create a temporary home directory
            home_dir = Path("temp_home")
            home_dir.mkdir()
            
            # Create some test wallet files
            (home_dir / "client_user1_wallet.json").write_text('{"address": "aitbc1test", "balance": 1000}')
            (home_dir / "miner_user2_wallet.json").write_text('{"address": "aitbc1test2", "balance": 2000}')
            
            # Patch the hardcoded path
            with patch('aitbc_cli.commands.simulate.Path') as mock_path_class:
                mock_path_class.return_value = home_dir
                mock_path_class.side_effect = lambda x: home_dir if x == "/home/oib/windsurf/aitbc/home" else Path(x)
                
                # Run command
                result = runner.invoke(simulate, [
                    'user',
                    'list'
                ], obj={'config': mock_config, 'output_format': 'json'})
                
                # Assertions
                assert result.exit_code == 0
                data = json.loads(result.output)
                assert 'users' in data
                assert isinstance(data['users'], list)
                assert len(data['users']) == 2
    
    def test_user_balance(self, runner, mock_config):
        """Test checking user balance"""
        with runner.isolated_filesystem():
            # Create a temporary home directory
            home_dir = Path("temp_home")
            home_dir.mkdir()
            
            # Create a test wallet file
            (home_dir / "testuser_wallet.json").write_text('{"address": "aitbc1testuser", "balance": 1500}')
            
            # Patch the hardcoded path
            with patch('aitbc_cli.commands.simulate.Path') as mock_path_class:
                mock_path_class.return_value = home_dir
                mock_path_class.side_effect = lambda x: home_dir if x == "/home/oib/windsurf/aitbc/home" else Path(x)
                
                # Run command
                result = runner.invoke(simulate, [
                    'user',
                    'balance',
                    'testuser'
                ], obj={'config': mock_config, 'output_format': 'json'})
                
                # Assertions
                assert result.exit_code == 0
                data = json.loads(result.output)
                assert data['balance'] == 1500
    
    def test_fund_user(self, runner, mock_config):
        """Test funding a test user"""
        with runner.isolated_filesystem():
            # Create a temporary home directory
            home_dir = Path("temp_home")
            home_dir.mkdir()
            
            # Create genesis and user wallet files
            (home_dir / "genesis_wallet.json").write_text('{"address": "aitbc1genesis", "balance": 1000000, "transactions": []}')
            (home_dir / "testuser_wallet.json").write_text('{"address": "aitbc1testuser", "balance": 1000, "transactions": []}')
            
            # Patch the hardcoded path
            with patch('aitbc_cli.commands.simulate.Path') as mock_path_class:
                mock_path_class.return_value = home_dir
                mock_path_class.side_effect = lambda x: home_dir if x == "/home/oib/windsurf/aitbc/home" else Path(x)
                
                # Run command
                result = runner.invoke(simulate, [
                    'user',
                    'fund',
                    'testuser',
                    '500'
                ], obj={'config': mock_config, 'output_format': 'json'})
                
                # Assertions
                assert result.exit_code == 0
                # Extract JSON from output
                data = extract_json_from_output(result.output)
                assert data['amount'] == 500
                assert data['new_balance'] == 1500
    
    def test_workflow_command(self, runner, mock_config):
        """Test workflow simulation command"""
        result = runner.invoke(simulate, [
            'workflow',
            '--jobs', '5',
            '--rounds', '2'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # The command should exist
        assert result.exit_code == 0
        # Extract last JSON from output (workflow emits multiple JSON objects)
        data = extract_last_json_from_output(result.output)
        assert data['status'] == 'completed'
        assert data['total_jobs'] == 10
    
    def test_load_test_command(self, runner, mock_config):
        """Test load test command"""
        result = runner.invoke(simulate, [
            'load-test',
            '--clients', '2',
            '--miners', '1',
            '--duration', '5',
            '--job-rate', '2'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # The command should exist
        assert result.exit_code == 0
        # Extract last JSON from output (load_test emits multiple JSON objects)
        data = extract_last_json_from_output(result.output)
        assert data['status'] == 'completed'
        assert 'duration' in data
        assert 'jobs_submitted' in data
    
    def test_scenario_commands(self, runner, mock_config):
        """Test scenario commands"""
        with runner.isolated_filesystem():
            # Create a test scenario file
            scenario_file = Path("test_scenario.json")
            scenario_data = {
                "name": "Test Scenario",
                "description": "A test scenario",
                "steps": [
                    {
                        "type": "submit_jobs",
                        "name": "Initial jobs",
                        "count": 2,
                        "prompt": "Test job"
                    },
                    {
                        "type": "wait",
                        "name": "Wait step",
                        "duration": 1
                    }
                ]
            }
            scenario_file.write_text(json.dumps(scenario_data))
            
            # Run scenario
            result = runner.invoke(simulate, [
                'scenario',
                '--file', str(scenario_file)
            ], obj={'config': mock_config, 'output_format': 'json'})
            
            assert result.exit_code == 0
            assert "Running scenario: Test Scenario" in result.output
    
    def test_results_command(self, runner, mock_config):
        """Test results command"""
        result = runner.invoke(simulate, [
            'results',
            'sim_123'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        # Extract JSON from output
        data = extract_json_from_output(result.output)
        assert data['simulation_id'] == 'sim_123'
    
    def test_reset_command(self, runner, mock_config):
        """Test reset command"""
        with runner.isolated_filesystem():
            # Create a temporary home directory
            home_dir = Path("temp_home")
            home_dir.mkdir()
            
            # Create existing wallet files
            (home_dir / "client_wallet.json").write_text("{}")
            (home_dir / "miner_wallet.json").write_text("{}")
            
            # Patch the hardcoded path
            with patch('aitbc_cli.commands.simulate.Path') as mock_path_class:
                mock_path_class.return_value = home_dir
                mock_path_class.side_effect = lambda x: home_dir if x == "/home/oib/windsurf/aitbc/home" else Path(x)
                
                # Run command with reset flag
                result = runner.invoke(simulate, [
                    'init',
                    '--reset'
                ], obj={'config': mock_config, 'output_format': 'json'})
                
                # Assertions
                assert result.exit_code == 0
                assert 'resetting' in result.output.lower()
    
    def test_invalid_distribution_format(self, runner, mock_config):
        """Test invalid distribution format"""
        result = runner.invoke(simulate, [
            'init',
            '--distribute', 'invalid'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        assert 'invalid distribution' in result.output.lower()
