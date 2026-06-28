#!/usr/bin/env python3
"""Create a new genesis wallet with secure random private key.

Uses secp256k1 (Ethereum-style) key generation with 0x-prefixed checksum
addresses, compatible with the blockchain node's transaction signature
verifier (Bug 4 fix) and the shared TransactionService signer (A1).
"""

import json
import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from eth_account import Account
from eth_keys import keys


def create_genesis_wallet(password: str = None):
    """Create genesis wallet with secure random secp256k1 private key"""
    # Generate secp256k1 keypair via eth-account
    account = Account.create()
    private_key_hex = account.key.hex()  # 64 hex chars, no 0x prefix
    address = account.address  # 0x-prefixed checksum address
    public_key_hex = keys.PrivateKey(bytes(account.key)).public_key.to_hex()

    # Generate password if not provided
    if not password:
        password = secrets.token_urlsafe(32)

    # Encrypt private key with password
    private_key_bytes = bytes.fromhex(private_key_hex)
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
        "address": address,
        "public_key": public_key_hex,
        "crypto": {
            "kdf": "pbkdf2",
            "kdfparams": {"salt": salt.hex(), "c": 100000, "dklen": 32, "prf": "hmac-sha256"},
            "cipher": "aes-256-gcm",
            "cipherparams": {"nonce": nonce.hex()},
            "ciphertext": ciphertext.hex(),
        },
        "keytype": "secp256k1",
        "version": 1,
    }

    # Write to keystore
    keystore_path = Path("/var/lib/aitbc/keystore/genesis.json")
    with open(keystore_path, "w") as f:
        json.dump(wallet_data, f, indent=2)

    # Save password to secure file
    password_path = Path("/var/lib/aitbc/keystore/.genesis_password")
    with open(password_path, "w") as f:
        f.write(password)
    os.chmod(password_path, 0o600)

    print("✅ Created new genesis wallet with secure random secp256k1 private key")
    print(f"Address: {address}")
    print(f"Wallet saved to: {keystore_path}")
    print(f"Password saved to: {password_path}")
    print("⚠️  IMPORTANT: The private key and password are saved to the files above.")
    print("⚠️  NEVER share or print the private key or password.")

    return address, private_key_hex, password


if __name__ == "__main__":
    create_genesis_wallet()
