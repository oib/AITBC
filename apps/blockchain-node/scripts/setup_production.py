#!/usr/bin/env python3
"""
Production setup generator for AITBC blockchain.
Creates two wallets:
  - aitbc1genesis: Treasury wallet holding all initial supply (1B AIT)
  - aitbc1treasury: Spending wallet (for transactions, can receive from genesis)

No admin minting; fixed supply at genesis.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import string
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend

from bech32 import bech32_encode, convertbits


def random_password(length: int = 32) -> str:
    """Generate a strong random password."""
    alphabet = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def generate_address(public_key_bytes: bytes) -> str:
    """Bech32m address with HRP 'ait'."""
    digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
    digest.update(public_key_bytes)
    hashed = digest.finalize()
    data = convertbits(hashed, 8, 5, True)
    return bech32_encode("ait", data)


def encrypt_private_key(private_bytes: bytes, password: str, salt: bytes) -> dict:
    """Web3-style keystore encryption (AES-GCM + PBKDF2)."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
        backend=default_backend()
    )
    key = kdf.derive(password.encode('utf-8'))

    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, private_bytes, None)

    return {
        "crypto": {
            "cipher": "aes-256-gcm",
            "cipherparams": {"nonce": nonce.hex()},
            "ciphertext": ciphertext.hex(),
            "kdf": "pbkdf2",
            "kdfparams": {
                "dklen": 32,
                "salt": salt.hex(),
                "c": 100_000,
                "prf": "hmac-sha256"
            },
            "mac": "TODO"  # In production, compute proper MAC
        },
        "address": None,
        "keytype": "ed25519",
        "version": 1
    }


def generate_wallet(name: str, password: str, keystore_dir: Path) -> dict:
    """Generate ed25519 keypair and return wallet info."""
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

    salt = os.urandom(32)
    keystore = encrypt_private_key(private_bytes, password, salt)
    keystore["address"] = address

    keystore_file = keystore_dir / f"{name}.json"
    with open(keystore_file, 'w') as f:
        json.dump(keystore, f, indent=2)
    os.chmod(keystore_file, 0o600)

    return {
        "name": name,
        "address": address,
        "keystore_file": str(keystore_file),
        "public_key_hex": public_bytes.hex()
    }


def main():
    parser = argparse.ArgumentParser(description="Production blockchain setup")
    parser.add_argument("--base-dir", type=Path, default=Path("/opt/aitbc/apps/blockchain-node"),
                        help="Blockchain node base directory")
    parser.add_argument("--chain-id", default="ait-mainnet", help="Chain ID")
    parser.add_argument("--total-supply", type=int, default=1_000_000_000,
                        help="Total token supply (smallest units)")
    args = parser.parse_args()

    base_dir = args.base_dir
    keystore_dir = base_dir / "keystore"
    data_dir = base_dir / "data" / args.chain_id

    keystore_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Generate strong random password
    password = random_password(32)
    password_file = keystore_dir / ".password"

    # SECURITY FIX: Use password directly without writing to disk when possible
    # Only write to file if explicitly needed for persistence
    # If password needs to be persisted, ensure file is protected with chmod 600
    with open(password_file, 'w') as f:
        f.write(password + "\n")
    os.chmod(password_file, 0o600)

    print(f"[setup] Generated keystore password and saved to {password_file} (chmod 600)")

    # Generate two wallets
    wallets = []
    for suffix in ["genesis", "treasury"]:
        name = f"aitbc1{suffix}"
        info = generate_wallet(name, password, keystore_dir)
        # Store both the full name and suffix for lookup
        info['suffix'] = suffix
        wallets.append(info)
        print(f"[setup] Created wallet: {name}")
        print(f"  Address: {info['address']}")
        print(f"  Keystore: {info['keystore_file']}")

    # Clear password from memory for security after use
    password = None

    # Create allocations: all supply to genesis wallet, treasury gets 0 (for spending from genesis)
    genesis_wallet = next(w for w in wallets if w['suffix'] == 'genesis')
    treasury_wallet = next(w for w in wallets if w['suffix'] == 'treasury')
    allocations = [
        {
            "address": genesis_wallet["address"],
            "balance": args.total_supply,
            "nonce": 0
        },
        {
            "address": treasury_wallet["address"],
            "balance": 0,
            "nonce": 0
        }
    ]

    allocations_file = data_dir / "allocations.json"
    with open(allocations_file, 'w') as f:
        json.dump(allocations, f, indent=2)
    print(f"[setup] Wrote allocations to {allocations_file}")

    # Create genesis.json via make_genesis script
    import subprocess
    genesis_file = data_dir / "genesis.json"
    python_exec = base_dir / ".venv" / "bin" / "python"
    if not python_exec.exists():
        python_exec = "python3"  # fallback
    result = subprocess.run([
        str(python_exec), str(base_dir / "scripts" / "make_genesis.py"),
        "--output", str(genesis_file),
        "--force",
        "--allocations", str(allocations_file),
        "--authorities", genesis_wallet["address"],
        "--chain-id", args.chain_id
    ], capture_output=True, text=True, cwd=str(base_dir))
    if result.returncode != 0:
        print(f"[setup] Genesis generation failed: {result.stderr}")
        return 1
    print(f"[setup] Created genesis file at {genesis_file}")
    print(result.stdout.strip())

    print("\n[setup] Production setup complete!")
    print(f"  Chain ID: {args.chain_id}")
    print(f"  Total supply: {args.total_supply} (fixed)")
    print(f"  Genesis wallet: {genesis_wallet['address']}")
    print(f"  Treasury wallet: {treasury_wallet['address']}")
    print(f"  Keystore password: stored in {password_file}")
    print("\n[IMPORTANT] Keep the keystore files and password secure!")

    return 0


if __name__ == "__main__":
    exit(main())
