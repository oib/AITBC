#!/usr/bin/env python3
"""
Keystore management for AITBC production keys.

Encrypts an EXISTING private key with a password using Fernet (AES-128).
The keystore address is derived from the private key itself (eth_account) —
never taken from the command line — so the file always names the account the
key actually controls. Key material is never printed.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path

from cryptography.fernet import Fernet
from eth_account import Account


# PBKDF2 work factor for newly written keystores (OWASP minimum). Stored in
# kdfparams as "c" so decoders pick the right count for older files.
KDF_ITERATIONS = 600000


def derive_key(password: str, salt: bytes = b"", iterations: int = KDF_ITERATIONS) -> bytes:
    """Derive a 32-byte key from the password using PBKDF2-HMAC-SHA256."""
    if not salt:
        salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations, dklen=32)
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
        "kdfparams": {"dklen": 32, "salt": base64.b64encode(salt).decode(), "c": KDF_ITERATIONS},
    }


def create_keystore(
    private_key: str, password: str, keystore_dir: Path | str = "/var/lib/aitbc/keystore", force: bool = False
) -> Path:
    """Encrypt ``private_key`` into ``<keystore_dir>/<derived-address>.json``.

    The address is derived from the key, so the keystore can never name an
    account the key does not control. The file is created O_EXCL with mode
    0600 — no write-then-chmod window and no silent overwrite.
    """
    address = Account.from_key(private_key).address
    keystore_dir = Path(keystore_dir)
    keystore_dir.mkdir(parents=True, exist_ok=True)
    out_file = keystore_dir / f"{address}.json"

    keystore = {
        "address": address,
        "crypto": encrypt_private_key(private_key, password),
        "created_at": datetime.now(UTC).isoformat(),
    }

    flags = os.O_WRONLY | os.O_CREAT
    if not force:
        flags |= os.O_EXCL
    try:
        fd = os.open(out_file, flags, 0o600)
    except FileExistsError:
        raise FileExistsError(f"Keystore file {out_file} exists. Use force=True to overwrite.") from None
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(keystore, indent=2))
    os.chmod(out_file, 0o600)
    return out_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Encrypt an existing private key into a keystore file (address is derived from the key)"
    )
    parser.add_argument(
        "--private-key",
        default=os.getenv("AITBC_PRIVATE_KEY") or os.getenv("PRIVATE_KEY"),
        help="Hex private key to encrypt (or set AITBC_PRIVATE_KEY). Never printed.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("/var/lib/aitbc/keystore"), help="Keystore directory")
    parser.add_argument("--force", action="store_true", help="Overwrite existing keystore file")
    parser.add_argument("--password", help="Encryption password (or read from KEYSTORE_PASSWORD / keystore/.password)")
    args = parser.parse_args()

    if not args.private_key:
        parser.error("a private key is required: pass --private-key or set AITBC_PRIVATE_KEY")

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

    try:
        out_file = create_keystore(args.private_key, password, keystore_dir=args.output_dir, force=args.force)
    except FileExistsError as exc:
        print(exc)
        sys.exit(1)

    print(f"[+] Keystore written to {out_file}")
    print("[!] Keep the password safe. Without it, the private key cannot be recovered.")


if __name__ == "__main__":
    main()
