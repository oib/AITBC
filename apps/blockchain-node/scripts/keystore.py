#!/usr/bin/env python3
"""
Production key management for AITBC blockchain.

Generates ed25519 keypairs and stores them in an encrypted JSON keystore
(Ethereum-style web3 keystore). Supports multiple wallets (treasury, proposer, etc.)

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
from typing import Dict, Any, Optional

# Uses Cryptography library for ed25519 and encryption
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend

# Address encoding: bech32m (HRP 'ait')
from bech32 import bech32_encode, convertbits


def generate_address(public_key_bytes: bytes) -> str:
    """Generate a bech32m address from a public key.
    1. Take SHA256 of the public key (produces 32 bytes)
    2. Convert to 5-bit groups (bech32)
    3. Encode with HRP 'ait'
    """
    digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
    digest.update(public_key_bytes)
    hashed = digest.finalize()
    # Convert to 5-bit words for bech32
    data = convertbits(hashed, 8, 5, True)
    return bech32_encode("ait", data)


def encrypt_private_key(private_key_bytes: bytes, password: str, salt: bytes) -> Dict[str, Any]:
    """Encrypt a private key using AES-GCM, wrapped in a JSON keystore."""
    # Derive key from password using PBKDF2
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
        backend=default_backend()
    )
    key = kdf.derive(password.encode('utf-8'))

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
            "kdfparams": {
                "dklen": 32,
                "salt": salt.hex(),
                "c": 100_000,
                "prf": "hmac-sha256"
            },
            "mac": mac
        },
        "address": None,  # to be filled
        "keytype": "ed25519",
        "version": 1
    }


def generate_keypair(name: str, password: str, keystore_dir: Path) -> Dict[str, Any]:
    """Generate a new ed25519 keypair and store in keystore."""
    salt = os.urandom(32)
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    address = generate_address(public_bytes)

    keystore = encrypt_private_key(private_bytes, password, salt)
    keystore["address"] = address

    keystore_file = keystore_dir / f"{name}.json"
    keystore_dir.mkdir(parents=True, exist_ok=True)
    with open(keystore_file, 'w') as f:
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
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=kdfparams["c"],
        backend=default_backend()
    )
    key = kdf.derive(password.encode('utf-8'))

    # Decrypt private key
    nonce = bytes.fromhex(crypto["cipherparams"]["nonce"])
    ciphertext = bytes.fromhex(crypto["ciphertext"])
    aesgcm = AESGCM(key)
    private_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_bytes)
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    address = generate_address(public_bytes)

    print(f"Keystore: {keystore_file}")
    print(f"Address: {address}")
    print(f"Public key (hex): {public_bytes.hex()}")


def main():
    from getpass import getpass
    from cryptography.hazmat.primitives import serialization

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
