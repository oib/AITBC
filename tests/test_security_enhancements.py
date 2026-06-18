"""
Security Enhancement Tests
Tests for enhanced secret management and blockchain-specific validation
"""

import pytest

from aitbc.crypto import SecretManager
from aitbc.security import SecurityValidator


class TestEnhancedSecretManager:
    """Test enhanced secret management features"""

    def test_secret_with_expiration(self):
        """Test secret expiration tracking"""
        manager = SecretManager(default_ttl_hours=1)

        # Set a secret with 1-hour TTL
        manager.set_secret("test_key", "secret_value", ttl_hours=1)

        # Should be accessible immediately
        assert manager.get_secret("test_key") == "secret_value"

        # Check metadata
        metadata = manager.get_secret_metadata("test_key")
        assert metadata is not None
        assert metadata["version"] == 1
        assert metadata["rotated_at"] is None
        assert not metadata["is_expired"]

    def test_secret_rotation(self):
        """Test secret rotation with version tracking"""
        manager = SecretManager()

        # Set initial secret
        manager.set_secret("api_key", "initial_value")
        assert manager.get_secret("api_key") == "initial_value"

        # Rotate secret
        success = manager.rotate_secret("api_key", "new_value")
        assert success
        assert manager.get_secret("api_key") == "new_value"

        # Check version incremented
        metadata = manager.get_secret_metadata("api_key")
        assert metadata["version"] == 2
        assert metadata["rotated_at"] is not None

    def test_secret_cleanup_expired(self):
        """Test cleanup of expired secrets"""
        manager = SecretManager(default_ttl_hours=1)

        # Set a secret with negative TTL to force immediate expiration
        manager.set_secret("temp_key", "temp_value", ttl_hours=-1)  # Already expired

        # Should be cleaned up
        cleaned = manager.cleanup_expired_secrets()
        assert cleaned >= 0

        # Secret should no longer be accessible
        assert manager.get_secret("temp_key") is None

    def test_encryption_key_rotation(self):
        """Test master encryption key rotation"""
        manager = SecretManager()

        # Set some secrets
        manager.set_secret("key1", "value1")
        manager.set_secret("key2", "value2")

        # Get current encryption key
        old_key = manager.get_encryption_key()

        # Rotate to new key
        from cryptography.fernet import Fernet

        new_key = Fernet.generate_key().decode("utf-8")
        success = manager.rotate_encryption_key(new_key)

        assert success
        assert manager.get_encryption_key() != old_key

        # Secrets should still be accessible
        assert manager.get_secret("key1") == "value1"
        assert manager.get_secret("key2") == "value2"

    def test_secret_export_without_values(self):
        """Test secret metadata export without values"""
        manager = SecretManager()
        manager.set_secret("test_key", "secret_value")

        # Export without values (safe)
        export = manager.export_secrets(include_values=False)
        assert "test_key" in export
        assert "value" not in export["test_key"]
        assert export["test_key"]["version"] == 1

    def test_secret_export_with_values(self):
        """Test secret export with values (use with caution)"""
        manager = SecretManager()
        manager.set_secret("test_key", "secret_value")

        # Export with values (for backup)
        export = manager.export_secrets(include_values=True)
        assert "test_key" in export
        assert export["test_key"]["value"] == "secret_value"

    def test_list_secrets_filters_expired(self):
        """Test that listing secrets can filter expired ones"""
        manager = SecretManager(default_ttl_hours=1)

        manager.set_secret("active_key", "active_value", ttl_hours=24)
        manager.set_secret("expired_key", "expired_value", ttl_hours=0)

        # Clean up expired first
        manager.cleanup_expired_secrets()

        # List should only show active secrets by default
        active_keys = manager.list_secrets(include_expired=False)
        assert "active_key" in active_keys

        # Including expired should show both (if they weren't cleaned)
        all_keys = manager.list_secrets(include_expired=True)
        assert len(all_keys) >= 1


