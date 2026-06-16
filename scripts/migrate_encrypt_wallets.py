#!/usr/bin/env python3
"""
Migrate existing wallet keystores to encrypt private keys at rest.

Reads all .json wallet files from the keystore directory, encrypts any
plaintext private keys using WALLET_IMPORT_PASSWORD, and rewrites the files.

Usage:
    WALLET_IMPORT_PASSWORD=your-password python scripts/migrate_encrypt_wallets.py
"""

import json
import os
import sys
from pathlib import Path

from aitbc import KEYSTORE_DIR
from aitbc.crypto import encrypt_private_key


def migrate_wallets(keystore_path: Path, password: str) -> tuple[int, int]:
    """Migrate all unencrypted wallet keystores to encrypted format.

    Returns:
        (migrated_count, skipped_count)
    """
    migrated = 0
    skipped = 0

    if not keystore_path.exists():
        print(f"Keystore directory does not exist: {keystore_path}")
        return migrated, skipped

    for wallet_file in keystore_path.glob("*.json"):
        try:
            with open(wallet_file) as f:
                wallet_data = json.load(f)

            # Skip if already encrypted or no private_key
            if wallet_data.get("encrypted", False):
                skipped += 1
                print(f"SKIP {wallet_file.name}: already encrypted")
                continue

            private_key = wallet_data.get("private_key", "")
            if not private_key:
                skipped += 1
                print(f"SKIP {wallet_file.name}: no private_key field")
                continue

            # Encrypt the private key
            encrypted_key = encrypt_private_key(private_key, password)
            wallet_data["private_key"] = encrypted_key
            wallet_data["encrypted"] = True

            # Write back
            with open(wallet_file, "w") as f:
                json.dump(wallet_data, f, indent=2)

            migrated += 1
            print(f"MIGRATED {wallet_file.name}: private key encrypted")

        except Exception as e:
            print(f"ERROR {wallet_file.name}: {e}")
            skipped += 1

    return migrated, skipped


def main() -> int:
    password = os.getenv("WALLET_IMPORT_PASSWORD", "")
    if not password:
        print("ERROR: WALLET_IMPORT_PASSWORD environment variable must be set")
        print("Usage: WALLET_IMPORT_PASSWORD=your-password python scripts/migrate_encrypt_wallets.py")
        return 1

    keystore_path = Path(os.getenv("WALLET_DIR", str(KEYSTORE_DIR)))
    print(f"Scanning keystore: {keystore_path}")
    print("Using password from WALLET_IMPORT_PASSWORD env var")

    migrated, skipped = migrate_wallets(keystore_path, password)

    print(f"\nMigration complete: {migrated} migrated, {skipped} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
