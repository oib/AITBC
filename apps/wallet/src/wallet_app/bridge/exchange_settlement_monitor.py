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
import os
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from aitbc.aitbc_logging import get_logger
from aitbc.async_tasks import create_task_with_logging
from aitbc.constants import DATA_DIR
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.utils import units_to_ait

from . import bridge_withdraw_monitor as wdm
from . import sell_escrow_monitor as sellmon
from .bridge_db import (
    get_exchange_settlement,
    get_open_exchange_settlements,
    init_db,
    insert_exchange_settlement,
    insert_monitor_mark,
    monitor_mark,
)
from .exchange_settlement_driver import (
    _FEE_AIT as _FEE_AIT,
    _MIRROR_FORWARD as _MIRROR_FORWARD,
    _NEXT_REFUND as _NEXT_REFUND,
    _NEXT_SETTLE as _NEXT_SETTLE,
    _NO_PAYOUT_LOG_SECONDS as _NO_PAYOUT_LOG_SECONDS,
    _REFUND_TARGETS as _REFUND_TARGETS,
    _REVIEW_PARENTS as _REVIEW_PARENTS,
    _TRADE_STATUS_HANDLERS as _TRADE_STATUS_HANDLERS,
    _ensure_trade_rows as _ensure_trade_rows,
    _escrow_sweep as _escrow_sweep,
    _expected_sweep as _expected_sweep,
    _find_escrow_outflow as _find_escrow_outflow,
    _handle_inflight as _handle_inflight,
    _handle_locked as _handle_locked,
    _handle_released as _handle_released,
    _handle_sealed_sweep as _handle_sealed_sweep,
    _inflight_sweep as _inflight_sweep,
    _log_no_payout as _log_no_payout,
    _mirror_pass as _mirror_pass,
    _mirror_path as _mirror_path,
    _mirror_trade_state as _mirror_trade_state,
    _no_payout_last_log as _no_payout_last_log,
    _process_settlement as _process_settlement,
    _release_eth_for_settlement as _release_eth_for_settlement,
    _resolve_release_failure as _resolve_release_failure,
    _resolve_sweep as _resolve_sweep,
    _set_status_and_mirror as _set_status_and_mirror,
    _start_refund as _start_refund,
    _sweep_fee_ait as _sweep_fee_ait,
    _update_with_retry as _update_with_retry,
    _verify_settlement_release_outcome as _verify_settlement_release_outcome,
)

logger = get_logger(__name__)

_db_initialized = False
_exchange_polling_enabled: bool = True

# Exchange ticks are 1e8 per AIT; chain units are 3.6e7 per AIT. Lock values
# arrive in chain units — the conversion floors (a lock can never be credited
# more cover than it actually carries).
_TICKS_PER_UNIT = 100_000_000
_UNITS_PER_AIT = 36_000_000

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


def _lock_refund_ref_id(tx_hash: str) -> int | None:
    """ref_id for an owner-sender inbound refund whose ``−order_id`` slot is
    already held: a deterministic negative derived from the lock hash and
    bounded below −2**59. Order ids are small positives, so the range can
    never collide with a ``+order_id`` remainder refund, a ``−order_id``
    inbound refund, or a trade id — and a re-scan derives the same id, so
    the UNIQUE pair dedupes instead of writing a second row. Fails closed:
    an empty or non-hex hash returns None, and the caller treats that like
    a held slot (duplicate → operator review)."""
    normalized = _norm_tx_hash(tx_hash)
    if not normalized or any(c not in _HEX_CHARS for c in normalized):
        return None
    return -(int(normalized[:15], 16) | (1 << 59))


def _units_to_ticks(units: int) -> int:
    """Chain units -> exchange ticks, floored — a lock's recorded cover can
    never exceed what was actually sent."""
    return (units * _TICKS_PER_UNIT) // _UNITS_PER_AIT


