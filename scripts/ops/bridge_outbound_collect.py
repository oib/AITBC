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
outbound send to a recorded depositor is a refund -- and
the release-leg tables' ``eth_tx_hash`` columns identify release legs --
an outbound tx whose hash the withdrawal, sell-lock or settlement ledger
recorded is a withdrawal.
``--funding-json`` (names a JSON list of funding-source addresses, the
BRIDGE_FUNDING_SOURCES set) marks float top-up returns as ``funding``.
Everything else is ``unidentified`` -- the reconcile script treats an
unidentified leg as a reason the verdict cannot be trusted.

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

``withdrawals_wei`` sums outbound txs whose hash appears in the ledger's
``eth_withdrawals.eth_tx_hash`` column (B13 release leg). Without
``--ledger`` no release can be identified and every unmatched send is
``unidentified``. Release-leg tables checked (same as the live monitor):
``eth_withdrawals``, ``bridge_sell_locks``, ``exchange_settlements``.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path

WEI_PER_ETH = Decimal(10) ** 18


def _wei(value: object, field: str) -> int:
    try:
        wei = int(str(value))
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"unparseable wei value {value!r} in {field}") from exc
    if wei < 0:
        raise SystemExit(f"negative wei value {value!r} in {field}")
    return wei


def _load_depositor_map(ledger: Path | None) -> dict[str, str]:
    """from_address -> tx_hash for recorded deposits — the refund-recipient
    set plus the deposit tx used as `matched_deposit_tx` evidence."""
    if ledger is None:
        return {}
    con = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(eth_deposits)")}
        tx_expr = "tx_hash" if "tx_hash" in cols else "NULL"
        rows = con.execute(f"SELECT from_address, {tx_expr} FROM eth_deposits WHERE from_address IS NOT NULL").fetchall()  # nosec
    finally:
        con.close()
    return {str(a).lower(): str(t) for a, t in rows}


def _load_depositors(ledger: Path | None) -> set[str]:
    """from_address values of recorded deposits — the refund-recipient set."""
    return set(_load_depositor_map(ledger))


# Keep in sync with bridge_monitor.storage._RELEASE_SOURCES — this script
# is standalone (run from repo root on operator-held exports), so it mirrors
# the tuple rather than importing the app package.
_RELEASE_SOURCES = (
    ("eth_withdrawals", ""),
    ("bridge_sell_locks", "bridge_sell_locks release"),
    ("exchange_settlements", "exchange_settlements release"),
)


def _load_release_sources(ledger: Path | None) -> dict[str, str]:
    """Lowercased eth_tx_hash -> source label across every release-leg
    table. Missing tables count as no rows, never an error (ledgers of
    varying age are valid input)."""
    if ledger is None:
        return {}
    con = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    out: dict[str, str] = {}
    try:
        for table, label in _RELEASE_SOURCES:
            try:
                # table is a fixed literal from _RELEASE_SOURCES above
                rows = con.execute(f"SELECT eth_tx_hash FROM {table} WHERE eth_tx_hash IS NOT NULL").fetchall()  # nosec
            except sqlite3.OperationalError:
                continue
            for (h,) in rows:
                out.setdefault(str(h).lower(), label)
    finally:
        con.close()
    return out


def classify(
    txs: list[dict], depositors: set[str], funding: set[str], releases: dict[str, str] | None = None
) -> dict[str, int]:
    releases = releases or {}
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
        if str(tx["tx_hash"]).lower() in releases:
            terms["withdrawals_wei"] += value  # hash-joined release leg: strongest evidence
        elif to in depositors:
            terms["refunds_wei"] += value
        elif to in funding:
            terms["refunds_wei"] += value  # funding-source returns behave like refunds
        else:
            terms["unidentified_wei"] += value
    return terms


