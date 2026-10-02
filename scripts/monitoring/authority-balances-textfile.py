#!/usr/bin/env python3
"""Export authority account balances as a node_exporter textfile.

Hub's Prometheus has no balance series, so nothing could warn that the escrow
settlement authority was running out of fee float (every release and refund
debits ``max(36, amount // 100)`` units from it; with too little balance both
fail and the escrowed funds stay locked).

Reads ``GET <RPC_URL>/rpc/accounts/<address>`` for each ``role:address`` in
``AITBC_WATCH_ACCOUNTS`` and writes, atomically, to
``<TEXTFILE_DIR>/aitbc_authority.prom``:

    aitbc_authority_balance_units{role=...,address=...}   balance in units (1 AIT = 36,000,000)
    aitbc_authority_nonce{role=...,address=...}           account nonce
    aitbc_authority_scrape_success{role=...,address=...}  1 if this read worked, else 0
    aitbc_authority_scrape_timestamp_seconds              when this run finished

A failed read leaves out that account's balance and nonce (a stale value must
not read as current) and sets ``scrape_success`` to 0. Run by a systemd timer
(aitbc-authority-balances.timer); stdlib only.

Environment:
    AITBC_WATCH_ACCOUNTS   comma-separated role:address pairs (required)
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


def parse_accounts(raw: str) -> list[tuple[str, str]]:
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
    if not accounts:
        raise ValueError("AITBC_WATCH_ACCOUNTS names no account")
    return accounts


def read_account(rpc_url: str, address: str, timeout: float = 5.0) -> tuple[int, int] | None:
    """(balance, nonce) from the node, or None when the read failed or the answer is not usable."""
    base = rpc_url.rstrip("/")
    if not base.startswith(("http://", "https://")):
        return None
    try:
        with urllib.request.urlopen(f"{base}/rpc/accounts/{address}", timeout=timeout) as response:  # nosec B310 - operator-configured RPC endpoint, scheme-checked above, address is regex-validated 0x-hex
            body = json.load(response)
        balance, nonce = body["balance"], body["nonce"]
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError):
        return None
    if isinstance(balance, bool) or isinstance(nonce, bool) or not isinstance(balance, int) or not isinstance(nonce, int):
        return None
    return balance, nonce


def render(readings: list[tuple[str, str, tuple[int, int] | None]], now: float) -> str:
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
        lines.append(f'aitbc_authority_scrape_success{{role="{role}",address="{address}"}} {0 if reading is None else 1}')
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
        accounts = parse_accounts(os.environ.get("AITBC_WATCH_ACCOUNTS", ""))
    except ValueError as exc:
        print(f"authority-balances: {exc}", file=sys.stderr)
        return 2
    rpc_url = os.environ.get("AITBC_RPC_URL", "http://127.0.0.1:8202")
    directory = os.environ.get("AITBC_TEXTFILE_DIR", "/var/lib/prometheus/node-exporter")
    readings = [(role, address, read_account(rpc_url, address)) for role, address in accounts]
    write_atomic(directory, render(readings, time.time()))
    failed = [role for role, _, reading in readings if reading is None]
    if failed:
        print(f"authority-balances: could not read {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
