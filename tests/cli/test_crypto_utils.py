"""
Tests for cryptographic utility functions
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest
from aitbc_cli.utils.crypto_utils import (
    MultisigSecurityManager,
    bech32_to_hex,
    create_signature_challenge,
    generate_nonce,
    hex_to_bech32,
    validate_multisig_transaction,
)


class TestCreateSignatureChallenge:
    """Test create_signature_challenge function"""

    def test_create_challenge_basic(self):
        """Test basic challenge creation"""
        tx_data = {
            "tx_id": "tx123",
            "to": "ait123",
            "amount": 100,
            "timestamp": 1234567890
        }
        nonce = "abc123"

        challenge = create_signature_challenge(tx_data, nonce)

        assert "AITBC_MULTISIG_CHALLENGE:" in challenge
        assert len(challenge) > len("AITBC_MULTISIG_CHALLENGE:")

    def test_create_challenge_with_missing_fields(self):
        """Test challenge creation with missing fields"""
        tx_data = {
            "tx_id": "tx123"
        }
        nonce = "abc123"

        challenge = create_signature_challenge(tx_data, nonce)

        assert "AITBC_MULTISIG_CHALLENGE:" in challenge

    def test_create_challenge_deterministic(self):
        """Test that same inputs produce same challenge"""
        tx_data = {
            "tx_id": "tx123",
            "to": "ait123",
            "amount": 100,
            "timestamp": 1234567890
        }
        nonce = "abc123"

        challenge1 = create_signature_challenge(tx_data, nonce)
        challenge2 = create_signature_challenge(tx_data, nonce)

        assert challenge1 == challenge2


class TestGenerateNonce:
    """Test generate_nonce function"""

    def test_generate_nonce_length(self):
        """Test nonce has correct length"""
        nonce = generate_nonce()

        # token_hex(16) produces 32 hex characters
        assert len(nonce) == 32

    def test_generate_nonce_unique(self):
        """Test that nonces are unique"""
        nonce1 = generate_nonce()
        nonce2 = generate_nonce()

        assert nonce1 != nonce2

    def test_generate_nonce_hex_format(self):
        """Test nonce is valid hex"""
        nonce = generate_nonce()

        try:
            int(nonce, 16)
        except ValueError:
            pytest.fail("Nonce is not valid hex")


class TestValidateMultisigTransaction:
    """Test validate_multisig_transaction function"""

    def test_validate_valid_transaction(self):
        """Test validation of valid transaction"""
        tx_data = {
            "tx_id": "tx123",
            "to": "ait1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
            "amount": 100,
            "timestamp": 1234567890,
            "nonce": "abc123"
        }

        is_valid, error = validate_multisig_transaction(tx_data)

        assert is_valid is True
        assert error == ""

    def test_validate_missing_field(self):
        """Test validation with missing required field"""
        tx_data = {
            "to": "ait123",
            "amount": 100,
            "timestamp": 1234567890,
            "nonce": "abc123"
        }

        is_valid, error = validate_multisig_transaction(tx_data)

        assert is_valid is False
        assert "Missing required field" in error

    def test_validate_invalid_address_prefix(self):
        """Test validation with invalid address prefix"""
        tx_data = {
            "tx_id": "tx123",
            "to": "eth123",
            "amount": 100,
            "timestamp": 1234567890,
            "nonce": "abc123"
        }

        is_valid, error = validate_multisig_transaction(tx_data)

        assert is_valid is False
        assert "must start with 'ait'" in error

    def test_validate_invalid_address_length(self):
        """Test validation with invalid address length"""
        tx_data = {
            "tx_id": "tx123",
            "to": "ait123",
            "amount": 100,
            "timestamp": 1234567890,
            "nonce": "abc123"
        }

        is_valid, error = validate_multisig_transaction(tx_data)

        assert is_valid is False
        assert "invalid length" in error

    def test_validate_invalid_address_characters(self):
        """Test validation with invalid address characters"""
        tx_data = {
            "tx_id": "tx123",
            "to": "ait1234567890ghijkl1234567890abcdef1234567890abcdef1234567890ab",
            "amount": 100,
            "timestamp": 1234567890,
            "nonce": "abc123"
        }

        is_valid, error = validate_multisig_transaction(tx_data)

        assert is_valid is False
        assert "invalid characters" in error

    def test_validate_negative_amount(self):
        """Test validation with negative amount"""
        tx_data = {
            "tx_id": "tx123",
            "to": "ait1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
            "amount": -100,
            "timestamp": 1234567890,
            "nonce": "abc123"
        }

        is_valid, error = validate_multisig_transaction(tx_data)

        assert is_valid is False
        assert "positive" in error

    def test_validate_invalid_amount_format(self):
        """Test validation with invalid amount format"""
        tx_data = {
            "tx_id": "tx123",
            "to": "ait1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
            "amount": "invalid",
            "timestamp": 1234567890,
            "nonce": "abc123"
        }

        is_valid, error = validate_multisig_transaction(tx_data)

        assert is_valid is False
        assert "Invalid amount format" in error


class TestBech32ToHex:
    """Test bech32_to_hex function"""

    def test_bech32_to_hex_aitbc1_prefix(self):
        """Test conversion with aitbc1 prefix"""
        bech32 = "aitbc1c10f0e4f"

        result = bech32_to_hex(bech32)

        assert result == "0xc10f0e4f"

    def test_bech32_to_hex_ait1_prefix(self):
        """Test conversion with ait1 prefix"""
        bech32 = "ait1c10f0e4f"

        result = bech32_to_hex(bech32)

        assert result == "0xc10f0e4f"

    def test_bech32_to_hex_already_hex(self):
        """Test conversion with already hex address"""
        hex_addr = "c10f0e4f"

        result = bech32_to_hex(hex_addr)

        assert result == "0xc10f0e4f"

    def test_bech32_to_hex_with_0x_prefix(self):
        """Test conversion with 0x prefix"""
        hex_addr = "0xc10f0e4f"

        result = bech32_to_hex(hex_addr)

        assert result == "0xc10f0e4f"

    def test_bech32_to_hex_empty(self):
        """Test conversion with empty string"""
        with pytest.raises(ValueError) as exc_info:
            bech32_to_hex("")

        assert "cannot be empty" in str(exc_info.value)


class TestHexToBech32:
    """Test hex_to_bech32 function"""

    def test_hex_to_bech32_without_prefix(self):
        """Test conversion without 0x prefix"""
        hex_addr = "c10f0e4f"

        result = hex_to_bech32(hex_addr)

        assert result == "aitbc1c10f0e4f"

    def test_hex_to_bech32_with_prefix(self):
        """Test conversion with 0x prefix"""
        hex_addr = "0xc10f0e4f"

        result = hex_to_bech32(hex_addr)

        assert result == "aitbc1c10f0e4f"

    def test_hex_to_bech32_empty(self):
        """Test conversion with empty string"""
        with pytest.raises(ValueError) as exc_info:
            hex_to_bech32("")

        assert "cannot be empty" in str(exc_info.value)


class TestMultisigSecurityManager:
    """Test MultisigSecurityManager class"""

    def test_create_signing_request_valid(self):
        """Test creating signing request with valid transaction"""
        manager = MultisigSecurityManager()
        tx_data = {
            "tx_id": "tx123",
            "to": "ait1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
            "amount": 100,
            "timestamp": 1234567890,
            "nonce": "abc123",
            "required_signers": ["addr1", "addr2"]
        }

        result = manager.create_signing_request(tx_data, "wallet123")

        assert result["tx_id"] == "tx123"
        assert "challenge" in result
        assert "nonce" in result
        assert result["signers_required"] == 2

    def test_create_signing_request_invalid_transaction(self):
        """Test creating signing request with invalid transaction"""
        manager = MultisigSecurityManager()
        tx_data = {
            "to": "ait123",
            "amount": 100
        }

        with pytest.raises(ValueError) as exc_info:
            manager.create_signing_request(tx_data, "wallet123")

        assert "Invalid transaction" in str(exc_info.value)

    def test_verify_and_add_signature_valid(self):
        """Test verifying and adding valid signature"""
        manager = MultisigSecurityManager()
        tx_data = {
            "tx_id": "tx123",
            "to": "ait1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
            "amount": 100,
            "timestamp": 1234567890,
            "nonce": "abc123",
            "required_signers": ["addr1", "addr2"]
        }

        manager.create_signing_request(tx_data, "wallet123")

        # Mock signature verification (would need real signing in production)
        success, message = manager.verify_and_add_signature("tx123", "0x123", "addr1")

        # Will fail signature verification but test the flow
        assert success is False
        assert "Invalid signature" in message

    def test_verify_and_add_signature_not_found(self):
        """Test verifying signature for non-existent transaction"""
        manager = MultisigSecurityManager()

        success, message = manager.verify_and_add_signature("nonexistent", "0x123", "addr1")

        assert success is False
        assert "not found" in message

    def test_cleanup_challenge(self):
        """Test cleaning up challenge"""
        manager = MultisigSecurityManager()
        tx_data = {
            "tx_id": "tx123",
            "to": "ait1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
            "amount": 100,
            "timestamp": 1234567890,
            "nonce": "abc123",
            "required_signers": []
        }

        manager.create_signing_request(tx_data, "wallet123")
        assert "tx123" in manager.pending_challenges

        manager.cleanup_challenge("tx123")
        assert "tx123" not in manager.pending_challenges

    def test_cleanup_nonexistent_challenge(self):
        """Test cleaning up non-existent challenge"""
        manager = MultisigSecurityManager()

        # Should not raise error
        manager.cleanup_challenge("nonexistent")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
