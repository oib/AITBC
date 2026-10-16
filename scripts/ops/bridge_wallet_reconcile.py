#!/usr/bin/env python3
"""Reconcile the bridge payout wallet's ETH balance against the monitor ledger.

Read-only ledger pass of BR-6: ``eth_deposits`` rows are the only recorded
inflows -- every row is a verified ETH transfer into the wallet, ``funding``
rows are operator top-ups that are owed no payout. The ledger has **no rows
for outbound ETH** (refunds, withdrawals, gas): those figures must be
supplied from chain data via ``--onchain``.

    python scripts/ops/bridge_wallet_reconcile.py \
        --ledger /var/lib/aitbc/bridge-monitor.db \
        --onchain outbound.json

``outbound.json`` is operator-produced (no RPC calls happen here):

    {
      "wallet_balance_wei": "1000000000000000000",
      "outbound": {
        "refunds_wei": "0",
        "withdrawals_wei": "0",
        "gas_wei": "0",
        "unidentified_wei": "0"
      }
    }

Verdict: ``BALANCED`` when wallet == inflows - outbound (within --dust-wei);
otherwise ``SURPLUS``/``DEFICIT`` with the amount in wei and ETH. A BALANCED
verdict is consistency with the *supplied* figures, not proof of correctness:
unledgered inbound sends and misclassified outbound legs are not visible here.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

WEI_PER_ETH = Decimal(10) ** 18

_SELECT = "SELECT status, amount_eth FROM eth_deposits"


def _wei(value: object, field: str) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"invalid {field} in --onchain JSON: {value!r}") from exc


def load_inflows(ledger: Path) -> dict[str, tuple[int, Decimal]]:
    """status -> (row count, summed amount_eth). Every row is ETH that arrived."""
    con = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    try:
        rows = con.execute(_SELECT).fetchall()
    finally:
        con.close()
    out: dict[str, list] = {}
    for status, amount in rows:
        bucket = out.setdefault(str(status), [0, Decimal(0)])
        bucket[0] += 1
        try:
            bucket[1] += Decimal(str(amount))
        except InvalidOperation as exc:
            raise SystemExit(f"unparseable amount_eth {amount!r} on status {status!r}") from exc
    return {k: (v[0], v[1]) for k, v in out.items()}


def load_outbound(ledger: Path) -> dict[str, int] | None:
    """Ledger-derived outbound terms from bridge_outbound (B13), or None when
    the table does not exist (pre-migration DB) — caller then stays on the
    operator-supplied --onchain outbound section."""
    con = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    try:
        exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bridge_outbound'").fetchone()
        if not exists:
            return None
        rows = con.execute(
            "SELECT kind, SUM(CAST(value_eth AS REAL)), SUM(gas_wei) FROM bridge_outbound GROUP BY kind"
        ).fetchall()
    finally:
        con.close()
    terms = {"refund": 0, "withdrawal": 0, "unidentified": 0, "gas": 0}
    for kind, value_eth, gas_wei in rows:
        kind = str(kind)
        # self_send rows return their value to the same wallet — only gas
        # counts as outbound. Unknown kinds still count.
        if kind != "self_send":
            terms[kind] = terms.get(kind, 0) + int(Decimal(str(value_eth or 0)) * WEI_PER_ETH)
        terms["gas"] += int(gas_wei or 0)
    return terms


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ledger", required=True, type=Path, help="bridge-monitor sqlite (opened read-only)")
    parser.add_argument("--onchain", required=True, type=Path, help="operator JSON: wallet balance + outbound wei")
    parser.add_argument("--dust-wei", type=int, default=0, help="residual tolerance in wei (default 0)")
    args = parser.parse_args(argv)

    onchain = json.loads(args.onchain.read_text(encoding="utf-8"))
    balance_wei = _wei(onchain.get("wallet_balance_wei"), "wallet_balance_wei")

    inflows = load_inflows(args.ledger)
    ledger_terms = load_outbound(args.ledger)

    outbound_source = "--onchain (operator-supplied)"
    if ledger_terms is None:
        outbound = onchain.get("outbound") or {}
        terms = {
            "refunds": _wei(outbound.get("refunds_wei", 0), "outbound.refunds_wei"),
            "withdrawals": _wei(outbound.get("withdrawals_wei", 0), "outbound.withdrawals_wei"),
            "gas": _wei(outbound.get("gas_wei", 0), "outbound.gas_wei"),
            "unidentified": _wei(outbound.get("unidentified_wei", 0), "outbound.unidentified_wei"),
        }
    else:
        outbound_source = "bridge_outbound ledger rows"
        terms = {
            "refunds": ledger_terms.get("refund", 0),
            "withdrawals": ledger_terms.get("withdrawal", 0),
            "gas": ledger_terms.get("gas", 0),
            "unidentified": ledger_terms.get("unidentified", 0),
        }

    print("BRIDGE WALLET RECONCILIATION (BR-6 ledger pass)")
    print("=" * 60)
    if ledger_terms is None:
        print("NOTE: eth_deposits records inflows only. Refunds, gas and")
        print("withdrawals have no ledger rows -- outbound figures come from")
        print("--onchain (operator-supplied chain data). BALANCED means the")
        print("supplied figures are consistent, not proof of correctness.")
    else:
        print("Outbound terms read from the bridge_outbound ledger table (B13);")
        print("--onchain supplies wallet_balance_wei only. BALANCED means the")
        print("ledger explains the wallet, not that classification is correct:")
        print("any unidentified outbound still needs operator review.")
    print(f"outbound source: {outbound_source}")
    print()
    print(f"{'ledger status':<16}{'rows':>6}{'ETH':>20}")
    print("-" * 42)
    total_eth = Decimal(0)
    for status in sorted(inflows):
        count, amount = inflows[status]
        total_eth += amount
        print(f"{status:<16}{count:>6}{amount:>20f}")
    print("-" * 42)
    print(f"{'inflow total':<16}{sum(c for c, _ in inflows.values()):>6}{total_eth:>20f}")
    print()

    inflow_wei = int((total_eth * WEI_PER_ETH).to_integral_value())
    outbound_wei = sum(terms.values())
    expected_wei = inflow_wei - outbound_wei

    print(f"outbound ({outbound_source}, wei):")
    for name, wei in terms.items():
        print(f"  {name:<14}{wei:>22}")
    print()
    print(f"ledger inflows   {inflow_wei:>24} wei  ({inflow_wei / WEI_PER_ETH} ETH)")
    print(f"outbound total   {outbound_wei:>24} wei")
    print(f"expected balance {expected_wei:>24} wei  ({expected_wei / WEI_PER_ETH} ETH)")
    print(f"actual balance   {balance_wei:>24} wei  ({Decimal(balance_wei) / WEI_PER_ETH} ETH)")

    diff = balance_wei - expected_wei
    print()
    if abs(diff) <= args.dust_wei:
        print("VERDICT: BALANCED")
        return 0
    direction = "SURPLUS" if diff > 0 else "DEFICIT"
    detail = (
        "wallet holds more than ledger+outbound explain (unledgered inbound, or outbound over-reported)"
        if diff > 0
        else "wallet is short vs ledger+outbound "
        "(refund/withdrawal/gas missing from --onchain, or an outbound leg the ledger cannot see)"
    )
    print(f"VERDICT: {direction} of {abs(diff)} wei ({abs(Decimal(diff)) / WEI_PER_ETH} ETH)")
    print(detail)
    return 1


if __name__ == "__main__":
    sys.exit(main())
