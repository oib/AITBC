#!/usr/bin/env python3
"""Read-only exchange-book verifier (ETH-19 phase 3, C7).

    venv/bin/python scripts/ops/exchange_verify.py --db /path/exchange.db
    venv/bin/python scripts/ops/exchange_verify.py --db /path/exchange.db \
        --bridge-db /var/lib/aitbc/data/bridge_deposits.db \
        --bridge-address 0xBridgeWallet... \
        --ait-rpc http://127.0.0.1:8202 --escrow-address 0xEscrow...
    venv/bin/python scripts/ops/exchange_verify.py --db /path/exchange.db \
        --bridge-db /var/lib/aitbc/data/bridge_deposits.db --settlement
    venv/bin/python scripts/ops/exchange_verify.py --db ... --no-chain --json

    On hub the AIT chain RPC for --ait-rpc is http://127.0.0.1:8202 (not
    8201 — that listener answers 401).

Re-derives the exchange DB's funding and settlement claims against the
chains before the book reopens after a crash/restore (design §11). Check
groups, each reported with counts and per-row detail:

- DB-internal  (always): funded-state/backing/debit/trade consistency,
  nonce uniqueness, registry completeness. A registered node without
  eth_address is flag-conditional (the flag lives in the service env —
  unreadable offline): WARN unless --settlement declares it on AND the
  node already has orders, which is a FAIL.
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
writes, no keys — all endpoints/addresses come from flags. The only
environment read is the --db default: EXCHANGE_DATABASE_URL /
AITBC_DATA_DIR, the same resolution apps/exchange/simple_exchange/db.py
get_db_path() uses, minus the directory creation (this script never
creates a DB). Exit status is 1 if any check FAILs; WARN and INFO never
fail the run. Rows whose chain leg is merely unsealed are WARN, not
FAIL — a lagging RPC is not evidence of loss.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from typing import Any

DEFAULT_ETH_RPC = "https://ethereum-sepolia-rpc.publicnode.com"
DEFAULT_DATA_DIR = "/var/lib/aitbc"
WEI_PER_ETH = Decimal(10) ** 18
UNITS_PER_AIT = Decimal(36_000_000)  # chain units per AIT
TICKS_PER_UNIT = Decimal(100_000_000)  # exchange ticks per AIT
# Mirrors the settlement monitor's _sweep_fee_ait() (aitbc.utils.units
# DEFAULT_TX_FEE_AIT): a lock remainder at or below this never earns an
# order_refund row — sweeping it would cost more than it returns.
SWEEP_FEE_AIT = Decimal("0.01")
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


def _service_db_path() -> str:
    """The exchange service's DB path — mirrors get_db_path() in
    apps/exchange/simple_exchange/db.py (EXCHANGE_DATABASE_URL with
    sqlite:/// stripped, else AITBC_DATA_DIR/data/exchange/exchange.db),
    minus its mkdir: this script must never create a DB."""
    raw = os.getenv("EXCHANGE_DATABASE_URL")
    if raw:
        if raw.startswith("sqlite:"):
            raw = raw[len("sqlite:") :]
        while raw.startswith("/"):
            raw = raw[1:]
        return "/" + raw
    return os.path.join(os.getenv("AITBC_DATA_DIR", DEFAULT_DATA_DIR), "data/exchange/exchange.db")


def _resolve_db(ns_db: str | None) -> str:
    """--db wins; otherwise the service default is used when readable."""
    if ns_db:
        return ns_db
    candidate = _service_db_path()
    if os.path.isfile(candidate) and os.access(candidate, os.R_OK):
        return candidate
    raise SystemExit(
        f"--db is required: no readable exchange DB at the service default {candidate} "
        "(checked EXCHANGE_DATABASE_URL / AITBC_DATA_DIR)"
    )


def _dec(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _lock_remainder_ait(order: dict, trades: list) -> Decimal | None:
    """Mirror of the monitor's remainder math: locked AIT minus every
    trade's amount+fee draw (each trade consumes its draw regardless of
    outcome). ``None`` when the order carries no locked_ticks."""
    locked_ticks = order["locked_ticks"]
    if locked_ticks is None:
        return None
    draw = Decimal(0)
    for t in trades:
        if t["sell_order_id"] == order["id"]:
            draw += Decimal(str(t["amount"])) + Decimal(str(t["fee_ait"] or "0"))
    return Decimal(int(locked_ticks)) / TICKS_PER_UNIT - draw


def _check_refund_row(order: dict, trades: list, add, refunds: dict) -> None:
    """The order_refund-ledger check for one backing_expired order. A
    remainder at/below the sweep fee deliberately earns no row — the
    monitor leaves it in escrow (dust), so that is INFO, not stranded."""
    status = refunds.get(order["id"])
    if status == "failed":
        add(
            FAIL,
            "db",
            f"order {order['id']}: backing_expired but backing_tx_hash set — order_refund row failed (stranded lock)",
        )
        return
    if status is not None:
        return
    remaining = _lock_remainder_ait(order, trades)
    if remaining is not None and remaining <= SWEEP_FEE_AIT:
        add(
            INFO,
            "db",
            f"order {order['id']}: backing_expired, lock remainder {remaining} AIT at/below the "
            f"{SWEEP_FEE_AIT} AIT sweep fee — no order_refund row needed (dust)",
        )
    else:
        add(
            FAIL,
            "db",
            f"order {order['id']}: backing_expired but backing_tx_hash set — no order_refund row (stranded lock)",
        )


def _check_order_rows(orders: dict, debits: dict, trades: list, add, refunds: dict | None) -> None:
    """Funded-state invariants per order row.

    A non-funded order may keep backing_tx_hash when the lock it points to is
    accounted for: the exchange's cancel path sets funded_state='backing_expired'
    and keeps the hash on purpose — the settlement monitor's stranded-lock scan
    needs it non-NULL to build the order_refund row, and it is the audit link to
    the lock. ``refunds`` maps order_id -> order_refund row status (None when the
    monitor DB was not provided — then the link is INFO, not FAIL)."""
    for order in orders.values():
        funded = order["funded_state"] == "funded"
        if order["order_type"] == "BUY" and funded and order["id"] not in debits:
            add(FAIL, "db", f"order {order['id']}: funded BUY without a prepaid_debits row")
        if order["order_type"] == "SELL" and funded and not order["backing_tx_hash"]:
            add(FAIL, "db", f"order {order['id']}: funded SELL without backing_tx_hash")
        if not funded and order["backing_tx_hash"]:
            if order["funded_state"] != "backing_expired":
                add(FAIL, "db", f"order {order['id']}: {order['funded_state']} but backing_tx_hash set")
            elif refunds is None:
                add(
                    INFO,
                    "db",
                    f"order {order['id']}: backing_expired with backing_tx_hash — refund link unchecked (no --bridge-db)",
                )
            else:
                _check_refund_row(order, trades, add, refunds)


def _check_nonce_uniqueness(orders: dict, add) -> None:
    seen_nonce: dict[tuple[str, Any], int] = {}
    for order in orders.values():
        key = (str(order["user_address"]).lower(), order["account_nonce"])
        if order["account_nonce"] is not None:
            if key in seen_nonce:
                add(FAIL, "db", f"orders {seen_nonce[key]} and {order['id']}: duplicate account_nonce")
            seen_nonce[key] = order["id"]


def _check_debit_rows(orders: dict, debits: dict, add) -> None:
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


def _check_trade_row(t: sqlite3.Row, orders: dict, filled_by_order: dict, add, settles: dict | None) -> None:
    for col in ("buy_order_id", "sell_order_id"):
        oid = t[col]
        if oid is not None and oid not in orders:
            add(FAIL, "db", f"trade {t['id']}: {col}={oid} references a missing order")
    if t["settlement_state"] == "settled":
        if not t["settlement_eth_tx_hash"]:
            add(FAIL, "db", f"trade {t['id']}: settled but missing settlement tx hash")
        if not t["settlement_ait_tx_hash"]:
            # The monitor's mirror posted only the fields present on the
            # pre-update row, so a hash persisted with the settled status
            # (leg seals) can be missing on the tape while living on the
            # exchange_settlements row — VERIFY-2 reads the ledger for it.
            if settles is None:
                add(
                    INFO,
                    "db",
                    f"trade {t['id']}: settled without settlement_ait_tx_hash — "
                    "settlement hash link unchecked (no --bridge-db)",
                )
            elif not settles.get(int(t["id"])):
                add(FAIL, "db", f"trade {t['id']}: settled but missing settlement tx hash")
    amt_ticks = _dec(t["amount"])
    if t["sell_order_id"] is not None and amt_ticks is not None:
        filled_by_order[t["sell_order_id"]] = filled_by_order.get(t["sell_order_id"], Decimal(0)) + amt_ticks
    if t["buy_order_id"] is not None and amt_ticks is not None:
        filled_by_order[t["buy_order_id"]] = filled_by_order.get(t["buy_order_id"], Decimal(0)) + amt_ticks


def _check_trade_rows(orders: dict, trades: list, add, settles: dict | None) -> None:
    filled_by_order: dict[int, Decimal] = {}
    for t in trades:
        _check_trade_row(t, orders, filled_by_order, add, settles)
    for order_id, filled_ait in filled_by_order.items():
        recorded = _dec(orders[order_id]["filled_ticks"] or 0)
        if recorded is not None and abs(Decimal(int(recorded)) / TICKS_PER_UNIT - filled_ait) > Decimal("1e-8"):
            add(
                WARN,
                "db",
                f"order {order_id}: recorded filled {Decimal(int(recorded)) / TICKS_PER_UNIT} != Σ trades {filled_ait}",
            )


def _refund_ref_statuses(bridge_db_path: str | None) -> dict | None:
    """order_id -> order_refund status from the monitor DB, or None when the
    monitor DB cannot be read (caller then reports INFO, not FAIL)."""
    if not bridge_db_path:
        return None
    try:
        bconn = _db(bridge_db_path)
    except sqlite3.Error:
        return None
    try:
        if not _has_table(bconn, "exchange_settlements"):
            return None
        return {
            int(r["ref_id"]): str(r["status"] or "")
            for r in bconn.execute("SELECT ref_id, status FROM exchange_settlements WHERE kind = 'order_refund'")
        }
    except sqlite3.Error:
        return None
    finally:
        bconn.close()


def _settle_trade_ait_hashes(bridge_db_path: str | None) -> dict | None:
    """trade_id -> settle_ait_tx_hash from settled trade-kind rows in the
    monitor DB, or None when the monitor DB cannot be read (caller then
    reports INFO, not FAIL)."""
    if not bridge_db_path:
        return None
    try:
        bconn = _db(bridge_db_path)
    except sqlite3.Error:
        return None
    try:
        if not _has_table(bconn, "exchange_settlements"):
            return None
        return {
            int(r["ref_id"]): str(r["settle_ait_tx_hash"])
            for r in bconn.execute(
                "SELECT ref_id, settle_ait_tx_hash FROM exchange_settlements WHERE kind = 'trade' AND status = 'settled'"
            )
            if r["settle_ait_tx_hash"]
        }
    except sqlite3.Error:
        return None
    finally:
        bconn.close()


def check_db_internal(
    conn: sqlite3.Connection, add, *, settlement_enabled: bool = False, bridge_db_path: str | None = None
) -> None:
    refunds = _refund_ref_statuses(bridge_db_path)
    settles = _settle_trade_ait_hashes(bridge_db_path)
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
        "SELECT id, amount, fee_ait, total, buyer_address, seller_address, buy_order_id, sell_order_id, "
        "settlement_state, settlement_eth_tx_hash, settlement_ait_tx_hash FROM trades"
    ).fetchall()

    _check_order_rows(orders, debits, trades, add, refunds)
    _check_nonce_uniqueness(orders, add)
    _check_debit_rows(orders, debits, add)
    _check_trade_rows(orders, trades, add, settles)

    if _has_table(conn, "node_registry"):
        # REPO-2: registered-without-eth_address is flag-conditional. The
        # exchange stores EXCHANGE_SETTLEMENT_ENABLED in its service env —
        # unreadable by an offline verifier — so the operator asserts it with
        # --settlement (mirroring the service's own unset=off default).
        #   flag off:                     WARN — payout is not needed yet
        #   flag on, node has orders:     FAIL — a seller cannot be paid
        #   flag on, node has no orders:  WARN — payout not yet needed
        order_counts: dict[str, int] = {}
        if settlement_enabled:
            for o in orders.values():
                ua = str(o["user_address"] or "").lower()
                order_counts[ua] = order_counts.get(ua, 0) + 1
        for r in conn.execute("SELECT address, status, eth_address FROM node_registry"):
            if r["status"] != "registered" or r["eth_address"]:
                continue
            if order_counts.get(str(r["address"]).lower(), 0):
                add(
                    FAIL,
                    "db",
                    f"node_registry {r['address']}: registered with orders but no eth_address "
                    "(settlement on — seller payout impossible)",
                )
            else:
                hint = (
                    "no orders — payout not yet needed" if settlement_enabled else "settlement off or --settlement not passed"
                )
                add(WARN, "db", f"node_registry {r['address']}: registered without eth_address ({hint})")
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


def _check_prepaid_deposit(d: sqlite3.Row, rpc_url: str, bridge_address: str | None, add) -> None:
    """One prepaid_deposits row against its ETH transaction + receipt."""
    txh = d["eth_tx_hash"]
    try:
        tx, receipt = _eth_tx(rpc_url, txh)
    except RpcError as e:
        add(WARN, "eth", f"deposit {txh}: {e}")
        return
    if tx is None:
        add(FAIL, "eth", f"deposit {txh}: not on chain")
        return
    bad = _receipt_ok(receipt)
    if bad:
        add(WARN if bad == "unsealed" else FAIL, "eth", f"deposit {txh}: {bad}")
        return
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


def _check_settlement_leg(t: sqlite3.Row, seller_eth: dict, rpc_url: str, add) -> None:
    """One trade's settlement_eth_tx_hash against its ETH tx + receipt."""
    txh = t["settlement_eth_tx_hash"]
    try:
        tx, receipt = _eth_tx(rpc_url, txh)
    except RpcError as e:
        add(WARN, "eth", f"trade {t['id']} settle {txh}: {e}")
        return
    if tx is None:
        add(FAIL, "eth", f"trade {t['id']} settle {txh}: not on chain")
        return
    bad = _receipt_ok(receipt)
    if bad:
        add(WARN if bad == "unsealed" else FAIL, "eth", f"trade {t['id']} settle {txh}: {bad}")
        return
    want_wei = _dec(t["total"])
    value_wei = int(str(tx.get("value") or "0x0"), 16)
    if want_wei is None or Decimal(value_wei) != want_wei * WEI_PER_ETH:
        add(FAIL, "eth", f"trade {t['id']} settle {txh}: value != {t['total']} ETH")
    want_to = seller_eth.get(t["sell_order_id"])
    if want_to and str(tx.get("to") or "").lower() != str(want_to).lower():
        add(FAIL, "eth", f"trade {t['id']} settle {txh}: to {tx.get('to')} != seller {want_to}")


