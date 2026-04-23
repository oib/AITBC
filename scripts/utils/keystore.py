#!/usr/bin/env python3
"""
Keystore management for AITBC production keys.
Generates a random private key and encrypts it with a password using Fernet (AES-128).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet


def derive_key(password: str, salt: bytes = b"") -> bytes:
    """Derive a 32-byte key from the password using PBKDF2-HMAC-SHA256."""
    if not salt:
        salt = secrets.token_bytes(16)
    # Use PBKDF2 for secure key derivation (100,000 iterations for security)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000, dklen=32)
    return base64.urlsafe_b64encode(dk), salt


def encrypt_private_key(private_key_hex: str, password: str) -> dict:
    """Encrypt a hex-encoded private key with Fernet, returning a keystore dict."""
    key, salt = derive_key(password)
    f = Fernet(key)
    token = f.encrypt(private_key_hex.encode())
    return {
        "cipher": "fernet",
        "cipherparams": {"salt": base64.b64encode(salt).decode()},
        "ciphertext": base64.b64encode(token).decode(),
        "kdf": "sha256",
        "kdfparams": {"dklen": 32, "salt": base64.b64encode(salt).decode()},
    }


def create_keystore(address: str, password: str, keystore_dir: Path | str = "/var/lib/aitbc/keystore", force: bool = False) -> Path:
    """Create encrypted keystore file and return its path."""
    keystore_dir = Path(keystore_dir)
    keystore_dir.mkdir(parents=True, exist_ok=True)
    out_file = keystore_dir / f"{address}.json"

    if out_file.exists() and not force:
        raise FileExistsError(f"Keystore file {out_file} exists. Use force=True to overwrite.")

    private_key = secrets.token_hex(32)
    encrypted = encrypt_private_key(private_key, password)
    keystore = {
        "address": address,
        "crypto": encrypted,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }

    out_file.write_text(json.dumps(keystore, indent=2))
    os.chmod(out_file, 0o600)
    return out_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate encrypted keystore for an account")
    parser.add_argument("address", help="Account address (e.g., aitbc1treasury)")
    parser.add_argument("--output-dir", type=Path, default=Path("/var/lib/aitbc/keystore"), help="Keystore directory")
    parser.add_argument("--force", action="store_true", help="Overwrite existing keystore file")
    parser.add_argument("--password", help="Encryption password (or read from KEYSTORE_PASSWORD / keystore/.password)")
    args = parser.parse_args()

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{args.address}.json"

    if out_file.exists() and not args.force:
        print(f"Keystore file {out_file} exists. Use --force to overwrite.")
        return

    # Determine password: CLI > env var > password file
    password = args.password
    if not password:
        password = os.getenv("KEYSTORE_PASSWORD")
    if not password:
        pw_file = Path("/var/lib/aitbc/keystore/.password")
        if pw_file.exists():
            password = pw_file.read_text().strip()
    if not password:
        print("No password provided. Set KEYSTORE_PASSWORD, pass --password, or create /var/lib/aitbc/keystore/.password")
        sys.exit(1)

    print(f"Generating keystore for {args.address}...")
    private_key = secrets.token_hex(32)
    print(f"Private key (hex): {private_key}")
    print("** SAVE THIS KEY SECURELY ** (It cannot be recovered from the encrypted file without the password)")

    encrypted = encrypt_private_key(private_key, password)
    keystore = {
        "address": args.address,
        "crypto": encrypted,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }

    out_file.write_text(json.dumps(keystore, indent=2))
    os.chmod(out_file, 0o600)
    print(f"[+] Keystore written to {out_file}")
    print(f"[!] Keep the password safe. Without it, the private key cannot be recovered.")


if __name__ == "__main__":
    main()
