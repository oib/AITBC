#!/usr/bin/env python3
"""Read-only exchange-book verifier (ETH-19 phase 3, C7).

    venv/bin/python scripts/ops/exchange_verify.py --db /path/exchange.db
    venv/bin/python scripts/ops/exchange_verify.py --db /path/exchange.db \
        --bridge-db /var/lib/aitbc/bridge_deposits.db \
        --bridge-address 0xBridgeWallet... \
        --ait-rpc http://127.0.0.1:8202 --escrow-address 0xEscrow...
    venv/bin/python scripts/ops/exchange_verify.py --db ... --no-chain --json

Re-derives the exchange DB's funding and settlement claims against the
chains before the book reopens after a crash/restore (design §11). Check
groups, each reported with counts and per-row detail:

- DB-internal  (always): funded-state/backing/debit/trade consistency,
  nonce uniqueness, registry completeness.
- bridge-db    (--bridge-db): every 'exchange_prepay' deposit row is
  either credited (a prepaid_deposits row holds its tx_hash) or carries a
  deliberate monitor-mark outcome; a bare exchange_prepay row is WARN.
- eth-chain    (unless --no-chain): prepaid_deposits.eth_tx_hash and
  trades.settlement_eth_tx_hash are sealed, successful, carry the
  expected value/tag/recipient on Sepolia.
- ait-chain    (--ait-rpc + --escrow-address): funded SELL orders show
  their backing_tx_hash as an escrow transfer with payload.sell_quote =
  order id from the order's owner; settled trades show both sweep legs.

Guarantees: stdlib only, sqlite opened read-only (``mode=ro``), no
writes, no keys, no environment reads — all endpoints/addresses come
from flags. Exit status is 1 if any check FAILs; WARN and INFO never
fail the run. Rows whose chain leg is merely unsealed are WARN, not
FAIL — a lagging RPC is not evidence of loss.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from typing import Any

DEFAULT_ETH_RPC = "https://ethereum-sepolia-rpc.publicnode.com"
WEI_PER_ETH = Decimal(10) ** 18
UNITS_PER_AIT = Decimal(36_000_000)  # chain units per AIT
TICKS_PER_UNIT = Decimal(100_000_000)  # exchange ticks per AIT
_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")

INFO, WARN, FAIL = "INFO", "WARN", "FAIL"


class RpcError(RuntimeError):
    pass


def _post_rpc(rpc_url: str, method: str, params: list, timeout: float = 15.0) -> Any:
    if not rpc_url.startswith(("http://", "https://")):
        raise RpcError(f"RPC endpoint must be http(s): {rpc_url!r}")
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
    req = urllib.request.Request(rpc_url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 -- scheme enforced above
            payload = json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        raise RpcError(f"RPC request failed: {exc}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RpcError(f"RPC returned a non-JSON reply: {exc}") from exc
    if "error" in payload:
        raise RpcError(f"RPC error: {payload['error']}")
    return payload.get("result")


def _ait_transfers(ait_rpc: str, address: str, timeout: float = 15.0) -> dict[str, dict[str, Any]]:
    """TRANSFER history for ``address`` keyed by tx hash (newest-first API,
    flattened here). The endpoint has no cursor; limit=0 returns all."""
    url = f"{ait_rpc.rstrip('/')}/rpc/transactions?transaction_type=TRANSFER&address={address}&limit=0"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # nosec B310 -- operator-supplied read URL
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RpcError(f"AIT transfers fetch failed: {exc}") from exc
    txs = data.get("transactions", data) if isinstance(data, dict) else data
    out = {}
    for tx in txs if isinstance(txs, list) else []:
        h = tx.get("tx_hash") or tx.get("hash")
        if h:
            out[str(h)] = tx
    return out


def _db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _dec(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def check_db_internal(conn: sqlite3.Connection, add) -> None:
    try:
        orders = {
            r["id"]: r
            for r in conn.execute(
                "SELECT id, order_type, status, funded_state, backing_tx_hash, locked_ticks, "
                "user_address, account_nonce, filled_ticks, seller_eth_address FROM orders"
            )
        }
    except sqlite3.OperationalError as e:
        add(FAIL, "db", f"phase-3 columns absent — is this a pre-settlement exchange DB? ({e})")
        return
    debits = (
        {
            r["order_id"]: r
            for r in conn.execute("SELECT order_id, node_address, amount_eth, committed_eth, state FROM prepaid_debits")
        }
        if _has_table(conn, "prepaid_debits")
        else {}
    )
    trades = conn.execute(
        "SELECT id, amount, total, buyer_address, seller_address, buy_order_id, sell_order_id, "
        "settlement_state, settlement_eth_tx_hash, settlement_ait_tx_hash FROM trades"
    ).fetchall()

    for order in orders.values():
        funded = order["funded_state"] == "funded"
        if order["order_type"] == "BUY" and funded and order["id"] not in debits:
            add(FAIL, "db", f"order {order['id']}: funded BUY without a prepaid_debits row")
        if order["order_type"] == "SELL" and funded and not order["backing_tx_hash"]:
            add(FAIL, "db", f"order {order['id']}: funded SELL without backing_tx_hash")
        if not funded and order["backing_tx_hash"]:
            add(FAIL, "db", f"order {order['id']}: {order['funded_state']} but backing_tx_hash set")

    seen_nonce: dict[tuple[str, Any], int] = {}
    for order in orders.values():
        key = (str(order["user_address"]).lower(), order["account_nonce"])
        if order["account_nonce"] is not None:
            if key in seen_nonce:
                add(FAIL, "db", f"orders {seen_nonce[key]} and {order['id']}: duplicate account_nonce")
            seen_nonce[key] = order["id"]

    for order_id, d in debits.items():
        if order_id not in orders:
            add(FAIL, "db", f"prepaid_debit order_id={order_id}: no such order")
            continue
        amt, com = _dec(d["amount_eth"]), _dec(d["committed_eth"])
        if amt is None or com is None or com > amt:
            add(
                FAIL,
                "db",
                f"prepaid_debit order {order_id}: committed_eth={d['committed_eth']} > amount_eth={d['amount_eth']}",
            )
        if d["node_address"].lower() != str(orders[order_id]["user_address"]).lower():
            add(
                FAIL,
                "db",
                f"prepaid_debit order {order_id}: node {d['node_address']} != order owner {orders[order_id]['user_address']}",
            )

    filled_by_order: dict[int, Decimal] = {}
    for t in trades:
        for col in ("buy_order_id", "sell_order_id"):
            oid = t[col]
            if oid is not None and oid not in orders:
                add(FAIL, "db", f"trade {t['id']}: {col}={oid} references a missing order")
        if t["settlement_state"] == "settled" and (not t["settlement_eth_tx_hash"] or not t["settlement_ait_tx_hash"]):
            add(FAIL, "db", f"trade {t['id']}: settled but missing settlement tx hash")
        amt_ticks = _dec(t["amount"])
        if t["sell_order_id"] is not None and amt_ticks is not None:
            filled_by_order[t["sell_order_id"]] = filled_by_order.get(t["sell_order_id"], Decimal(0)) + amt_ticks
        if t["buy_order_id"] is not None and amt_ticks is not None:
            filled_by_order[t["buy_order_id"]] = filled_by_order.get(t["buy_order_id"], Decimal(0)) + amt_ticks
    for order_id, filled_ait in filled_by_order.items():
        recorded = _dec(orders[order_id]["filled_ticks"] or 0)
        if recorded is not None and abs(Decimal(int(recorded)) / TICKS_PER_UNIT - filled_ait) > Decimal("1e-8"):
            add(
                WARN,
                "db",
                f"order {order_id}: recorded filled {Decimal(int(recorded)) / TICKS_PER_UNIT} != Σ trades {filled_ait}",
            )

    if _has_table(conn, "node_registry"):
        for r in conn.execute("SELECT address, status, eth_address FROM node_registry"):
            if r["status"] == "registered" and not r["eth_address"]:
                add(FAIL, "db", f"node_registry {r['address']}: registered without eth_address")
    add(INFO, "db", f"{len(orders)} orders, {len(debits)} debits, {len(trades)} trades checked")


def check_bridge_db(conn: sqlite3.Connection, bridge_db_path: str, add) -> None:
    bconn = _db(bridge_db_path)
    try:
        if not _has_table(bconn, "eth_deposits"):
            add(FAIL, "bridge-db", "bridge_deposits.db has no eth_deposits table")
            return
        credited = (
            {r["eth_tx_hash"] for r in conn.execute("SELECT eth_tx_hash FROM prepaid_deposits")}
            if _has_table(conn, "prepaid_deposits")
            else set()
        )
        marks = {}
        if _has_table(bconn, "exchange_monitor_marks"):
            for m in bconn.execute("SELECT mark, outcome FROM exchange_monitor_marks"):
                if str(m["mark"]).startswith("credit:"):
                    marks[m["mark"][7:]] = m["outcome"]
        rows = bconn.execute(
            "SELECT tx_hash, recipient, amount_eth FROM eth_deposits WHERE status='exchange_prepay'"
        ).fetchall()
        pending = 0
        for r in rows:
            txh = r["tx_hash"]
            if txh in credited:
                continue
            outcome = marks.get(txh)
            if outcome in ("unattributable", "rejected", "malformed_tag"):
                add(INFO, "bridge-db", f"prepay {txh}: monitor outcome {outcome} — operator lane")
            else:
                pending += 1
                add(WARN, "bridge-db", f"prepay {txh}: {r['amount_eth']} ETH not yet credited (outcome={outcome})")
        add(INFO, "bridge-db", f"{len(rows)} exchange_prepay rows: {len(rows) - pending} explained, {pending} pending")
    finally:
        bconn.close()


def _eth_tx(rpc_url: str, tx_hash: str) -> tuple[dict | None, dict | None]:
    tx = _post_rpc(rpc_url, "eth_getTransactionByHash", [tx_hash])
    receipt = _post_rpc(rpc_url, "eth_getTransactionReceipt", [tx_hash])
    return tx, receipt


def _receipt_ok(receipt: dict | None) -> str | None:
    """None when sealed+successful; else the reason string."""
    if receipt is None:
        return "unsealed"
    if receipt.get("status") not in ("0x1", "0x01"):
        return f"reverted (status={receipt.get('status')})"
    return None


def check_eth_chain(conn: sqlite3.Connection, rpc_url: str, bridge_address: str | None, add) -> None:
    deposits = (
        conn.execute("SELECT node_address, amount_eth, eth_tx_hash FROM prepaid_deposits").fetchall()
        if _has_table(conn, "prepaid_deposits")
        else []
    )
    for d in deposits:
        txh = d["eth_tx_hash"]
        try:
            tx, receipt = _eth_tx(rpc_url, txh)
        except RpcError as e:
            add(WARN, "eth", f"deposit {txh}: {e}")
            continue
        if tx is None:
            add(FAIL, "eth", f"deposit {txh}: not on chain")
            continue
        bad = _receipt_ok(receipt)
        if bad:
            add(WARN if bad == "unsealed" else FAIL, "eth", f"deposit {txh}: {bad}")
            continue
        want_eth = _dec(d["amount_eth"])
        value_wei = int(str(tx.get("value") or "0x0"), 16)
        if want_eth is None or Decimal(value_wei) != want_eth * WEI_PER_ETH:
            add(FAIL, "eth", f"deposit {txh}: value {value_wei} wei != {d['amount_eth']} ETH")
        data = str(tx.get("input") or "")
        try:
            tag = bytes.fromhex(data[2:] if data.startswith("0x") else data).decode("utf-8").strip()
        except (ValueError, UnicodeDecodeError):
            tag = ""
        want_tag = f"EXCHANGE_DEPOSIT:{d['node_address']}"
        if tag.lower() != want_tag.lower():
            add(FAIL, "eth", f"deposit {txh}: input tag {tag!r} != {want_tag!r}")
        if bridge_address and str(tx.get("to") or "").lower() != bridge_address.lower():
            add(FAIL, "eth", f"deposit {txh}: to {tx.get('to')} != bridge {bridge_address}")
    add(INFO, "eth", f"{len(deposits)} prepaid deposits checked")

    settled = conn.execute(
        "SELECT id, total, settlement_eth_tx_hash, sell_order_id FROM trades WHERE settlement_eth_tx_hash IS NOT NULL"
    ).fetchall()
    seller_eth = {r["id"]: r["seller_eth_address"] for r in conn.execute("SELECT id, seller_eth_address FROM orders")}
    for t in settled:
        txh = t["settlement_eth_tx_hash"]
        try:
            tx, receipt = _eth_tx(rpc_url, txh)
        except RpcError as e:
            add(WARN, "eth", f"trade {t['id']} settle {txh}: {e}")
            continue
        if tx is None:
            add(FAIL, "eth", f"trade {t['id']} settle {txh}: not on chain")
            continue
        bad = _receipt_ok(receipt)
        if bad:
            add(WARN if bad == "unsealed" else FAIL, "eth", f"trade {t['id']} settle {txh}: {bad}")
            continue
        want_wei = _dec(t["total"])
        value_wei = int(str(tx.get("value") or "0x0"), 16)
        if want_wei is None or Decimal(value_wei) != want_wei * WEI_PER_ETH:
            add(FAIL, "eth", f"trade {t['id']} settle {txh}: value != {t['total']} ETH")
        want_to = seller_eth.get(t["sell_order_id"])
        if want_to and str(tx.get("to") or "").lower() != str(want_to).lower():
            add(FAIL, "eth", f"trade {t['id']} settle {txh}: to {tx.get('to')} != seller {want_to}")
    add(INFO, "eth", f"{len(settled)} settlement ETH legs checked")


def check_ait_chain(conn: sqlite3.Connection, ait_rpc: str, escrow: str, add) -> None:
    try:
        escrow_txs = _ait_transfers(ait_rpc, escrow)
    except RpcError as e:
        add(WARN, "ait", str(e))
        return
    sells = conn.execute(
        "SELECT id, order_type, amount_ticks, user_address, backing_tx_hash FROM orders "
        "WHERE order_type='SELL' AND funded_state='funded'"
    ).fetchall()
    for o in sells:
        txh = o["backing_tx_hash"]
        tx = escrow_txs.get(str(txh))
        if tx is None:
            add(FAIL, "ait", f"order {o['id']}: backing {txh} not in escrow transfer history")
            continue
        to_addr = str(tx.get("recipient") or tx.get("to") or "")
        sender = str(tx.get("sender") or tx.get("from") or "")
        payload = tx.get("payload") or {}
        if to_addr.lower() != escrow.lower():
            add(FAIL, "ait", f"order {o['id']}: backing {txh} to {to_addr} != escrow")
        if payload.get("sell_quote") != o["id"]:
            add(FAIL, "ait", f"order {o['id']}: backing {txh} sell_quote={payload.get('sell_quote')}")
        if sender.lower() != str(o["user_address"]).lower():
            add(FAIL, "ait", f"order {o['id']}: backing {txh} from {sender} != owner {o['user_address']}")
        want_units = Decimal(int(o["amount_ticks"])) / TICKS_PER_UNIT * UNITS_PER_AIT
        if Decimal(int(tx.get("value") or 0)) < want_units:
            add(FAIL, "ait", f"order {o['id']}: lock {tx.get('value')} units < notional {want_units}")
    add(INFO, "ait", f"{len(sells)} funded SELL backings checked")

    legs = conn.execute(
        "SELECT id, amount, fee_ait, buyer_address, settlement_ait_tx_hash, settlement_fee_tx_hash "
        "FROM trades WHERE settlement_ait_tx_hash IS NOT NULL"
    ).fetchall()
    for t in legs:
        txh = t["settlement_ait_tx_hash"]
        tx = escrow_txs.get(str(txh))
        if tx is None:
            add(FAIL, "ait", f"trade {t['id']}: ait leg {txh} not in escrow history")
        else:
            to_addr = str(tx.get("recipient") or tx.get("to") or "")
            if to_addr.lower() != str(t["buyer_address"]).lower():
                add(FAIL, "ait", f"trade {t['id']}: ait leg to {to_addr} != buyer {t['buyer_address']}")
            want = _dec(t["amount"])
            if want is not None and Decimal(int(tx.get("value") or 0)) != want * UNITS_PER_AIT:
                add(FAIL, "ait", f"trade {t['id']}: ait leg value {tx.get('value')} != {want * UNITS_PER_AIT} units")
        fee_hash = t["settlement_fee_tx_hash"]
        fee = _dec(t["fee_ait"])
        if fee and fee > 0:
            if fee_hash is None:
                add(FAIL, "ait", f"trade {t['id']}: fee owed ({t['fee_ait']} AIT) but no fee tx hash")
            elif str(fee_hash) not in escrow_txs:
                add(FAIL, "ait", f"trade {t['id']}: fee leg {fee_hash} not in escrow history")
        elif fee_hash is not None:
            add(WARN, "ait", f"trade {t['id']}: fee leg {fee_hash} recorded for a zero-fee trade")
    add(INFO, "ait", f"{len(legs)} settlement AIT legs checked")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True, help="exchange SQLite DB path")
    ap.add_argument("--bridge-db", help="bridge_deposits.db path — enables the prepay cross-check")
    ap.add_argument("--rpc-url", default=DEFAULT_ETH_RPC, help="Sepolia JSON-RPC endpoint")
    ap.add_argument("--bridge-address", help="expected deposit destination (enforces `to` on prepays)")
    ap.add_argument("--ait-rpc", help="AITBC chain RPC base URL — enables AIT checks with --escrow-address")
    ap.add_argument("--escrow-address", help="sell-escrow account address for AIT checks")
    ap.add_argument("--no-chain", action="store_true", help="DB-internal checks only")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ns = ap.parse_args()

    findings: list[dict[str, str]] = []

    def add(sev: str, scope: str, msg: str) -> None:
        findings.append({"severity": sev, "scope": scope, "message": msg})

    try:
        conn = _db(ns.db)
    except sqlite3.Error as e:
        print(f"FAIL db: cannot open {ns.db} read-only: {e}", file=sys.stderr)
        return 1
    try:
        check_db_internal(conn, add)
        if ns.bridge_db:
            check_bridge_db(conn, ns.bridge_db, add)
        if not ns.no_chain:
            check_eth_chain(conn, ns.rpc_url, ns.bridge_address, add)
            if ns.ait_rpc and ns.escrow_address:
                check_ait_chain(conn, ns.ait_rpc, ns.escrow_address, add)
            else:
                add(INFO, "ait", "no --ait-rpc/--escrow-address — AIT chain checks skipped")
    finally:
        conn.close()

    fails = [f for f in findings if f["severity"] == FAIL]
    warns = [f for f in findings if f["severity"] == WARN]
    if ns.json:
        print(json.dumps({"ok": not fails, "fail": len(fails), "warn": len(warns), "findings": findings}, indent=2))
    else:
        for f in findings:
            if f["severity"] != INFO:
                print(f"{f['severity']} {f['scope']}: {f['message']}")
        infos = [f["message"] for f in findings if f["severity"] == INFO]
        for m in infos:
            print(f"  .. {m}")
        print(f"{'FAIL' if fails else 'OK'} — {len(fails)} failures, {len(warns)} warnings")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
