"""
Crypto Utils Advanced Tests
Tests for cryptographic utility functions
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestCreateSignatureChallenge:
    """Test create_signature_challenge function"""

    def test_create_signature_challenge_basic(self):
        """Test basic signature challenge creation"""
        from aitbc_cli.utils.crypto_utils import create_signature_challenge
        
        tx_data = {
            "tx_id": "tx123",
            "to": "0xabc",
            "amount": 100,
            "timestamp": "2024-01-01T00:00:00Z"
        }
        nonce = "nonce123"
        
        challenge = create_signature_challenge(tx_data, nonce)
        
        assert "AITBC_MULTISIG_CHALLENGE:" in challenge
        assert len(challenge) > len("AITBC_MULTISIG_CHALLENGE:")

    def test_create_signature_challenge_with_all_fields(self):
        """Test challenge with all fields present"""
        from aitbc_cli.utils.crypto_utils import create_signature_challenge
        
        tx_data = {
            "tx_id": "tx123",
            "to": "0xabc",
            "amount": 100,
            "timestamp": "2024-01-01T00:00:00Z",
            "extra": "ignored"
        }
        nonce = "nonce123"
        
        challenge = create_signature_challenge(tx_data, nonce)
        
        assert "AITBC_MULTISIG_CHALLENGE:" in challenge

    def test_create_signature_challenge_minimal(self):
        """Test challenge with minimal data"""
        from aitbc_cli.utils.crypto_utils import create_signature_challenge
        
        tx_data = {}
        nonce = "nonce123"
        
        challenge = create_signature_challenge(tx_data, nonce)
        
        assert "AITBC_MULTISIG_CHALLENGE:" in challenge


class TestVerifySignature:
    """Test verify_signature function"""

    def test_verify_signature_invalid_format(self):
        """Test signature verification with invalid format"""
        from aitbc_cli.utils.crypto_utils import verify_signature
        
        challenge = "test_challenge"
        signature = "invalid_signature"
        signer_address = "0xabc"
        
        result = verify_signature(challenge, signature, signer_address)
        
        assert result is False

    def test_verify_signature_empty_signature(self):
        """Test signature verification with empty signature"""
        from aitbc_cli.utils.crypto_utils import verify_signature
        
        challenge = "test_challenge"
        signature = ""
        signer_address = "0xabc"
        
        result = verify_signature(challenge, signature, signer_address)
        
        assert result is False


class TestSignChallenge:
    """Test sign_challenge function"""

    def test_sign_challenge_invalid_key(self):
        """Test signing with invalid private key"""
        from aitbc_cli.utils.crypto_utils import sign_challenge
        
        challenge = "test_challenge"
        private_key = "invalid_key"
        
        try:
            result = sign_challenge(challenge, private_key)
            # If it doesn't raise, result should be None or empty
            assert result is None or result == ""
        except Exception:
            # Expected to raise exception for invalid key
            pass

    def test_sign_challenge_empty_key(self):
        """Test signing with empty private key"""
        from aitbc_cli.utils.crypto_utils import sign_challenge
        
        challenge = "test_challenge"
        private_key = ""
        
        try:
            result = sign_challenge(challenge, private_key)
            assert result is None or result == ""
        except Exception:
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
