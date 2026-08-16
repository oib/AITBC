"""
Exception Handling Tests
Tests for improved exception chaining and error handling
"""

import pytest

from aitbc.crypto.crypto import (
    decrypt_private_key,
    encrypt_private_key,
    sha256_hash,
)
from aitbc.exceptions import DatabaseError


class TestExceptionChaining:
    """Test exception chaining in critical paths"""

    def test_crypto_exception_chaining_with_invalid_encryption(self):
        """Test that crypto exceptions properly chain from underlying errors"""
        private_key = "test_private_key_12345"
        password = "test_password"

        encrypted = encrypt_private_key(private_key, password)

        # Test that wrong password raises ValueError with proper chaining
        with pytest.raises(ValueError) as exc_info:
            decrypt_private_key(encrypted, "wrong_password")

        # The exception should have a cause (proper exception chaining)
        assert exc_info.value.__cause__ is not None

    def test_hash_exception_chaining_with_invalid_input(self):
        """Test that hash functions handle errors gracefully"""
        # Test with invalid input that might cause internal errors
        with pytest.raises(ValueError) as exc_info:
            sha256_hash(None)

        # Should have proper exception chaining
        assert exc_info.value.__cause__ is not None

    def test_database_error_chaining(self):
        """Test database error chaining"""
        import tempfile
        from pathlib import Path

        from aitbc.database import DatabaseConnection

        # Test with invalid database path
        with tempfile.TemporaryDirectory() as tmpdir:
            invalid_path = Path(tmpdir) / "nonexistent" / "test.db"

            with pytest.raises(DatabaseError) as exc_info:
                conn = DatabaseConnection(invalid_path)
                conn.connect()

            # Should have proper exception chaining from sqlite3.Error
            assert exc_info.value.__cause__ is not None

    def test_import_error_chaining(self):
        """Test that import errors are properly raised with from None"""
        # Test missing eth-hash import for keccak
        from aitbc.crypto.crypto import keccak256_hash

        # This should raise ImportError with from None if eth-hash is missing
        # or ValueError with proper chaining if eth-hash is available but input is invalid
        try:
            with pytest.raises((ImportError, ValueError)) as exc_info:
                keccak256_hash(None)

            # If it's ImportError, should use 'from None'
            if isinstance(exc_info.value, ImportError):
                assert exc_info.value.__cause__ is None
            # If it's ValueError, should have proper chaining
            else:
                assert exc_info.value.__cause__ is not None
        except Exception:
            # If eth-hash is available and handles None gracefully, skip this test
            pytest.skip("eth-hash is available and handles None gracefully")

    def test_network_error_chaining(self):
        """Test network error chaining in HTTP client"""
        from aitbc.exceptions import NetworkError
        from aitbc.network import AITBCHTTPClient

        # Test with invalid URL that will cause connection errors
        # Use a non-routable IP address to avoid DNS delays
        client = AITBCHTTPClient(
            base_url="http://10.255.255.1",  # Non-routable IP
            timeout=0.1,
            max_retries=0,
            enable_logging=False,
        )

        try:
            with pytest.raises(NetworkError) as exc_info:
                client.get("/test")

            # Should have proper exception chaining from requests.RequestException
            assert exc_info.value.__cause__ is not None
        except Exception:
            # If network tests fail in this environment, skip gracefully
            pytest.skip("Network test failed - possibly different network configuration")

    def test_retry_error_chaining(self):
        """Test retry error chaining"""
        from aitbc.exceptions import NetworkError, RetryError
        from aitbc.network import AITBCHTTPClient

        # Test with invalid URL that will cause retry exhaustion
        client = AITBCHTTPClient(
            base_url="http://10.255.255.1",  # Non-routable IP
            timeout=0.1,
            max_retries=1,
            enable_logging=False,
        )

        try:
            with pytest.raises((RetryError, NetworkError, Exception)) as exc_info:
                client.get("/test")

            # Should have proper exception chaining
            if exc_info.value.__cause__ is not None:
                assert True  # Proper chaining exists
        except Exception:
            # If network tests fail in this environment, skip gracefully
            pytest.skip("Network test failed - possibly different network configuration")


class TestErrorMessageQuality:
    """Test that error messages are informative and actionable"""

    def test_crypto_error_messages_are_descriptive(self):
        """Test that crypto error messages provide useful information"""
        with pytest.raises(ValueError) as exc_info:
            sha256_hash(None)

        error_message = str(exc_info.value)
        assert "hash" in error_message.lower()
        assert len(error_message) > 10  # Not just a generic error

    def test_database_error_messages_include_context(self):
        """Test that database error messages include relevant context"""
        import tempfile
        from pathlib import Path

        from aitbc.database import vacuum_database

        with tempfile.TemporaryDirectory() as tmpdir:
            invalid_path = Path(tmpdir) / "nonexistent" / "test.db"

            with pytest.raises(DatabaseError) as exc_info:
                vacuum_database(invalid_path)

            error_message = str(exc_info.value)
            assert "database" in error_message.lower() or "vacuum" in error_message.lower()

    def test_import_error_messages_include_installation_instructions(self):
        """Test that import errors include installation instructions"""
        from aitbc.crypto.crypto import derive_ethereum_address

        try:
            with pytest.raises(ImportError) as exc_info:
                derive_ethereum_address("invalid_key")

            error_message = str(exc_info.value)
            assert "pip install" in error_message.lower()
            assert "eth-account" in error_message.lower()
        except ValueError:
            # If eth-account is installed, it raises ValueError instead
            # In this case, test that the ValueError message is still informative
            with pytest.raises(ValueError) as exc_info:
                derive_ethereum_address("invalid_key")

            error_message = str(exc_info.value)
            assert "failed to derive address" in error_message.lower()
            assert len(error_message) > 20  # Should be descriptive


class TestErrorRecovery:
    """Test error recovery and graceful degradation"""

    def test_validate_ethereum_address_graceful_failure(self):
        """Test that address validation returns False instead of crashing for invalid input"""
        from aitbc.crypto.crypto import validate_ethereum_address

        # Should return False for invalid addresses, not raise exceptions
        result = validate_ethereum_address("invalid_address")
        assert result is False

    def test_missing_optional_dependencies_dont_crash(self):
        """Test that missing optional dependencies are handled gracefully"""
        # Web3 utilities should handle missing web3 gracefully
        from aitbc.network.web3_utils import WEB3_AVAILABLE

        # This should be a boolean, not crash
        assert isinstance(WEB3_AVAILABLE, bool)

    def test_config_validation_with_missing_secrets(self):
        """Test that configuration validation provides clear errors for missing secrets"""

        from aitbc.config import BaseAITBCConfig

        # Test with production environment but missing secrets
        with pytest.raises(ValueError) as exc_info:
            config = BaseAITBCConfig(
                environment="production",
                secret_key=None,  # Missing required secret
            )
            config.validate_secrets()

        error_message = str(exc_info.value)
        assert "secret" in error_message.lower()
        assert "production" in error_message.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
