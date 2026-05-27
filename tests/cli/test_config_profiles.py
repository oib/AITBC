"""Integration tests for config profiles CLI commands

These tests require no running services but validate file system side effects
and actual profile CRUD operations.
"""

import pytest
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
def profiles_dir(tmp_path):
    """Create and return profiles directory"""
    profiles_dir = tmp_path / ".config" / "aitbc" / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    return profiles_dir


class TestConfigProfilesIntegration:
    """Integration tests for config profiles with file system validation"""

    def test_profiles_save_creates_file(self, runner, mock_config, profiles_dir):
        """Test saving a profile creates the correct file"""
        profile_name = "test_profile"
        
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = profiles_dir.parent.parent.parent
            
            result = runner.invoke(config, [
                'profiles', 'save', profile_name
            ], obj={'config': mock_config, 'output': 'table'})
            
            assert result.exit_code == 0
            assert f"Profile '{profile_name}' saved" in result.output
            
            # Verify file was created
            profile_file = profiles_dir / f"{profile_name}.yaml"
            assert profile_file.exists()
            
            # Verify file content
            with open(profile_file) as f:
                profile_data = yaml.safe_load(f)
            assert profile_data['coordinator_url'] == 'http://127.0.0.1:18000'
            assert profile_data['timeout'] == 30
            assert 'api_key' not in profile_data  # API key should not be saved

    def test_profiles_save_overwrites_existing(self, runner, mock_config, profiles_dir):
        """Test saving a profile overwrites existing profile"""
        profile_name = "overwrite_test"
        
        # Create existing profile
        profile_file = profiles_dir / f"{profile_name}.yaml"
        profile_file.write_text(yaml.dump({
            "coordinator_url": "http://old:8000",
            "timeout": 10
        }))
        
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = profiles_dir.parent.parent.parent
            
            result = runner.invoke(config, [
                'profiles', 'save', profile_name
            ], obj={'config': mock_config, 'output': 'table'})
            
            assert result.exit_code == 0
            
            # Verify file was overwritten
            with open(profile_file) as f:
                profile_data = yaml.safe_load(f)
            assert profile_data['coordinator_url'] == 'http://127.0.0.1:18000'
            assert profile_data['timeout'] == 30

    def test_profiles_list_empty(self, runner, mock_config, profiles_dir):
        """Test listing profiles when none exist"""
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = profiles_dir.parent.parent.parent
            
            result = runner.invoke(config, [
                'profiles', 'list'
            ], obj={'config': mock_config, 'output': 'json'})
            
            assert result.exit_code == 0
            import json
            data = json.loads(result.output)
            assert data['profiles'] == []

    def test_profiles_list_multiple(self, runner, mock_config, profiles_dir):
        """Test listing multiple profiles"""
        # Create test profiles
        profile1 = profiles_dir / "profile1.yaml"
        profile1.write_text(yaml.dump({
            "coordinator_url": "http://test1:8000",
            "timeout": 30
        }))
        
        profile2 = profiles_dir / "profile2.yaml"
        profile2.write_text(yaml.dump({
            "coordinator_url": "http://test2:8000",
            "timeout": 60
        }))
        
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = profiles_dir.parent.parent.parent
            
            result = runner.invoke(config, [
                'profiles', 'list'
            ], obj={'config': mock_config, 'output': 'json'})
            
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data['profiles']) == 2
            assert data['profiles'][0]['name'] == 'profile1'
            assert data['profiles'][1]['name'] == 'profile2'

    def test_profiles_load_creates_config(self, runner, mock_config, profiles_dir, tmp_path):
        """Test loading a profile creates config file"""
        profile_name = "load_test"
        
        # Create profile
        profile_file = profiles_dir / f"{profile_name}.yaml"
        profile_file.write_text(yaml.dump({
            "coordinator_url": "http://loaded:8000",
            "timeout": 45
        }))
        
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = profiles_dir.parent.parent.parent
            
            with runner.isolated_filesystem(temp_dir=tmp_path):
                result = runner.invoke(config, [
                    'profiles', 'load', profile_name
                ], obj={'config': mock_config, 'output': 'table'})
                
                assert result.exit_code == 0
                assert f"Profile '{profile_name}' loaded" in result.output
                
                # Verify config file was created
                config_file = Path.cwd() / ".aitbc.yaml"
                assert config_file.exists()
                
                with open(config_file) as f:
                    config_data = yaml.safe_load(f)
                assert config_data['coordinator_url'] == 'http://loaded:8000'
                assert config_data['timeout'] == 45

    def test_profiles_load_nonexistent(self, runner, mock_config, profiles_dir):
        """Test loading a non-existent profile"""
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = profiles_dir.parent.parent.parent
            
            result = runner.invoke(config, [
                'profiles', 'load', 'nonexistent'
            ], obj={'config': mock_config, 'output': 'table'})
            
            assert result.exit_code != 0
            assert "not found" in result.output

    def test_profiles_delete_removes_file(self, runner, mock_config, profiles_dir):
        """Test deleting a profile removes the file"""
        profile_name = "delete_test"
        
        # Create profile
        profile_file = profiles_dir / f"{profile_name}.yaml"
        profile_file.write_text(yaml.dump({
            "coordinator_url": "http://test:8000",
            "timeout": 30
        }))
        
        assert profile_file.exists()
        
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = profiles_dir.parent.parent.parent
            
            result = runner.invoke(config, [
                'profiles', 'delete', profile_name
            ], obj={'config': mock_config, 'output': 'table'}, input='y\n')
            
            assert result.exit_code == 0
            assert f"Profile '{profile_name}' deleted" in result.output
            assert not profile_file.exists()

    def test_profiles_delete_cancelled(self, runner, mock_config, profiles_dir):
        """Test profile deletion cancelled by user"""
        profile_name = "keep_test"
        
        # Create profile
        profile_file = profiles_dir / f"{profile_name}.yaml"
        profile_file.write_text(yaml.dump({
            "coordinator_url": "http://test:8000",
            "timeout": 30
        }))
        
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = profiles_dir.parent.parent.parent
            
            result = runner.invoke(config, [
                'profiles', 'delete', profile_name
            ], obj={'config': mock_config, 'output': 'json'}, input='n\n')
            
            assert result.exit_code == 0
            assert profile_file.exists()  # Should still exist

    def test_profiles_delete_nonexistent(self, runner, mock_config, profiles_dir):
        """Test deleting a non-existent profile"""
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = profiles_dir.parent.parent.parent
            
            result = runner.invoke(config, [
                'profiles', 'delete', 'nonexistent'
            ], obj={'config': mock_config, 'output': 'table'})
            
            assert result.exit_code != 0
            assert "not found" in result.output

    def test_profiles_roundtrip(self, runner, mock_config, profiles_dir, tmp_path):
        """Test save -> list -> load -> delete roundtrip"""
        profile_name = "roundtrip_test"
        
        # Save
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = profiles_dir.parent.parent.parent
            
            result = runner.invoke(config, [
                'profiles', 'save', profile_name
            ], obj={'config': mock_config, 'output': 'table'})
            assert result.exit_code == 0
            
            # List
            result = runner.invoke(config, [
                'profiles', 'list'
            ], obj={'config': mock_config, 'output': 'json'})
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert profile_name in [p['name'] for p in data['profiles']]
            
            # Load
            with runner.isolated_filesystem(temp_dir=tmp_path):
                result = runner.invoke(config, [
                    'profiles', 'load', profile_name
                ], obj={'config': mock_config, 'output': 'table'})
                assert result.exit_code == 0
            
            # Delete
            result = runner.invoke(config, [
                'profiles', 'delete', profile_name
            ], obj={'config': mock_config, 'output': 'table'}, input='y\n')
            assert result.exit_code == 0
            
            # Verify deleted
            profile_file = profiles_dir / f"{profile_name}.yaml"
            assert not profile_file.exists()

    def test_profiles_with_different_configs(self, runner, mock_config, profiles_dir):
        """Test saving profiles with different config values"""
        # Modify config for different profile
        mock_config.coordinator_url = "http://different:9000"
        mock_config.timeout = 90
        
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = profiles_dir.parent.parent.parent
            
            result = runner.invoke(config, [
                'profiles', 'save', 'different_profile'
            ], obj={'config': mock_config, 'output': 'table'})
            
            assert result.exit_code == 0
            
            profile_file = profiles_dir / "different_profile.yaml"
            with open(profile_file) as f:
                profile_data = yaml.safe_load(f)
            assert profile_data['coordinator_url'] == 'http://different:9000'
            assert profile_data['timeout'] == 90

    def test_profiles_directory_creation(self, runner, mock_config, tmp_path):
        """Test that profiles directory is created if it doesn't exist"""
        profiles_dir = tmp_path / ".config" / "aitbc" / "profiles"
        # Don't create it beforehand
        
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = tmp_path
            
            result = runner.invoke(config, [
                'profiles', 'save', 'new_profile'
            ], obj={'config': mock_config, 'output': 'table'})
            
            assert result.exit_code == 0
            assert profiles_dir.exists()
            assert (profiles_dir / "new_profile.yaml").exists()