async def _scan_order_locks(cfg: ExchangeCfg, head: int | None) -> dict[str, int]:
    """Post ``order_funded`` for fresh escrow locks bound to orders; create
    ``order_refund`` rows for locks an order cannot take. Every processed
    lock tx is marked so re-scanning the full history is cheap — including a
    lock at/below the refund sweep fee (``below_fee``): the mark is terminal,
    logged once at WARNING and left for operator review rather than re-evaluated
    every poll."""
    txs = await sellmon._fetch_transfers(cfg.escrow.escrow_address, limit=0)
    stats = {"scanned": 0, "funded": 0, "refunds": 0, "http_refused": 0}
    for tx in txs:
        recipient = tx.get("recipient") or tx.get("to") or ""
        if recipient.lower() != cfg.escrow.escrow_address.lower():
            continue
        if not wdm.tx_sealed_confirmed(tx):
            continue  # not sealed, or sealed-but-failed — no value moved (#1916)
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
        except Exception as e:  # noqa: BLE001 - unmarked item retried next poll — a failed lock must not kill the lane
            logger.error("order-lock handling failed for %s on order %s: %s", tx_hash, order_id, e)
            continue  # unmarked — retried next poll
        if outcome is None:
            # Refused locks retry next poll. below_fee marks like every
            # other terminal outcome — a permanent dust lock must not be
            # re-evaluated forever (CLEAN-1); the mark keeps it visible
            # for operator review instead of silently stranding it.
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
        # The "below_fee" outcome marks the lock — terminal, not retried
        # (CLEAN-1; an endless re-eval silently stranded the escrowed AIT).
        logger.warning(
            "Order %s inbound lock %s of %s AIT is at/below the %s AIT refund sweep fee — no order_refund; operator review",
            order_id,
            tx_hash,
            lock_ait,
            _sweep_fee_ait(),
        )
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
        lock_ref = _lock_refund_ref_id(tx_hash)
        if lock_ref is None:
            logger.error(
                "Order %s owner lock %r: tx hash is empty or not hex — cannot derive a lock-keyed refund ref_id; operator refund needed",
                order_id,
                tx_hash,
            )
            return "duplicate"
        ref_id = lock_ref
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
        except Exception as e:  # noqa: BLE001 - post failure retried next poll
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
        except Exception as e:  # noqa: BLE001 - event post failure logged, poll continues
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
        except Exception as e:  # noqa: BLE001 - event post failure logged, poll continues
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
    except Exception:  # noqa: BLE001 - probe containment — unreadable means unproven
        return None
    for tx in txs:
        if _norm_tx_hash(tx.get("tx_hash") or tx.get("hash")) == _norm_tx_hash(backing_tx_hash):
            return tx.get("sender") or tx.get("from")
    return None


# ---------------------------------------------------------------------------
# Lane 4 — trade settlement driver
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
    except Exception as e:  # noqa: BLE001 - lane containment — other lanes still run
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
        except Exception as e:  # noqa: BLE001 - row containment — one bad settlement must not kill the drain
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
    except Exception as e:  # noqa: BLE001 - height probe containment — lane skipped this poll
        logger.error("Chain height unavailable — expiry lane skipped this poll: %s", e)
        head = None

    await _run_lane(summary, "locks", "Escrow lock scan", _scan_order_locks(cfg, head))
    await _run_lane(summary, "credits", "Prepay scan", _scan_prepay_credits(cfg))
    await _run_lane(summary, "backing", "Backing scan", _scan_backing(cfg, head))

    try:
        new_rows = _ensure_trade_rows(cfg)
        summary["new_rows"] = {"created": new_rows["created"]}
        summary["no_payout_skipped"] = new_rows["no_payout_skipped"]
    except Exception as e:  # noqa: BLE001 - lane containment
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
                # INFO on settlements processed, rows created, or a
                # new_rows failure string; DEBUG on routine empty polls.
                new_rows = summary.get("new_rows")
                did_work = (
                    summary.get("processed", 0) > 0
                    or (isinstance(new_rows, dict) and new_rows.get("created", 0) > 0)
                    or isinstance(new_rows, str)
                )
                log = logger.info if did_work else logger.debug
                log("Exchange settlement poll completed: %s", summary)
        except Exception as e:  # noqa: BLE001 - poll containment — a failed pass must not end the monitor loop
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
        task = create_task_with_logging(exchange_settlement_loop(), name="exchange_settlement_monitor")
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
