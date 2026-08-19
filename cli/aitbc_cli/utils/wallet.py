"""
Wallet utility functions for AITBC CLI
"""

import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def decrypt_private_key(keystore_path: Path, password: str) -> str:
    """Decrypt a wallet private key from its keystore file.

    Supports the v1.0 PBKDF2+FERNET wallet format produced by ``aitbc wallet create``
    (``private_key`` is a dict with ``encrypted_data``, ``salt``, etc.) and the
    older blockchain-node AES-256-GCM keystore format (``crypto`` dict).
    """
    from aitbc.security.encryption import decrypt_value

    with open(keystore_path) as f:
        wallet = json.load(f)

    # v1.0 CLI wallet: private key is encrypted under the "private_key" dict
    if isinstance(wallet.get("private_key"), dict):
        return decrypt_value(wallet["private_key"], password)

    # Legacy keystore format used by blockchain-node / scripts
    crypto = wallet.get("crypto") or wallet
    if isinstance(crypto, dict):
        cipher = crypto.get("cipher", crypto.get("algorithm", ""))
        if cipher in ("aes-256-gcm",):
            salt = bytes.fromhex(crypto["kdfparams"]["salt"])
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=crypto["kdfparams"]["c"],
                backend=default_backend(),
            )
            key = kdf.derive(password.encode())
            aesgcm = AESGCM(key)
            nonce = bytes.fromhex(crypto["cipherparams"]["nonce"])
            priv = aesgcm.decrypt(nonce, bytes.fromhex(crypto["ciphertext"]), None)
            return priv.hex()

        if cipher in ("fernet", "PBKDF2-SHA256-Fernet"):
            from cryptography.fernet import Fernet

            kdfparams = crypto.get("kdfparams", {})
            if "salt" in kdfparams:
                salt = base64.b64decode(kdfparams["salt"])
            else:
                salt = bytes.fromhex(kdfparams.get("salt", ""))

            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000, dklen=32)
            fernet_key = base64.urlsafe_b64encode(dk)
            fernet = Fernet(fernet_key)
            ciphertext = base64.b64decode(crypto["ciphertext"])
            priv = fernet.decrypt(ciphertext)
            return priv.decode()

    raise ValueError(f"Unsupported cipher in keystore {keystore_path}")