def check_eth_chain(conn: sqlite3.Connection, rpc_url: str, bridge_address: str | None, add) -> None:
    deposits = (
        conn.execute("SELECT node_address, amount_eth, eth_tx_hash FROM prepaid_deposits").fetchall()
        if _has_table(conn, "prepaid_deposits")
        else []
    )
    for d in deposits:
        _check_prepaid_deposit(d, rpc_url, bridge_address, add)
    add(INFO, "eth", f"{len(deposits)} prepaid deposits checked")

    settled = conn.execute(
        "SELECT id, total, settlement_eth_tx_hash, sell_order_id FROM trades WHERE settlement_eth_tx_hash IS NOT NULL"
    ).fetchall()
    seller_eth = {r["id"]: r["seller_eth_address"] for r in conn.execute("SELECT id, seller_eth_address FROM orders")}
    for t in settled:
        _check_settlement_leg(t, seller_eth, rpc_url, add)
    add(INFO, "eth", f"{len(settled)} settlement ETH legs checked")


def _check_sell_backing(o: sqlite3.Row, escrow_txs: dict, escrow: str, add) -> None:
    """One funded SELL order's backing_tx_hash against the escrow history."""
    txh = o["backing_tx_hash"]
    tx = escrow_txs.get(str(txh))
    if tx is None:
        add(FAIL, "ait", f"order {o['id']}: backing {txh} not in escrow transfer history")
        return
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


