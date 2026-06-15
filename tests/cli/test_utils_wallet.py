"""
Wallet Utils Tests
Tests for wallet utility functions
"""

import base64
import json
import os
import tempfile
from pathlib import Path

import pytest


class TestDecryptPrivateKey:
    """Test decrypt_private_key function"""

    def test_decrypt_private_key_aes_gcm(self):
        """Test decrypting private key with AES-256-GCM"""
        import os

        from aitbc_cli.utils.wallet import decrypt_private_key
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        with tempfile.TemporaryDirectory() as tmpdir:
            keystore_path = Path(tmpdir) / "keystore.json"
            password = "testpassword123"

            # Create a valid AES-256-GCM keystore
            salt = os.urandom(32)
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000, backend=default_backend())
            key = kdf.derive(password.encode())
            aesgcm = AESGCM(key)
            nonce = os.urandom(12)
            private_key = "0x1234567890abcdef"
            ciphertext = aesgcm.encrypt(nonce, bytes.fromhex(private_key[2:]), None)

            keystore_data = {
                "crypto": {
                    "cipher": "aes-256-gcm",
                    "ciphertext": ciphertext.hex(),
                    "cipherparams": {"nonce": nonce.hex()},
                    "kdfparams": {"salt": salt.hex(), "c": 100000},
                }
            }

            with open(keystore_path, "w") as f:
                json.dump(keystore_data, f)

            result = decrypt_private_key(keystore_path, password)

            assert result == private_key[2:]

    def test_decrypt_private_key_fernet(self):
        """Test decrypting private key with Fernet"""
        import hashlib

        from aitbc_cli.utils.wallet import decrypt_private_key
        from cryptography.fernet import Fernet

        with tempfile.TemporaryDirectory() as tmpdir:
            keystore_path = Path(tmpdir) / "keystore.json"
            password = "testpassword123"

            # Create a valid Fernet keystore
            salt = os.urandom(16)
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000, dklen=32)
            fernet_key = base64.urlsafe_b64encode(dk)
            f = Fernet(fernet_key)
            private_key = "0x1234567890abcdef"
            ciphertext = f.encrypt(private_key.encode())

            keystore_data = {
                "crypto": {
                    "cipher": "fernet",
                    "ciphertext": base64.b64encode(ciphertext).decode(),
                    "kdfparams": {"salt": base64.b64encode(salt).decode()},
                }
            }

            with open(keystore_path, "w") as f:
                json.dump(keystore_data, f)

            result = decrypt_private_key(keystore_path, password)

            assert result == private_key

    def test_decrypt_private_key_unsupported_cipher(self):
        """Test decrypting with unsupported cipher"""
        from aitbc_cli.utils.wallet import decrypt_private_key

        with tempfile.TemporaryDirectory() as tmpdir:
            keystore_path = Path(tmpdir) / "keystore.json"

            keystore_data = {"crypto": {"cipher": "unsupported-cipher", "ciphertext": "abc123"}}

            with open(keystore_path, "w") as f:
                json.dump(keystore_data, f)

            with pytest.raises(ValueError, match="Unsupported cipher"):
                decrypt_private_key(keystore_path, "password")

    def test_decrypt_private_key_flat_crypto_structure(self):
        """Test decrypting with flat crypto structure (no nested 'crypto' key)"""
        from aitbc_cli.utils.wallet import decrypt_private_key

        with tempfile.TemporaryDirectory() as tmpdir:
            keystore_path = Path(tmpdir) / "keystore.json"

            keystore_data = {"cipher": "unsupported-cipher", "ciphertext": "abc123"}

            with open(keystore_path, "w") as f:
                json.dump(keystore_data, f)

            # Should handle flat structure and raise error for unsupported cipher
            with pytest.raises(ValueError, match="Unsupported cipher"):
                decrypt_private_key(keystore_path, "password")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
