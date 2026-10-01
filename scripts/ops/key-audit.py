#!/usr/bin/env python3
"""Key-audit helper for AITBC backups.

Inspects keystore/wallet JSON files and environment files for Ethereum-style
private keys, derives the corresponding public address, and compares it to the
declared address in the same source.  Private keys are never written to the
report.

Leftover copies of env files (``node.env.bak-20260926`` and the like) are listed
too, flagged ``"backup": true``: a rotated key lives on in them. They stay out of
the ``ok`` / ``mismatches`` verdict, which the nightly backup acts on.

``--find-address ADDRESS`` (repeatable) additionally lists every file, backups
included, that holds a private key deriving to ADDRESS. It matches the key by
value, so the variable name, JSON field or comment around it does not matter; the
name-based scan missed two hub backups that way on 2026-10-01. The key itself is
never printed or stored, only file names, modes and counts.

Usage:
    PYTHONPATH=/opt/aitbc /opt/aitbc/venv/bin/python scripts/ops/key-audit.py --report /path/to/key-audit.json
    PYTHONPATH=/opt/aitbc /opt/aitbc/venv/bin/python scripts/ops/key-audit.py --report /tmp/ka.json --find-address 0x02B8...
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


def _find_declared_address(base: str, text: str) -> str | None:
    """Find the declared address variable matching a key variable's base name."""
    for aline in text.splitlines():
        am = re.match(rf"^\s*{re.escape(base)}_ADDRESS\s*=\s*(\S+)\s*$", aline, re.IGNORECASE)
        if am:
            return am.group(1)
        # also try GENESIS_ADDRESS for GENESIS_PRIVATE_KEY / GENESIS_WALLET_PRIVATE_KEY
        if base.upper() in ("GENESIS", "GENESIS_WALLET"):
            gm = re.match(r"^\s*GENESIS_ADDRESS\s*=\s*(\S+)\s*$", aline, re.IGNORECASE)
            if gm:
                return gm.group(1)
        # and NODE_WALLET_ADDRESS for any *_WALLET_PRIVATE_KEY — but not
        # for GENESIS_WALLET, which is a different wallet from NODE_WALLET.
        if base.upper().endswith("WALLET") and base.upper() not in ("GENESIS", "GENESIS_WALLET"):
            nm = re.match(r"^\s*NODE_WALLET_ADDRESS\s*=\s*(\S+)\s*$", aline, re.IGNORECASE)
            if nm:
                return nm.group(1)
    return None


def _audit_env(path: Path, text: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    # find any key variable name with PRIVATE_KEY or WALLET_KEY or PROPOSER_KEY
    for line in text.splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\S+)\s*$", line)
        if not m:
            continue
        key_name, value = m.group(1), m.group(2)
        if (
            "PRIVATE_KEY" not in key_name.upper()
            and "WALLET_KEY" not in key_name.upper()
            and "PROPOSER_KEY" not in key_name.upper()
        ):
            continue
        derived = _derive_eth(value)
        if not derived:
            continue
        # find a matching address variable: remove _KEY / _PRIVATE_KEY suffix and look for _ADDRESS
        base = re.sub(r"(_PRIVATE_KEY|_KEY)$", "", key_name)
        declared_raw = _find_declared_address(base, text)
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


ETC_DIR = Path("/etc/aitbc")
WALLET_DIRS = (Path("/var/lib/aitbc/keystore"), Path("/var/lib/aitbc/wallets"))

# Name fragments of the copies operators leave behind (``node.env.bak-20260926``, ``blockchain.env.orig``).
BACKUP_TAGS = (".bak", ".orig", ".old", "~", ".save", ".swp")

# A private key as it appears in a file: 64 hex digits, optionally 0x-prefixed.
_HEX_KEY = re.compile(r"(?<![0-9a-fA-F])(?:0x)?([0-9a-fA-F]{64})(?![0-9a-fA-F])")


def _is_backup_name(name: str) -> bool:
    """A leftover copy of an env file: not itself an ``.env``/``.json`` source, but named like a backup."""
    return not name.endswith((".env", ".json")) and any(tag in name for tag in BACKUP_TAGS)


