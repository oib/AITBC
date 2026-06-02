#!/usr/bin/env python3
"""Import file-based wallets from ~/.aitbc/wallets/ into the wallet daemon."""

import base64
import json
import os
import sys
from pathlib import Path

import httpx

WALLET_DAEMON_URL = os.getenv("WALLET_DAEMON_URL", "http://localhost:8108")
WALLET_DIR = Path(os.getenv("WALLET_DIR", os.path.expanduser("~/.aitbc/wallets")))
IMPORT_PASSWORD = os.getenv("WALLET_IMPORT_PASSWORD", "Aitbc-Import-Pass1")


def import_wallets():
    if not WALLET_DIR.exists():
        print(f"Wallet directory not found: {WALLET_DIR}")
        sys.exit(1)

    wallet_files = list(WALLET_DIR.glob("*.json"))
    if not wallet_files:
        print(f"No wallet files found in {WALLET_DIR}")
        sys.exit(0)

    print(f"Found {len(wallet_files)} wallet(s) in {WALLET_DIR}")

    # Check daemon is up
    try:
        r = httpx.get(f"{WALLET_DAEMON_URL}/health", timeout=5)
        r.raise_for_status()
        print(f"Daemon healthy: {r.json()}")
    except Exception as e:
        print(f"Daemon not available at {WALLET_DAEMON_URL}: {e}")
        sys.exit(1)

    # Check existing wallets
    existing = set()
    try:
        r = httpx.get(f"{WALLET_DAEMON_URL}/v1/wallets", timeout=5)
        for w in r.json().get("items", []):
            existing.add(w["wallet_id"])
    except Exception:
        pass

    imported = 0
    skipped = 0
    failed = 0

    for wallet_file in wallet_files:
        try:
            with open(wallet_file) as f:
                data = json.load(f)

            wallet_id = data.get("wallet_id") or wallet_file.stem
            address = data.get("address", "")
            private_key_hex = data.get("private_key", "").lstrip("0x")
            chain_id = data.get("chain_id", "ait-hub.aitbc.bubuit.net")

            if wallet_id in existing:
                print(f"  SKIP  {wallet_id} (already in daemon)")
                skipped += 1
                continue

            if not private_key_hex:
                print(f"  SKIP  {wallet_id} (no private key)")
                skipped += 1
                continue

            # Encode private key as base64 (daemon expects base64)
            private_key_bytes = bytes.fromhex(private_key_hex)
            secret_b64 = base64.b64encode(private_key_bytes).decode()

            payload = {
                "wallet_id": wallet_id,
                "chain_id": chain_id,
                "password": IMPORT_PASSWORD,
                "secret_key": secret_b64,
                "metadata": {
                    "address": address,
                    "imported_from": str(wallet_file),
                    "original_address": address,
                }
            }

            r = httpx.post(f"{WALLET_DAEMON_URL}/v1/wallets", json=payload, timeout=10)
            if r.status_code in (200, 201):
                result = r.json()
                wallet = result.get("wallet", {})
                print(f"  OK    {wallet_id} (address={address})")
                imported += 1
            elif r.status_code == 400 and "already exists" in r.text:
                print(f"  SKIP  {wallet_id} (already exists)")
                skipped += 1
            else:
                print(f"  FAIL  {wallet_id}: {r.status_code} {r.text}")
                failed += 1

        except Exception as e:
            print(f"  ERROR {wallet_file.name}: {e}")
            failed += 1

    print(f"\nDone: {imported} imported, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    import_wallets()
