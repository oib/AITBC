#!/usr/bin/env python3
"""Create a new genesis wallet with secure random private key"""

import json
import hashlib
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from datetime import datetime
import secrets
import base64
import os
from pathlib import Path
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def derive_address_from_public_key(pub_key_bytes: bytes) -> str:
    """Derive AITBC address from public key"""
    # Hash the public key
    digest = hashlib.sha256(pub_key_bytes).digest()
    # Take first 20 bytes and encode as hex
    address_hash = digest[:20].hex()
    # Return with aitbc1 prefix
    return f"aitbc1{address_hash}"

def create_genesis_wallet(password: str = None):
    """Create genesis wallet with secure random private key"""
    # Generate cryptographically secure random private key (32 bytes)
    private_key_bytes = secrets.token_bytes(32)
    
    # Generate Ed25519 key pair from private key
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    public_key = private_key.public_key()
    
    # Get public key bytes
    pub_key_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    
    # Derive address
    address = derive_address_from_public_key(pub_key_bytes)
    
    # Convert to ait1 prefix format (matching genesis.json format)
    ait_address = address.replace("aitbc1", "ait1")
    
    # Generate password if not provided
    if not password:
        password = secrets.token_urlsafe(32)
    
    # Encrypt private key with password
    salt = secrets.token_bytes(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = kdf.derive(password.encode())
    
    # Encrypt using AES-GCM
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ciphertext = aesgcm.encrypt(nonce, private_key_bytes, None)
    
    # Create wallet data
    wallet_data = {
        "address": ait_address,
        "public_key": pub_key_bytes.hex(),
        "crypto": {
            "kdf": "pbkdf2",
            "kdfparams": {
                "salt": salt.hex(),
                "c": 100000,
                "dklen": 32,
                "prf": "hmac-sha256"
            },
            "cipher": "aes-256-gcm",
            "cipherparams": {
                "nonce": nonce.hex()
            },
            "ciphertext": ciphertext.hex()
        },
        "version": 1
    }
    
    # Write to keystore
    keystore_path = Path("/var/lib/aitbc/keystore/genesis.json")
    with open(keystore_path, 'w') as f:
        json.dump(wallet_data, f, indent=2)
    
    # Save password to secure file
    password_path = Path("/var/lib/aitbc/keystore/.genesis_password")
    with open(password_path, 'w') as f:
        f.write(password)
    os.chmod(password_path, 0o600)
    
    print(f"✅ Created new genesis wallet with secure random private key")
    print(f"Address: {ait_address}")
    print(f"Public key: {pub_key_bytes.hex()}")
    print(f"Private key: {private_key_bytes.hex()}")
    print(f"Password: {password}")
    print(f"Wallet saved to: {keystore_path}")
    print(f"Password saved to: {password_path}")
    print(f"⚠️  IMPORTANT: Store the password securely!")
    
    return ait_address, pub_key_bytes.hex(), private_key_bytes.hex(), password

if __name__ == "__main__":
    create_genesis_wallet()
