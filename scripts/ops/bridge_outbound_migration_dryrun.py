#!/usr/bin/env python3
"""BR-7: dry-run the B13 ``bridge_outbound`` migration on a throwaway database.

B13 (TOPOLOGY/2026-10-08-b13-bridge-outbound-ledger-design.md) adds a
``bridge_outbound`` table to the bridge-monitor ledger so outbound ETH
(depositor refunds, operator withdrawals, their gas) stops being invisible:
today ``eth_deposits`` records inflows only and
``scripts/ops/bridge_wallet_reconcile.py`` can only close the books on
operator-supplied ``--onchain`` figures.

This script proves the migration and the close-the-loop path end to end on a
throwaway SQLite file built from fixtures — **never** a live host database:

1. bootstrap ``eth_deposits`` (same column set as
   ``apps/bridge-monitor/src/bridge_monitor/storage.py``) and seed fixture
   deposits;
2. apply the B13 ``CREATE TABLE bridge_outbound`` DDL, then PRAGMA-verify the
   columns (same discipline as the monitor's PRAGMA-first migrations);
3. classify + insert fixture outbound txs the way the design's writer
   (``record_outbound`` at the ``from == bridge_eth_address`` scan branch)
   will: ``to`` a known depositor -> ``refund`` with ``matched_deposit_tx``;
   a configured funding/operator address -> ``withdrawal``; otherwise
   ``unidentified``. INSERT OR IGNORE on the PRIMARY KEY mirrors the planned
   dedupe;
4. cross-check the ledger-derived terms (the design's GROUP BY query) against
   ``bridge_outbound_collect.classify`` run on the same tx list — a
   disagreement is itself a finding;
5. run ``bridge_outbound_collect.py`` -> ``--onchain`` JSON ->
   ``bridge_wallet_reconcile.py`` and print the verdict.

With no fixture flags a built-in demo set is used whose verdict is BALANCED.
Exit code 0 iff reconcile reports BALANCED and ledger terms match collector
terms with no unidentified or ungassed rows.

Guardrails: the scratch database path must live outside the data/service
directories, must not already exist unless ``--replace`` is given, and the
scratch dir is deleted afterwards unless ``--keep``. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLLECTOR = HERE / "bridge_outbound_collect.py"
RECONCILE = HERE / "bridge_wallet_reconcile.py"

# Guard: the throwaway db must never land where real ledgers live.
_FORBIDDEN_SCRATCH_PREFIXES = ("/var/lib", "/etc", "/usr", "/opt/aitbc/data", "/data")

WEI_PER_ETH = 10**18
GAS_USED = 21000
GAS_PRICE_WEI = 2_000_000_000  # 2 gwei

# Same column set the monitor bootstraps (storage.py init) — the migration's
# precondition is an existing ledger, not an empty file.
ETH_DEPOSITS_DDL = """
CREATE TABLE IF NOT EXISTS eth_deposits (
    id TEXT PRIMARY KEY,
    tx_hash TEXT UNIQUE NOT NULL,
    from_address TEXT NOT NULL,
    recipient TEXT,
    amount_eth NUMERIC NOT NULL,
    amount_ait NUMERIC NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    ait_tx_hash TEXT,
    eth_usd_price TEXT,
    ait_usd_price TEXT,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    next_retry_at TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    verified_at TIMESTAMP,
    completed_at TIMESTAMP,
    signed_tx TEXT,
    envelope_hash TEXT,
    submitted_height INTEGER,
    rebroadcast_count INTEGER NOT NULL DEFAULT 0
)
"""

# Verbatim from the B13 design (TOPOLOGY/2026-10-08, section 2). The live
# migration adds this one CREATE TABLE statement to storage.py's bootstrap.
BRIDGE_OUTBOUND_DDL = """
CREATE TABLE IF NOT EXISTS bridge_outbound (
    tx_hash       TEXT PRIMARY KEY,
    to_address    TEXT NOT NULL,
    value_eth     NUMERIC NOT NULL,
    gas_wei       INTEGER,
    block_height  INTEGER NOT NULL,
    kind          TEXT NOT NULL,
    matched_deposit_tx TEXT,
    note          TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

BRIDGE_OUTBOUND_COLUMNS = {
    "tx_hash",
    "to_address",
    "value_eth",
    "gas_wei",
    "block_height",
    "kind",
    "matched_deposit_tx",
    "note",
    "created_at",
}


def demo_fixtures() -> dict:
    """A self-contained fixture set whose reconcile verdict is BALANCED.

    Deposits 1.0 + 0.5 ETH from two depositors; outbound = a 0.25 ETH refund
    to the first depositor + a 0.1 ETH withdrawal to the funding account,
    each burning 21000 gas @ 2 gwei. Wallet balance is inflow - outbound -
    gas, computed below (the "chain truth" the fixtures simulate).
    """
    depositor = "0x1111111111111111111111111111111111111111"
    depositor_b = "0x3333333333333333333333333333333333333333"
    funding = "0x2222222222222222222222222222222222222222"
    deposits = [
        {"id": "d1", "tx_hash": "0xdep1", "from_address": depositor, "amount_eth": "1.0", "status": "completed"},
        {"id": "d2", "tx_hash": "0xdep2", "from_address": depositor_b, "amount_eth": "0.5", "status": "completed"},
    ]
    gas = GAS_USED * GAS_PRICE_WEI
    txs = [
        {
            "tx_hash": "0xout1",
            "to": depositor,
            "value_wei": str(25 * 10**16),
            "gas_used": GAS_USED,
            "gas_price_wei": str(GAS_PRICE_WEI),
            "status": 1,
            "block_height": 100,
        },
        {
            "tx_hash": "0xout2",
            "to": funding,
            "value_wei": str(10 * 10**16),
            "gas_used": GAS_USED,
            "gas_price_wei": str(GAS_PRICE_WEI),
            "status": 1,
            "block_height": 101,
        },
    ]
    inflow = sum(int(Decimal(d["amount_eth"]) * WEI_PER_ETH) for d in deposits)
    balance = inflow - sum(int(t["value_wei"]) for t in txs) - 2 * gas
    return {"deposits": deposits, "txs": txs, "funding": [funding], "balance_wei": balance}


def build_db(db_path: Path, deposits: list[dict], outbound_txs: list[dict], funding: set[str]) -> dict[str, int]:
    """Create the throwaway ledger, apply the B13 DDL, insert fixture rows."""
    con = sqlite3.connect(db_path)
    try:
        con.execute(ETH_DEPOSITS_DDL)
        for i, d in enumerate(deposits):
            con.execute(
                "INSERT INTO eth_deposits (id, tx_hash, from_address, amount_eth, amount_ait, status)"
                " VALUES (?, ?, ?, ?, '0', ?)",
                (d.get("id", f"d{i}"), d["tx_hash"], d["from_address"], d["amount_eth"], d.get("status", "completed")),
            )
        # --- the migration under test -------------------------------------
        con.execute(BRIDGE_OUTBOUND_DDL)
        cols = {r[1] for r in con.execute("PRAGMA table_info(bridge_outbound)")}
        if not BRIDGE_OUTBOUND_COLUMNS <= cols:
            raise SystemExit(f"bridge_outbound schema mismatch after migration: {sorted(cols)}")
        # ------------------------------------------------------------------
        depositors = {str(d["from_address"]).lower(): str(d["tx_hash"]) for d in deposits}
        counts = {"refund": 0, "withdrawal": 0, "unidentified": 0}
        for tx in outbound_txs:
            to = str(tx["to"]).lower()
            if to in depositors:
                kind, matched = "refund", depositors[to]
            elif to in funding:
                kind, matched = "withdrawal", None
            else:
                kind, matched = "unidentified", None
            counts[kind] += 1
            gas = (
                int(tx["gas_used"]) * int(tx["gas_price_wei"])
                if tx.get("gas_used") is not None and tx.get("gas_price_wei") is not None
                else None
            )
            con.execute(
                "INSERT OR IGNORE INTO bridge_outbound"
                " (tx_hash, to_address, value_eth, gas_wei, block_height, kind, matched_deposit_tx)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    tx["tx_hash"],
                    to,
                    str(Decimal(int(tx.get("value_wei", 0))) / WEI_PER_ETH),
                    gas,
                    int(tx.get("block_height", 0)),
                    kind,
                    matched,
                ),
            )
        con.commit()
    finally:
        con.close()
    return counts


