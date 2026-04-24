#!/usr/bin/env python3
"""
Keystore authentication for AITBC CLI.
Loads and decrypts keystore credentials for authenticated blockchain operations.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

from aitbc.paths import get_keystore_path
from cryptography.fernet import Fernet


def derive_key(password: str, salt: bytes = b"") -> tuple[bytes, bytes]:
    """Derive a 32-byte key from the password using PBKDF2-HMAC-SHA256."""
    if not salt:
        import secrets
        salt = secrets.token_bytes(16)
    # Use PBKDF2 for secure key derivation (100,000 iterations for security)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000, dklen=32)
    return base64.urlsafe_b64encode(dk), salt


def decrypt_private_key(keystore_data: Dict[str, Any], password: str) -> str:
    """Decrypt a private key from keystore data using Fernet."""
    crypto = keystore_data.get("crypto", {})
    cipherparams = crypto.get("cipherparams", {})
    
    salt = base64.b64decode(cipherparams.get("salt", ""))
    ciphertext = base64.b64decode(crypto.get("ciphertext", ""))
    
    key, _ = derive_key(password, salt)
    f = Fernet(key)
    
    decrypted = f.decrypt(ciphertext)
    return decrypted.decode()


def load_keystore(address: str, keystore_dir: Path | str = "/var/lib/aitbc/keystore") -> Dict[str, Any]:
    """Load keystore file for a given address."""
    keystore_dir = Path(keystore_dir)
    keystore_file = keystore_dir / f"{address}.json"
    
    if not keystore_file.exists():
        raise FileNotFoundError(f"Keystore not found for address: {address}")
    
    with open(keystore_file) as f:
        return json.load(f)


def get_private_key(address: str, password: Optional[str] = None, 
                    password_file: Optional[str] = None) -> str:
    """
    Get decrypted private key for an address.
    
    Priority for password:
    1. Provided password parameter
    2. KEYSTORE_PASSWORD environment variable
    3. Password file at /var/lib/aitbc/keystore/.password
    """
    # Determine password
    if password:
        pass_password = password
    else:
        pass_password = os.getenv("KEYSTORE_PASSWORD")
        if not pass_password and password_file:
            with open(password_file) as f:
                pass_password = f.read().strip()
        if not pass_password:
            pw_file = get_keystore_path(".password")
            if pw_file.exists():
                pass_password = pw_file.read_text().strip()
    
    if not pass_password:
        raise ValueError(
            "No password provided. Set KEYSTORE_PASSWORD, pass --password, "
            "or create a .password file in the keystore directory"
        )
    
    # Load and decrypt keystore
    keystore_data = load_keystore(address)
    return decrypt_private_key(keystore_data, pass_password)


def sign_message(message: str, private_key_hex: str) -> str:
    """
    Sign a message using the private key.
    Returns the signature as a hex string.
    
    Note: This is a simplified implementation. In production, use proper cryptographic signing.
    """
    import hashlib
    import hmac
    
    # Simple HMAC-based signature (for demonstration)
    # In production, use proper ECDSA signing with the private key
    key_bytes = bytes.fromhex(private_key_hex)
    signature = hmac.new(key_bytes, message.encode(), hashlib.sha256).hexdigest()
    
    return f"0x{signature}"


def get_auth_headers(address: str, password: Optional[str] = None,
                    password_file: Optional[str] = None) -> Dict[str, str]:
    """
    Get authentication headers for authenticated RPC calls.
    
    Returns a dict with 'X-Address' and 'X-Signature' headers.
    """
    private_key = get_private_key(address, password, password_file)
    
    # Create a simple auth message (in production, this should include timestamp and nonce)
    auth_message = f"auth:{address}"
    signature = sign_message(auth_message, private_key)
    
    return {
        "X-Address": address,
        "X-Signature": signature,
    }
