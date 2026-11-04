#!/usr/bin/env python3
"""One-off migration script: rewrite legacy ait1.../aitbc1... addresses to 0x.

Targets:
- /etc/aitbc/*.env
- /var/lib/aitbc/wallets/*.json
- chain genesis / validator configs (when run with --genesis)

This script must be run on a live node after
pulling the 0x-only branch and before restarting services.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def _body(address: str) -> str | None:
    m = re.fullmatch(r"(?:aitbc1|ait1)([0-9a-fA-F]{40})", address.strip())
    if not m:
        return None
    return m.group(1).lower()


def _to_evm(address: str) -> str | None:
    body = _body(address)
    if not body:
        return None
    try:
        from eth_utils import to_checksum_address

        return to_checksum_address(f"0x{body}")
    except Exception:
        return f"0x{body}"


def _transform_value(value: str) -> str:
    """Replace ait1/aitbc1 addresses in an env value with 0x, including JSON arrays/objects."""
    body = _body(value)
    if body:
        evm = _to_evm(value)
        return evm if evm else value

    # Try JSON (e.g. VALIDATOR_SET) — but only rewrite the line when a legacy
    # address was actually replaced; otherwise re-serialisation would rewrite
    # formatting of a value that held no ait1/aitbc1 address (#936).
    try:
        parsed = json.loads(value)
        changed = _walk(parsed)
        if changed:
            return json.dumps(parsed, separators=(",", ":"))
        return value
    except (json.JSONDecodeError, ValueError):
        pass

    # Try comma-separated or space-separated addresses
    parts = re.split(r"([,\s]+)", value)
    out = []
    for part in parts:
        evm = _to_evm(part)
        out.append(evm if evm else part)
    return "".join(out)


def _walk(obj: Any) -> bool:
    """Rewrite legacy addresses in place; True when anything changed."""
    changed = False
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                evm = _to_evm(v)
                if evm:
                    obj[k] = evm
                    changed = True
            else:
                changed = _walk(v) or changed
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str):
                evm = _to_evm(item)
                if evm:
                    obj[i] = evm
                    changed = True
            else:
                changed = _walk(item) or changed
    return changed


def migrate_env_files(env_dir: Path) -> None:
    for path in env_dir.glob("*.env"):
        original = path.read_text()
        lines = []
        changed = False
        for line in original.splitlines(keepends=True):
            if "=" in line:
                key, sep, value = line.partition("=")
                new_value = _transform_value(value.rstrip("\n"))
                if new_value != value.rstrip("\n"):
                    changed = True
                lines.append(f"{key}{sep}{new_value}\n")
            else:
                lines.append(line)
        if changed:
            backup = Path(f"{path}.pre-0x-migration")
            backup.touch(0o600)  # env lines can hold secrets — 0600, not umask
            backup.write_text(original)
            path.write_text("".join(lines))
            print(f"migrated {path} (backup {backup})")


def migrate_wallets(wallet_dir: Path) -> None:
    for path in wallet_dir.glob("*.json"):
        data = json.loads(path.read_text())
        private_key = data.get("private_key") or data.get("seed") or data.get("mnemonic")
        if not private_key:
            print(f"skip {path}: no private key", file=sys.stderr)
            continue
        try:
            from eth_account import Account

            account = Account.from_key(str(private_key).removeprefix("0x"))
            evm_address = account.address
        except Exception as e:
            print(f"skip {path}: cannot derive address ({e})", file=sys.stderr)
            continue
        # Normalise the stored side the same way as the derived side: the
        # ait1/aitbc1 strip is for legacy spellings, and a 0x wallet kept its
        # prefix so it always read as a mismatch (#936).
        stored_body = (
            data["address"].lower().removeprefix("0x").replace("aitbc1", "").replace("ait1", "") if data.get("address") else ""
        )
        if stored_body and stored_body != evm_address[2:].lower():
            print(
                f"warning {path}: stored address {data['address']} does not match derived {evm_address}; keeping original in backup",
                file=sys.stderr,
            )
            backup = Path(f"{path}.pre-0x-mismatch")
            backup.touch(0o600)  # the copy carries the private key — 0600
            backup.write_text(json.dumps(data, indent=2))
        data["address"] = evm_address
        # Keep an existing public_key; only derive one when the wallet has none.
        # The old code overwrote it with "" whenever the private attribute was
        # absent, which is every supported eth_account (#936).
        if not data.get("public_key"):
            from eth_keys import keys as _eth_keys

            data["public_key"] = (
                _eth_keys.PrivateKey(bytes.fromhex(str(private_key).removeprefix("0x"))).public_key.to_hex().removeprefix("0x")
            )
        path.write_text(json.dumps(data, indent=2))
        print(f"migrated {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-dir", default="/etc/aitbc")
    parser.add_argument("--wallet-dir", default="/var/lib/aitbc/wallets")
    parser.add_argument("--genesis-only", action="store_true")
    args = parser.parse_args()

    if not args.genesis_only:
        migrate_env_files(Path(args.env_dir))
        migrate_wallets(Path(args.wallet_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
