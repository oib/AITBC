#!/usr/bin/env python3
"""Create a new genesis wallet with secure random private key.

Uses secp256k1 (Ethereum-style) key generation with 0x-prefixed checksum
addresses, compatible with the blockchain node's transaction signature
verifier (Bug 4 fix) and the shared TransactionService signer (A1).
"""

import json
import os
import secrets
import sys
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

    # #860: refuse before doing any work — O_EXCL + 0600 at creation,
    # never an overwrite. KEYSTORE_DIR is the scratch hook; the reset
    # guard (#290) hard-stops a default run at the live keystore.
    keystore_dir = Path(os.environ.get("KEYSTORE_DIR", "/var/lib/aitbc/keystore"))
    keystore_path = keystore_dir / "genesis.json"
    password_path = keystore_dir / ".genesis_password"

    from aitbc.utils import reset_guard

    try:
        reset_guard.assert_scratch_targets(keystore_path, password_path)
    except reset_guard.ResetGuardError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        sys.exit(1)
    for path in (keystore_path, password_path):
        if path.exists():
            print(f"refused: {path} already exists — no overwrite (#860)", file=sys.stderr)
            sys.exit(1)

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

    # Write to keystore — atomic O_EXCL, mode 0600 (#860).
    keystore_dir.mkdir(parents=True, exist_ok=True)
    try:
        with open(keystore_path, "x", opener=lambda p, f: os.open(p, f, 0o600)) as f:
            json.dump(wallet_data, f, indent=2)
        with open(password_path, "x", opener=lambda p, f: os.open(p, f, 0o600)) as f:
            f.write(password)
    except FileExistsError:
        print("refused: keystore file appeared during write — no overwrite (#860)", file=sys.stderr)
        sys.exit(1)

    print("✅ Created new genesis wallet with secure random secp256k1 private key")
    print(f"Address: {address}")
    print(f"Wallet saved to: {keystore_path}")
    print(f"Password saved to: {password_path}")
    print("⚠️  IMPORTANT: The private key and password are saved to the files above.")
    print("⚠️  NEVER share or print the private key or password.")

    return address, private_key_hex, password


if __name__ == "__main__":
    create_genesis_wallet()
