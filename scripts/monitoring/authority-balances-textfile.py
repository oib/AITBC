#!/usr/bin/env python3
"""Export authority account balances as a node_exporter textfile.

Hub's Prometheus has no balance series, so nothing could warn that the escrow
settlement authority was running out of fee float (every release and refund
debits ``max(36, amount // 100)`` units from it; with too little balance both
fail and the escrowed funds stay locked).

The watched roles come from the live chain parameters at run time —
``GET <RPC_URL>/rpc/state/snapshot`` — so an authority rotation needs no unit
edit:

    escrow_settlement   <- escrow_settlement_authority
    bridge_release      <- bridge_release_authority
    bond_slash          <- bond_slash_authority
    governance_executor <- governance_executors (every list member)

``AITBC_WATCH_ACCOUNTS`` (``role:address`` pairs) is no longer required: an
entry for a parameter-managed role is the fallback used only when the parameter
read fails, and entries for other roles are always-on extras (to keep watching
a retired authority, give it its own role name — a fallback entry for a managed
role is dormant while the parameter resolves). When a role falls back the run
still reports ``scrape_success`` 0 for it — a fallback address may be stale and
must not look like a clean parameter-derived read; when no fallback exists the
role is reported with an empty ``address`` label.

Reads ``GET <RPC_URL>/rpc/accounts/<address>`` for each resolved
``role:address`` and writes, atomically, to
``<TEXTFILE_DIR>/aitbc_authority.prom``:

    aitbc_authority_balance_units{role=...,address=...}   balance in units (1 AIT = 36,000,000)
    aitbc_authority_nonce{role=...,address=...}           account nonce
    aitbc_authority_scrape_success{role=...,address=...}  1 if this read worked, else 0
    aitbc_authority_scrape_timestamp_seconds              when this run finished

A missing account row (HTTP 404) is a fresh zero account — balance 0, nonce 0,
scrape_success 1 — an unfunded authority is readable. A failed read leaves out
that account's balance and nonce (a stale value must not read as current) and
sets ``scrape_success`` to 0. Run by a systemd timer
(aitbc-authority-balances.timer); stdlib only.

Environment:
    AITBC_WATCH_ACCOUNTS   optional extra / fallback role:address pairs
    AITBC_RPC_URL          default http://127.0.0.1:8202
    AITBC_TEXTFILE_DIR     default /var/lib/prometheus/node-exporter
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request

OUTPUT_NAME = "aitbc_authority.prom"
_ROLE = re.compile(r"^[a-z][a-z0-9_]*$")
_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")

# Roles whose watch address is derived from the live chain parameter named here.
# A rotation of one of these parameters re-points the exporter on its next run.
PARAMETER_ROLES = {
    "escrow_settlement": "escrow_settlement_authority",
    "bridge_release": "bridge_release_authority",
    "bond_slash": "bond_slash_authority",
}

# Same, for parameters holding a comma-separated list — every valid member is
# watched under the role. A member that fails the address check marks the role
# stale without dropping the valid members.
LIST_PARAMETER_ROLES = {
    "governance_executor": "governance_executors",
}


def parse_accounts(raw: str, *, allow_empty: bool = False) -> list[tuple[str, str]]:
    """``role:address,role:address`` -> [(role, address)]; raises ValueError on a bad entry."""
    accounts: list[tuple[str, str]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        role, sep, address = part.partition(":")
        if not sep or not _ROLE.match(role) or not _ADDRESS.match(address):
            raise ValueError(f"expected role:0x<40 hex>, got {part!r}")
        accounts.append((role, address))
    if not accounts and not allow_empty:
        raise ValueError("AITBC_WATCH_ACCOUNTS names no account")
    return accounts


def fetch_parameters(rpc_url: str, timeout: float = 10.0) -> dict[str, str] | None:
    """``{parameter: value}`` from the state snapshot, or None when the read fails."""
    base = rpc_url.rstrip("/")
    if not base.startswith(("http://", "https://")):
        return None
    try:
        with urllib.request.urlopen(f"{base}/rpc/state/snapshot", timeout=timeout) as response:  # nosec B310 - operator-configured RPC endpoint, scheme-checked above, fixed path
            body = json.load(response)
        return {str(p["parameter"]): str(p["value"]) for p in body["chain_parameters"]}
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError):
        return None


def read_account(rpc_url: str, address: str, timeout: float = 5.0) -> tuple[int, int] | None:
    """(balance, nonce) from the node; (0, 0) for a missing account row; None when the read failed."""
    base = rpc_url.rstrip("/")
    if not base.startswith(("http://", "https://")):
        return None
    try:
        with urllib.request.urlopen(f"{base}/rpc/accounts/{address}", timeout=timeout) as response:  # nosec B310 - operator-configured RPC endpoint, scheme-checked above, address is regex-validated 0x-hex
            body = json.load(response)
        balance, nonce = body["balance"], body["nonce"]
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return 0, 0
        return None
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError):
        return None
    if isinstance(balance, bool) or isinstance(nonce, bool) or not isinstance(balance, int) or not isinstance(nonce, int):
        return None
    return balance, nonce


def resolve_accounts(
    parameters: dict[str, str] | None, env_accounts: list[tuple[str, str]]
) -> tuple[list[tuple[str, str]], set[str]]:
    """Split the watch list into resolved ``(role, address)`` pairs and roles left blind.

    Parameter-managed roles resolve from the live parameters; when a parameter
    is unreadable or malformed the env entry for that role is the fallback, and
    the role is marked stale (its ``scrape_success`` is forced 0 — the fallback
    address may itself be old). A managed role with no fallback resolves to an
    empty address. Env entries for unmanaged roles are plain extras.
    """
    resolved: list[tuple[str, str]] = []
    stale: set[str] = set()
    managed = set(PARAMETER_ROLES) | set(LIST_PARAMETER_ROLES)
    for role, parameter in PARAMETER_ROLES.items():
        value = (parameters or {}).get(parameter, "")
        address = value.strip()
        if _ADDRESS.match(address):
            resolved.append((role, address))
            continue
        fallback = next((a for r, a in env_accounts if r == role), "")
        resolved.append((role, fallback))
        stale.add(role)
    for role, parameter in LIST_PARAMETER_ROLES.items():
        members = [a.strip() for a in (parameters or {}).get(parameter, "").split(",") if a.strip()]
        valid = [a for a in members if _ADDRESS.match(a)]
        if valid:
            resolved.extend((role, a) for a in valid)
            if len(valid) != len(members):
                stale.add(role)
            continue
        fallbacks = [a for r, a in env_accounts if r == role]
        if fallbacks:
            resolved.extend((role, a) for a in fallbacks)
        else:
            resolved.append((role, ""))
        stale.add(role)
    resolved.extend((role, address) for role, address in env_accounts if role not in managed)
    return resolved, stale


def render(readings: list[tuple[str, str, tuple[int, int] | None]], stale_roles: set[str], now: float) -> str:
    lines = [
        "# HELP aitbc_authority_balance_units Account balance in units (1 AIT = 36000000).",
        "# TYPE aitbc_authority_balance_units gauge",
    ]
    for role, address, reading in readings:
        if reading is not None:
            lines.append(f'aitbc_authority_balance_units{{role="{role}",address="{address}"}} {reading[0]}')
    lines += ["# HELP aitbc_authority_nonce Account nonce.", "# TYPE aitbc_authority_nonce gauge"]
    for role, address, reading in readings:
        if reading is not None:
            lines.append(f'aitbc_authority_nonce{{role="{role}",address="{address}"}} {reading[1]}')
    lines += [
        "# HELP aitbc_authority_scrape_success 1 when the account was read in the last run.",
        "# TYPE aitbc_authority_scrape_success gauge",
    ]
    for role, address, reading in readings:
        lines.append(
            f'aitbc_authority_scrape_success{{role="{role}",address="{address}"}} {0 if reading is None or role in stale_roles else 1}'
        )
    lines += [
        "# HELP aitbc_authority_scrape_timestamp_seconds Unix time the last run finished.",
        "# TYPE aitbc_authority_scrape_timestamp_seconds gauge",
        f"aitbc_authority_scrape_timestamp_seconds {int(now)}",
    ]
    return "\n".join(lines) + "\n"


def write_atomic(directory: str, text: str) -> None:
    """Write beside the target and rename: node_exporter never reads a half-written file."""
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".aitbc_authority.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, os.path.join(directory, OUTPUT_NAME))
    except BaseException:
        os.unlink(tmp)
        raise


def main() -> int:
    try:
        env_accounts = parse_accounts(os.environ.get("AITBC_WATCH_ACCOUNTS", ""), allow_empty=True)
    except ValueError as exc:
        print(f"authority-balances: {exc}", file=sys.stderr)
        return 2
    rpc_url = os.environ.get("AITBC_RPC_URL", "http://127.0.0.1:8202")
    directory = os.environ.get("AITBC_TEXTFILE_DIR", "/var/lib/prometheus/node-exporter")
    parameters = fetch_parameters(rpc_url)
    accounts, stale = resolve_accounts(parameters, env_accounts)
    readings = [(role, address, read_account(rpc_url, address) if address else None) for role, address in accounts]
    write_atomic(directory, render(readings, stale, time.time()))
    failed = [role for role, _, reading in readings if reading is None]
    if stale:
        print(
            f"authority-balances: chain parameters unreadable, env fallback used for {', '.join(sorted(stale))}",
            file=sys.stderr,
        )
    if failed:
        print(f"authority-balances: could not read {', '.join(failed)}", file=sys.stderr)
    return 1 if failed or stale else 0


if __name__ == "__main__":
    sys.exit(main())
