"""
Wallet utility functions for AITBC CLI
"""

import json
import os
import hashlib
import base64
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def decrypt_private_key(keystore_path: Path, password: str) -> str:
    """Decrypt private key from keystore file.
    
    Supports both keystore formats:
    - AES-256-GCM (blockchain-node standard)
    - Fernet (scripts/utils standard)
    """
    with open(keystore_path) as f:
        ks = json.load(f)
    
    crypto = ks.get('crypto', ks)  # Handle both nested and flat crypto structures
    
    # Detect encryption method
    cipher = crypto.get('cipher', crypto.get('algorithm', ''))
    
    if cipher == 'aes-256-gcm' or cipher == 'aes-256-gcm':
        # AES-256-GCM (blockchain-node standard)
        salt = bytes.fromhex(crypto['kdfparams']['salt'])
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=crypto['kdfparams']['c'],
            backend=default_backend()
        )
        key = kdf.derive(password.encode())
        aesgcm = AESGCM(key)
        nonce = bytes.fromhex(crypto['cipherparams']['nonce'])
        priv = aesgcm.decrypt(nonce, bytes.fromhex(crypto['ciphertext']), None)
        return priv.hex()
    
    elif cipher == 'fernet' or cipher == 'PBKDF2-SHA256-Fernet':
        # Fernet (scripts/utils standard)
        from cryptography.fernet import Fernet
        
        # Derive Fernet key using the same method as scripts/utils/keystore.py
        kdfparams = crypto.get('kdfparams', {})
        if 'salt' in kdfparams:
            salt = base64.b64decode(kdfparams['salt'])
        else:
            # Fallback for older format
            salt = bytes.fromhex(kdfparams.get('salt', ''))
        
        # Use PBKDF2 for secure key derivation (100,000 iterations for security)
        dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000, dklen=32)
        fernet_key = base64.urlsafe_b64encode(dk)
        
        f = Fernet(fernet_key)
        ciphertext = base64.b64decode(crypto['ciphertext'])
        priv = f.decrypt(ciphertext)
        return priv.decode()
    
    else:
        raise ValueError(f"Unsupported cipher: {cipher}")