class TestBlockchainValidation:
    """Test blockchain-specific input validation"""

    def test_validate_private_key_valid(self):
        """Test valid private key validation"""
        valid_keys = [
            "0x" + "a" * 64,
            "f" * 64,
            "0x1234567890abcdef" + "0" * 48,  # Mix of hex chars
        ]

        for key in valid_keys:
            assert SecurityValidator.validate_ethereum_private_key(key)

    def test_validate_private_key_invalid(self):
        """Test invalid private key validation"""
        invalid_keys = [
            "short_key",
            "0x" + "g" * 64,  # Invalid hex character
            "0x" + "a" * 63,  # Too short
            "0x" + "a" * 65,  # Too long
            "",  # Empty
            "not_a_key_at_all",
        ]

        for key in invalid_keys:
            assert not SecurityValidator.validate_ethereum_private_key(key)

    def test_validate_chain_id_valid(self):
        """Test valid chain ID validation"""
        valid_chain_ids = [1, 1337, 56, 137, "1", "1337", "56"]

        for chain_id in valid_chain_ids:
            assert SecurityValidator.validate_chain_id(chain_id)

    def test_validate_chain_id_invalid(self):
        """Test invalid chain ID validation"""
        invalid_chain_ids = [0, -1, "0", "-1", "abc", "", "1.5"]

        for chain_id in invalid_chain_ids:
            assert not SecurityValidator.validate_chain_id(chain_id)

    def test_validate_contract_address_valid(self):
        """Test valid contract address validation"""
        valid_addresses = ["0x" + "a" * 40, "0x1234567890abcdef1234567890abcdef12345678", "0x" + "0" * 40]

        for address in valid_addresses:
            assert SecurityValidator.validate_contract_address(address)

    def test_validate_contract_address_invalid(self):
        """Test invalid contract address validation"""
        invalid_addresses = [
            "0x" + "a" * 39,  # Too short
            "0x" + "a" * 41,  # Too long
            "0x" + "g" * 40,  # Invalid hex
            "",  # Empty
        ]

        for address in invalid_addresses:
            assert not SecurityValidator.validate_contract_address(address)

    def test_validate_block_number_valid(self):
        """Test valid block number validation"""
        valid_blocks = [1, 1000000, 12345678, "1", "1000000"]

        for block in valid_blocks:
            assert SecurityValidator.validate_block_number(block)

    def test_validate_block_number_invalid(self):
        """Test invalid block number validation"""
        invalid_blocks = [0, -1, "0", "-1", "abc", ""]

        for block in invalid_blocks:
            assert not SecurityValidator.validate_block_number(block)

    def test_validate_gas_price_valid(self):
        """Test valid gas price validation"""
        valid_prices = [1, 1000000000, 5000000000, "1", "1000000000"]

        for price in valid_prices:
            assert SecurityValidator.validate_gas_price(price)

    def test_validate_gas_price_invalid(self):
        """Test invalid gas price validation"""
        invalid_prices = [0, -1, "0", "-1", "abc", ""]

        for price in invalid_prices:
            assert not SecurityValidator.validate_gas_price(price)

    def test_validate_gas_limit_valid(self):
        """Test valid gas limit validation"""
        valid_limits = [21000, 100000, 8000000, "21000", "100000"]

        for limit in valid_limits:
            assert SecurityValidator.validate_gas_limit(limit)

    def test_validate_gas_limit_invalid(self):
        """Test invalid gas limit validation"""
        invalid_limits = [0, -1, 100000000, "0", "-1", "abc"]

        for limit in invalid_limits:
            assert not SecurityValidator.validate_gas_limit(limit)

    def test_validate_transaction_data_valid(self):
        """Test valid transaction data validation"""
        valid_data = [
            "",  # Empty is valid
            "0x",  # Just prefix
            "0xaabbcc",  # Valid hex
            "deadbeef",  # Valid hex without prefix
            "0x" + "00" * 32,  # 32 bytes of zeros
        ]

        for data in valid_data:
            assert SecurityValidator.validate_transaction_data(data)

    def test_validate_transaction_data_invalid(self):
        """Test invalid transaction data validation"""
        invalid_data = [
            "0xggg",  # Invalid hex
            "xyz",  # Invalid hex without prefix
        ]

        for data in invalid_data:
            assert not SecurityValidator.validate_transaction_data(data)

    def test_validate_amount_valid(self):
        """Test valid amount validation"""
        valid_amounts = [0, 1, 100.5, "0", "1", "100.5", 0.001]

        for amount in valid_amounts:
            assert SecurityValidator.validate_amount(amount)

    def test_validate_amount_invalid(self):
        """Test invalid amount validation"""
        invalid_amounts = [-1, "-1", -100.5, "abc", ""]

        for amount in invalid_amounts:
            assert not SecurityValidator.validate_amount(amount)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
