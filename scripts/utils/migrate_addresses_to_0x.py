#!/usr/bin/env python3
"""One-off migration script: rewrite legacy ait1.../aitbc1... addresses to 0x.

Targets:
- /etc/aitbc/*.env
- /var/lib/aitbc/wallets/*.json
- chain genesis / validator configs (when run with --genesis)

This script must be run on the live node (aitbc3, hub.aitbc, hub2.aitbc) after
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

    # Try JSON (e.g. VALIDATOR_SET)
    try:
        parsed = json.loads(value)
        _walk(parsed)
        return json.dumps(parsed, separators=(",", ":"))
    except (json.JSONDecodeError, ValueError):
        pass

    # Try comma-separated or space-separated addresses
    parts = re.split(r"([,\s]+)", value)
    out = []
    for part in parts:
        evm = _to_evm(part)
        out.append(evm if evm else part)
    return "".join(out)


def _walk(obj: Any) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                evm = _to_evm(v)
                if evm:
                    obj[k] = evm
            else:
                _walk(v)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str):
                evm = _to_evm(item)
                if evm:
                    obj[i] = evm
            else:
                _walk(item)


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
        if (
            data.get("address")
            and data["address"].lower().replace("aitbc1", "").replace("ait1", "") != evm_address[2:].lower()
        ):
            print(
                f"warning {path}: stored address {data['address']} does not match derived {evm_address}; keeping original in backup",
                file=sys.stderr,
            )
            backup = Path(f"{path}.pre-0x-mismatch")
            backup.write_text(json.dumps(data, indent=2))
        data["address"] = evm_address
        data["public_key"] = account._public_key.hex() if hasattr(account, "_public_key") else ""
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
