"""
Tests for wallet utility functions
"""

import base64
import json
import sys
from pathlib import Path
from unittest.mock import mock_open, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest  # noqa: E402
from aitbc_cli.utils.wallet import decrypt_private_key  # noqa: E402


class TestDecryptPrivateKey:
    """Test decrypt_private_key function"""

    @patch("builtins.open", new_callable=mock_open)
    def test_decrypt_aes256_gcm(self, mock_file):
        """Test AES-256-GCM decryption"""
        # Mock keystore data with valid hex strings
        keystore_data = {
            "crypto": {
                "cipher": "aes-256-gcm",
                "kdfparams": {"salt": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", "c": 1000},
                "cipherparams": {"nonce": "0123456789abcdef01234567"},
                "ciphertext": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            }
        }
        mock_file.return_value.read.return_value = json.dumps(keystore_data)

        with patch("aitbc_cli.utils.wallet.PBKDF2HMAC") as mock_kdf, patch("aitbc_cli.utils.wallet.AESGCM") as mock_aesgcm:
            mock_key = b"0" * 32
            mock_kdf.return_value.derive.return_value = mock_key
            mock_aesgcm.return_value.decrypt.return_value = b"decrypted_key"

            result = decrypt_private_key(Path("/test/keystore.json"), "password")

            assert result == "6465637279707465645f6b6579"  # hex of b'decrypted_key'

    @patch("builtins.open", new_callable=mock_open)
    def test_decrypt_fernet(self, mock_file):
        """Test Fernet decryption"""
        # Mock keystore data
        keystore_data = {
            "crypto": {
                "cipher": "fernet",
                "kdfparams": {"salt": base64.b64encode(b"salt").decode()},
                "ciphertext": base64.b64encode(b"encrypted").decode(),
            }
        }
        mock_file.return_value.read.return_value = json.dumps(keystore_data)

        with (
            patch("aitbc_cli.utils.wallet.hashlib.pbkdf2_hmac") as mock_pbkdf2,
            patch("cryptography.fernet.Fernet") as mock_fernet,
        ):
            mock_pbkdf2.return_value = b"0" * 32
            mock_fernet.return_value.decrypt.return_value = b"decrypted_key"

            result = decrypt_private_key(Path("/test/keystore.json"), "password")

            assert result == "decrypted_key"

    @patch("builtins.open", new_callable=mock_open)
    def test_decrypt_fernet_hex_salt(self, mock_file):
        """Test Fernet decryption with hex salt (older format)"""
        # Mock keystore data with hex salt
        keystore_data = {
            "crypto": {
                "cipher": "PBKDF2-SHA256-Fernet",
                "kdfparams": {
                    "salt": "73616c74"  # hex for 'salt'
                },
                "ciphertext": base64.b64encode(b"encrypted").decode(),
            }
        }
        mock_file.return_value.read.return_value = json.dumps(keystore_data)

        with (
            patch("aitbc_cli.utils.wallet.hashlib.pbkdf2_hmac") as mock_pbkdf2,
            patch("cryptography.fernet.Fernet") as mock_fernet,
        ):
            mock_pbkdf2.return_value = b"0" * 32
            mock_fernet.return_value.decrypt.return_value = b"decrypted_key"

            result = decrypt_private_key(Path("/test/keystore.json"), "password")

            assert result == "decrypted_key"

    @patch("builtins.open", new_callable=mock_open)
    def test_decrypt_flat_crypto_structure(self, mock_file):
        """Test decryption with flat crypto structure (no nested 'crypto' key)"""
        keystore_data = {
            "cipher": "aes-256-gcm",
            "kdfparams": {"salt": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", "c": 1000},
            "cipherparams": {"nonce": "0123456789abcdef01234567"},
            "ciphertext": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        }
        mock_file.return_value.read.return_value = json.dumps(keystore_data)

        with patch("aitbc_cli.utils.wallet.PBKDF2HMAC") as mock_kdf, patch("aitbc_cli.utils.wallet.AESGCM") as mock_aesgcm:
            mock_key = b"0" * 32
            mock_kdf.return_value.derive.return_value = mock_key
            mock_aesgcm.return_value.decrypt.return_value = b"decrypted_key"

            result = decrypt_private_key(Path("/test/keystore.json"), "password")

            assert result == "6465637279707465645f6b6579"

    @patch("builtins.open", new_callable=mock_open)
    def test_decrypt_unsupported_cipher(self, mock_file):
        """Test error on unsupported cipher"""
        keystore_data = {"crypto": {"cipher": "unknown-cipher", "ciphertext": "1234"}}
        mock_file.return_value.read.return_value = json.dumps(keystore_data)

        with pytest.raises(ValueError) as exc_info:
            decrypt_private_key(Path("/test/keystore.json"), "password")

        assert "Unsupported cipher" in str(exc_info.value)

    @patch("builtins.open", new_callable=mock_open)
    def test_decrypt_no_cipher_field(self, mock_file):
        """Test error when cipher field is missing"""
        keystore_data = {"crypto": {"ciphertext": "1234"}}
        mock_file.return_value.read.return_value = json.dumps(keystore_data)

        with pytest.raises(ValueError) as exc_info:
            decrypt_private_key(Path("/test/keystore.json"), "password")

        assert "Unsupported cipher" in str(exc_info.value)

    @patch("builtins.open", new_callable=mock_open)
    def test_decrypt_file_not_found(self, mock_file):
        """Test error when keystore file doesn't exist"""
        mock_file.side_effect = FileNotFoundError("File not found")

        with pytest.raises(FileNotFoundError):
            decrypt_private_key(Path("/nonexistent/keystore.json"), "password")

    @patch("builtins.open", new_callable=mock_open)
    def test_decrypt_invalid_json(self, mock_file):
        """Test error when keystore file has invalid JSON"""
        mock_file.return_value.read.return_value = "invalid json"

        with pytest.raises(json.JSONDecodeError):
            decrypt_private_key(Path("/test/keystore.json"), "password")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
