#!/usr/bin/env python3
"""Collect outbound ETH figures for bridge-wallet reconciliation (BR-6/B13).

Spec for how the operator supplies the outbound terms that
``bridge_wallet_reconcile.py --onchain`` consumes. This script is
**read-only and offline**: it does not call an Ethereum RPC and does not
touch the live monitor DB -- it classifies an operator-supplied JSON dump
of transactions sent *from* the bridge payout wallet and emits the
``--onchain`` document.

Input (``--txs``): a JSON list of outbound transactions, each:

    {
      "tx_hash": "0x…",            # required
      "to": "0x…",                 # required, recipient
      "value_wei": "123",          # required, decimal string or int
      "gas_used": 21000,           # optional, for the gas term
      "gas_price_wei": "2000000000",
      "status": 1                  # optional; failed txs count gas only
    }

The operator produces the dump from a block explorer or their own RPC
node; this script never reaches the network.

Matching (``--ledger``, optional, opened mode=ro): the monitor's
``eth_deposits.from_address`` set identifies refund recipients -- an
outbound send to a recorded depositor is a refund. ``--funding-json``
(names a JSON list of funding-source addresses, the BRIDGE_FUNDING_SOURCES
set) marks float top-up returns as ``funding``. Everything else is
``unidentified`` -- the reconcile script treats an unidentified leg as a
reason the verdict cannot be trusted.

Output: the ``--onchain`` JSON for bridge_wallet_reconcile.py:

    {
      "wallet_balance_wei": "<from --balance-wei>",
      "outbound": {
        "refunds_wei": "…",
        "withdrawals_wei": "0",
        "gas_wei": "…",
        "unidentified_wei": "…"
      }
    }

``withdrawals_wei`` is always 0 here: no ledger field identifies a
withdrawal, so a send that is neither a refund nor a funding return is
unidentified until the B13 outbound ledger exists.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def _wei(value: object, field: str) -> int:
    try:
        wei = int(str(value))
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"unparseable wei value {value!r} in {field}") from exc
    if wei < 0:
        raise SystemExit(f"negative wei value {value!r} in {field}")
    return wei


def _load_depositors(ledger: Path | None) -> set[str]:
    """from_address values of recorded deposits — the refund-recipient set."""
    if ledger is None:
        return set()
    con = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT DISTINCT from_address FROM eth_deposits WHERE from_address IS NOT NULL").fetchall()
    finally:
        con.close()
    return {str(r[0]).lower() for r in rows}


def classify(txs: list[dict], depositors: set[str], funding: set[str]) -> dict[str, int]:
    terms = {"refunds_wei": 0, "withdrawals_wei": 0, "gas_wei": 0, "unidentified_wei": 0}
    for i, tx in enumerate(txs):
        if not isinstance(tx, dict) or not tx.get("tx_hash") or not tx.get("to"):
            raise SystemExit(f"txs[{i}]: missing tx_hash or to")
        value = _wei(tx.get("value_wei", 0), f"txs[{i}].value_wei")
        gas_used = tx.get("gas_used")
        gas_price = tx.get("gas_price_wei")
        if gas_used is not None and gas_price is not None:
            terms["gas_wei"] += _wei(gas_used, f"txs[{i}].gas_used") * _wei(gas_price, f"txs[{i}].gas_price_wei")
        failed = tx.get("status") in (0, "0", "failed")
        if failed or value == 0:
            continue  # a failed send moves no value; the gas already counted
        to = str(tx["to"]).lower()
        if to in depositors:
            terms["refunds_wei"] += value
        elif to in funding:
            terms["refunds_wei"] += value  # funding-source returns behave like refunds
        else:
            terms["unidentified_wei"] += value
    return terms


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--txs", required=True, type=Path, help="JSON list of outbound txs (operator-supplied)")
    parser.add_argument("--ledger", type=Path, help="bridge-monitor sqlite for depositor matching (mode=ro)")
    parser.add_argument("--funding-json", type=Path, help="JSON list of funding-source addresses")
    parser.add_argument("--balance-wei", required=True, help="wallet's real ETH balance in wei")
    parser.add_argument("--out", type=Path, help="write the --onchain JSON here (default stdout)")
    args = parser.parse_args(argv)

    txs = json.loads(args.txs.read_text(encoding="utf-8"))
    if not isinstance(txs, list):
        raise SystemExit("--txs must be a JSON list")
    funding = {a.lower() for a in json.loads(args.funding_json.read_text())} if args.funding_json else set()
    depositors = _load_depositors(args.ledger)

    terms = classify(txs, depositors, funding)
    out = {
        "wallet_balance_wei": str(_wei(args.balance_wei, "--balance-wei")),
        "outbound": {k: str(v) for k, v in terms.items()},
    }
    doc = json.dumps(out, indent=2)
    if args.out:
        args.out.write_text(doc + "\n", encoding="utf-8")
    else:
        print(doc)
    if terms["unidentified_wei"]:
        print(
            f"NOTE: {terms['unidentified_wei']} wei of outbound value is UNIDENTIFIED — "
            "the reconcile verdict cannot be read as proof until the outbound ledger (B13) exists.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
