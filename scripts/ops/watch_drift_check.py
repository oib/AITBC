#!/usr/bin/env python3
"""Check the exporter's extras watch list against the keys it mirrors.

``AITBC_WATCH_ACCOUNTS`` extras in ``aitbc-authority-balances.service`` watch
service/validator identities that are *not* chain parameters, so they do not
auto-follow a rotation: a rotated key leaves the exporter alerting on the old
address while the live one goes blind (that blind spot is what the
governance-proposer extras entry exists to close — this script keeps it
closed).

For every watch entry whose role has a known env-var binding, the address the
unit watches is compared with the address *derived* from the private key the
service env actually carries:

    ROLE   host  watched=0x…  derived=0x…   OK|MISMATCH|ERROR|SKIP

Roles without a binding (parameter-managed fallbacks, retired identities) are
reported SKIP with the reason — a retired identity *should* diverge from any
env that once held it. Exit status is 1 on any MISMATCH or ERROR, else 0.

Read-only: it never writes, never prints a key value or an env line — only
role names, the watched address, and the derived address. ``eth_keys`` does
the derivation; without it every mapped role reports ERROR.

Usage:
    watch_drift_check.py [--unit-file PATH] [--env-dir DIR]

Defaults match the hub deployment: the unit in this checkout and
``/etc/aitbc``. Tests pass fixture paths for both.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_ACCOUNT = re.compile(r"^([a-z][a-z0-9_]*):(0x[0-9a-fA-F]{40})$")
_ENV_ASSIGN = re.compile(r"^([A-Z][A-Z0-9_]*)=(\S*)")
_HEX_KEY = re.compile(r"^(?:0x)?[0-9a-fA-F]{64}$")

# role -> (host label, env file basename, env var name). Only extras roles
# whose address is owned by a named env var are bound here; parameter-managed
# roles resolve on-chain and need no drift check.
ROLE_CHECKS: dict[str, tuple[str, str, str]] = {
    "governance_proposer": ("hub", "aitbc-governance.env", "GOVERNANCE_PROPOSER_PRIVATE_KEY"),
    "validator_hub": ("hub", "validator-secrets.env", "PROPOSER_KEY"),
}

SKIP_REASONS: dict[str, str] = {
    "escrow_settlement": "parameter-managed role (on-chain fallback only)",
    "bridge_release": "parameter-managed role (on-chain fallback only)",
    "bond_slash": "parameter-managed role (on-chain fallback only)",
    "governance_executor": "parameter-managed role (on-chain fallback only)",
    "proposer_retired": "retired identity — no live env binding by design",
}


def parse_watch_accounts(unit_text: str) -> list[tuple[str, str]]:
    """``AITBC_WATCH_ACCOUNTS`` from a unit file -> [(role, address)].

    Raises ValueError on a missing/bad entry, same shapes the exporter
    accepts (``role:0x<40 hex>``, comma-separated).
    """
    raw = ""
    prefix = "Environment=AITBC_WATCH_ACCOUNTS="
    for line in unit_text.splitlines():
        line = line.strip()
        if line.startswith(prefix):
            raw = line[len(prefix) :].strip()
    accounts: list[tuple[str, str]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        m = _ACCOUNT.match(part)
        if not m:
            raise ValueError(f"expected role:0x<40 hex>, got {part!r}")
        accounts.append((m.group(1), m.group(2)))
    return accounts


def read_env_var(env_dir: Path, filename: str, var: str) -> str | None:
    """The value of ``var`` in ``env_dir/filename``, or None when absent.

    Only the first whitespace-separated token of the value is taken (a
    trailing ``#`` comment would not survive EnvironmentFile parsing
    anyway); the file is opened read-only and no line content leaves this
    function.
    """
    path = env_dir / filename
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _ENV_ASSIGN.match(line.strip())
        if m and m.group(1) == var:
            return m.group(2).split("#", 1)[0] or None
    return None


def derive_address(key_hex: str) -> str | None:
    """Checksum-free lowercase address for a 64-hex private key, else None."""
    try:
        from eth_keys import keys
    except ImportError:
        return None
    raw = key_hex[2:] if key_hex.startswith(("0x", "0X")) else key_hex
    try:
        return str(keys.PrivateKey(bytes.fromhex(raw)).public_key.to_checksum_address()).lower()
    except Exception:  # noqa: BLE001 - unparseable key material derives to None
        return None


def check(unit_text: str, env_dir: Path, *, out=sys.stdout) -> int:  # noqa: B008 - sys.stdout binds at call time in main()
    rc = 0
    try:
        accounts = parse_watch_accounts(unit_text)
    except ValueError as exc:
        print(f"ERROR  unit file: {exc}", file=out)
        return 1
    if not accounts:
        print("unit file names no AITBC_WATCH_ACCOUNTS entries", file=out)
        return 0
    for role, watched in accounts:
        binding = ROLE_CHECKS.get(role)
        if binding is None:
            reason = SKIP_REASONS.get(role, "no env binding defined")
            print(f"SKIP    {role:<22} watched={watched}  ({reason})", file=out)
            continue
        host, env_file, var = binding
        key_hex = read_env_var(env_dir, env_file, var)
        if key_hex is None:
            print(f"ERROR   {role:<22} host={host}  {env_file}: {var} not found", file=out)
            rc = 1
            continue
        if not _HEX_KEY.match(key_hex):
            print(f"ERROR   {role:<22} host={host}  {env_file}: {var} is not a 64-hex key", file=out)
            rc = 1
            continue
        derived = derive_address(key_hex)
        if derived is None:
            print(f"ERROR   {role:<22} host={host}  derivation unavailable or key invalid", file=out)
            rc = 1
            continue
        state = "OK" if derived == watched.lower() else "MISMATCH"
        if state == "MISMATCH":
            rc = 1
        print(f"{state:<7} {role:<22} host={host}  watched={watched}  derived={derived}", file=out)
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--unit-file",
        default=str(Path(__file__).resolve().parents[1] / "monitoring" / "aitbc-authority-balances.service"),
        help="aitbc-authority-balances.service (default: this checkout's)",
    )
    ap.add_argument("--env-dir", default="/etc/aitbc", help="directory holding the env files")
    args = ap.parse_args()
    unit_path = Path(args.unit_file)
    if not unit_path.is_file():
        print(f"ERROR  unit file not found: {unit_path}")
        return 1
    return check(unit_path.read_text(), Path(args.env_dir))


if __name__ == "__main__":
    sys.exit(main())
