"""
Tests for AITBC crypto module (crypto/crypto.py)
This module has 0% coverage and 110 statements.
"""

from unittest.mock import Mock, patch

import pytest

# Import the module normally
from aitbc.crypto import crypto

# ============================================================================
# Ethereum Address Derivation Tests
# ============================================================================


class TestDeriveEthereumAddress:
    """Test derive_ethereum_address function"""

    def test_derive_address_missing_dependency(self):
        with patch.dict("sys.modules", {"eth_account": None}):
            with pytest.raises(ImportError, match="eth-account is required"):
                crypto.derive_ethereum_address("test_key")

    def test_derive_address_with_0x_prefix(self):
        with patch.dict("sys.modules", {"eth_account": Mock()}):
            from eth_account import Account as MockAccount

            mock_account_instance = Mock()
            mock_account_instance.address = "0xABC123"
            MockAccount.from_key.return_value = mock_account_instance

            result = crypto.derive_ethereum_address("0xtest_key")
            assert result == "0xABC123"

    def test_derive_address_without_0x_prefix(self):
        with patch.dict("sys.modules", {"eth_account": Mock()}):
            from eth_account import Account as MockAccount

            mock_account_instance = Mock()
            mock_account_instance.address = "0xABC123"
            MockAccount.from_key.return_value = mock_account_instance

            result = crypto.derive_ethereum_address("test_key")
            assert result == "0xABC123"

    def test_derive_address_invalid_key(self):
        with patch.dict("sys.modules", {"eth_account": Mock()}):
            from eth_account import Account as MockAccount

            MockAccount.from_key.side_effect = Exception("Invalid key")

            with pytest.raises(ValueError, match="Failed to derive address"):
                crypto.derive_ethereum_address("invalid_key")


# ============================================================================
# Transaction Signing Tests
# ============================================================================


class TestSignTransactionHash:
    """Test sign_transaction_hash function"""

    def test_sign_hash_missing_dependency(self):
        with patch.dict("sys.modules", {"eth_account": None}):
            with pytest.raises(ImportError, match="eth-account is required"):
                crypto.sign_transaction_hash("hash", "key")

    def test_sign_hash_with_0x_prefixes(self):
        with patch.dict("sys.modules", {"eth_account": Mock()}):
            from eth_account import Account as MockAccount

            mock_account_instance = Mock()
            mock_signed = Mock()
            mock_signed.signature.hex.return_value = "0xsig123"
            mock_account_instance.unsafe_sign_hash.return_value = mock_signed
            MockAccount.from_key.return_value = mock_account_instance

            result = crypto.sign_transaction_hash("0x1234567890abcdef", "0x1234567890abcdef")
            assert result == "0xsig123"

    def test_sign_hash_without_prefixes(self):
        with patch.dict("sys.modules", {"eth_account": Mock()}):
            from eth_account import Account as MockAccount

            mock_account_instance = Mock()
            mock_signed = Mock()
            mock_signed.signature.hex.return_value = "0xsig123"
            mock_account_instance.unsafe_sign_hash.return_value = mock_signed
            MockAccount.from_key.return_value = mock_account_instance

            result = crypto.sign_transaction_hash("1234567890abcdef", "1234567890abcdef")
            assert result == "0xsig123"

    def test_sign_hash_error(self):
        with patch.dict("sys.modules", {"eth_account": Mock()}):
            from eth_account import Account as MockAccount

            MockAccount.from_key.side_effect = Exception("Sign error")

            with pytest.raises(ValueError, match="Failed to sign"):
                crypto.sign_transaction_hash("1234567890abcdef", "1234567890abcdef")


# ============================================================================
# Signature Verification Tests
# ============================================================================


