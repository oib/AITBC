#!/usr/bin/env python3
"""Recurring bridge payout audit, run by fleet-config-check.sh.

Two invariants, evaluated across every bridge deposit ledger found on the
fleet against the canonical chain:

1. every COMPLETED row's ait_tx_hash exists as a sealed transaction
   (row present with a non-null block_height) in the chain transactions
   table — a recorded payout that never landed is a phantom completion;
2. every ETH deposit hash maps to at most one distinct payout hash — two
   different ait_tx_hash values recorded for one deposit across the
   ledgers is a double payment.

Ledgers: any ``bridge_deposits*.db`` under /var/lib/aitbc (opened read-only;
``.bak`` files excluded). Chain: the first ``chain.db`` under
/var/lib/aitbc/data on the preferred chain host, falling back through the
fleet. Nothing is written to any database.

Usage: bridge-payout-audit.py [--chain-host NAME] host=ssh-target ...
Exit: 0 clean, 1 violation or audit itself could not complete.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys

SSH = ["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes"]

LEDGER_REMOTE = r"""
import glob, json, sqlite3
rows = []
for db in sorted(glob.glob('/var/lib/aitbc/**/bridge_deposits*.db', recursive=True)):
    if db.endswith('.bak'):
        continue
    try:
        con = sqlite3.connect('file:%s?mode=ro' % db, uri=True, timeout=10)
        cols = {r[1] for r in con.execute('PRAGMA table_info(eth_deposits)')}
        err = 'error_message' if 'error_message' in cols else 'NULL'
        rcp = 'recipient' if 'recipient' in cols else 'NULL'
        amt = 'amount_eth' if 'amount_eth' in cols else 'NULL'
        for h, ait, st, em, rc, am, fr in con.execute('SELECT tx_hash, ait_tx_hash, status, %s, %s, %s, from_address FROM eth_deposits' % (err, rcp, amt)):
            rows.append({'db': db, 'tx_hash': h, 'ait_tx_hash': ait, 'status': st, 'error_message': em, 'recipient': rc, 'amount_eth': am, 'from_address': fr})
        con.close()
    except Exception as exc:
        rows.append({'db': db, 'error': str(exc)})
print(json.dumps(rows))
"""

CHAIN_REMOTE = r"""
import glob, json, sqlite3, sys
hashes = json.loads(sys.argv[1])
# several island dirs can coexist; the live chain db has the highest head
best, best_h = None, -1
for db in sorted(glob.glob('/var/lib/aitbc/data/*/chain.db')):
    try:
        c = sqlite3.connect('file:%s?mode=ro' % db, uri=True, timeout=10)
        h = c.execute('SELECT MAX(height) FROM block').fetchone()[0]
        c.close()
        if h is not None and h > best_h:
            best, best_h = db, h
    except Exception:
        continue
if best is None:
    print(json.dumps({'error': 'no chain.db under /var/lib/aitbc/data'}))
    sys.exit(0)
con = sqlite3.connect('file:%s?mode=ro' % best, uri=True, timeout=10)
out = {'db': best, 'sealed': {}, 'pending': {}}
for h in hashes:
    row = con.execute('SELECT block_height FROM "transaction" WHERE tx_hash = ?', (h,)).fetchone()
    if row is None:
        out['sealed'][h] = None
    elif row[0] is None:
        out['pending'][h] = True
        out['sealed'][h] = None
    else:
        out['sealed'][h] = row[0]
