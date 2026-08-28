#!/usr/bin/env python3
"""Generate a hub proposer wallet and keystore for AITBC.

Run after the Python venv exists so eth_account is available.
It writes /var/lib/aitbc/data/keystore/proposer.json and sets
proposer_id in /etc/aitbc/blockchain.env and /etc/aitbc/credentials/proposer_id.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
from pathlib import Path


def _read_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"')
    return env


def _set_env(path: Path, key: str, value: str) -> None:
    lines = path.read_text().splitlines() if path.exists() else []
    updated = False
    new_lines: list[str] = []
    for line in lines:
        if re.match(rf"^\s*{re.escape(key)}\s*=", line):
            new_lines.append(f"{key}={value}")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(f"{key}={value}")
    path.write_text("\n".join(new_lines) + "\n")


def main() -> int:
    env_path = Path("/etc/aitbc/blockchain.env")
    creds_path = Path("/etc/aitbc/credentials/proposer_id")
    keystore_dir = Path("/var/lib/aitbc/data/keystore")
    keystore_file = keystore_dir / "proposer.json"
    password_file = Path("/etc/aitbc/credentials/keystore_password")

    if not env_path.exists():
        print("ERROR: /etc/aitbc/blockchain.env not found", file=sys.stderr)
        return 1

    env = _read_env(env_path)
    blockchain_mode = env.get("BLOCKCHAIN_MODE", "follower")
    if blockchain_mode != "hub":
        print("Node is not a hub; skipping proposer wallet generation")
        return 0

    keystore_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(keystore_dir, 0o700)

    if keystore_file.exists():
        data = json.loads(keystore_file.read_text())
        address = data.get("address", "")
        if address:
            _set_env(env_path, "proposer_id", address)
            creds_path.write_text(address)
            print(f"Existing proposer keystore found, proposer_id set to {address}")
            return 0

    from eth_account import Account
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    import hmac
    import hashlib

    password = ""
    if password_file.exists():
        password = password_file.read_text().strip()
    if not password:
        password = secrets.token_hex(32)
        password_file.write_text(password)
        os.chmod(password_file, 0o600)

    account = Account.create()
    private_bytes = bytes(account.key)
    address = account.address

    salt = os.urandom(32)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
        backend=default_backend(),
    )
    key = kdf.derive(password.encode("utf-8"))
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, private_bytes, None)
    mac_data = key[16:32] + ciphertext
    mac = hmac.new(key[:16], mac_data, hashlib.sha256).hexdigest()

    keystore = {
        "crypto": {
            "cipher": "aes-256-gcm",
            "cipherparams": {"nonce": nonce.hex()},
            "ciphertext": ciphertext.hex(),
            "kdf": "pbkdf2",
            "kdfparams": {"dklen": 32, "salt": salt.hex(), "c": 100_000, "prf": "hmac-sha256"},
            "mac": mac,
        },
        "address": address,
        "keytype": "secp256k1",
        "version": 1,
    }

    keystore_file.write_text(json.dumps(keystore, indent=2))
    os.chmod(keystore_file, 0o600)

    # Write password for node to find it
    (keystore_dir / ".password").write_text(password)
    os.chmod(keystore_dir / ".password", 0o600)

    _set_env(env_path, "proposer_id", address)
    creds_path.write_text(address)
    os.chmod(creds_path, 0o600)

    print(f"Generated proposer wallet: {address}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
