"""Tests for config CLI commands"""

import pytest
import json
import yaml
import os
import tempfile
from pathlib import Path
from click.testing import CliRunner
from unittest.mock import Mock, patch
from aitbc_cli.commands.config import config


@pytest.fixture
def runner():
    """Create CLI runner"""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Mock configuration"""
    config = Mock()
    config.coordinator_url = "http://127.0.0.1:18000"
    config.api_key = None
    config.timeout = 30
    config.config_file = "/home/oib/.aitbc/config.yaml"
    return config


@pytest.fixture
def temp_config_file():
    """Create temporary config file"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        config_data = {
            "coordinator_url": "http://test:8000",
            "api_key": "test_key",
            "timeout": 60
        }
        yaml.dump(config_data, f)
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    os.unlink(temp_path)


class TestConfigCommands:
    """Test config command group"""
    
    def test_show_config(self, runner, mock_config):
        """Test showing current configuration"""
        result = runner.invoke(config, [
            'show'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['coordinator_url'] == 'http://127.0.0.1:18000'
        assert data['api_key'] is None  # mock_config has api_key=None
        assert data['timeout'] == 30
    
    def test_set_coordinator_url(self, runner, mock_config, tmp_path):
        """Test setting coordinator URL"""
        with runner.isolated_filesystem():
            result = runner.invoke(config, [
                'set',
                'coordinator_url',
                'http://new:8000'
            ], obj={'config': mock_config, 'output_format': 'table'})
            
            assert result.exit_code == 0
            assert 'Coordinator URL set to: http://new:8000' in result.output
            
            # Verify file was created in current directory
            config_file = Path.cwd() / ".aitbc.yaml"
            assert config_file.exists()
            with open(config_file) as f:
                saved_config = yaml.safe_load(f)
            assert saved_config['coordinator_url'] == 'http://new:8000'
    
    def test_set_api_key(self, runner, mock_config):
        """Test setting API key"""
        result = runner.invoke(config, [
            'set',
            'api_key',
            'new_test_key_12345'
        ], obj={'config': mock_config, 'output_format': 'table'})
        
        assert result.exit_code == 0
        assert 'API key set (use --global to set permanently)' in result.output
    
    def test_set_timeout(self, runner, mock_config):
        """Test setting timeout"""
        with runner.isolated_filesystem():
            result = runner.invoke(config, [
                'set',
                'timeout',
                '45'
            ], obj={'config': mock_config, 'output_format': 'table'})
            
            assert result.exit_code == 0
            assert 'Timeout set to: 45s' in result.output
    
    def test_set_invalid_timeout(self, runner, mock_config):
        """Test setting invalid timeout"""
        result = runner.invoke(config, [
            'set',
            'timeout',
            'invalid'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code != 0
        assert 'Timeout must be an integer' in result.output
    
    def test_set_invalid_key(self, runner, mock_config):
        """Test setting invalid configuration key"""
        result = runner.invoke(config, [
            'set',
            'invalid_key',
            'value'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code != 0
        assert 'Unknown configuration key' in result.output
    
    def test_path_command(self, runner, mock_config, tmp_path):
        """Test showing configuration file path"""
        with runner.isolated_filesystem():
            result = runner.invoke(config, [
                'path'
            ], obj={'config': mock_config, 'output_format': 'table'})
            
            assert result.exit_code == 0
            assert '.aitbc.yaml' in result.output
    
    def test_path_global(self, runner, mock_config):
        """Test showing global config path"""
        result = runner.invoke(config, [
            'path',
            '--global'
        ], obj={'config': mock_config, 'output_format': 'table'})
        
        assert result.exit_code == 0
        assert '.config/aitbc/config.yaml' in result.output
    
    @patch('aitbc_cli.commands.config.subprocess.run')
    def test_edit_command(self, mock_run, runner, mock_config, tmp_path):
        """Test editing configuration file"""
        
        # Change to the tmp_path directory
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # The actual config file will be in the current working directory
            actual_config_file = Path.cwd() / ".aitbc.yaml"
            
            result = runner.invoke(config, [
                'edit'
            ], obj={'config': mock_config, 'output_format': 'json'})
            
            assert result.exit_code == 0
            # Verify editor was called
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args[0] == 'nano'
            assert str(actual_config_file) in args
    
    def test_reset_config_cancelled(self, runner, mock_config, temp_config_file):
        """Test config reset cancelled by user"""
        # Change to the directory containing the config file
        config_dir = Path(temp_config_file).parent
        with runner.isolated_filesystem(temp_dir=config_dir):
            # Copy the config file to the current directory
            import shutil
            local_config = Path.cwd() / ".aitbc.yaml"
            shutil.copy2(temp_config_file, local_config)
            
            result = runner.invoke(config, [
                'reset'
            ], obj={'config': mock_config, 'output_format': 'json'}, input='n\n')
            
            assert result.exit_code == 0
            # File should still exist
            assert local_config.exists()
    
    def test_reset_config_confirmed(self, runner, mock_config, temp_config_file):
        """Test config reset confirmed"""
        # Change to the directory containing the config file
        config_dir = Path(temp_config_file).parent
        with runner.isolated_filesystem(temp_dir=config_dir):
            # Copy the config file to the current directory
            import shutil
            local_config = Path.cwd() / ".aitbc.yaml"
            shutil.copy2(temp_config_file, local_config)
            
            result = runner.invoke(config, [
                'reset'
            ], obj={'config': mock_config, 'output_format': 'table'}, input='y\n')
            
            assert result.exit_code == 0
            assert 'Configuration reset' in result.output
            # File should be deleted
            assert not local_config.exists()
    
    def test_reset_no_config(self, runner, mock_config):
        """Test reset when no config file exists"""
        with runner.isolated_filesystem():
            result = runner.invoke(config, [
                'reset'
            ], obj={'config': mock_config, 'output_format': 'json'})
            
            assert result.exit_code == 0
            assert 'No configuration file found' in result.output
    
    def test_export_yaml(self, runner, mock_config, temp_config_file):
        """Test exporting configuration as YAML"""
        # Change to the directory containing the config file
        config_dir = Path(temp_config_file).parent
        with runner.isolated_filesystem(temp_dir=config_dir):
            # Copy the config file to the current directory
            import shutil
            local_config = Path.cwd() / ".aitbc.yaml"
            shutil.copy2(temp_config_file, local_config)
            
            result = runner.invoke(config, [
                'export',
                '--format', 'yaml'
            ], obj={'config': mock_config, 'output_format': 'table'})
            
            assert result.exit_code == 0
            output_data = yaml.safe_load(result.output)
            assert output_data['coordinator_url'] == 'http://test:8000'
            assert output_data['api_key'] == '***REDACTED***'
    
    def test_export_json(self, runner, mock_config, temp_config_file):
        """Test exporting configuration as JSON"""
        # Change to the directory containing the config file
        config_dir = Path(temp_config_file).parent
        with runner.isolated_filesystem(temp_dir=config_dir):
            # Copy the config file to the current directory
            import shutil
            local_config = Path.cwd() / ".aitbc.yaml"
            shutil.copy2(temp_config_file, local_config)
            
            result = runner.invoke(config, [
                'export',
                '--format', 'json'
            ], obj={'config': mock_config, 'output_format': 'table'})
            
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data['coordinator_url'] == 'http://test:8000'
            assert data['api_key'] == '***REDACTED***'
    

    def test_export_empty_yaml(self, runner, mock_config, tmp_path):
        """Test exporting an empty YAML config file"""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            local_config = Path.cwd() / ".aitbc.yaml"
            local_config.write_text("")

            result = runner.invoke(config, [
                'export',
                '--format', 'json'
            ], obj={'config': mock_config, 'output_format': 'table'})

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data == {}


    def test_export_empty_yaml_yaml_format(self, runner, mock_config, tmp_path):
        """Test exporting an empty YAML config file as YAML"""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            local_config = Path.cwd() / ".aitbc.yaml"
            local_config.write_text("")

            result = runner.invoke(config, [
                'export',
                '--format', 'yaml'
            ], obj={'config': mock_config, 'output_format': 'table'})

            assert result.exit_code == 0
            data = yaml.safe_load(result.output)
            assert data == {}

    def test_export_no_config(self, runner, mock_config):
        """Test export when no config file exists"""
        with runner.isolated_filesystem():
            result = runner.invoke(config, [
                'export'
            ], obj={'config': mock_config, 'output_format': 'json'})
            
            assert result.exit_code != 0
            assert 'No configuration file found' in result.output
    
    def test_import_config_yaml(self, runner, mock_config, tmp_path):
        """Test importing YAML configuration"""
        # Create import file
        import_file = tmp_path / "import.yaml"
        import_data = {
            "coordinator_url": "http://imported:8000",
            "timeout": 90
        }
        import_file.write_text(yaml.dump(import_data))
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # The config file will be created in the current directory
            actual_config_file = Path.cwd() / ".aitbc.yaml"
            
            result = runner.invoke(config, [
                'import-config',
                str(import_file)
            ], obj={'config': mock_config, 'output_format': 'table'})
            
            assert result.exit_code == 0
            assert 'Configuration imported' in result.output
            
            # Verify import
            with open(actual_config_file) as f:
                saved_config = yaml.safe_load(f)
            assert saved_config['coordinator_url'] == 'http://imported:8000'
            assert saved_config['timeout'] == 90
    
    def test_import_config_json(self, runner, mock_config, tmp_path):
        """Test importing JSON configuration"""
        # Create import file
        import_file = tmp_path / "import.json"
        import_data = {
            "coordinator_url": "http://json:8000",
            "timeout": 60
        }
        import_file.write_text(json.dumps(import_data))
        
        config_file = tmp_path / ".aitbc.yaml"
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # The config file will be created in the current directory
            actual_config_file = Path.cwd() / ".aitbc.yaml"
            
            result = runner.invoke(config, [
                'import-config',
                str(import_file)
            ], obj={'config': mock_config, 'output_format': 'table'})
            
            assert result.exit_code == 0
            
            # Verify import
            with open(actual_config_file) as f:
                saved_config = yaml.safe_load(f)
            assert saved_config['coordinator_url'] == 'http://json:8000'
            assert saved_config['timeout'] == 60
    
    def test_import_merge(self, runner, mock_config, temp_config_file, tmp_path):
        """Test importing with merge option"""
        # Create import file
        import_file = tmp_path / "import.yaml"
        import_data = {
            "timeout": 45
        }
        import_file.write_text(yaml.dump(import_data))
        
        # Change to the directory containing the config file
        config_dir = Path(temp_config_file).parent
        with runner.isolated_filesystem(temp_dir=config_dir):
            # Copy the config file to the current directory
            import shutil
            local_config = Path.cwd() / ".aitbc.yaml"
            shutil.copy2(temp_config_file, local_config)
            
            result = runner.invoke(config, [
                'import-config',
                str(import_file),
                '--merge'
            ], obj={'config': mock_config, 'output_format': 'table'})
            
            assert result.exit_code == 0
            
            # Verify merge - original values should remain
            with open(local_config) as f:
                saved_config = yaml.safe_load(f)
            assert saved_config['coordinator_url'] == 'http://test:8000'  # Original
            assert saved_config['timeout'] == 45  # Updated
    
    def test_import_nonexistent_file(self, runner, mock_config):
        """Test importing non-existent file"""
        result = runner.invoke(config, [
            'import-config',
            '/nonexistent/file.yaml'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code != 0
        assert 'File not found' in result.output
    
    def test_validate_valid_config(self, runner, mock_config):
        """Test validating valid configuration"""
        result = runner.invoke(config, [
            'validate'
        ], obj={'config': mock_config, 'output_format': 'table'})
        
        assert result.exit_code == 0
        assert 'Configuration valid' in result.output
    
    def test_validate_missing_url(self, runner, mock_config):
        """Test validating config with missing URL"""
        mock_config.coordinator_url = None
        
        result = runner.invoke(config, [
            'validate'
        ], obj={'config': mock_config, 'output_format': 'table'})
        
        assert result.exit_code != 0
        assert 'validation failed' in result.output
    
    def test_validate_invalid_url(self, runner, mock_config):
        """Test validating config with invalid URL"""
        mock_config.coordinator_url = "invalid-url"
        
        result = runner.invoke(config, [
            'validate'
        ], obj={'config': mock_config, 'output_format': 'table'})
        
        assert result.exit_code != 0
        assert 'validation failed' in result.output
    
    def test_validate_short_api_key(self, runner, mock_config):
        """Test validating config with short API key"""
        mock_config.api_key = "short"
        
        result = runner.invoke(config, [
            'validate'
        ], obj={'config': mock_config, 'output_format': 'table'})
        
        assert result.exit_code != 0
        assert 'validation failed' in result.output
    
    def test_validate_no_api_key(self, runner, mock_config):
        """Test validating config without API key (warning)"""
        mock_config.api_key = None
        
        result = runner.invoke(config, [
            'validate'
        ], obj={'config': mock_config, 'output_format': 'table'})
        
        assert result.exit_code == 0
        assert 'valid with warnings' in result.output
    
    @patch.dict(os.environ, {'CLIENT_API_KEY': 'env_key_123'})
    def test_environments(self, runner, mock_config):
        """Test listing environment variables"""
        result = runner.invoke(config, [
            'environments'
        ], obj={'config': mock_config, 'output_format': 'table'})
        
        assert result.exit_code == 0
        assert 'CLIENT_API_KEY' in result.output
    
    def test_profiles_save(self, runner, mock_config, tmp_path):
        """Test saving a configuration profile"""
        # Patch Path.home to return tmp_path
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = tmp_path
            
            result = runner.invoke(config, [
                'profiles',
                'save',
                'test_profile'
            ], obj={'config': mock_config, 'output_format': 'table'})
            
            assert result.exit_code == 0
            assert "Profile 'test_profile' saved" in result.output
            
            # Verify profile was created
            profile_file = tmp_path / ".config" / "aitbc" / "profiles" / "test_profile.yaml"
            assert profile_file.exists()
            with open(profile_file) as f:
                profile_data = yaml.safe_load(f)
            assert profile_data['coordinator_url'] == 'http://127.0.0.1:18000'
    
    def test_profiles_list(self, runner, mock_config, tmp_path):
        """Test listing configuration profiles"""
        # Create test profiles
        profiles_dir = tmp_path / ".config" / "aitbc" / "profiles"
        profiles_dir.mkdir(parents=True, exist_ok=True)
        
        profile1 = profiles_dir / "profile1.yaml"
        profile1.write_text(yaml.dump({"coordinator_url": "http://test1:8000"}))
        
        profile2 = profiles_dir / "profile2.yaml"
        profile2.write_text(yaml.dump({"coordinator_url": "http://test2:8000"}))
        
        # Patch Path.home to return tmp_path
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = tmp_path
            
            result = runner.invoke(config, [
                'profiles',
                'list'
            ], obj={'config': mock_config, 'output_format': 'table'})
            
            assert result.exit_code == 0
            assert 'profile1' in result.output
            assert 'profile2' in result.output
    
    def test_profiles_load(self, runner, mock_config, tmp_path):
        """Test loading a configuration profile"""
        # Create test profile
        profiles_dir = tmp_path / ".config" / "aitbc" / "profiles"
        profiles_dir.mkdir(parents=True, exist_ok=True)
        
        profile_file = profiles_dir / "load_me.yaml"
        profile_file.write_text(yaml.dump({"coordinator_url": "http://127.0.0.1:18000"}))
        
        # Patch Path.home to return tmp_path
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = tmp_path
            
            result = runner.invoke(config, [
                'profiles',
                'load',
                'load_me'
            ], obj={'config': mock_config, 'output_format': 'table'})
            
            assert result.exit_code == 0
            assert "Profile 'load_me' loaded" in result.output
    
    def test_profiles_delete(self, runner, mock_config, tmp_path):
        """Test deleting a configuration profile"""
        # Create test profile
        profiles_dir = tmp_path / ".config" / "aitbc" / "profiles"
        profiles_dir.mkdir(parents=True, exist_ok=True)
        
        profile_file = profiles_dir / "delete_me.yaml"
        profile_file.write_text(yaml.dump({"coordinator_url": "http://test:8000"}))
        
        # Patch Path.home to return tmp_path
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = tmp_path
            
            result = runner.invoke(config, [
                'profiles',
                'delete',
                'delete_me'
            ], obj={'config': mock_config, 'output_format': 'table'}, input='y\n')
            
            assert result.exit_code == 0
            assert "Profile 'delete_me' deleted" in result.output
            assert not profile_file.exists()
    
    def test_profiles_delete_cancelled(self, runner, mock_config, tmp_path):
        """Test profile deletion cancelled by user"""
        # Create test profile
        profiles_dir = tmp_path / ".config" / "aitbc" / "profiles"
        profiles_dir.mkdir(parents=True, exist_ok=True)
        
        profile_file = profiles_dir / "keep_me.yaml"
        profile_file.write_text(yaml.dump({"coordinator_url": "http://test:8000"}))
        
        # Patch Path.home to return tmp_path
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = tmp_path
            
            result = runner.invoke(config, [
                'profiles',
                'delete',
                'keep_me'
            ], obj={'config': mock_config, 'output_format': 'json'}, input='n\n')
            
            assert result.exit_code == 0
            assert profile_file.exists()  # Should still exist