def ledger_terms(db_path: Path) -> dict[str, int | None]:
    """The design's section-5 query: outbound terms derived from the new table."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT kind, COUNT(*), SUM(CAST(value_eth AS REAL)), SUM(gas_wei) FROM bridge_outbound GROUP BY kind"
        ).fetchall()
        ungassed = con.execute("SELECT COUNT(*) FROM bridge_outbound WHERE gas_wei IS NULL").fetchone()[0]
    finally:
        con.close()
    terms = {"refund": 0, "withdrawal": 0, "unidentified": 0}
    gas_total = 0
    for kind, _count, value_eth, gas_wei in rows:
        terms[kind] = int(Decimal(str(value_eth)) * WEI_PER_ETH) if value_eth else 0
        gas_total += int(gas_wei or 0)
    return {
        "refunds_wei": terms["refund"],
        "withdrawals_wei": terms["withdrawal"],
        "unidentified_wei": terms["unidentified"],
        "gas_wei": gas_total,
        "ungassed_rows": int(ungassed),
    }


def _check_scratch_dir(scratch: Path, replace: bool) -> None:
    real = scratch.resolve()
    if any(str(real).startswith(p) for p in _FORBIDDEN_SCRATCH_PREFIXES):
        raise SystemExit(f"refusing scratch dir under {real}: must not touch live/service paths")
    if scratch.exists():
        if replace:
            shutil.rmtree(scratch)
        else:
            raise SystemExit(f"scratch dir {scratch} already exists (use --replace or a fresh path)")


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scratch-dir", type=Path, help="throwaway dir (default: mktemp under TMPDIR)")
    parser.add_argument("--deposits-json", type=Path, help="fixture deposits [{tx_hash, from_address, amount_eth, status}]")
    parser.add_argument("--txs", type=Path, help="fixture outbound txs (collector --txs shape)")
    parser.add_argument("--funding-json", type=Path, help="fixture funding-source addresses")
    parser.add_argument("--balance-wei", type=int, help="simulated wallet balance (default: derived from fixtures)")
    parser.add_argument("--replace", action="store_true", help="delete an existing scratch dir first")
    parser.add_argument("--keep", action="store_true", help="keep the scratch dir after the run")
    parser.add_argument("--json", action="store_true", help="machine-readable summary on stdout last line")
    args = parser.parse_args(argv)

    own_tmp = args.scratch_dir is None
    scratch = Path(tempfile.mkdtemp(prefix="br7-dryrun-")) if own_tmp else args.scratch_dir
    if not own_tmp:
        _check_scratch_dir(scratch, args.replace)
    scratch.mkdir(parents=True, exist_ok=True)
    db_path = scratch / "bridge-monitor.db"
    onchain_path = scratch / "outbound.json"

    try:
        fx = demo_fixtures()
        deposits = json.loads(args.deposits_json.read_text()) if args.deposits_json else fx["deposits"]
        txs = json.loads(args.txs.read_text()) if args.txs else fx["txs"]
        funding = (
            {a.lower() for a in json.loads(args.funding_json.read_text())}
            if args.funding_json
            else {a.lower() for a in fx["funding"]}
        )
        if not args.txs:
            txs_path = scratch / "txs.json"
            txs_path.write_text(json.dumps(txs), encoding="utf-8")
        else:
            txs_path = args.txs
        funding_path = scratch / "funding.json"
        funding_path.write_text(json.dumps(sorted(funding)), encoding="utf-8")

        if args.balance_wei is not None:
            balance_wei = args.balance_wei
        else:
            inflow = sum(int(Decimal(str(d["amount_eth"])) * WEI_PER_ETH) for d in deposits)
            gas = sum(
                int(t["gas_used"]) * int(t["gas_price_wei"])
                for t in txs
                if t.get("gas_used") is not None and t.get("gas_price_wei") is not None
            )
            balance_wei = inflow - sum(int(t.get("value_wei", 0)) for t in txs) - gas

        print("BR-7 — B13 bridge_outbound migration dry run (throwaway db)")
        print("=" * 60)
        print(f"scratch:  {scratch}")
        print(f"ledger:   {db_path} ({len(deposits)} fixture deposits)")
        counts = build_db(db_path, deposits, txs, funding)
        print(f"migrated: bridge_outbound created, {sum(counts.values())} rows {counts}")

        terms = ledger_terms(db_path)
        print(f"ledger terms (design §5 query): {terms}")

        collect = _run(
            [
                sys.executable,
                str(COLLECTOR),
                "--txs",
                str(txs_path),
                "--ledger",
                str(db_path),
                "--funding-json",
                str(funding_path),
                "--balance-wei",
                str(balance_wei),
                "--out",
                str(onchain_path),
            ]
        )
        if collect.returncode != 0:
            print(collect.stderr, file=sys.stderr)
            raise SystemExit(f"collector failed rc={collect.returncode}")
        onchain = json.loads(onchain_path.read_text(encoding="utf-8"))
        collector_terms = {k: int(v) for k, v in onchain["outbound"].items()}
        # The collector folds funding-source sends into refunds_wei while the
        # ledger keeps them as ``withdrawal`` — same outbound total, different
        # bucket. Reconcile only uses the total, so the cross-check compares
        # totals; a bucket-level difference is reported as a note.
        if (
            collector_terms["refunds_wei"] != terms["refunds_wei"]
            or collector_terms["withdrawals_wei"] != terms["withdrawals_wei"]
        ):
            print(
                "NOTE: bucket split differs (collector refunds="
                f"{collector_terms['refunds_wei']} + withdrawals={collector_terms['withdrawals_wei']} vs ledger "
                f"refund={terms['refunds_wei']} + withdrawal={terms['withdrawals_wei']}) — funding-source sends are "
                "refunds to the collector, withdrawals to the ledger; totals are what reconcile uses"
            )
        terms_match = (
            collector_terms["gas_wei"] == terms["gas_wei"]
            and collector_terms["unidentified_wei"] == terms["unidentified_wei"]
            and sum(v for k, v in collector_terms.items() if k != "gas_wei")
            == terms["refunds_wei"] + terms["withdrawals_wei"] + terms["unidentified_wei"]
        )
        if not terms_match:
            print(f"FINDING: ledger totals != collector terms {collector_terms}")

        rec = _run([sys.executable, str(RECONCILE), "--ledger", str(db_path), "--onchain", str(onchain_path)])
        print()
        print(rec.stdout)
        if rec.returncode not in (0, 1):
            print(rec.stderr, file=sys.stderr)
            raise SystemExit(f"reconcile crashed rc={rec.returncode}")
        balanced = "VERDICT: BALANCED" in rec.stdout

        summary = {
            "scratch": str(scratch),
            "rows": counts,
            "ledger_terms": terms,
            "collector_terms": collector_terms,
            "terms_match": terms_match,
            "verdict": "BALANCED" if balanced else "not balanced",
        }
        if args.json:
            print(json.dumps(summary))
        ok = balanced and terms_match and terms["unidentified_wei"] == 0 and terms["ungassed_rows"] == 0
        print(f"DRY-RUN VERDICT: {'OK' if ok else 'ATTENTION NEEDED'}")
        return 0 if ok else 1
    finally:
        if not args.keep:
            shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