class TestVerifySignature:
    """Test verify_signature function"""

    # These mocked eth_account.Account._recover_hash and asserted on what the mock
    # returned, which pinned a private third-party API rather than any behaviour of
    # verify_signature. They passed whether or not verification worked, and would break on
    # any refactor that moved recovery -- as consolidating it onto _recover_address did,
    # while nothing about verification changed. test_verify_signature_error was worse: it
    # mocked a method the code no longer calls, so the ValueError it asserted came from
    # somewhere else entirely and it passed by accident.
    #
    # They now sign with a real key and check the result, which is the only assertion that
    # separates a working verifier from a broken one.

    _PRIVATE_KEY = "0x" + "42" * 32

    def _digest_and_signature(self):
        import hashlib

        from eth_account import Account

        account = Account.from_key(self._PRIVATE_KEY)
        digest = hashlib.sha256(b"a message").digest()
        signature = "0x" + account.unsafe_sign_hash(digest).signature.hex()
        return digest.hex(), signature, account.address

    def test_verify_signature_valid(self):
        digest_hex, signature, address = self._digest_and_signature()

        assert crypto.verify_signature(digest_hex, signature, address) is True

    def test_verify_signature_accepts_a_standard_recovery_id(self):
        """v is 27/28 from any standard signer; the verifier must take it (V23-01)."""
        from eth_account import Account

        raw = Account.from_key(self._PRIVATE_KEY).unsafe_sign_hash(bytes(32)).signature
        assert raw[64] in (27, 28)

        assert crypto.verify_signature(bytes(32).hex(), "0x" + raw.hex(), Account.from_key(self._PRIVATE_KEY).address)

    def test_verify_signature_accepts_an_unprefixed_address(self):
        digest_hex, signature, address = self._digest_and_signature()

        assert crypto.verify_signature(digest_hex, signature, address.removeprefix("0x")) is True

    def test_verify_signature_invalid(self):
        from eth_account import Account

        digest_hex, signature, _ = self._digest_and_signature()
        other = Account.from_key("0x" + "43" * 32)

        assert crypto.verify_signature(digest_hex, signature, other.address) is False

    def test_verify_signature_rejects_a_tampered_digest(self):
        import hashlib

        _, signature, address = self._digest_and_signature()
        tampered = hashlib.sha256(b"a different message").digest().hex()

        assert crypto.verify_signature(tampered, signature, address) is False

    def test_verify_signature_error(self):
        """A signature that cannot be decoded is an error, not a quiet False."""
        digest_hex, _, address = self._digest_and_signature()

        with pytest.raises(ValueError, match="Failed to verify signature"):
            crypto.verify_signature(digest_hex, "0xdeadbeef", address)


# ============================================================================
# Private Key Encryption Tests
# ============================================================================


class TestEncryptPrivateKey:
    """Test encrypt_private_key function"""

    def test_encrypt_private_key_success(self):
        result = crypto.encrypt_private_key("my_secret_key", "password123")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_encrypt_private_key_different_passwords(self):
        key1 = crypto.encrypt_private_key("my_secret_key", "password123")
        key2 = crypto.encrypt_private_key("my_secret_key", "different_password")
        assert key1 != key2  # Different passwords should produce different encrypted keys

    def test_encrypt_private_key_same_password_different_salt(self):
        key1 = crypto.encrypt_private_key("my_secret_key", "password123")
        key2 = crypto.encrypt_private_key("my_secret_key", "password123")
        assert key1 != key2  # Random salt should produce different outputs


# ============================================================================
# Private Key Decryption Tests
# ============================================================================


class TestDecryptPrivateKey:
    """Test decrypt_private_key function"""

    def test_decrypt_private_key_success(self):
        original_key = "my_secret_key"
        password = "password123"
        encrypted = crypto.encrypt_private_key(original_key, password)

        decrypted = crypto.decrypt_private_key(encrypted, password)
        assert decrypted == original_key

    def test_decrypt_private_key_wrong_password(self):
        original_key = "my_secret_key"
        password = "password123"
        encrypted = crypto.encrypt_private_key(original_key, password)

        with pytest.raises(ValueError, match="Failed to decrypt"):
            crypto.decrypt_private_key(encrypted, "wrong_password")

    def test_decrypt_private_key_invalid_data(self):
        with pytest.raises(ValueError, match="Failed to decrypt"):
            crypto.decrypt_private_key("invalid_encrypted_data", "password")


# ============================================================================
# Secure Random Bytes Tests
# ============================================================================


