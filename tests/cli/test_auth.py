"""
Auth Tests
Tests for authentication and credential management
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestAuthManager:
    """Test AuthManager class"""

    @patch('auth.keyring.get_keyring')
    def test_auth_manager_initialization(self, mock_get_keyring):
        """Test AuthManager initialization"""
        from auth import AuthManager
        
        mock_keyring = Mock()
        mock_get_keyring.return_value = mock_keyring
        
        manager = AuthManager()
        
        assert manager.keyring == mock_keyring

    @patch('auth.keyring.get_keyring')
    def test_store_credential_success(self, mock_get_keyring):
        """Test successful credential storage"""
        from auth import AuthManager
        
        mock_keyring = Mock()
        mock_get_keyring.return_value = mock_keyring
        
        manager = AuthManager()
        manager.store_credential("test", "api_key_123", "dev")
        
        mock_keyring.set_password.assert_called_once_with("aitbc-cli", "dev_test", "api_key_123")

    @patch('auth.keyring.get_keyring')
    def test_store_credential_error(self, mock_get_keyring):
        """Test credential storage with error"""
        from auth import AuthManager
        
        mock_keyring = Mock()
        mock_keyring.set_password.side_effect = Exception("Storage error")
        mock_get_keyring.return_value = mock_keyring
        
        manager = AuthManager()
        manager.store_credential("test", "api_key_123")
        
        # Should not raise, just log error

    @patch('auth.keyring.get_keyring')
    def test_get_credential_success(self, mock_get_keyring):
        """Test successful credential retrieval"""
        from auth import AuthManager
        
        mock_keyring = Mock()
        mock_keyring.get_password.return_value = "api_key_123"
        mock_get_keyring.return_value = mock_keyring
        
        manager = AuthManager()
        result = manager.get_credential("test", "dev")
        
        assert result == "api_key_123"
        mock_keyring.get_password.assert_called_once_with("aitbc-cli", "dev_test")

    @patch('auth.keyring.get_keyring')
    def test_get_credential_not_found(self, mock_get_keyring):
        """Test credential retrieval when not found"""
        from auth import AuthManager
        
        mock_keyring = Mock()
        mock_keyring.get_password.return_value = None
        mock_get_keyring.return_value = mock_keyring
        
        manager = AuthManager()
        result = manager.get_credential("nonexistent")
        
        assert result is None

    @patch('auth.keyring.get_keyring')
    def test_get_credential_error(self, mock_get_keyring):
        """Test credential retrieval with error"""
        from auth import AuthManager
        
        mock_keyring = Mock()
        mock_keyring.get_password.side_effect = Exception("Retrieval error")
        mock_get_keyring.return_value = mock_keyring
        
        manager = AuthManager()
        result = manager.get_credential("test")
        
        assert result is None

    @patch('auth.keyring.get_keyring')
    def test_delete_credential_success(self, mock_get_keyring):
        """Test successful credential deletion"""
        from auth import AuthManager
        
        mock_keyring = Mock()
        mock_get_keyring.return_value = mock_keyring
        
        manager = AuthManager()
        manager.delete_credential("test", "dev")
        
        mock_keyring.delete_password.assert_called_once_with("aitbc-cli", "dev_test")

    @patch('auth.keyring.get_keyring')
    def test_delete_credential_error(self, mock_get_keyring):
        """Test credential deletion with error"""
        from auth import AuthManager
        
        mock_keyring = Mock()
        mock_keyring.delete_password.side_effect = Exception("Delete error")
        mock_get_keyring.return_value = mock_keyring
        
        manager = AuthManager()
        manager.delete_credential("test")
        
        # Should not raise, just log error

    @patch('auth.keyring.get_keyring')
    def test_list_credentials(self, mock_get_keyring):
        """Test listing credentials"""
        from auth import AuthManager
        
        mock_keyring = Mock()
        mock_keyring.get_password.side_effect = lambda service, key: "key" if "client" in key else None
        mock_get_keyring.return_value = mock_keyring
        
        manager = AuthManager()
        credentials = manager.list_credentials()
        
        assert isinstance(credentials, list)

    @patch('auth.keyring.get_keyring')
    @patch.dict('os.environ', {'CLIENT_API_KEY': 'env_key_123'})
    def test_store_env_credential_success(self, mock_get_keyring):
        """Test storing credential from environment variable"""
        from auth import AuthManager
        
        mock_keyring = Mock()
        mock_get_keyring.return_value = mock_keyring
        
        manager = AuthManager()
        result = manager.store_env_credential("client")
        
        assert result is True
        mock_keyring.set_password.assert_called_once()

    @patch('auth.keyring.get_keyring')
    @patch.dict('os.environ', {}, clear=True)
    def test_store_env_credential_not_set(self, mock_get_keyring):
        """Test storing credential when env var not set"""
        from auth import AuthManager
        
        mock_keyring = Mock()
        mock_get_keyring.return_value = mock_keyring
        
        manager = AuthManager()
        result = manager.store_env_credential("client")
        
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
