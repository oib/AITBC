"""
Crypto Utils Tests
Tests for cryptographic utility functions
"""

import sys
from pathlib import Path
from unittest.mock import patch, Mock

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestCreateSignatureChallenge:
    """Test create_signature_challenge function"""

    def test_create_signature_challenge(self):
        """Test creating a signature challenge"""
        from aitbc_cli.utils.crypto_utils import create_signature_challenge
        
        tx_data = {
            "tx_id": "tx123",
            "to": "0xabc123",
            "amount": 100,
            "timestamp": 1234567890
        }
        nonce = "nonce123"
        
        result = create_signature_challenge(tx_data, nonce)
        
        assert result.startswith("AITBC_MULTISIG_CHALLENGE:")
        assert len(result) > len("AITBC_MULTISIG_CHALLENGE:")

    def test_create_signature_challenge_deterministic(self):
        """Test that challenge is deterministic for same inputs"""
        from aitbc_cli.utils.crypto_utils import create_signature_challenge
        
        tx_data = {
            "tx_id": "tx123",
            "to": "0xabc123",
            "amount": 100,
            "timestamp": 1234567890
        }
        nonce = "nonce123"
        
        result1 = create_signature_challenge(tx_data, nonce)
        result2 = create_signature_challenge(tx_data, nonce)
        
        assert result1 == result2

    def test_create_signature_challenge_different_inputs(self):
        """Test that different inputs produce different challenges"""
        from aitbc_cli.utils.crypto_utils import create_signature_challenge
        
        tx_data1 = {
            "tx_id": "tx123",
            "to": "0xabc123",
            "amount": 100,
            "timestamp": 1234567890
        }
        tx_data2 = {
            "tx_id": "tx456",
            "to": "0xabc123",
            "amount": 100,
            "timestamp": 1234567890
        }
        nonce = "nonce123"
        
        result1 = create_signature_challenge(tx_data1, nonce)
        result2 = create_signature_challenge(tx_data2, nonce)
        
        assert result1 != result2


class TestVerifySignature:
    """Test verify_signature function"""

    def test_verify_signature_invalid_signature_format(self):
        """Test verifying with invalid signature format"""
        from aitbc_cli.utils.crypto_utils import verify_signature
        
        challenge = "test_challenge"
        invalid_signature = "not_a_hex_signature"
        signer_address = "0xabc123"
        
        result = verify_signature(challenge, invalid_signature, signer_address)
        
        assert result is False

    def test_verify_signature_empty_signature(self):
        """Test verifying with empty signature"""
        from aitbc_cli.utils.crypto_utils import verify_signature
        
        challenge = "test_challenge"
        empty_signature = ""
        signer_address = "0xabc123"
        
        result = verify_signature(challenge, empty_signature, signer_address)
        
        assert result is False


class TestSignChallenge:
    """Test sign_challenge function"""

    def test_sign_challenge_invalid_key(self):
        """Test signing with invalid private key"""
        from aitbc_cli.utils.crypto_utils import sign_challenge
        
        challenge = "test_challenge"
        invalid_key = "invalid_key"
        
        # Should raise ValueError for invalid key
        with pytest.raises(ValueError):
            sign_challenge(challenge, invalid_key)

    def test_sign_challenge_empty_key(self):
        """Test signing with empty private key"""
        from aitbc_cli.utils.crypto_utils import sign_challenge
        
        challenge = "test_challenge"
        empty_key = ""
        
        # Should raise ValueError for empty key
        with pytest.raises(ValueError):
            sign_challenge(challenge, empty_key)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
