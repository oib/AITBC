"""Tests for auth CLI commands"""

import pytest
import json
import os
from click.testing import CliRunner
from unittest.mock import Mock, patch
from aitbc_cli.commands.auth import auth


@pytest.fixture
def runner():
    """Create CLI runner"""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Mock configuration"""
    return {}


class TestAuthCommands:
    """Test auth command group"""
    
    @patch('aitbc_cli.commands.auth.AuthManager')
    def test_login_success(self, mock_auth_manager_class, runner, mock_config):
        """Test successful login"""
        # Setup mock
        mock_auth_manager = Mock()
        mock_auth_manager_class.return_value = mock_auth_manager
        
        # Run command
        result = runner.invoke(auth, [
            'login',
            'test_api_key_12345',
            '--environment', 'dev'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['status'] == 'logged_in'
        assert data['environment'] == 'dev'
        
        # Verify credential stored
        mock_auth_manager.store_credential.assert_called_once_with(
            'client', 'test_api_key_12345', 'dev'
        )
    
    @patch('aitbc_cli.commands.auth.AuthManager')
    def test_login_invalid_key(self, mock_auth_manager_class, runner, mock_config):
        """Test login with invalid API key"""
        # Run command with short key
        result = runner.invoke(auth, [
            'login',
            'short',
            '--environment', 'dev'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code != 0
        assert 'Invalid API key' in result.output
        
        # Verify credential not stored
        mock_auth_manager_class.return_value.store_credential.assert_not_called()
    
    @patch('aitbc_cli.commands.auth.AuthManager')
    def test_logout_success(self, mock_auth_manager_class, runner, mock_config):
        """Test successful logout"""
        # Setup mock
        mock_auth_manager = Mock()
        mock_auth_manager_class.return_value = mock_auth_manager
        
        # Run command
        result = runner.invoke(auth, [
            'logout',
            '--environment', 'prod'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['status'] == 'logged_out'
        assert data['environment'] == 'prod'
        
        # Verify credential deleted
        mock_auth_manager.delete_credential.assert_called_once_with(
            'client', 'prod'
        )
    
    @patch('aitbc_cli.commands.auth.AuthManager')
    def test_token_show(self, mock_auth_manager_class, runner, mock_config):
        """Test token command with show flag"""
        # Setup mock
        mock_auth_manager = Mock()
        mock_auth_manager.get_credential.return_value = 'secret_key_123'
        mock_auth_manager_class.return_value = mock_auth_manager
        
        # Run command
        result = runner.invoke(auth, [
            'token',
            '--show',
            '--environment', 'staging'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['api_key'] == 'secret_key_123'
        assert data['environment'] == 'staging'
        
        # Verify credential retrieved
        mock_auth_manager.get_credential.assert_called_once_with(
            'client', 'staging'
        )
    
    @patch('aitbc_cli.commands.auth.AuthManager')
    def test_token_hidden(self, mock_auth_manager_class, runner, mock_config):
        """Test token command without show flag"""
        # Setup mock
        mock_auth_manager = Mock()
        mock_auth_manager.get_credential.return_value = 'secret_key_123'
        mock_auth_manager_class.return_value = mock_auth_manager
        
        # Run command
        result = runner.invoke(auth, [
            'token',
            '--environment', 'staging'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['api_key'] == '***REDACTED***'
        assert data['length'] == len('secret_key_123')
    
    @patch('aitbc_cli.commands.auth.AuthManager')
    def test_token_not_found(self, mock_auth_manager_class, runner, mock_config):
        """Test token command when no credential stored"""
        # Setup mock
        mock_auth_manager = Mock()
        mock_auth_manager.get_credential.return_value = None
        mock_auth_manager_class.return_value = mock_auth_manager
        
        # Run command
        result = runner.invoke(auth, [
            'token',
            '--environment', 'nonexistent'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['message'] == 'No API key stored'
        assert data['environment'] == 'nonexistent'
    
    @patch('aitbc_cli.commands.auth.AuthManager')
    def test_status_authenticated(self, mock_auth_manager_class, runner, mock_config):
        """Test status when authenticated"""
        # Setup mock
        mock_auth_manager = Mock()
        mock_auth_manager.list_credentials.return_value = ['client@dev', 'miner@prod']
        mock_auth_manager_class.return_value = mock_auth_manager
        
        # Run command
        result = runner.invoke(auth, [
            'status'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['status'] == 'authenticated'
        assert len(data['stored_credentials']) == 2
        assert 'client@dev' in data['stored_credentials']
        assert 'miner@prod' in data['stored_credentials']
    
    @patch('aitbc_cli.commands.auth.AuthManager')
    def test_status_not_authenticated(self, mock_auth_manager_class, runner, mock_config):
        """Test status when not authenticated"""
        # Setup mock
        mock_auth_manager = Mock()
        mock_auth_manager.list_credentials.return_value = []
        mock_auth_manager_class.return_value = mock_auth_manager
        
        # Run command
        result = runner.invoke(auth, [
            'status'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['status'] == 'not_authenticated'
        assert data['message'] == 'No stored credentials found'
    
    @patch('aitbc_cli.commands.auth.AuthManager')
    def test_refresh_success(self, mock_auth_manager_class, runner, mock_config):
        """Test refresh command"""
        # Setup mock
        mock_auth_manager = Mock()
        mock_auth_manager.get_credential.return_value = 'valid_key'
        mock_auth_manager_class.return_value = mock_auth_manager
        
        # Run command
        result = runner.invoke(auth, [
            'refresh',
            '--environment', 'dev'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['status'] == 'refreshed'
        assert data['environment'] == 'dev'
        assert 'placeholder' in data['message']
    
    @patch('aitbc_cli.commands.auth.AuthManager')
    def test_refresh_no_key(self, mock_auth_manager_class, runner, mock_config):
        """Test refresh with no stored key"""
        # Setup mock
        mock_auth_manager = Mock()
        mock_auth_manager.get_credential.return_value = None
        mock_auth_manager_class.return_value = mock_auth_manager
        
        # Run command
        result = runner.invoke(auth, [
            'refresh',
            '--environment', 'nonexistent'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code != 0
        assert 'No API key found' in result.output
    
    @patch('aitbc_cli.commands.auth.AuthManager')
    def test_keys_list(self, mock_auth_manager_class, runner, mock_config):
        """Test keys list command"""
        # Setup mock
        mock_auth_manager = Mock()
        mock_auth_manager.list_credentials.return_value = [
            'client@dev', 'miner@dev', 'admin@prod'
        ]
        mock_auth_manager_class.return_value = mock_auth_manager
        
        # Run command
        result = runner.invoke(auth, [
            'keys',
            'list'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data['credentials']) == 3
    
    @patch('aitbc_cli.commands.auth.AuthManager')
    def test_keys_create(self, mock_auth_manager_class, runner, mock_config):
        """Test keys create command"""
        # Setup mock
        mock_auth_manager = Mock()
        mock_auth_manager_class.return_value = mock_auth_manager
        
        # Run command
        result = runner.invoke(auth, [
            'keys',
            'create',
            'miner',
            'miner_key_abcdef',
            '--permissions', 'mine,poll',
            '--environment', 'prod'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['status'] == 'created'
        assert data['name'] == 'miner'
        assert data['environment'] == 'prod'
        assert data['permissions'] == 'mine,poll'
        
        # Verify credential stored
        mock_auth_manager.store_credential.assert_called_once_with(
            'miner', 'miner_key_abcdef', 'prod'
        )
    
    @patch('aitbc_cli.commands.auth.AuthManager')
    def test_keys_revoke(self, mock_auth_manager_class, runner, mock_config):
        """Test keys revoke command"""
        # Setup mock
        mock_auth_manager = Mock()
        mock_auth_manager_class.return_value = mock_auth_manager
        
        # Run command
        result = runner.invoke(auth, [
            'keys',
            'revoke',
            'old_miner',
            '--environment', 'dev'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['status'] == 'revoked'
        assert data['name'] == 'old_miner'
        assert data['environment'] == 'dev'
        
        # Verify credential deleted
        mock_auth_manager.delete_credential.assert_called_once_with(
            'old_miner', 'dev'
        )
    
    @patch.dict(os.environ, {'CLIENT_API_KEY': 'env_test_key'})
    @patch('aitbc_cli.commands.auth.AuthManager')
    def test_import_env_success(self, mock_auth_manager_class, runner, mock_config):
        """Test successful import from environment"""
        import os
        
        # Setup mock
        mock_auth_manager = Mock()
        mock_auth_manager_class.return_value = mock_auth_manager
        
        # Run command
        result = runner.invoke(auth, [
            'import-env',
            'client'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['status'] == 'imported'
        assert data['name'] == 'client'
        assert data['source'] == 'CLIENT_API_KEY'
        
        # Verify credential stored
        mock_auth_manager.store_credential.assert_called_once_with(
            'client', 'env_test_key'
        )
    
    @patch.dict(os.environ, {})
    @patch('aitbc_cli.commands.auth.AuthManager')
    def test_import_env_not_set(self, mock_auth_manager_class, runner, mock_config):
        """Test import when environment variable not set"""
        import os
        
        # Setup mock
        mock_auth_manager = Mock()
        mock_auth_manager_class.return_value = mock_auth_manager
        
        # Run command
        result = runner.invoke(auth, [
            'import-env',
            'client'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Assertions
        assert result.exit_code != 0
        assert 'CLIENT_API_KEY not set' in result.output
