"""Exchange settlement monitor (ETH-8 phase 3, wallet side).

The authoritative settlement machine for AIT/ETH exchange trades. It reads
``exchange.db`` ``mode=ro`` only — the exchange service is the single writer
there, and every state change this monitor needs is posted through the one
loopback endpoint ``POST /api/internal/exchange-settlement`` (API-key
authenticated, raw-peer loopback enforced server-side). The ledger it owns
is ``exchange_settlements`` in ``bridge_deposits.db``: one row per trade
(``UNIQUE(kind, ref_id)``), forward-only, and the exchange-side mirror only
ever follows it — a mirror 409 means the mirror missed intermediate states,
which the monitor replays in order; mirror failures never block the ledger.

Lanes, each inside its own try/except so one RPC's outage cannot stall the
others:

1. Escrow lock scan — sealed TRANSFERs to ``AIT_SELL_ESCROW`` whose
   ``payload.sell_quote`` is an order id (``sellq_*`` belongs to the ETH-7
   sell lane) are posted as ``order_funded``. Locks on orders that cannot
   take them (unknown, already funded by another tx, closed) get a
   ``order_refund`` settlement row that sweeps the lock back to its sender.
2. Prepay scan — ``eth_deposits`` rows at status ``exchange_prepay``,
   written by the deposit monitor when an inbound ETH transfer carries an
   ``EXCHANGE_DEPOSIT:<addr>`` input tag, are posted as ``prepaid_credit``;
   a 409 (unregistered node) is recorded 'unattributable' and a 400
   'rejected', both for operator handling.
3. Backing watch — open orders past ``expiry_height`` get
   ``order_backing_expired``; closed BUY orders still holding an open
   debit get ``debit_refund``. Expired/cancelled funded SELL orders get an
   ``order_refund`` row returning the lock remainder (locked − all trade
   draws — every trade consumes its full amount+fee from the lock).
4. Trade driver — exchange trades with a non-terminal ``settlement_state``
   get a ``kind='trade'`` ledger row and are driven
   locked→releasing→released→settling→settled (ETH release to the seller's
   payout address via the wdm machinery; the escrow sweep splits
   ``amount → buyer`` then ``fee → treasury`` as two serialized legs) or
   →refund_pending→refunding→refunded (only on a *proven* unsent ETH
   release — the seller's lock then returns to the seller and the mirror
   releases the buyer's committed ETH).

Serialization: escrow sweeps share one nonce space with sell locks — the
in-flight check unions ``bridge_sell_locks`` and ``exchange_settlements``.
ETH releases draw on the shared bridge float — ``_pending_eth_reserve``
carries this lane as its third term.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from aitbc.aitbc_logging import get_logger
from aitbc.constants import DATA_DIR
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.utils import ait_to_units, units_to_ait
from aitbc.utils.units import DEFAULT_TX_FEE_AIT

from . import bridge_withdraw_monitor as wdm
from . import sell_escrow_monitor as sellmon
from .bridge_db import (
    get_exchange_inflight_sweep,
    get_exchange_settlement,
    get_open_exchange_settlements,
    get_sell_inflight_sweep,
    init_db,
    insert_exchange_settlement,
    insert_monitor_mark,
    monitor_mark,
    update_exchange_settlement,
)

logger = get_logger(__name__)

_db_initialized = False
_exchange_polling_enabled: bool = True

# Exchange ticks are 1e8 per AIT; chain units are 3.6e7 per AIT. Lock values
# arrive in chain units — the conversion floors (a lock can never be credited
# more cover than it actually carries).
_TICKS_PER_UNIT = 100_000_000
_UNITS_PER_AIT = 36_000_000

_FEE_AIT = Decimal(str(DEFAULT_TX_FEE_AIT))

# The mirror's forward map — the wallet-side copy. A drift test pins it to
# the exchange handler's _TRADE_STATE_FORWARD; the ledger's own transitions
# are driven by the monitor, the map exists only for mirror replay.
_MIRROR_FORWARD: dict[str, frozenset[str]] = {
    "locked": frozenset({"releasing", "queued_reserve", "needs_review"}),
    "queued_reserve": frozenset({"releasing", "needs_review"}),
    "releasing": frozenset({"released", "needs_review", "needs_review_release", "refund_pending"}),
    "released": frozenset({"settling", "queued_fee_settle", "needs_review_sweep", "refund_pending"}),
    "queued_fee_settle": frozenset({"settling", "needs_review_sweep"}),
    "settling": frozenset({"settled", "needs_review_sweep"}),
    "refund_pending": frozenset({"refunding", "queued_fee_refund", "needs_review_sweep"}),
    "queued_fee_refund": frozenset({"refunding", "needs_review_sweep"}),
    "refunding": frozenset({"refunded", "needs_review_sweep"}),
    "needs_review": frozenset({"releasing", "refund_pending"}),
    "needs_review_release": frozenset({"released", "refund_pending"}),
    "needs_review_sweep": frozenset({"settling", "refunding", "settled", "refunded"}),
    "settled": frozenset(),
    "refunded": frozenset(),
    "failed": frozenset(),
}

_TERMINAL_STATUSES = frozenset({"settled", "refunded", "failed"})


@dataclass(frozen=True)
class ExchangeCfg:
    """Exchange-side config for the settlement monitor. ``escrow`` reuses the
    sell monitor's validated escrow block — same account, same custody."""

    escrow: sellmon.SellConfig
    exchange_url: str
    api_key: str
    exchange_db_path: str
    poll_interval: int
    max_eth_per_tx: Decimal
    min_reserve_eth: Decimal
    max_payout_fraction: Decimal


def _exchange_db_path() -> str:
    """The exchange.db path — same env/default resolution as the exchange
    service, but the monitor only ever opens it ``mode=ro``."""
    raw = os.getenv("EXCHANGE_DATABASE_URL", f"sqlite:///{DATA_DIR}/data/exchange/exchange.db")
    if raw.startswith("sqlite:"):
        raw = raw[len("sqlite:") :]
    while raw.startswith("/"):
        raw = raw[1:]
    return "/" + raw


def _exchange_config() -> ExchangeCfg:
    api_key = os.getenv("EXCHANGE_API_KEY", "")
    if not api_key:
        raise ValueError("EXCHANGE_API_KEY not configured — the settlement endpoint cannot authenticate")
    return ExchangeCfg(
        escrow=sellmon._sell_config(),
        exchange_url=os.getenv("EXCHANGE_INTERNAL_URL", "http://127.0.0.1:8106").rstrip("/"),
        api_key=api_key,
        exchange_db_path=_exchange_db_path(),
        poll_interval=sellmon._positive_int_env("EXCHANGE_SETTLEMENT_POLL_INTERVAL", "30"),
        max_eth_per_tx=sellmon._decimal_env("EXCHANGE_SETTLEMENT_MAX_ETH_PER_TX", "0.05"),
        min_reserve_eth=sellmon._decimal_env("ETH_WITHDRAW_MIN_RESERVE", "0.005"),
        max_payout_fraction=sellmon._decimal_env("BRIDGE_MAX_PAYOUT_FRACTION", "0.5"),
    )


def exchange_feature_enabled() -> bool:
    """Master switch: BRIDGE_ENABLED + EXCHANGE_SETTLEMENT_ENABLED."""
    return wdm.BRIDGE_ENABLED and os.getenv("EXCHANGE_SETTLEMENT_ENABLED", "false").lower() == "true"


def exchange_config_status() -> tuple[bool, str]:
    if not exchange_feature_enabled():
        return (False, "exchange settlement disabled")
    try:
        _exchange_config()
    except ValueError as e:
        return (False, str(e))
    return (True, "")


def _ensure_db() -> None:
    global _db_initialized
    if not _db_initialized:
        init_db()
        _db_initialized = True


# ---------------------------------------------------------------------------
# exchange.db read-only access + the single write path (loopback endpoint)
# ---------------------------------------------------------------------------