class TestGenerateSecureRandomBytes:
    """Test generate_secure_random_bytes function"""

    def test_generate_random_bytes_default_length(self):
        result = crypto.generate_secure_random_bytes()
        assert isinstance(result, str)
        assert len(result) == 64  # 32 bytes = 64 hex chars

    def test_generate_random_bytes_custom_length(self):
        result = crypto.generate_secure_random_bytes(16)
        assert isinstance(result, str)
        assert len(result) == 32  # 16 bytes = 32 hex chars

    def test_generate_random_bytes_different_results(self):
        result1 = crypto.generate_secure_random_bytes()
        result2 = crypto.generate_secure_random_bytes()
        assert result1 != result2  # Should be random


# ============================================================================
# Keccak-256 Hash Tests
# ============================================================================


class TestKeccak256Hash:
    """Test keccak256_hash function"""

    def test_keccak256_missing_dependency(self):
        pytest.skip("eth-hash dependency test skipped - module handles import internally")

    def test_keccak256_string_input(self):
        result = crypto.keccak256_hash("test")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_keccak256_bytes_input(self):
        result = crypto.keccak256_hash(b"test")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_keccak256_error(self):
        pytest.skip("Cannot test error path with actual eth-hash installed")


# ============================================================================
# SHA-256 Hash Tests
# ============================================================================


class TestSha256Hash:
    """Test sha256_hash function"""

    def test_sha256_string_input(self):
        result = crypto.sha256_hash("test")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 produces 64 hex chars

    def test_sha256_bytes_input(self):
        result = crypto.sha256_hash(b"test")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_sha256_consistent(self):
        result1 = crypto.sha256_hash("test")
        result2 = crypto.sha256_hash("test")
        assert result1 == result2  # Same input should produce same hash

    def test_sha256_different_inputs(self):
        result1 = crypto.sha256_hash("test1")
        result2 = crypto.sha256_hash("test2")
        assert result1 != result2


# ============================================================================
# Ethereum Address Validation Tests
# ============================================================================


class TestValidateEthereumAddress:
    """Test validate_ethereum_address function (delegates to aitbc.utils.validation.validate_address)"""

    def test_validate_address_valid_checksum(self):
        # A valid EIP-55 checksum address
        result = crypto.validate_ethereum_address("0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed")
        assert result is True

    def test_validate_address_valid_lowercase_not_checksum(self):
        # All-lowercase 0x address is not checksummed — should fail checksum check
        result = crypto.validate_ethereum_address("0x5aaeb6053f3e94c9b9a09f33669435e7ef1beaed")
        assert result is False

    def test_validate_address_invalid_format(self):
        result = crypto.validate_ethereum_address("invalid")
        assert result is False

    def test_validate_address_too_short(self):
        result = crypto.validate_ethereum_address("0xABC")
        assert result is False

    def test_validate_address_empty(self):
        result = crypto.validate_ethereum_address("")
        assert result is False

    def test_validate_address_legacy_prefix(self):
        # Legacy ait1/aitbc1 prefix addresses are accepted
        result = crypto.validate_ethereum_address("ait1abc123")
        assert result is True


# ============================================================================
# Ethereum Private Key Generation Tests
# ============================================================================


class TestGenerateEthereumPrivateKey:
    """Test generate_ethereum_private_key function"""

    def test_generate_private_key_missing_dependency(self):
        with patch.dict("sys.modules", {"eth_account": None}):
            with pytest.raises(ImportError, match="eth-account is required"):
                crypto.generate_ethereum_private_key()

    def test_generate_private_key_success(self):
        with patch.dict("sys.modules", {"eth_account": Mock()}):
            from eth_account import Account as MockAccount

            mock_account_instance = Mock()
            mock_account_instance.key.hex.return_value = "0x1234567890abcdef"
            MockAccount.create.return_value = mock_account_instance

            result = crypto.generate_ethereum_private_key()
            assert result == "0x1234567890abcdef"

    def test_generate_private_key_error(self):
        with patch.dict("sys.modules", {"eth_account": Mock()}):
            from eth_account import Account as MockAccount

            MockAccount.create.side_effect = Exception("Generation error")

            with pytest.raises(ValueError, match="Failed to generate private key"):
                crypto.generate_ethereum_private_key()