def emit_rows(
    txs: list[dict],
    depositor_map: dict[str, str],
    funding: set[str],
    releases: dict[str, str] | None = None,
    self_address: str | None = None,
) -> list[dict]:
    """Per-tx bridge_outbound rows — same classification order as the live
    writer in bridge_monitor.main._record_outbound (release hash, self-send,
    depositor, funding, unidentified), so a backfilled table matches what the
    monitor itself would have written."""
    releases = releases or {}
    self_addr = (self_address or "").lower()
    rows: list[dict] = []
    for i, tx in enumerate(txs):
        if not isinstance(tx, dict) or not tx.get("tx_hash") or not tx.get("to"):
            raise SystemExit(f"txs[{i}]: missing tx_hash or to")
        value = _wei(tx.get("value_wei", 0), f"txs[{i}].value_wei")
        gas_used = tx.get("gas_used")
        gas_price = tx.get("gas_price_wei")
        gas_wei = (
            _wei(gas_used, f"txs[{i}].gas_used") * _wei(gas_price, f"txs[{i}].gas_price_wei")
            if gas_used is not None and gas_price is not None
            else None
        )
        failed = tx.get("status") in (0, "0", "failed")
        to = str(tx["to"]).lower()
        tx_hash = str(tx["tx_hash"])
        note: str | None = None
        matched: str | None = None
        if tx_hash.lower() in releases:
            kind = "withdrawal"
            note = releases[tx_hash.lower()] or None
        elif to == self_addr and self_addr:
            kind = "self_send"
        elif to in depositor_map:
            kind, matched = "refund", depositor_map[to]
        elif to in funding:
            kind, note = "withdrawal", "float return to funding source"
        else:
            kind = "unidentified"
        if failed:
            note = (note + "; " if note else "") + f"tx failed — gas burned, intended {value} wei not moved"
            value = 0  # a reverted send moves no value; only its gas is outbound
        block_height = tx.get("block_height")
        if block_height is None:
            raise SystemExit(f"txs[{i}]: missing block_height — bridge_outbound.block_height is NOT NULL")
        rows.append(
            {
                "tx_hash": tx_hash,
                "to_address": to,
                "value_eth": str(Decimal(value) / WEI_PER_ETH),
                "gas_wei": gas_wei,
                "block_height": _wei(block_height, f"txs[{i}].block_height"),
                "kind": kind,
                "matched_deposit_tx": matched,
                "note": note,
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--txs", required=True, type=Path, help="JSON list of outbound txs (operator-supplied)")
    parser.add_argument("--ledger", type=Path, help="bridge-monitor sqlite for depositor matching (mode=ro)")
    parser.add_argument("--funding-json", type=Path, help="JSON list of funding-source addresses")
    parser.add_argument("--balance-wei", required=True, help="wallet's real ETH balance in wei")
    parser.add_argument("--out", type=Path, help="write the --onchain JSON here (default stdout)")
    parser.add_argument(
        "--emit-rows",
        type=Path,
        help="BR-6 backfill: also write classified bridge_outbound row dicts "
        "(tx_hash, to_address, value_eth, gas_wei, block_height, kind, "
        "matched_deposit_tx, note) to this JSON file — feed to "
        "record_outbound or inspect before a live INSERT",
    )
    parser.add_argument(
        "--self-address",
        help="bridge wallet address; outbound sends back to it classify as self_send (value returns — gas only)",
    )
    args = parser.parse_args(argv)

    txs = json.loads(args.txs.read_text(encoding="utf-8"))
    if not isinstance(txs, list):
        raise SystemExit("--txs must be a JSON list")
    funding = {a.lower() for a in json.loads(args.funding_json.read_text())} if args.funding_json else set()
    depositors = _load_depositors(args.ledger)
    releases = _load_release_sources(args.ledger)

    terms = classify(txs, depositors, funding, releases)
    if args.emit_rows:
        args.emit_rows.write_text(
            json.dumps(emit_rows(txs, _load_depositor_map(args.ledger), funding, releases, args.self_address), indent=2)
            + "\n",
            encoding="utf-8",
        )
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
            "matched to no release, depositor or funding source; the verdict cannot be read as proof.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