con.close()
print(json.dumps(out))
"""


def remote_python(target: str, program: str, arg: str | None = None) -> str | None:
    # program goes via stdin ("python3 -") — argv is re-parsed by the remote
    # login shell, so extra args must be shell-quoted to survive the hop.
    cmd = "python3 -" + (" " + shlex.quote(arg) if arg is not None else "")
    try:
        proc = subprocess.run(
            [*SSH, target, cmd],
            input=program,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return proc.stdout


def main() -> int:
    args = sys.argv[1:]
    chain_pref = None
    if args[:1] == ["--chain-host"]:
        chain_pref, args = args[1], args[2:]
    hosts = []  # (name, ssh_target)
    for spec in args:
        name, _, target = spec.partition("=")
        hosts.append((name, target or name))
    if not hosts:
        print("FAIL: no hosts given", flush=True)
        return 1

    bad = 0
    ledgers: list[dict] = []
    for name, target in hosts:
        raw = remote_python(target, LEDGER_REMOTE)
        if raw is None:
            print(f"  {name:<14} UNREACHABLE (ledger dump failed)", flush=True)
            bad = 1
            continue
        try:
            rows = json.loads(raw)
        except json.JSONDecodeError:
            print(f"  {name:<14} FAIL: ledger dump unparsable", flush=True)
            bad = 1
            continue
        n = 0
        for row in rows:
            row["host"] = name
            if "error" in row:
                print(f"  {name:<14} FAIL: {row['db']}: {row['error']}", flush=True)
                bad = 1
                continue
            n += 1
            ledgers.append(row)
        print(f"  {name:<14} {n} ledger deposit row(s)", flush=True)

    # invariant 2: one deposit hash -> at most one distinct payout hash
    payouts_by_deposit: dict[str, set[str]] = {}
    for row in ledgers:
        ait = row.get("ait_tx_hash")
        if ait:
            payouts_by_deposit.setdefault(row["tx_hash"], set()).add(ait)
    for dep, hashes in sorted(payouts_by_deposit.items()):
        if len(hashes) > 1:
            print(
                f"  FAIL: deposit {dep[:18]}… has {len(hashes)} distinct payouts: "
                + ", ".join(sorted(h[:18] + "…") for h in hashes),
                flush=True,
            )
            bad = 1

    # written-off rows are deliberately unsettled (each carries a written
    # reason) — listed for visibility, not a violation. Rows WITH a
    # recorded recipient are owed money and listed separately so an
    # operator can't quietly write off a debt.
    def _valid_recip(addr: object) -> bool:
        return isinstance(addr, str) and addr.startswith("0x") and len(addr) == 42

    for row in ledgers:
        if row.get("status") != "written_off":
            continue
        if _valid_recip(row.get("recipient")):
            print(
                f"  WRITTEN-OFF DEBT: {row['host']} {row['db']}: {row['tx_hash'][:18]}… "
                f"recipient {row['recipient'][:18]}… — verify deliberate: "
                f"{(row.get('error_message') or 'no reason!')[:80]}",
                flush=True,
            )
        else:
            print(
                f"  note: {row['host']} {row['db']}: written-off deposit {row['tx_hash'][:18]}… "
                f"({(row.get('error_message') or 'no reason!')[:90]})",
                flush=True,
            )
        if not row.get("error_message"):
            print("  FAIL: written-off row without a recorded reason", flush=True)
            bad = 1

    # funding rows: operator float top-ups — recorded, not owed a payout.
    # Listed so every ETH inflow is visible in the audit.
    for row in ledgers:
        if row.get("status") == "funding":
            print(
                f"  funding: {row['host']} {row['db']}: {row['tx_hash'][:18]}… "
                f"{row.get('amount_eth')} ETH from {(row.get('from_address') or '?')[:18]}…",
                flush=True,
            )

    # collect every payout hash that must exist sealed on chain
    need = {row["ait_tx_hash"] for row in ledgers if row.get("status") == "completed" and row.get("ait_tx_hash")}
    missing_hash_rows = [row for row in ledgers if row.get("status") == "completed" and not row.get("ait_tx_hash")]
    for row in missing_hash_rows:
        print(
            f"  FAIL: {row['host']} {row['db']}: COMPLETED row {row['tx_hash'][:18]}… has no ait_tx_hash",
            flush=True,
        )
        bad = 1

    if need:
        sealed: dict[str, object] | None = None
        pending: set[str] = set()
        chain_desc = None
        ordered = sorted(hosts, key=lambda h: 0 if h[0] == chain_pref else 1)
        for name, target in ordered:
            raw = remote_python(target, CHAIN_REMOTE, json.dumps(sorted(need)))
            if raw is None:
                continue
            try:
                out = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if "error" in out:
                continue
            sealed = out["sealed"]
            pending = set(out.get("pending", {}))
            chain_desc = f"{name}:{out['db']}"
            break
        if sealed is None:
            print("  FAIL: no host could answer the chain query", flush=True)
            bad = 1
        else:
            print(f"  chain view: {chain_desc}", flush=True)
            for row in ledgers:
                if row.get("status") != "completed" or not row.get("ait_tx_hash"):
                    continue
                h = row["ait_tx_hash"]
                height = sealed.get(h)
                if height is None:
                    where = "in mempool, not sealed" if h in pending else "absent from chain"
                    print(
                        f"  FAIL: {row['host']}: COMPLETED deposit {row['tx_hash'][:18]}… payout {h[:18]}… {where}",
                        flush=True,
                    )
                    bad = 1

    if bad == 0:
        print(f"  ok: {len(ledgers)} ledger rows, {len(need)} sealed payout(s) verified", flush=True)
    return bad


if __name__ == "__main__":
    sys.exit(main())
