#!/usr/bin/env python3
"""
Production key management for AITBC blockchain.

Generates secp256k1 keypairs (Ethereum-style) with 0x-prefixed checksum
addresses and stores them in an encrypted JSON keystore (web3-style).
Supports multiple wallets (treasury, proposer, etc.)

Usage:
  python keystore.py --name treasury --create --password <secret>
  python keystore.py --name proposer --create --password <secret>
  python keystore.py --name treasury --show
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path
from typing import Any

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from eth_account import Account
from eth_keys import keys


def encrypt_private_key(private_key_bytes: bytes, password: str, salt: bytes) -> dict[str, Any]:
    """Encrypt a private key using AES-GCM, wrapped in a JSON keystore."""
    # Derive key from password using PBKDF2
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000, backend=default_backend())
    key = kdf.derive(password.encode("utf-8"))

    # Encrypt with AES-GCM
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    encrypted = aesgcm.encrypt(nonce, private_key_bytes, None)

    # Compute MAC for web3 keystore format (HMAC-SHA256)
    # MAC is computed over derived_key[16:32] + ciphertext
    mac_data = key[16:32] + encrypted
    mac = hmac.new(key[:16], mac_data, hashlib.sha256).hexdigest()

    return {
        "crypto": {
            "cipher": "aes-256-gcm",
            "cipherparams": {"nonce": nonce.hex()},
            "ciphertext": encrypted.hex(),
            "kdf": "pbkdf2",
            "kdfparams": {"dklen": 32, "salt": salt.hex(), "c": 100_000, "prf": "hmac-sha256"},
            "mac": mac,
        },
        "address": None,  # to be filled
        "keytype": "secp256k1",
        "version": 1,
    }


def generate_keypair(name: str, password: str, keystore_dir: Path) -> dict[str, Any]:
    """Generate a new secp256k1 keypair and store in keystore."""
    salt = os.urandom(32)
    account = Account.create()
    private_bytes = bytes(account.key)
    address = account.address

    keystore = encrypt_private_key(private_bytes, password, salt)
    keystore["address"] = address

    keystore_file = keystore_dir / f"{name}.json"
    keystore_dir.mkdir(parents=True, exist_ok=True)
    with open(keystore_file, "w") as f:
        json.dump(keystore, f, indent=2)
    os.chmod(keystore_file, 0o600)

    print(f"Generated {name} keypair")
    print(f"  Address: {address}")
    print(f"  Keystore: {keystore_file}")
    return keystore


def show_keyinfo(keystore_file: Path, password: str) -> None:
    """Decrypt and show key info (address, public key)."""
    with open(keystore_file) as f:
        data = json.load(f)

    # Derive key from password
    crypto = data["crypto"]
    kdfparams = crypto["kdfparams"]
    salt = bytes.fromhex(kdfparams["salt"])
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=kdfparams["c"], backend=default_backend())
    key = kdf.derive(password.encode("utf-8"))

    # Decrypt private key
    nonce = bytes.fromhex(crypto["cipherparams"]["nonce"])
    ciphertext = bytes.fromhex(crypto["ciphertext"])
    aesgcm = AESGCM(key)
    private_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    account = Account.from_key(private_bytes)

    print(f"Keystore: {keystore_file}")
    print(f"Address: {account.address}")
    print(f"Public key (hex): {keys.PrivateKey(bytes(account.key)).public_key.to_hex()}")


def main():
    from getpass import getpass

    parser = argparse.ArgumentParser(description="Production keystore management")
    parser.add_argument("--name", required=True, help="Key name (e.g., treasury, proposer)")
    parser.add_argument("--create", action="store_true", help="Generate new keypair")
    parser.add_argument("--show", action="store_true", help="Show address/public key (prompt for password)")
    parser.add_argument("--password", help="Password (avoid using in CLI; prefer prompt or env)")
    parser.add_argument("--keystore-dir", type=Path, default=Path("/opt/aitbc/keystore"), help="Keystore directory")
    args = parser.parse_args()

    if args.create:
        pwd = args.password or os.getenv("KEYSTORE_PASSWORD") or getpass("New password: ")
        if not pwd:
            print("Password required")
            sys.exit(1)
        generate_keypair(args.name, pwd, args.keystore_dir)

    elif args.show:
        pwd = args.password or os.getenv("KEYSTORE_PASSWORD") or getpass("Password: ")
        if not pwd:
            print("Password required")
            sys.exit(1)
        keystore_file = args.keystore_dir / f"{args.name}.json"
        if not keystore_file.exists():
            print(f"Keystore not found: {keystore_file}")
            sys.exit(1)
        show_keyinfo(keystore_file, pwd)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
