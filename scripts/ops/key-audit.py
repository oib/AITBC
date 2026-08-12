#!/usr/bin/env python3
"""Key-audit helper for AITBC backups.

Inspects keystore/wallet JSON files and environment files for Ethereum-style
private keys, derives the corresponding public address, and compares it to the
declared address in the same source.  Private keys are never written to the
report.

Usage:
    PYTHONPATH=/opt/aitbc /opt/aitbc/venv/bin/python scripts/ops/key-audit.py --report /path/to/key-audit.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any


def _normalize_address(addr: str | None) -> str | None:
    if not addr:
        return None
    addr = addr.strip().lower()
    if addr.startswith("0x"):
        return addr
    if addr.startswith("ait1"):
        return "0x" + addr[4:]
    if addr.startswith("aitbc1"):
        return "0x" + addr[6:]
    return None


def _derive_eth(private_key: str) -> str | None:
    if not private_key:
        return None
    pk = private_key.strip()
    if len(pk) == 64 + 2 and pk.startswith("0x"):
        pass
    elif len(pk) == 64:
        pk = "0x" + pk
    else:
        return None
    try:
        from aitbc.crypto.crypto import derive_ethereum_address

        return derive_ethereum_address(pk).lower()
    except Exception:
        return None


def _audit_json(path: Path, data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    results: list[dict[str, Any]] = []
    pk = data.get("private_key") or data.get("GENESIS_PRIVATE_KEY") or data.get("secret")
    if isinstance(pk, str) and (pk.startswith("0x") or all(c in "0123456789abcdefABCDEF" for c in pk) or len(pk) in (64, 66)):
        derived = _derive_eth(pk)
        declared_raw = data.get("address") or data.get("GENESIS_ADDRESS")
        if isinstance(declared_raw, str) and declared_raw.startswith("aitbc1"):
            # aitbc1-prefixed addresses use a different (non-Ethereum) key scheme; we cannot audit them here
            results.append(
                {
                    "source": str(path),
                    "key_name": "private_key",
                    "declared_raw": declared_raw,
                    "derived": derived,
                    "match": None,
                    "note": "non-ethereum aitbc1 address, audit skipped",
                }
            )
            return results
        declared = _normalize_address(declared_raw)
        results.append(
            {
                "source": str(path),
                "key_name": "private_key",
                "declared_raw": declared_raw,
                "declared": declared,
                "derived": derived,
                "match": (derived == declared) if (derived and declared) else None,
            }
        )
    return results


def _audit_env(path: Path, text: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    # find any key variable name with PRIVATE_KEY or WALLET_KEY or PROPOSER_KEY
    for line in text.splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\S+)\s*$", line)
        if not m:
            continue
        key_name, value = m.group(1), m.group(2)
        if "PRIVATE_KEY" not in key_name.upper() and "WALLET_KEY" not in key_name.upper() and "PROPOSER_KEY" not in key_name.upper():
            continue
        derived = _derive_eth(value)
        if not derived:
            continue
        # find a matching address variable: remove _KEY / _PRIVATE_KEY suffix and look for _ADDRESS
        base = re.sub(r"(_PRIVATE_KEY|_KEY)$", "", key_name)
        declared_raw = None
        for aline in text.splitlines():
            am = re.match(rf"^\s*{re.escape(base)}_ADDRESS\s*=\s*(\S+)\s*$", aline, re.IGNORECASE)
            if am:
                declared_raw = am.group(1)
                break
            # also try GENESIS_ADDRESS for GENESIS_PRIVATE_KEY / GENESIS_WALLET_PRIVATE_KEY
            if base.upper() in ("GENESIS", "GENESIS_WALLET"):
                gm = re.match(r"^\s*GENESIS_ADDRESS\s*=\s*(\S+)\s*$", aline, re.IGNORECASE)
                if gm:
                    declared_raw = gm.group(1)
                    break
            # and NODE_WALLET_ADDRESS for any *_WALLET_PRIVATE_KEY
            if base.upper().endswith("WALLET"):
                nm = re.match(r"^\s*NODE_WALLET_ADDRESS\s*=\s*(\S+)\s*$", aline, re.IGNORECASE)
                if nm:
                    declared_raw = nm.group(1)
                    break
        declared = _normalize_address(declared_raw)
        results.append(
            {
                "source": str(path),
                "key_name": key_name,
                "declared_raw": declared_raw,
                "declared": declared,
                "derived": derived,
                "match": (derived == declared) if (derived and declared) else None,
            }
        )
    return results


def _scan() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for path in sorted(Path("/var/lib/aitbc/keystore").glob("*.json")):
        try:
            with open(path) as f:
                data = json.load(f)
            results.extend(_audit_json(path, data))
        except Exception as e:
            results.append({"source": str(path), "error": f"read/parse failed: {e}"})

    for path in sorted(Path("/var/lib/aitbc/wallets").glob("*.json")):
        try:
            with open(path) as f:
                data = json.load(f)
            results.extend(_audit_json(path, data))
        except Exception as e:
            results.append({"source": str(path), "error": f"read/parse failed: {e}"})

    for path in sorted(Path("/etc/aitbc").glob("*.env")):
        try:
            with open(path) as f:
                text = f.read()
            results.extend(_audit_env(path, text))
        except Exception as e:
            results.append({"source": str(path), "error": f"read failed: {e}"})

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit AITBC private keys vs declared addresses")
    parser.add_argument("--report", required=True, help="Path to write the audit JSON report")
    args = parser.parse_args()

    findings = _scan()
    report = {
        "ok": all(f.get("match") for f in findings if f.get("match") is not None),
        "mismatches": [f for f in findings if f.get("match") is False],
        "findings": findings,
    }
    os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
    with open(args.report, "w") as f:
        json.dump(report, f, indent=2)
    print(f"wrote {args.report}: {len(findings)} findings, {len(report['mismatches'])} mismatches")


if __name__ == "__main__":
    main()