def _ro_connect(cfg: ExchangeCfg) -> sqlite3.Connection:
    """Read-only connection to exchange.db. The exchange service owns every
    write; this monitor's only write path is the loopback endpoint."""
    conn = sqlite3.connect(f"file:{cfg.exchange_db_path}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _ro_one(cfg: ExchangeCfg, sql: str, params: tuple = ()) -> sqlite3.Row | None:
    conn = _ro_connect(cfg)
    try:
        row = conn.execute(sql, params).fetchone()
        return row if isinstance(row, sqlite3.Row) else None
    finally:
        conn.close()


def _ro_all(cfg: ExchangeCfg, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    conn = _ro_connect(cfg)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


async def _post_event(cfg: ExchangeCfg, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """POST one settlement event to the internal endpoint. Returns
    (status, body); transport errors propagate — the caller decides."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{cfg.exchange_url}/api/internal/exchange-settlement",
            json=payload,
            headers={"X-Api-Key": cfg.api_key},
        )
    try:
        body = resp.json()
    except ValueError:
        body = {}
    return resp.status_code, body if isinstance(body, dict) else {}


# ---------------------------------------------------------------------------
# Lane 1 — escrow order-lock scan
# ---------------------------------------------------------------------------


def _exchange_order_id(payload_value: Any) -> int | None:
    """The exchange order id in ``payload.sell_quote``: an int or an
    all-digit string. ``sellq_*`` belongs to the ETH-7 sell lane; booleans
    and other shapes are neither lane's."""
    if isinstance(payload_value, bool):
        return None
    if isinstance(payload_value, int):
        return payload_value
    if isinstance(payload_value, str) and payload_value.isdigit():
        return int(payload_value)
    return None


_HEX_CHARS = frozenset("0123456789abcdef")


def _norm_tx_hash(value: Any) -> str:
    """Lower-case, 0x-less chain hash for equality checks — the RPC spells
    one hash with either case or prefix across endpoints, so comparisons
    normalize both sides rather than trusting the wire spelling."""
    h = str(value or "").strip().lower()
    return h[2:] if h.startswith("0x") else h


def _lock_refund_ref_id(tx_hash: str) -> int:
    """ref_id for an owner-sender inbound refund whose ``−order_id`` slot is
    already held: a deterministic negative derived from the lock hash and
    bounded below −2**59. Order ids are small positives, so the range can
    never collide with a ``+order_id`` remainder refund, a ``−order_id``
    inbound refund, or a trade id — and a re-scan derives the same id, so
    the UNIQUE pair dedupes instead of writing a second row."""
    return -(int(_norm_tx_hash(tx_hash)[:15], 16) | (1 << 59))


# The below-fee skip leaves the lock unmarked, so it is re-evaluated every
# poll — rate-limit the notice to INFO once per lock per hour, DEBUG
# between, or a permanent dust lock would spam the journal. The hash is
# attacker-chosen, so the map is bounded: at the cap stale entries are
# pruned and, if still full, it resets wholesale (a restart already
# re-logs each live lock once, so a reset is no worse).
_BELOW_FEE_LOG_SECONDS = 3600
_BELOW_FEE_LOG_MAX = 8192
_below_fee_last_log: dict[str, int] = {}


def _log_below_fee(order_id: int, tx_hash: str, lock_ait: Decimal) -> None:
    now = int(time.monotonic())
    last = _below_fee_last_log.get(tx_hash)
    if last is not None and now - last < _BELOW_FEE_LOG_SECONDS:
        logger.debug("Order %s lock %s is still below the refund sweep fee — no row", order_id, tx_hash)
        return
    if len(_below_fee_last_log) >= _BELOW_FEE_LOG_MAX:
        cutoff = now - _BELOW_FEE_LOG_SECONDS
        for stale in [k for k, v in _below_fee_last_log.items() if v < cutoff]:
            del _below_fee_last_log[stale]
        if len(_below_fee_last_log) >= _BELOW_FEE_LOG_MAX:
            _below_fee_last_log.clear()
    _below_fee_last_log[tx_hash] = now
    logger.info(
        "Order %s lock %s of %s AIT: lock value cannot cover the refund sweep fee — no row",
        order_id,
        tx_hash,
        lock_ait,
    )


def _units_to_ticks(units: int) -> int:
    """Chain units -> exchange ticks, floored — a lock's recorded cover can
    never exceed what was actually sent."""
    return (units * _TICKS_PER_UNIT) // _UNITS_PER_AIT


async def _scan_order_locks(cfg: ExchangeCfg, head: int | None) -> dict[str, int]:
    """Post ``order_funded`` for fresh escrow locks bound to orders; create
    ``order_refund`` rows for locks an order cannot take. Every processed
    lock tx is marked so re-scanning the full history is cheap — except a
    lock at/below the refund sweep fee (``below_fee``): it stays unmarked
    so a fee change can pick it back up, and its log line is rate-limited."""
    txs = await sellmon._fetch_transfers(cfg.escrow.escrow_address, limit=0)
    stats = {"scanned": 0, "funded": 0, "refunds": 0, "http_refused": 0}
    for tx in txs:
        recipient = tx.get("recipient") or tx.get("to") or ""
        if recipient.lower() != cfg.escrow.escrow_address.lower():
            continue
        if tx.get("block_height") is None:
            continue
        payload = tx.get("payload") or {}
        order_id = _exchange_order_id(payload.get("sell_quote"))
        if order_id is None:
            continue
        tx_hash = tx.get("tx_hash") or tx.get("hash") or ""
        if not tx_hash:
            continue
        stats["scanned"] += 1
        if monitor_mark(f"lock:{tx_hash}") is not None:
            continue
        sender = tx.get("sender") or tx.get("from") or ""
        order = _ro_one(
            cfg,
            "SELECT status, funded_state, backing_tx_hash, user_address FROM orders WHERE id = ?",
            (order_id,),
        )
        try:
            outcome = await _order_lock_outcome(cfg, order, tx, order_id, sender, tx_hash, head, stats)
        except Exception as e:
            logger.error("order-lock handling failed for %s on order %s: %s", tx_hash, order_id, e)
            continue  # unmarked — retried next poll
        if outcome is None or outcome == "below_fee":
            # Refused locks retry next poll; below-fee dust is deliberately
            # unmarked too — re-evaluating it each poll is cheap and a fee
            # change picks the lock back up.
            continue
        insert_monitor_mark(f"lock:{tx_hash}", detail=sender, outcome=outcome)
    return stats


async def _lock_refund(
    cfg: ExchangeCfg,
    order_id: int,
    sender: str,
    lock_ait: Decimal,
    tx_hash: str,
    stats: dict[str, int],
    *,
    owner_lock: bool = False,
) -> str:
    """order_refund for a lock the order can't take; counts the row."""
    if lock_ait <= _sweep_fee_ait():
        # Same caller-side bound _refund_stranded_locks applies to the lock
        # remainder: a lock worth less than its refund sweep stays in escrow
        # rather than draining the shared float each cycle. One check here
        # covers both inserts in _ensure_order_refund (-order_id and the
        # owner fallback), because it runs before either is attempted.
        _log_below_fee(order_id, tx_hash, lock_ait)
        return "below_fee"
    outcome = await _ensure_order_refund(cfg, order_id, sender, lock_ait, tx_hash, remainder=False, owner_lock=owner_lock)
    if outcome == "refunding":
        stats["refunds"] += 1
    return outcome


async def _order_lock_outcome(
    cfg: ExchangeCfg,
    order: Any,
    tx: dict[str, Any],
    order_id: int,
    sender: str,
    tx_hash: str,
    head: int | None,
    stats: dict[str, int],
) -> str | None:
    """The monitor-mark outcome for one escrow-bound lock tx — None when the
    endpoint refused non-terminally and the lock must stay unmarked."""
    lock_ait = units_to_ait(int(tx.get("value", 0) or 0))
    if order is None:
        return await _lock_refund(cfg, order_id, sender, lock_ait, tx_hash, stats)
    if _norm_tx_hash(order["backing_tx_hash"]) == _norm_tx_hash(tx_hash):
        return "recorded"
    owner_lock = _sender_owns_order(sender, order["user_address"])
    if order["status"] == "open" and order["funded_state"] == "unfunded" and owner_lock:
        event: dict[str, Any] = {
            "event": "order_funded",
            "order_id": order_id,
            "locked_ticks": _units_to_ticks(int(tx.get("value") or 0)),
            "backing_tx_hash": tx_hash,
        }
        if head is not None:
            event["head"] = head
        status_code, body = await _post_event(cfg, event)
        if status_code == 200:
            stats["funded"] += 1
            return "funded"
        if status_code in (404, 409):
            # Order gone or lock can't cover it — the AIT goes back.
            return await _lock_refund(cfg, order_id, sender, lock_ait, tx_hash, stats, owner_lock=True)
        # Any other refusal (5xx, 401/403, the flag-off 503) is transient or a
        # misconfiguration — marking it would drop the lock from the scan
        # forever and strand escrowed AIT with no refund row. Warn once per
        # poll and count it so a persistent refusal stays visible.
        stats["http_refused"] += 1
        logger.warning(
            "order_funded for lock %s on order %s refused with %s — left unmarked, retried next poll: %s",
            tx_hash,
            order_id,
            status_code,
            body,
        )
        return None
    return await _lock_refund(cfg, order_id, sender, lock_ait, tx_hash, stats, owner_lock=owner_lock)


def _sender_owns_order(sender: str, user_address: Any) -> bool:
    """A lock funds only its owner's order — a lock sent by anyone else is a
    stray and gets refunded to its sender, never credited as order backing."""
    try:
        return canonical_address(sender, strict=True) == canonical_address(str(user_address or ""), strict=True)
    except (TypeError, ValueError):
        return False


async def _ensure_order_refund(
    cfg: ExchangeCfg,
    order_id: int,
    sender: str,
    amount_ait: Decimal,
    tx_hash: str,
    *,
    remainder: bool,
    owner_lock: bool = False,
) -> str:
    """Create the order_refund row returning this lock to its sender.

    ref_id convention under UNIQUE(kind,ref_id): ``remainder=True`` — the
    order's own lock-remainder refund — keys on ``+order_id`` (one per order);
    ``remainder=False`` — a refund for an *inbound* lock the order could not
    take — keys on ``-order_id``, so a stranger's dust lock can never squat
    the row the owner's remainder refund needs. A stranger's second and later
    dust locks stay a logged duplicate — the one-refund-per-order bound keeps
    a dust spammer from draining the escrow's sweep-fee float.

    Squat residual (ETH-JOIN-2): when the ``-order_id`` slot is already held,
    an *owner*-sender lock (same sender check as crediting) still gets its
    refund — the row falls back to a lock-hash-derived ref_id below −2**59,
    disjoint from every order/trade id and deterministic per lock, so a
    re-scan dedupes onto it. A stranger's lock never gets the fallback."""
    if not sender:
        logger.error("Lock %s on order %s has no sender — cannot refund", tx_hash, order_id)
        return "no_sender"
    ref_id = order_id if remainder else -order_id
    row_id = insert_exchange_settlement(
        "order_refund",
        ref_id,
        seller_address=canonical_address(sender),
        amount_ait=amount_ait,
        fee_ait=Decimal(0),
    )
    lock_keyed = False
    if row_id is None and not remainder and owner_lock:
        normalized = _norm_tx_hash(tx_hash)
        if not normalized or any(c not in _HEX_CHARS for c in normalized):
            logger.error(
                "Order %s owner lock %r: tx hash is empty or not hex — cannot derive a lock-keyed refund ref_id; operator refund needed",
                order_id,
                tx_hash,
            )
            return "bad_tx_hash"
        ref_id = _lock_refund_ref_id(tx_hash)
        row_id = insert_exchange_settlement(
            "order_refund",
            ref_id,
            seller_address=canonical_address(sender),
            amount_ait=amount_ait,
            fee_ait=Decimal(0),
        )
        lock_keyed = row_id is not None
    if row_id is None:
        logger.error(
            "Order %s has a second stray lock %s — no free order_refund ref_id; operator refund needed for this lock",
            order_id,
            tx_hash,
        )
        return "duplicate"
    logger.warning(
        "Order %s cannot take lock %s (%s AIT from %s) — order_refund %s created%s",
        order_id,
        tx_hash,
        amount_ait,
        sender,
        row_id,
        f" (lock-keyed ref_id {ref_id} — -order_id slot held)" if lock_keyed else "",
    )
    return "refunding"


# ---------------------------------------------------------------------------
# Lane 2 — prepaid deposit scan
# ---------------------------------------------------------------------------


async def _scan_prepay_credits(cfg: ExchangeCfg) -> dict[str, int]:
    """Post ``prepaid_credit`` for exchange-prepay deposits. The
    ``exchange_monitor_marks`` table dedupes per tx hash: a 409 is
    recorded 'unattributable' (unregistered node) and a 400 'rejected'
    (deterministic refusal — bad tag text can never credit), so neither
    retries forever; 401/5xx stay unmarked for the next poll."""
    conn_rows = _bridge_db_prepay_rows()
    stats = {"scanned": 0, "credited": 0, "unattributable": 0, "rejected": 0}
    for tx_hash, node_address, amount_eth in conn_rows:
        stats["scanned"] += 1
        if monitor_mark(f"credit:{tx_hash}") is not None:
            continue
        if not node_address:
            # Tag carried no address at all — nothing to credit ever.
            insert_monitor_mark(f"credit:{tx_hash}", detail="", outcome="malformed_tag")
            logger.error("Exchange deposit %s carries an empty EXCHANGE_DEPOSIT tag — operator handling required", tx_hash)
            continue
        try:
            status_code, body = await _post_event(
                cfg,
                {
                    "event": "prepaid_credit",
                    "node_address": node_address,
                    "amount_eth": amount_eth,
                    "eth_tx_hash": tx_hash,
                },
            )
        except Exception as e:
            logger.error("prepaid_credit post failed for %s: %s", tx_hash, e)
            continue
        if status_code == 200:
            insert_monitor_mark(f"credit:{tx_hash}", detail=node_address, outcome="credited")
            stats["credited"] += 1
        elif status_code == 409:
            # Unregistered node — operator resolves the deposit deliberately.
            insert_monitor_mark(f"credit:{tx_hash}", detail=node_address, outcome="unattributable")
            stats["unattributable"] += 1
            logger.error(
                "Exchange deposit %s (%s ETH) is unattributable — node %s is not registered; operator handling required",
                tx_hash,
                amount_eth,
                node_address,
            )
        elif status_code == 400:
            # Deterministic refusal (malformed address hex etc.) — retrying
            # can never credit, so mark it and leave the money for an
            # operator refund instead of spamming the endpoint.
            insert_monitor_mark(f"credit:{tx_hash}", detail=node_address, outcome="rejected")
            stats["rejected"] += 1
            logger.error(
                "Exchange deposit %s (%s ETH) rejected by the endpoint — tag '%s' is not a valid address; operator handling required",
                tx_hash,
                amount_eth,
                node_address,
            )
        else:
            # 401/403/5xx — retryable next poll, leave unmarked.
            logger.error("prepaid_credit for %s refused with %s: %s", tx_hash, status_code, body)
    return stats


def _bridge_db_prepay_rows() -> list[tuple[str, str, str]]:
    """(tx_hash, tag_address, amount_eth) for exchange-prepay deposits —
    'exchange_prepay' rows whose recipient carries the raw
    ``EXCHANGE_DEPOSIT:<addr>`` tag the buyer typed. Synchronous sqlite on
    our own ledger DB."""
    conn = _connect_bridge_db()
    try:
        rows = conn.execute(
            "SELECT tx_hash, recipient, amount_eth FROM eth_deposits WHERE status = 'exchange_prepay'"
        ).fetchall()
    finally:
        conn.close()
    out: list[tuple[str, str, str]] = []
    for tx_hash, tag, amount_eth in rows:
        tag_text = str(tag or "")
        addr = tag_text.split(":", 1)[1].strip() if ":" in tag_text else ""
        out.append((str(tx_hash), addr, str(amount_eth)))
    return out


def _connect_bridge_db() -> sqlite3.Connection:
    from . import bridge_db

    return bridge_db._connect_db()


# ---------------------------------------------------------------------------
# Lane 3 — backing expiry / debit reconciliation / lock-remainder refunds
# ---------------------------------------------------------------------------


async def _expire_order_backings(cfg: ExchangeCfg, head: int | None, stats: dict[str, int]) -> None:
    """order_backing_expired events for open orders whose window lapsed."""
    if head is None:
        return
    for row in _ro_all(
        cfg,
        "SELECT id FROM orders WHERE status = 'open' AND funded_state != 'backing_expired' "
        "AND expiry_height IS NOT NULL AND expiry_height <= ?",
        (head,),
    ):
        try:
            status_code, _body = await _post_event(cfg, {"event": "order_backing_expired", "order_id": row["id"]})
            if status_code == 200:
                stats["expired"] += 1
        except Exception as e:
            logger.error("order_backing_expired post failed for order %s: %s", row["id"], e)


async def _refund_stranded_debits(cfg: ExchangeCfg, stats: dict[str, int]) -> None:
    """debit_refund events for open prepaid debits on closed orders."""
    for row in _ro_all(
        cfg,
        "SELECT d.order_id AS order_id FROM prepaid_debits d JOIN orders o ON o.id = d.order_id "
        "WHERE d.state = 'open' AND o.status != 'open'",
    ):
        try:
            status_code, _body = await _post_event(cfg, {"event": "debit_refund", "order_id": row["order_id"]})
            if status_code == 200:
                stats["debits"] += 1
        except Exception as e:
            logger.error("debit_refund post failed for order %s: %s", row["order_id"], e)


async def _refund_stranded_locks(cfg: ExchangeCfg, stats: dict[str, int]) -> None:
    """Funded SELL orders that closed without spending their whole lock. The
    remainder is locked_ait − Σ(trade draws); every trade consumes exactly
    its amount+fee from the lock regardless of outcome, so a live trade
    still owes its draw — refund only once none remain open."""
    for row in _ro_all(
        cfg,
        "SELECT id, user_address, locked_ticks, backing_tx_hash, funded_state, status FROM orders "
        "WHERE backing_tx_hash IS NOT NULL AND locked_ticks IS NOT NULL AND order_type = 'SELL' "
        "AND (status IN ('expired', 'cancelled', 'filled') OR funded_state = 'backing_expired')",
    ):
        order_id = int(row["id"])
        if get_exchange_settlement("order_refund", order_id) is not None:
            continue
        # Trade amounts are TEXT decimals — sum in Python for exactness.
        draws_rows = _ro_all(
            cfg,
            "SELECT amount, fee_ait FROM trades WHERE sell_order_id = ?",
            (order_id,),
        )
        draw_ait = Decimal(0)
        for d in draws_rows:
            draw_ait += Decimal(str(d["amount"])) + Decimal(str(d["fee_ait"] or "0"))
        live = _ro_one(
            cfg,
            "SELECT COUNT(*) FROM trades WHERE sell_order_id = ? AND "
            "settlement_state IS NOT NULL AND settlement_state NOT IN ('settled', 'refunded', 'failed')",
            (order_id,),
        )
        if live and int(live[0]):
            continue  # live settlements still owe their draw from the lock
        remaining_ait = Decimal(int(row["locked_ticks"])) / Decimal(_TICKS_PER_UNIT) - draw_ait
        if remaining_ait <= 0:
            continue
        if remaining_ait <= _sweep_fee_ait():
            # Dust: cumulative-difference fees can leave a remainder that
            # costs more in sweep fee than it returns — leave it in escrow.
            logger.info(
                "Order %s lock remainder %s AIT is at/below the %s AIT sweep fee — no order_refund",
                row["id"],
                remaining_ait,
                _sweep_fee_ait(),
            )
            continue
        sender = await _lock_sender(cfg, str(row["backing_tx_hash"]))
        outcome = await _ensure_order_refund(
            cfg, order_id, sender or str(row["user_address"]), remaining_ait, str(row["backing_tx_hash"]), remainder=True
        )
        if outcome == "refunding":
            stats["refunds"] += 1


async def _scan_backing(cfg: ExchangeCfg, head: int | None) -> dict[str, int]:
    """Expire order backing whose window lapsed, reconcile stranded BUY
    debits, and create order_refund rows for expired/cancelled funded SELL
    orders whose lock remainder is stranded once all their trades resolve."""
    stats = {"expired": 0, "debits": 0, "refunds": 0}
    await _expire_order_backings(cfg, head, stats)
    await _refund_stranded_debits(cfg, stats)
    await _refund_stranded_locks(cfg, stats)
    return stats


async def _lock_sender(cfg: ExchangeCfg, backing_tx_hash: str) -> str | None:
    """The recorded lock's sender — the refund goes to whoever sent it, not
    blindly to the order owner (same stranger-lock rule as the sell lane)."""
    try:
        txs = await sellmon._fetch_transfers(cfg.escrow.escrow_address)
    except Exception:
        return None
    for tx in txs:
        if _norm_tx_hash(tx.get("tx_hash") or tx.get("hash")) == _norm_tx_hash(backing_tx_hash):
            return tx.get("sender") or tx.get("from")
    return None


# ---------------------------------------------------------------------------
# Lane 4 — trade settlement driver
# ---------------------------------------------------------------------------

# The no-payout-address skip retries forever — a later registry entry
# self-heals — so the ERROR is rate-limited to one line per trade per hour
# and the rest of the polls drop to DEBUG (visible without flooding).
_NO_PAYOUT_LOG_SECONDS = 3600
_no_payout_last_log: dict[int, int] = {}


def _log_no_payout(trade_id: int, seller_address: str) -> None:
    now = int(time.monotonic())
    last = _no_payout_last_log.get(trade_id)
    if last is not None and now - last < _NO_PAYOUT_LOG_SECONDS:
        logger.debug("Trade %s still has no resolvable seller payout address — skipped", trade_id)
        return
    _no_payout_last_log[trade_id] = now
    logger.error(
        "Trade %s seller %s has no resolvable payout address (order snapshot and registry empty) "
        "— no settlement row; retried until one exists",
        trade_id,
        seller_address,
    )


def _ensure_trade_rows(cfg: ExchangeCfg) -> dict[str, int]:
    """Create kind='trade' ledger rows for exchange trades the mirror says
    are not finished. Denormalizes the fields the driver needs so the
    ledger survives exchange.db pruning."""
    created = 0
    no_payout_skipped = 0
    rows = _ro_all(
        cfg,
        "SELECT id, amount, total, fee_ait, buyer_address, seller_address, buy_order_id, sell_order_id, "
        "settlement_state FROM trades WHERE settlement_state IS NOT NULL AND "
        "settlement_state NOT IN ('settled', 'refunded', 'failed')",
    )
    for row in rows:
        trade_id = int(row["id"])
        if row["buy_order_id"] is None or row["sell_order_id"] is None:
            mark = f"unlinked-trade:{trade_id}"
            if monitor_mark(mark) is not None:
                continue
            # No row can ever be derived from a NULL link — mark terminal
            # once so the trade stops logging an ERROR every poll while it
            # waits for operator reconciliation.
            insert_monitor_mark(
                mark,
                detail=f"buy_order_id={row['buy_order_id']} sell_order_id={row['sell_order_id']}",
                outcome="no_order_links",
            )
            logger.error("Trade %s has no order links — no settlement row can be derived; marked terminal", trade_id)
            continue
        if get_exchange_settlement("trade", trade_id) is not None:
            continue
        sell_order = (
            _ro_one(
                cfg,
                "SELECT user_address, seller_eth_address FROM orders WHERE id = ?",
                (row["sell_order_id"],),
            )
            if row["sell_order_id"] is not None
            else None
        )
        buy_order = (
            _ro_one(
                cfg,
                "SELECT user_address FROM orders WHERE id = ?",
                (row["buy_order_id"],),
            )
            if row["buy_order_id"] is not None
            else None
        )
        seller_address = str((sell_order["user_address"] if sell_order else None) or row["seller_address"] or "")
        seller_eth = (sell_order["seller_eth_address"] if sell_order else None) or None
        if not seller_eth:
            reg = _ro_one(cfg, "SELECT eth_address FROM node_registry WHERE address = ?", (seller_address,))
            seller_eth = reg["eth_address"] if reg else None
        if not seller_eth:
            # No payout address yet — skip without a row or a mark: a seller
            # who registers one later settles on the next poll.
            no_payout_skipped += 1
            _log_no_payout(trade_id, seller_address)
            continue
        row_id = insert_exchange_settlement(
            "trade",
            trade_id,
            buy_order_id=row["buy_order_id"],
            sell_order_id=row["sell_order_id"],
            buyer_address=str((buy_order["user_address"] if buy_order else None) or row["buyer_address"] or ""),
            seller_address=seller_address,
            seller_eth_address=seller_eth,
            amount_ait=Decimal(str(row["amount"])),
            eth_amount=Decimal(str(row["total"])),
            fee_ait=Decimal(str(row["fee_ait"] or "0")),
        )
        if row_id is not None:
            created += 1
            logger.info("Recorded exchange settlement %s for trade %s", row_id, trade_id)
    return {"created": created, "no_payout_skipped": no_payout_skipped}


async def _update_with_retry(row_id: str, status: str, **fields: Any) -> bool:
    """Persist a settlement status with the ETH-9 retry discipline."""
    last_exc: Exception | None = None
    for attempt in range(wdm._STATUS_PERSIST_ATTEMPTS):
        try:
            return update_exchange_settlement(row_id, status, **fields)
        except Exception as e:
            last_exc = e
            logger.error(
                "Failed to persist settlement %s status %s (attempt %d/%d): %s",
                row_id,
                status,
                attempt + 1,
                wdm._STATUS_PERSIST_ATTEMPTS,
                e,
            )
            if attempt < wdm._STATUS_PERSIST_ATTEMPTS - 1:
                await asyncio.sleep(wdm._STATUS_PERSIST_DELAYS[attempt])
    raise RuntimeError(f"could not persist settlement {row_id} status {status}: {last_exc}")


async def _set_status_and_mirror(cfg: ExchangeCfg, row: dict[str, Any], status: str, **fields: Any) -> None:
    """Ledger transition + best-effort mirror — the ledger is truth and the
    mirror only ever follows it, so a mirror failure is logged, never
    raised. order_refund rows have no tape row (ref_id shares the
    order/trade int space) — mirroring one could post trade_state onto an
    unrelated trade, so they never mirror."""
    await _update_with_retry(str(row["id"]), status, **fields)
    if str(row.get("kind")) == "trade":
        await _mirror_trade_state(cfg, str(row["ref_id"]), status, row)


# Canonical replay lanes — the happy-path states the ledger actually walks.
# Hop-count minimisation (BFS) is *wrong* here: it happily replays
# locked→needs_review→refund_pending→…, painting a review state the tape
# never saw. Each lane walks only its canonical states; queue/review states
# are "positions" that resume onto the spine.
_NEXT_SETTLE = {
    "locked": "releasing",
    "queued_reserve": "releasing",
    "needs_review": "releasing",
    "releasing": "released",
    "needs_review_release": "released",
    "released": "settling",
    "queued_fee_settle": "settling",
    "needs_review_sweep": "settling",
    "settling": "settled",
}
_NEXT_REFUND = {
    "locked": "releasing",
    "queued_reserve": "releasing",
    "needs_review": "releasing",
    "releasing": "refund_pending",
    "released": "refund_pending",
    "needs_review_release": "refund_pending",
    "refund_pending": "refunding",
    "queued_fee_refund": "refunding",
    "needs_review_sweep": "refunding",
    "refunding": "refunded",
}
# Off-spine targets: the canonical spine state that can step onto them.
_REVIEW_PARENTS = {
    "needs_review": ("locked", "releasing"),
    "needs_review_release": ("releasing",),
    "queued_reserve": ("locked",),
    "queued_fee_settle": ("released",),
    "queued_fee_refund": ("refund_pending",),
    "needs_review_sweep": ("released", "settling", "refunding", "queued_fee_settle", "queued_fee_refund"),
}
_REFUND_TARGETS = frozenset({"refund_pending", "queued_fee_refund", "refunding", "refunded"})


def _mirror_path(current: str, target: str) -> list[str] | None:
    """The canonical lane path current→target, or None when the mirror is
    ahead of / off the ledger's lane (divergent — logged, never forced)."""
    if current == target:
        return []
    lane = _NEXT_REFUND if target in _REFUND_TARGETS else _NEXT_SETTLE

    def _walk(start: str, end: str) -> list[str] | None:
        path: list[str] = []
        state = start
        while state != end:
            nxt = lane.get(state)
            if nxt is None or nxt not in _MIRROR_FORWARD.get(state, frozenset()):
                return None
            path.append(nxt)
            state = nxt
            if len(path) > 8:
                return None
        return path

    if target in lane.values() or target in ("settled", "refunded"):
        return _walk(current, target)
    # Off-spine target (review/queue states): walk to a canonical parent,
    # then step on.
    for parent in _REVIEW_PARENTS.get(target, ()):
        sub = _mirror_path(current, parent)
        if sub is not None and target in _MIRROR_FORWARD.get(parent, frozenset()):
            return [*sub, target]
    # Direct-edge fallback (e.g. locked→needs_review).
    if target in _MIRROR_FORWARD.get(current, frozenset()):
        return [target]
    return None


async def _mirror_trade_state(cfg: ExchangeCfg, ref_id: str, target: str, row: dict[str, Any]) -> None:
    """Replay the mirror to the ledger's current state.

    A 409 means the mirror missed intermediate states — replay the missing
    path in order. Any divergence (mirror ahead, off-lane) is logged; the
    ledger never blocks on the mirror (user's C5 rule)."""
    trade_id = int(ref_id)
    mirror = _ro_one(cfg, "SELECT settlement_state FROM trades WHERE id = ?", (trade_id,))
    current = str(mirror["settlement_state"]) if mirror and mirror["settlement_state"] else "locked"
    if current == target:
        return
    path = _mirror_path(current, target)
    if not path:
        logger.error(
            "Settlement mirror for trade %s diverged: mirror %s, ledger %s — cannot replay; operator check",
            trade_id,
            current,
            target,
        )
        return
    hashes: dict[str, Any] = {}
    if row.get("eth_tx_hash"):
        hashes["eth_tx_hash"] = row["eth_tx_hash"]
    if row.get("settle_ait_tx_hash"):
        hashes["ait_tx_hash"] = row["settle_ait_tx_hash"]
    if row.get("settle_fee_tx_hash"):
        hashes["fee_tx_hash"] = row["settle_fee_tx_hash"]
    if row.get("refund_tx_hash"):
        hashes["ait_tx_hash"] = row["refund_tx_hash"]
    for state in path:
        try:
            status_code, body = await _post_event(
                cfg,
                {"event": "trade_state", "trade_id": trade_id, "state": state, **hashes},
            )
        except Exception as e:
            logger.error("Mirror post for trade %s -> %s failed: %s", trade_id, state, e)
            return
        if status_code != 200:
            # A refused step stops this replay; the next poll re-derives the
            # remaining path from the mirror's actual position.
            logger.error("Mirror post for trade %s -> %s refused %s: %s", trade_id, state, status_code, body)
            return


# --- ETH release (buyer's owed ETH → seller payout) --------------------------


async def _release_eth_for_settlement(cfg: ExchangeCfg, row: dict[str, Any]) -> None:
    """Send the trade's ETH cost to the seller's payout address — wdm
    machinery: estimated gas, shared-float reserve, deterministic hash +
    nonce persisted before broadcast."""
    seller_eth = str(row.get("seller_eth_address") or "")
    amount_eth = Decimal(str(row["eth_amount"]))
    if not seller_eth or not wdm._is_valid_eth_address(seller_eth):
        await _update_with_retry(
            str(row["id"]),
            "needs_review",
            error="seller has no valid payout address on file",
        )
        return
    gas_price = await wdm._eth_gas_price()
    gas_limit = await wdm._release_gas_limit(seller_eth, amount_eth)
    gas_cost = Decimal(gas_price * gas_limit) / Decimal(10**18)
    required = amount_eth + gas_cost
    balance = await wdm._eth_balance(wdm.ETH_WALLET_ADDRESS)
    available = balance - wdm._pending_eth_reserve()
    fraction_cap = balance * cfg.max_payout_fraction
    if amount_eth > cfg.max_eth_per_tx:
        await _update_with_retry(
            str(row["id"]),
            "queued_reserve",
            error=f"{amount_eth} ETH exceeds EXCHANGE_SETTLEMENT_MAX_ETH_PER_TX={cfg.max_eth_per_tx}",
        )
        return
    if amount_eth > fraction_cap:
        await _update_with_retry(
            str(row["id"]),
            "queued_reserve",
            error=f"{amount_eth} ETH exceeds BRIDGE_MAX_PAYOUT_FRACTION={cfg.max_payout_fraction} of float {balance}",
        )
        return
    if available - required < cfg.min_reserve_eth:
        await _update_with_retry(
            str(row["id"]),
            "queued_reserve",
            error=f"deficit — need {required} + {cfg.min_reserve_eth} reserve, have {available}",
        )
        return
    key, error = wdm._validate_release_key()
    if not key:
        raise RuntimeError(error)
    account = wdm.EthAccount.from_key(key)
    async with wdm.ETH_RELEASE_NONCE_LOCK:
        nonce = await wdm._eth_nonce(wdm.ETH_WALLET_ADDRESS)
        raw, eth_tx_hash = wdm._sign_release_tx(account, seller_eth, amount_eth, nonce, gas_price, gas_limit)
        await _update_with_retry(str(row["id"]), "releasing", eth_tx_hash=eth_tx_hash, release_nonce=nonce)
        sent = await wdm._broadcast_release_tx(raw)
    if sent.lower() != eth_tx_hash.lower():
        logger.warning("Broadcast reported %s; keeping signed hash %s", sent, eth_tx_hash)
    await _mirror_trade_state(cfg, str(row["ref_id"]), "releasing", {**row, "eth_tx_hash": eth_tx_hash})
    logger.info(
        "Settlement %s: broadcast %s ETH to %s (tx %s, gas %d) — awaiting receipt proof",
        row["id"],
        amount_eth,
        seller_eth,
        eth_tx_hash,
        gas_limit,
    )


async def _verify_settlement_release_outcome(row: dict[str, Any]) -> tuple[str, str]:
    """(outcome, reason) for the trade's ETH release — the shared ETH-9b
    composer (receipt at depth wins; nonce alone is never proof)."""
    fresh = get_exchange_settlement(str(row["kind"]), int(row["ref_id"]))
    if not fresh:
        return "unknown", "verify_error"
    # ait_tx_hash is only read for log context by the composer — give it a
    # readable label for this lane's rows.
    fresh.setdefault("ait_tx_hash", f"{row['kind']}:{row['ref_id']}")
    return await wdm._compose_release_outcome_detail(fresh)


# --- escrow sweeps (amount→buyer, fee→treasury; or lock→seller) --------------


def _sweep_fee_ait() -> Decimal:
    """Each escrow sweep spends the standard transfer fee on top."""
    return _FEE_AIT


def _inflight_sweep(exclude_id: str | None = None) -> bool:
    """Any unsealed escrow outflow — union of both tables sharing the
    escrow's nonce space. ``exclude_id`` lets a row continue to its next
    leg right after proving its own intent sealed."""
    other = get_exchange_inflight_sweep()
    if other is not None and str(other["id"]) != exclude_id:
        return True
    return get_sell_inflight_sweep() is not None


def _expected_sweep(cfg: ExchangeCfg, row: dict[str, Any]) -> tuple[str, int, str]:
    """(recipient, amount_units, exs_ref) the row's in-flight escrow outflow
    must match — the current leg: settle leg1 amount→buyer while
    settle_ait_tx_hash is empty, leg2 fee→treasury after; refund legs send
    amount+fee (order_refund rows carry fee 0 = the whole lock)."""
    if row["status"] in ("settling", "queued_fee_settle"):
        if row.get("settle_ait_tx_hash"):
            return (
                canonical_address(cfg.escrow.treasury_address),
                ait_to_units(Decimal(str(row["fee_ait"] or 0))),
                str(row["id"]),
            )
        return canonical_address(str(row["buyer_address"])), ait_to_units(Decimal(str(row["amount_ait"]))), str(row["id"])
    return (
        canonical_address(str(row["seller_address"])),
        ait_to_units(Decimal(str(row["amount_ait"])) + Decimal(str(row["fee_ait"] or 0))),
        str(row["id"]),
    )


async def _find_escrow_outflow(cfg: ExchangeCfg, nonce: int, to_address: str, amount_units: int, exs_ref: str) -> dict | None:
    """The sealed escrow outflow this row's intent produced — nonce AND
    recipient AND amount AND ``payload.exs_ref`` must all match, so a
    foreign transaction at the same nonce can never be credited here."""
    txs = await sellmon._fetch_transfers(cfg.escrow.escrow_address)
    for tx in txs:
        if tx.get("block_height") is None:
            continue
        sender = (tx.get("sender") or tx.get("from") or "").lower()
        if sender != cfg.escrow.escrow_address.lower():
            continue
        tx_nonce = tx.get("nonce")
        if tx_nonce is None or int(tx_nonce) != nonce:
            continue
        recipient = (tx.get("recipient") or tx.get("to") or "").lower()
        payload = tx.get("payload") or {}
        if recipient == to_address.lower() and int(tx.get("value") or 0) == amount_units and payload.get("exs_ref") == exs_ref:
            return tx
    return None


async def _escrow_sweep(
    cfg: ExchangeCfg,
    row: dict[str, Any],
    intent_status: str,
    fee_park_status: str,
) -> str:
    """Start the row's next escrow outflow — serialized across both sweep
    lanes, float-checked, intent persisted before broadcast (ETH-9)."""
    if _inflight_sweep():
        logger.info("Settlement %s: escrow sweep deferred — another sweep in flight", row["id"])
        return "deferred"
    to_address, amount_units, exs_ref = _expected_sweep(cfg, row)
    amount_ait = units_to_ait(amount_units)
    nonce, balance = await sellmon._account_view(cfg.escrow.escrow_address)
    required = amount_ait + _sweep_fee_ait()
    if balance < required:
        deficit = required - balance
        await _update_with_retry(
            str(row["id"]),
            fee_park_status,
            error=f"escrow fee float deficit {deficit} AIT (need {required}, have {balance})",
        )
        return "fee_parked"
    signed_tx = await sellmon._sign_escrow_transfer(
        cfg.escrow, to_address, amount_ait, {"exs_ref": exs_ref, "reason": row["status"]}, nonce
    )
    await _update_with_retry(str(row["id"]), intent_status, escrow_out_nonce=nonce, escrow_out_tx=json.dumps(signed_tx))
    tx_hash = await sellmon._broadcast_ait_tx(signed_tx)
    logger.info(
        "Settlement %s: escrow sweep broadcast (%s AIT -> %s, nonce %d, tx %s) — awaiting seal",
        row["id"],
        amount_ait,
        to_address,
        nonce,
        tx_hash,
    )
    return "sent"


async def _resolve_sweep(cfg: ExchangeCfg, row: dict[str, Any]) -> None:
    """Resolve an in-flight 'settling'/'refunding' intent, or start the next
    leg / next sweep when the intent slot is stale.

    Terminal status comes only from the chain: the sealed outflow matching
    nonce+recipient+amount+exs_ref. Settle is two legs — leg1 (amount→buyer)
    sealing triggers leg2 (fee→treasury): sign first, then ONE update
    records leg1's hash and leg2's intent together, so the intent fields
    always describe the currently unsealed leg."""
    row_id = str(row["id"])
    status = str(row["status"])
    if status == "queued_fee_settle" and _expected_sweep(cfg, row)[1] <= 0:
        # A row parked by an older build with a zero/sub-unit fee — no fee
        # leg is owed, settle straight away.
        await _set_status_and_mirror(cfg, row, "settled")
        return
    if status in ("queued_fee_settle", "queued_fee_refund"):
        # Fee-float park — retry the same leg's sweep initiation.
        intent = "settling" if status == "queued_fee_settle" else "refunding"
        await _escrow_sweep(cfg, row, intent, status)
        return
    nonce = row.get("escrow_out_nonce")
    if nonce is None:
        # No live intent — start this leg's sweep (settle leg1 after
        # 'released', or a refund sweep from 'refund_pending').
        await _escrow_sweep(cfg, row, status, "queued_fee_settle" if status == "settling" else "queued_fee_refund")
        return
    to_address, amount_units, exs_ref = _expected_sweep(cfg, row)
    outflow = await _find_escrow_outflow(cfg, int(nonce), to_address, amount_units, exs_ref)
    if outflow is not None:
        await _handle_sealed_sweep(cfg, row, outflow)
        return
    # No matching sealed outflow: consumed nonce by a foreign tx is
    # undecidable → needs_review_sweep; a still-free nonce means the
    # broadcast never landed → re-broadcast the stored blob (identical
    # signature, never a second payment).
    account_nonce, _balance = await sellmon._account_view(cfg.escrow.escrow_address)
    if account_nonce > int(nonce):
        await _update_with_retry(
            row_id,
            "needs_review_sweep",
            error=f"escrow nonce {nonce} consumed by an unmatched transaction",
        )
        logger.error("Settlement %s: escrow nonce %d sealed to an unmatched tx — needs review", row_id, nonce)
        return
    stored = row.get("escrow_out_tx")
    if not stored:
        await _update_with_retry(row_id, "needs_review_sweep", error="escrow sweep blob missing")
        return
    tx_hash = await sellmon._broadcast_ait_tx(json.loads(stored))
    logger.info("Settlement %s: re-broadcast stored %s blob (tx %s) — still in flight", row_id, status, tx_hash)


async def _handle_sealed_sweep(cfg: ExchangeCfg, row: dict[str, Any], outflow: dict[str, Any]) -> None:
    """The sealed outflow matching this row's intent — terminal status for
    refunds, leg-1→leg-2 advance for settles, or the fee-leg seal.

    Leg 1 sealing triggers leg 2: sign first, then ONE update records
    leg1's hash and leg2's intent together, so the intent fields always
    describe the currently unsealed leg."""
    row_id = str(row["id"])
    status = str(row["status"])
    nonce = row.get("escrow_out_nonce")
    sealed_hash = outflow.get("tx_hash") or outflow.get("hash")
    if status == "refunding":
        await _set_status_and_mirror(cfg, row, "refunded", refund_tx_hash=sealed_hash)
        logger.info("Settlement %s: refund sealed at escrow nonce %d", row_id, nonce)
        return
    if not row.get("settle_ait_tx_hash"):
        # Leg 1 sealed — sign leg 2 and persist (hash + new intent) in
        # one update, then broadcast. A crash before the update replays
        # the whole step next poll: leg2 is never broadcast unsigned.
        # Another lane may still hold an unsigned intent at the same
        # nonce — leg-2 defers in that case; the sealed leg-1 outflow is
        # simply re-found next poll.
        if _inflight_sweep(exclude_id=row_id):
            logger.info("Settlement %s: fee leg deferred — another sweep in flight", row_id)
            return
        to2, amount2, ref2 = _expected_sweep(cfg, {**row, "settle_ait_tx_hash": sealed_hash})
        if amount2 <= 0:
            # EXCHANGE_FEE_PCT=0 or a fee under one chain unit — sending
            # leg 2 would be a zero-value transfer; leg 1 alone settles.
            await _set_status_and_mirror(cfg, row, "settled", settle_ait_tx_hash=sealed_hash)
            logger.info("Settlement %s: leg 1 sealed, no fee owed — settled", row_id)
            return
        nonce2, balance = await sellmon._account_view(cfg.escrow.escrow_address)
        leg2_ait = units_to_ait(amount2)
        if balance < leg2_ait + _sweep_fee_ait():
            await _update_with_retry(
                row_id,
                "queued_fee_settle",
                settle_ait_tx_hash=sealed_hash,
                error=f"escrow fee float deficit before fee leg (need {leg2_ait + _sweep_fee_ait()}, have {balance})",
            )
            return
        signed2 = await sellmon._sign_escrow_transfer(
            cfg.escrow, to2, leg2_ait, {"exs_ref": ref2, "reason": "settle_fee"}, nonce2
        )
        await _update_with_retry(
            row_id,
            "settling",
            settle_ait_tx_hash=sealed_hash,
            escrow_out_nonce=nonce2,
            escrow_out_tx=json.dumps(signed2),
        )
        tx_hash2 = await sellmon._broadcast_ait_tx(signed2)
        logger.info("Settlement %s: fee leg broadcast (tx %s, nonce %d)", row_id, tx_hash2, nonce2)
        return
    await _set_status_and_mirror(cfg, row, "settled", settle_fee_tx_hash=sealed_hash)
    logger.info("Settlement %s: fee leg sealed — settled", row_id)


async def _mirror_pass(cfg: ExchangeCfg) -> int:
    """Replay the mirror for every trade-kind ledger row, including terminal
    ones — a transition-time post that failed would otherwise leave the
    tape behind forever once the row leaves the open worklist."""
    conn = _connect_bridge_db()
    try:
        rows = conn.execute(
            "SELECT id, kind, ref_id, status, eth_tx_hash, settle_ait_tx_hash, settle_fee_tx_hash, refund_tx_hash "
            "FROM exchange_settlements WHERE kind = 'trade'"
        ).fetchall()
    finally:
        conn.close()
    mirrored = 0
    for r in rows:
        row = {
            "id": r[0],
            "kind": r[1],
            "ref_id": r[2],
            "status": r[3],
            "eth_tx_hash": r[4],
            "settle_ait_tx_hash": r[5],
            "settle_fee_tx_hash": r[6],
            "refund_tx_hash": r[7],
        }
        await _mirror_trade_state(cfg, str(row["ref_id"]), str(row["status"]), row)
        mirrored += 1
    return mirrored


# --- per-status handlers -----------------------------------------------------


async def _handle_locked(cfg: ExchangeCfg, row: dict[str, Any]) -> None:
    """'locked'/'queued_reserve': admit the trade to the ETH release —
    valid payout address, caps, shared-float reserve, then intent-before-
    broadcast release."""
    try:
        await _release_eth_for_settlement(cfg, row)
    except Exception as e:
        logger.error("ETH release failed for settlement %s: %s", row["id"], e)
        await _resolve_release_failure(cfg, row, e)


async def _resolve_release_failure(cfg: ExchangeCfg, row: dict[str, Any], exc: Exception) -> None:
    """Refund only on positive proof the release never sent."""
    outcome, _reason = await _verify_settlement_release_outcome(row)
    if outcome == "sent":
        logger.warning("Settlement %s: ETH release confirmed despite error (%s)", row["id"], exc)
        await _set_status_and_mirror(cfg, row, "released")
    elif outcome == "not_sent":
        await _update_with_retry(str(row["id"]), "refund_pending", error=f"release failed: {exc}")
        await _mirror_trade_state(cfg, str(row["ref_id"]), "refund_pending", row)
        await _start_refund(cfg, row, f"release failed: {exc}")
    else:
        await _update_with_retry(str(row["id"]), "needs_review", error=f"release outcome unverifiable: {exc}")
        logger.error("Settlement %s marked needs_review — release outcome unverifiable: %s", row["id"], exc)


async def _handle_inflight(cfg: ExchangeCfg, row: dict[str, Any]) -> None:
    """'releasing'/'needs_review'/'needs_review_release': the ETH-9b resume
    check — sent → released, proven unsent → refund path, unknown → stays
    (needs_review rows park but keep re-verifying every poll)."""
    outcome, reason = await _verify_settlement_release_outcome(row)
    if outcome == "sent":
        await _set_status_and_mirror(cfg, row, "released")
        logger.info("Settlement %s: ETH release confirmed on chain", row["id"])
    elif outcome == "not_sent":
        await _set_status_and_mirror(cfg, row, "refund_pending", error="release never reached the chain")
        await _start_refund(cfg, row, "release never reached the chain")
    else:
        if row["status"] not in ("needs_review", "needs_review_release"):
            await _set_status_and_mirror(cfg, row, "needs_review", error="release outcome unverifiable")
        if reason == "absent_in_grace":
            logger.warning(
                "Settlement %s (%s) not yet visible on-chain — inside absence grace; parked",
                row["id"],
                row["status"],
            )
        else:
            logger.error("Settlement %s (%s) still unverifiable — needs review", row["id"], row["status"])


async def _handle_released(cfg: ExchangeCfg, row: dict[str, Any]) -> None:
    """'released': re-verify the receipt each poll; on 'sent' start the
    settle sweeps, on 'not_sent' (reorg/dropped) refund the lock."""
    outcome, _reason = await _verify_settlement_release_outcome(row)
    if outcome == "sent":
        await _escrow_sweep(cfg, {**row, "status": "settling"}, "settling", "queued_fee_settle")
    elif outcome == "not_sent":
        await _set_status_and_mirror(cfg, row, "refund_pending", error="release transaction dropped or reverted")
        await _start_refund(cfg, row, "release transaction dropped or reverted")


async def _start_refund(cfg: ExchangeCfg, row: dict[str, Any], reason: str) -> None:
    """Initiate the escrow refund sweep for this row (retriable until the
    intent persists; in-flight rows belong to the resolver)."""
    try:
        await _escrow_sweep(cfg, {**row, "status": "refunding"}, "refunding", "queued_fee_refund")
        return
    except Exception as e:
        logger.error("Refund sweep errored for settlement %s: %s", row["id"], e)
    fresh = get_exchange_settlement(str(row["kind"]), int(row["ref_id"])) or {}
    if fresh.get("status") == "refunding":
        logger.error("Settlement %s: refund broadcast threw post-intent — the resolver will prove it", row["id"])


async def _process_settlement(cfg: ExchangeCfg, row: dict[str, Any]) -> None:
    kind = str(row["kind"])
    status = str(row["status"])
    if status == "needs_review_sweep":
        # Terminal for the machine — only an operator moves it.
        return
    if kind == "order_refund":
        # No ETH leg, no mirror: locked → refund sweep → refunded.
        if status in ("locked", "refund_pending", "queued_fee_refund"):
            await _start_refund(cfg, row, "order refund")
        elif status == "refunding":
            await _resolve_sweep(cfg, row)
        return
    handler = _TRADE_STATUS_HANDLERS.get(status)
    if handler is not None:
        await handler(cfg, row)


_TRADE_STATUS_HANDLERS: dict[str, Callable[[ExchangeCfg, dict[str, Any]], Awaitable[None]]] = {
    "locked": _handle_locked,
    "queued_reserve": _handle_locked,
    "releasing": _handle_inflight,
    "needs_review": _handle_inflight,
    "needs_review_release": _handle_inflight,
    "released": _handle_released,
    "settling": _resolve_sweep,
    "refunding": _resolve_sweep,
    "refund_pending": lambda cfg, row: _start_refund(cfg, row, str(row.get("error") or "refund")),
    "queued_fee_settle": _resolve_sweep,
    "queued_fee_refund": _resolve_sweep,
}


# ---------------------------------------------------------------------------
# Poll loop
# ---------------------------------------------------------------------------


def _settlement_preflight() -> tuple[ExchangeCfg | None, str | None]:
    """The env/key gate every poll passes: returns (cfg, None) when the lane
    may run, else (None, the skip reason the summary reports verbatim)."""
    enabled, reason = exchange_config_status()
    if not enabled:
        return None, reason
    try:
        cfg = _exchange_config()
    except ValueError as e:
        return None, str(e)
    key_error = sellmon._validate_escrow_key(cfg.escrow)
    if key_error:
        return None, key_error
    if not wdm.ETH_WALLET_ADDRESS:
        return None, "ETH_WALLET_ADDRESS not set"
    return cfg, None


async def _run_lane(summary: dict[str, Any], key: str, label: str, awaitable: Any) -> None:
    """One poll lane: a failure lands in the summary as 'failed: …' and is
    logged — the other lanes still run."""
    try:
        summary[key] = await awaitable
    except Exception as e:
        logger.error("%s failed this poll: %s", label, e)
        summary[key] = f"failed: {e}"


async def _drain_open_settlements(cfg: ExchangeCfg, summary: dict[str, Any]) -> None:
    # In-flight sweeps resolve first — a sealed outflow frees the
    # serialized escrow slot before any new sweep initiation runs.
    open_rows = get_open_exchange_settlements()
    worklist = [r for r in open_rows if r["status"] in ("settling", "refunding")]
    worklist += [r for r in open_rows if r["status"] not in ("settling", "refunding")]
    processed = 0
    for row in worklist:
        try:
            await _process_settlement(cfg, row)
            processed += 1
        except Exception as e:
            logger.error("Error processing settlement %s: %s", row.get("id"), e)
    summary["processed"] = processed


async def poll_exchange_settlements_once() -> dict[str, Any]:
    """Run a single settlement poll cycle."""
    cfg, skip_reason = _settlement_preflight()
    if cfg is None:
        return {"skipped": True, "reason": skip_reason}

    _ensure_db()
    summary: dict[str, Any] = {"skipped": False}

    try:
        head: int | None = await sellmon._chain_height()
    except Exception as e:
        logger.error("Chain height unavailable — expiry lane skipped this poll: %s", e)
        head = None

    await _run_lane(summary, "locks", "Escrow lock scan", _scan_order_locks(cfg, head))
    await _run_lane(summary, "credits", "Prepay scan", _scan_prepay_credits(cfg))
    await _run_lane(summary, "backing", "Backing scan", _scan_backing(cfg, head))

    try:
        new_rows = _ensure_trade_rows(cfg)
        summary["new_rows"] = {"created": new_rows["created"]}
        summary["no_payout_skipped"] = new_rows["no_payout_skipped"]
    except Exception as e:
        logger.error("Trade-row ensure failed this poll: %s", e)
        summary["new_rows"] = f"failed: {e}"

    await _drain_open_settlements(cfg, summary)
    await _run_lane(summary, "mirrored", "Mirror pass", _mirror_pass(cfg))
    return summary


async def exchange_settlement_loop() -> None:
    """Main loop for the exchange settlement monitor."""
    enabled, reason = exchange_config_status()
    if not enabled:
        logger.info("Exchange settlement monitor disabled: %s", reason)
        return
    try:
        cfg = _exchange_config()
    except ValueError as e:
        logger.error("Exchange settlement monitor refused to start: %s", e)
        return
    key_error = sellmon._validate_escrow_key(cfg.escrow)
    if key_error:
        logger.error("Exchange settlement monitor disabled: %s", key_error)
        return
    _ensure_db()
    logger.info(
        "Starting exchange settlement monitor (escrow %s, endpoint %s)",
        cfg.escrow.escrow_address,
        cfg.exchange_url,
    )
    logger.info("Exchange settlement poll interval: %ss", cfg.poll_interval)
    while True:
        if not _exchange_polling_enabled:
            logger.info("Exchange settlement auto-poll disabled, sleeping")
            await asyncio.sleep(1)
            continue
        try:
            summary = await poll_exchange_settlements_once()
            if not summary.get("skipped"):
                logger.info("Exchange settlement poll completed: %s", summary)
        except Exception as e:
            logger.error("Error in exchange settlement loop: %s", e)
        for _ in range(cfg.poll_interval):
            if not _exchange_polling_enabled:
                break  # type: ignore[unreachable]
            await asyncio.sleep(1)


def start_exchange_settlement_monitoring() -> asyncio.Task[None] | None:
    """Start the exchange settlement monitor as an asyncio task — one
    disabled log line and None when unconfigured. Never falls back to
    another key."""
    enabled, reason = exchange_config_status()
    if not enabled:
        logger.info("Exchange settlement monitor disabled: %s", reason)
        return None
    try:
        _exchange_config()
    except ValueError as e:
        logger.error("Exchange settlement monitor refused to start: %s", e)
        return None
    try:
        task = asyncio.create_task(exchange_settlement_loop())
        return task
    except RuntimeError:
        logger.debug("No event loop running; starting exchange settlement monitor in a thread", exc_info=True)
        import threading

        def _run_sync() -> None:
            asyncio.run(exchange_settlement_loop())

        monitor_thread = threading.Thread(target=_run_sync, daemon=True)
        monitor_thread.start()
        return None


def set_exchange_polling_enabled(enabled: bool) -> None:
    global _exchange_polling_enabled
    _exchange_polling_enabled = enabled