def _scan(etc_dir: Path = ETC_DIR, wallet_dirs: tuple[Path, ...] = WALLET_DIRS) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for directory in wallet_dirs:
        for path in sorted(directory.glob("*.json")):
            try:
                with open(path) as f:
                    data = json.load(f)
                results.extend(_audit_json(path, data))
            except Exception as e:
                results.append({"source": str(path), "error": f"read/parse failed: {e}"})

    for path in sorted(etc_dir.glob("*.env")):
        try:
            with open(path) as f:
                text = f.read()
            results.extend(_audit_env(path, text))
        except Exception as e:
            results.append({"source": str(path), "error": f"read failed: {e}"})

    # Backup copies are listed too, flagged: a rotated key lives on in them. They stay out of the verdict (see
    # build_report), because a stale copy disagreeing with itself is not a live inconsistency.
    if etc_dir.is_dir():
        for path in sorted(etc_dir.iterdir()):
            if path.is_file() and _is_backup_name(path.name):
                try:
                    findings = _audit_env(path, path.read_text(errors="ignore"))
                except OSError as e:
                    results.append({"source": str(path), "backup": True, "error": f"read failed: {e}"})
                    continue
                results.extend({**finding, "backup": True} for finding in findings)

    return results


def _candidate_files(etc_dir: Path, wallet_dirs: tuple[Path, ...]) -> list[Path]:
    files: list[Path] = []
    for directory in (etc_dir, *wallet_dirs):
        if directory.is_dir():
            files.extend(p for p in sorted(directory.iterdir()) if p.is_file())
    return files


def _find_by_value(
    addresses: list[str], etc_dir: Path = ETC_DIR, wallet_dirs: tuple[Path, ...] = WALLET_DIRS
) -> list[dict[str, Any]]:
    """Every file holding a private key that derives to one of ``addresses``.

    Found by value, so the variable name, the JSON field or a comment around the key do not matter. The key itself
    is never returned, printed or stored.
    """
    wanted = set(addresses)
    derived: dict[str, str | None] = {}
    hits: list[dict[str, Any]] = []
    for path in _candidate_files(etc_dir, wallet_dirs):
        try:
            text = path.read_text(errors="ignore")
        except OSError as e:
            hits.append({"source": str(path), "error": f"read failed: {e}"})
            continue
        matched: set[str] = set()
        count = 0
        for m in _HEX_KEY.finditer(text):
            token = m.group(1).lower()
            if token not in derived:
                derived[token] = _derive_eth(token)
            address = derived[token]
            if address is not None and address in wanted:
                matched.add(address)
                count += 1
        if count:
            hits.append(
                {
                    "source": str(path),
                    "backup": _is_backup_name(path.name),
                    "mode": oct(path.stat().st_mode & 0o7777),
                    "addresses": sorted(matched),
                    "occurrences": count,
                }
            )
    return hits


def build_report(
    etc_dir: Path = ETC_DIR,
    wallet_dirs: tuple[Path, ...] = WALLET_DIRS,
    find_addresses: list[str] | None = None,
) -> dict[str, Any]:
    findings = _scan(etc_dir, wallet_dirs)
    live = [f for f in findings if not f.get("backup")]
    report: dict[str, Any] = {
        "ok": all(f.get("match") for f in live if f.get("match") is not None),
        "mismatches": [f for f in live if f.get("match") is False],
        "findings": findings,
    }
    if find_addresses:
        report["found_by_value"] = _find_by_value(find_addresses, etc_dir, wallet_dirs)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit AITBC private keys vs declared addresses")
    parser.add_argument("--report", required=True, help="Path to write the audit JSON report")
    parser.add_argument(
        "--find-address",
        action="append",
        default=[],
        metavar="ADDRESS",
        help="also list every file (backups included) holding a private key that derives to ADDRESS, whatever its "
        "variable name; repeatable. The key is never printed.",
    )
    args = parser.parse_args()

    addresses: list[str] = []
    for raw in args.find_address:
        normalized = _normalize_address(raw)
        if not normalized:
            parser.error(f"not an address: {raw}")
        addresses.append(normalized)

    report = build_report(find_addresses=addresses)
    os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
    with open(args.report, "w") as f:
        json.dump(report, f, indent=2)
    print(f"wrote {args.report}: {len(report['findings'])} findings, {len(report['mismatches'])} mismatches")
    for address in addresses:
        hits = [h for h in report["found_by_value"] if address in h.get("addresses", [])]
        backups = sum(1 for h in hits if h.get("backup"))
        print(f"{address}: {len(hits)} file(s) hold its key ({backups} of them backups)")
        for h in hits:
            print(f"  {h['source']}  mode {h['mode']}  x{h['occurrences']}{'  (backup)' if h['backup'] else ''}")


if __name__ == "__main__":
    main()