def _check_ait_leg(t: sqlite3.Row, escrow_txs: dict, add, ait_hash: str | None = None) -> None:
    """One trade's settlement AIT leg (+ fee leg) against the escrow history.

    ``ait_hash`` is the ledger fallback: the settle leg's tx hash read from
    exchange_settlements when the tape column is empty (VERIFY-2/VERIFY-3 —
    pre-mirror-fix trades keep the hash only on the ledger row)."""
    txh = ait_hash or t["settlement_ait_tx_hash"]
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


def check_ait_chain(conn: sqlite3.Connection, ait_rpc: str, escrow: str, add, bridge_db_path: str | None = None) -> None:
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
        _check_sell_backing(o, escrow_txs, escrow, add)
    add(INFO, "ait", f"{len(sells)} funded SELL backings checked")

    legs = conn.execute(
        "SELECT id, amount, fee_ait, buyer_address, settlement_ait_tx_hash, settlement_fee_tx_hash "
        "FROM trades WHERE settlement_ait_tx_hash IS NOT NULL"
    ).fetchall()
    for t in legs:
        _check_ait_leg(t, escrow_txs, add)
    tape_count = len(legs)

    ledger_count = 0
    # VERIFY-3: pre-mirror-fix trades carry the leg hash only on the settled
    # ledger row. A settled trade with neither tape nor ledger hash is skipped
    # here — the DB check already FAILs it; re-reporting would double-count.
    settles = _settle_trade_ait_hashes(bridge_db_path)
    if settles:
        missing = conn.execute(
            "SELECT id, amount, fee_ait, buyer_address, settlement_ait_tx_hash, settlement_fee_tx_hash "
            "FROM trades WHERE settlement_state = 'settled' AND settlement_ait_tx_hash IS NULL"
        ).fetchall()
        for t in missing:
            ledger_hash = settles.get(int(t["id"]))
            if ledger_hash:
                _check_ait_leg(t, escrow_txs, add, ait_hash=ledger_hash)
                ledger_count += 1
    add(
        INFO,
        "ait",
        f"{tape_count + ledger_count} settlement AIT legs checked ({tape_count} from tape, {ledger_count} from ledger)",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--db",
        default=None,
        help="exchange SQLite DB path (default: the service path from EXCHANGE_DATABASE_URL / AITBC_DATA_DIR, "
        "i.e. /var/lib/aitbc/data/exchange/exchange.db, when it is readable)",
    )
    ap.add_argument(
        "--bridge-db",
        default=(os.environ.get("BRIDGE_DEPOSITS_DB") or "").strip() or None,
        help="bridge_deposits.db path — enables the prepay cross-check (default: BRIDGE_DEPOSITS_DB env var)",
    )
    ap.add_argument("--rpc-url", default=DEFAULT_ETH_RPC, help="Sepolia JSON-RPC endpoint")
    ap.add_argument("--bridge-address", help="expected deposit destination (enforces `to` on prepays)")
    ap.add_argument("--ait-rpc", help="AITBC chain RPC base URL — enables AIT checks with --escrow-address")
    ap.add_argument("--escrow-address", help="sell-escrow account address for AIT checks")
    ap.add_argument("--no-chain", action="store_true", help="DB-internal checks only")
    ap.add_argument(
        "--settlement",
        action="store_true",
        help="declare EXCHANGE_SETTLEMENT_ENABLED on for the DB under test — a "
        "registered node with orders but no eth_address is then a FAIL (else "
        "a WARN). The verifier cannot read the flag offline; mirroring the "
        "service's own unset=off default, omitting this means settlement-off.",
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ns = ap.parse_args()
    ns.db = _resolve_db(ns.db)

    findings: list[dict[str, str]] = []

    def add(sev: str, scope: str, msg: str) -> None:
        findings.append({"severity": sev, "scope": scope, "message": msg})

    try:
        conn = _db(ns.db)
    except sqlite3.Error as e:
        print(f"FAIL db: cannot open {ns.db} read-only: {e}", file=sys.stderr)
        return 1
    try:
        check_db_internal(conn, add, settlement_enabled=ns.settlement, bridge_db_path=ns.bridge_db)
        if ns.bridge_db:
            check_bridge_db(conn, ns.bridge_db, add)
        if not ns.no_chain:
            check_eth_chain(conn, ns.rpc_url, ns.bridge_address, add)
            if ns.ait_rpc and ns.escrow_address:
                check_ait_chain(conn, ns.ait_rpc, ns.escrow_address, add, bridge_db_path=ns.bridge_db)
            else:
                add(
                    INFO,
                    "ait",
                    "AIT chain checks skipped — pass --ait-rpc http://127.0.0.1:8202 --escrow-address 0x... "
                    "to enable backing/settlement-leg verification",
                )
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
