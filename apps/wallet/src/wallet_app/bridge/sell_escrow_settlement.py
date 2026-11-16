"""Sell-escrow settlement decisions — split out of ``sell_escrow_monitor.py`` (#1860).

This module holds the escrow sweep legs (settle → treasury, refund → shop),
the ETH-release path that reuses the ETH-9/9b machinery, and the per-status
lock handlers. ``sell_escrow_monitor`` re-exports every name here, so
``sell_escrow_monitor.<name>`` keeps resolving for callers and tests.

Cross-module seam: the handful of helpers this lane shares with the
monitor's lifecycle side (the RPC readers ``_fetch_transfers`` /
``_account_view`` / ``_broadcast_ait_tx`` / ``_chain_height``, the patched
DB write ``update_sell_lock_status``, the price feed ``get_eth_prices_fresh``,
``_lock_age_seconds`` and the key-slot loader ``_load_escrow_key``) stay
defined on ``sell_escrow_monitor`` and are reached through the deferred
delegates below — resolving them at call time keeps
``patch("...sell_escrow_monitor.<name>")`` working exactly as before the
split.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from wallet_app.utc_time import parse_stored, utc_now

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.utils import ait_to_units
from aitbc.utils.units import DEFAULT_TX_FEE_AIT

from . import bridge_withdraw_monitor as wdm
from .bridge_db import (
    get_sell_eth_committed_since,
    get_sell_inflight_sweep,
    get_sell_lock_by_ait_tx_hash,
    get_sell_lock_by_quote_id,
    get_sell_quote,
    update_sell_quote_status,
)
from .price_api import apply_bridge_fee, calculate_eth_amount

if TYPE_CHECKING:
    from .sell_escrow_monitor import SellConfig

# Same logger name as the monitor module so journal lines keep their tag.
logger = get_logger("wallet_app.bridge.sell_escrow_monitor")


def update_sell_lock_status(ait_tx_hash: str, status: str, **fields: Any) -> bool:
    """Deferred delegate to ``sell_escrow_monitor.update_sell_lock_status`` —
    the tests' flaky-write stub is patched onto that module, so the delegate
    must read the attribute at call time."""
    from . import sell_escrow_monitor as _sem

    return _sem.update_sell_lock_status(ait_tx_hash, status, **fields)


async def get_eth_prices_fresh() -> dict[str, Any] | None:
    """Deferred delegate to ``sell_escrow_monitor.get_eth_prices_fresh``."""
    from . import sell_escrow_monitor as _sem

    return await _sem.get_eth_prices_fresh()


async def _fetch_transfers(address: str, limit: int = 0) -> list[dict[str, Any]]:
    """Deferred delegate to ``sell_escrow_monitor._fetch_transfers``."""
    from . import sell_escrow_monitor as _sem

    return await _sem._fetch_transfers(address, limit=limit)


async def _account_view(address: str) -> tuple[int, Decimal]:
    """Deferred delegate to ``sell_escrow_monitor._account_view``."""
    from . import sell_escrow_monitor as _sem

    return await _sem._account_view(address)


async def _broadcast_ait_tx(signed_tx: dict[str, Any]) -> str:
    """Deferred delegate to ``sell_escrow_monitor._broadcast_ait_tx``."""
    from . import sell_escrow_monitor as _sem

    return await _sem._broadcast_ait_tx(signed_tx)


async def _chain_height() -> int:
    """Deferred delegate to ``sell_escrow_monitor._chain_height``."""
    from . import sell_escrow_monitor as _sem

    return await _sem._chain_height()


def _lock_age_seconds(row: dict[str, Any]) -> float:
    """Deferred delegate to ``sell_escrow_monitor._lock_age_seconds``."""
    from . import sell_escrow_monitor as _sem

    return _sem._lock_age_seconds(row)


def _load_escrow_key(cfg: SellConfig) -> Any:
    """Deferred delegate to ``sell_escrow_monitor._load_escrow_key`` — the
    key-slot custody code stays on the monitor module."""
    from . import sell_escrow_monitor as _sem

    return _sem._load_escrow_key(cfg)


# AIT escrow nonce serialization across BOTH sweep lanes (sell locks and
# exchange settlements): they share the escrow account's nonce space, and
# the union inflight-check → nonce read → sign → intent-write → broadcast
# sequence is not atomic on its own — two lanes interleaving can read the
# same nonce, sign colliding envelopes, and the loser parks in
# needs_review_sweep. One shared lock (the AIT-side twin of
# ETH_RELEASE_NONCE_LOCK in bridge_withdraw_monitor) keeps a lane's whole
# check→sign→intent→broadcast section atomic; the second lane's union
# check then sees the first's persisted intent and defers. Both monitors
# are asyncio tasks on the wallet service's single event loop, so an
# asyncio.Lock suffices (same caveat as the ETH lock: the sell_admin CLI
# runs in its own process and is covered only by the DB-level union
# check, which still applies).
AIT_ESCROW_SWEEP_LOCK = asyncio.Lock()

# Sibling-lock statuses that consume a quote — everything still live or
# ambiguous. 'orphaned'/'refunded'/'failed'/'settled' siblings do not block.
_SELL_BINDING_STATUSES = (
    "locked",
    "releasing",
    "released",
    "settling",
    "refunding",
    "refund_pending",
    "stale_price",
    "queued_reserve",
    "queued_fee_settle",
    "queued_fee_refund",
    "needs_review",
    "needs_review_sweep",
)


# Marker tail on a fee-parked row's ``error`` — the write in ``_escrow_sweep``
# and the reason split in ``_parked_refund_reason`` share this exact string so
# a re-parked row recovers its original reason instead of accumulating
# deficit text.
_FEE_FLOAT_DEFICIT_MARK = "; escrow fee float deficit"

# Warned-once fee-float deficits: (ait_tx_hash, deficit, park_status). A
# parked row retries every poll — the WARNING must fire once per deficit
# state, not per cycle (journal noise feeds JournalErrors). A deficit that
# changes is a new state and warns again.
_fee_float_warned: set[tuple[str, str, str]] = set()


def _sweep_fee_ait() -> Decimal:
    """Each escrow sweep spends the standard transfer fee on top of the
    moved amount — the escrow needs a seed balance for exactly this."""
    return Decimal(str(DEFAULT_TX_FEE_AIT))


async def compute_sell_quote(ait_amount: Decimal) -> dict[str, Any] | None:
    """Compute the quote payload for an AIT sell amount.

    Returns None when the feed is unavailable or stale — callers must not
    price off a dead feed (route 503s, monitor parks the lock).
    """
    meta = await get_eth_prices_fresh()
    if meta is None:
        return None
    estimate = await calculate_eth_amount(ait_amount, eth_price_usd=meta["usd"])
    if not estimate:
        return None
    return {
        "eth_amount": estimate["amount_eth"],
        "fee_ait": estimate["fee_ait"],
        "net_ait": estimate["net_ait"],
        "rate_eth_usd": meta["usd"],
        "ait_usd": estimate["ait_usd"],
        "feed_age_seconds": Decimal(str(meta["feed_age_seconds"])),
    }


def _eth_for_lock_at_quote(amount_ait: Decimal, quote: dict[str, Any]) -> Decimal:
    """ETH owed for a lock at the rates frozen on its quote row."""
    if Decimal(str(amount_ait)) == Decimal(str(quote["ait_amount"])):
        return Decimal(str(quote["eth_amount"]))
    fee_ait, net_ait = apply_bridge_fee(Decimal(str(amount_ait)))
    eth_usd = Decimal(str(quote["rate_eth_usd"]))
    ait_usd = Decimal(str(quote["ait_usd"]))
    return (Decimal(str(net_ait)) * ait_usd / eth_usd).quantize(Decimal("0.00000001"))


def _exchange_inflight_sweep() -> bool:
    """An exchange settlement row holds the escrow's one in-flight sweep —
    shared nonce space, so this lane defers while it resolves."""
    if os.getenv("EXCHANGE_SETTLEMENT_ENABLED", "false").lower() != "true":
        return False
    try:
        from .bridge_db import get_exchange_inflight_sweep

        return get_exchange_inflight_sweep() is not None
    except Exception:  # noqa: BLE001 - inflight probe defaults to not-in-flight on failure
        return False


# ---------------------------------------------------------------------------
# Escrow-leg signing (AIT side) — settle to treasury / refund to shop
# ---------------------------------------------------------------------------


async def _sign_escrow_transfer(
    cfg: SellConfig, to_address: str, amount_ait: Decimal, payload_extra: dict[str, Any], nonce: int
) -> dict[str, Any]:
    """Build and sign an escrow-account TRANSFER at the given nonce."""
    from eth_utils import keccak

    value = ait_to_units(amount_ait)
    tx_payload = {
        "type": "TRANSFER",
        "chain_id": cfg.chain_id,
        "from": cfg.escrow_address,
        "to": canonical_address(to_address),
        "amount": value,
        "fee": ait_to_units(_sweep_fee_ait()),
        "nonce": nonce,
        "payload": {"amount": value, **payload_extra},
    }
    unsigned = {k: v for k, v in tx_payload.items() if k != "signature"}
    message = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    private_key = _load_escrow_key(cfg)
    signature = private_key.sign_msg_hash(keccak(message))
    tx_payload["signature"] = signature.to_bytes().hex()
    return tx_payload


async def _update_lock_status_with_retry(ait_tx_hash: str, status: str, **fields: Any) -> bool:
    """Persist a sell-lock status with the ETH-9 retry discipline: a write
    that fails after a broadcast must never fall through to a second send."""
    last_exc: Exception | None = None
    for attempt in range(wdm._STATUS_PERSIST_ATTEMPTS):
        try:
            return update_sell_lock_status(ait_tx_hash, status, **fields)
        except Exception as e:  # noqa: BLE001 - persist retry — any store failure alike
            last_exc = e
            logger.error(
                "Failed to persist sell lock %s status %s (attempt %d/%d): %s",
                ait_tx_hash,
                status,
                attempt + 1,
                wdm._STATUS_PERSIST_ATTEMPTS,
                e,
            )
            if attempt < wdm._STATUS_PERSIST_ATTEMPTS - 1:
                await asyncio.sleep(wdm._STATUS_PERSIST_DELAYS[attempt])
    raise RuntimeError(f"could not persist sell lock {ait_tx_hash} status {status}: {last_exc}")


def _expected_sweep(cfg: SellConfig, row: dict[str, Any], lane: str | None = None) -> tuple[str, int, str]:
    """(recipient, amount_units, sell_ref) the row's escrow outflow must
    match — derived from the row, the same values the stored blob carries.

    ``lane`` is "settle" or "refund"; when omitted it is read from the
    row's current status (the monitor's resolver sees only
    'settling'/'refunding' rows). sell_admin passes the lane it recovered
    from the persisted intent, since a 'needs_review_sweep' status no
    longer says which lane the sweep was in."""
    if lane is None:
        lane = "settle" if row["status"] in ("settling", "queued_fee_settle") else "refund"
    to_address = cfg.treasury_address if lane == "settle" else str(row["shop_ait_address"])
    return canonical_address(to_address), ait_to_units(Decimal(str(row["amount_ait"]))), str(row["ait_tx_hash"])


async def _find_escrow_outflow(
    cfg: SellConfig, nonce: int, to_address: str, amount_units: int, sell_ref: str
) -> dict[str, Any] | None:
    """Find the escrow's SEALED outbound TRANSFER that this row's recorded
    intent produced — matched on nonce AND recipient AND amount AND
    ``payload.sell_ref``, so a different transaction at the same nonce (a
    manual send, another row's sweep) can never be credited to this row.
    Mempool-pending txs (no ``block_height``) and failed-sealed txs
    (``status != 'confirmed'``) do not count as sealed (#1916)."""
    txs = await _fetch_transfers(cfg.escrow_address)
    for tx in txs:
        if not wdm.tx_sealed_confirmed(tx):
            continue
        sender = (tx.get("sender") or tx.get("from") or "").lower()
        if sender != cfg.escrow_address.lower():
            continue
        tx_nonce = tx.get("nonce")
        if tx_nonce is None or int(tx_nonce) != nonce:
            continue
        recipient = (tx.get("recipient") or tx.get("to") or "").lower()
        payload = tx.get("payload") or {}
        if (
            recipient == to_address.lower()
            and int(tx.get("value") or 0) == amount_units
            and payload.get("sell_ref") == sell_ref
        ):
            return tx
    return None


async def _escrow_sweep(
    cfg: SellConfig,
    row: dict[str, Any],
    to_address: str,
    reason: str,
    intent_status: str,
    fee_park_status: str,
) -> str:
    """Start an escrow → ``to_address`` sweep, serialized and float-checked.

    Serialization: at most one sweep (``settling``/``refunding``) is in
    flight at a time — while one is, this returns ``"deferred"`` and the row
    keeps its caller status to retry on a later poll.

    Fee float: the escrow pays ``amount + 0.01 AIT`` (the transfer fee). A
    short balance parks the row in ``fee_park_status`` with the deficit —
    never an exception, never a failed sign.

    On send, the nonce AND signed blob are persisted *before* broadcast and
    the row goes to ``intent_status`` — and stays there until the outflow is
    found *sealed* (see ``_resolve_escrow_sweep``). A broadcast returning a
    hash is not proof of seal, so terminal status is never written here.

    The whole check→nonce→sign→intent→broadcast section runs under
    ``AIT_ESCROW_SWEEP_LOCK`` so the exchange settlement lane cannot
    interleave a colliding nonce (ESCROW-SWEEP-NONCE-RACE-1, #1920).
    """
    async with AIT_ESCROW_SWEEP_LOCK:
        if get_sell_inflight_sweep() or _exchange_inflight_sweep():
            logger.info(
                "Sell lock %s: escrow sweep %s deferred — another sweep is in flight",
                row["ait_tx_hash"],
                reason,
            )
            return "deferred"

        amount_ait = Decimal(str(row["amount_ait"]))
        nonce, balance = await _account_view(cfg.escrow_address)
        required = amount_ait + _sweep_fee_ait()
        if balance < required:
            deficit = required - balance
            update_sell_lock_status(
                row["ait_tx_hash"],
                fee_park_status,
                error=f"{reason}{_FEE_FLOAT_DEFICIT_MARK} {deficit} AIT (need {required} AIT, have {balance})",
                expected_statuses={row["status"]},
            )
            warn_key = (str(row["ait_tx_hash"]), str(deficit), fee_park_status)
            if warn_key not in _fee_float_warned:
                _fee_float_warned.add(warn_key)
                logger.warning(
                    "Sell lock %s: escrow fee float short %s AIT (balance %s, need %s) — parked %s",
                    row["ait_tx_hash"],
                    deficit,
                    balance,
                    required,
                    fee_park_status,
                )
            return "fee_parked"

        payload_extra = {"sell_ref": row["ait_tx_hash"], "reason": reason}
        signed_tx = await _sign_escrow_transfer(cfg, to_address, amount_ait, payload_extra, nonce)
        persisted = await _update_lock_status_with_retry(
            row["ait_tx_hash"],
            intent_status,
            escrow_out_nonce=nonce,
            escrow_out_tx=json.dumps(signed_tx),
            expected_statuses={row["status"]},
        )
        if not persisted:
            # CAS lost (#1918): the row moved on since the snapshot — broadcasting
            # now would send an outflow no ledger state owns.
            logger.warning(
                "Sell lock %s: sweep intent write lost CAS (was %s) — row moved on; not broadcasting",
                row["ait_tx_hash"],
                row["status"],
            )
            return "deferred"
        tx_hash = await _broadcast_ait_tx(signed_tx)
        logger.info(
            "Sell lock %s: escrow sweep %s broadcast (%s AIT -> %s, nonce %d, tx %s) — awaiting seal",
            row["ait_tx_hash"],
            reason,
            amount_ait,
            to_address,
            nonce,
            tx_hash,
        )
        return "sent"


async def _resolve_escrow_sweep(cfg: SellConfig, row: dict[str, Any]) -> None:
    """Resolve an in-flight 'settling'/'refunding' row.

    Terminal status comes only from the chain: the sealed outflow matching
    nonce+recipient+amount+``sell_ref`` writes 'settled'/'refunded' with its
    real hash. If the recorded nonce is still unconsumed, the stored signed
    blob is re-broadcast — identical signature at the same nonce, which the
    chain dedups, so a resume can never produce a second payment. If the
    nonce was consumed by a *different* transaction (a manual send), the row
    goes to 'needs_review_sweep' — the ETH-9b rule, never a blind re-send.
    """
    nonce = row.get("escrow_out_nonce")
    if nonce is None:
        # Intent persisted but nonce missing — undecidable, needs a human.
        update_sell_lock_status(
            row["ait_tx_hash"],
            "needs_review_sweep",
            error="escrow sweep nonce missing",
            expected_statuses={row["status"]},
        )
        return
    final_status = "settled" if row["status"] == "settling" else "refunded"
    hash_field = "settle_tx_hash" if final_status == "settled" else "refund_tx_hash"
    to_address, amount_units, sell_ref = _expected_sweep(cfg, row)
    outflow = await _find_escrow_outflow(cfg, int(nonce), to_address, amount_units, sell_ref)
    if outflow is not None:
        await _update_lock_status_with_retry(
            row["ait_tx_hash"],
            final_status,
            **{hash_field: outflow.get("tx_hash") or outflow.get("hash")},
            expected_statuses={row["status"]},
        )
        logger.info("Sell lock %s: %s sealed at escrow nonce %d", row["ait_tx_hash"], final_status, nonce)
        return
    account_nonce, _balance = await _account_view(cfg.escrow_address)
    if account_nonce > int(nonce):
        # The nonce was consumed by a transaction that does NOT match this
        # row's intent — a manual send or foreign sweep. Never auto-resolve.
        update_sell_lock_status(
            row["ait_tx_hash"],
            "needs_review_sweep",
            error=f"escrow nonce {nonce} consumed by an unmatched transaction",
            expected_statuses={row["status"]},
        )
        logger.error(
            "Sell lock %s: escrow nonce %d sealed to an unmatched tx — needs review",
            row["ait_tx_hash"],
            nonce,
        )
        return
    # The nonce is still free — the original broadcast never sealed.
    # Re-broadcast the stored signed blob: identical signature at the same
    # nonce — a fresh signature could double-pay, this cannot.
    stored = row.get("escrow_out_tx")
    if not stored:
        update_sell_lock_status(
            row["ait_tx_hash"],
            "needs_review_sweep",
            error="escrow sweep blob missing",
            expected_statuses={row["status"]},
        )
        return
    signed_tx = json.loads(stored)
    tx_hash = await _broadcast_ait_tx(signed_tx)
    logger.info(
        "Sell lock %s: re-broadcast stored %s blob (tx %s) — still in flight until sealed",
        row["ait_tx_hash"],
        row["status"],
        tx_hash,
    )


async def _settle_lock(cfg: SellConfig, row: dict[str, Any]) -> None:
    """Settle escrowed AIT to the hub treasury (the sell's AIT leg)."""
    await _escrow_sweep(cfg, row, cfg.treasury_address, "sell_settle", "settling", "queued_fee_settle")


async def _refund_lock(cfg: SellConfig, row: dict[str, Any], reason: str) -> None:
    """Refund escrowed AIT to the shop.

    Deferred/parked outcomes leave the row in a retriable status. A failure
    before the 'refunding' intent persisted leaves the row untouched — the
    next healthy poll retries it, so an outage can never burn a refundable
    row. Once the intent + signed blob are persisted, the row is in flight
    and ``_resolve_escrow_sweep`` owns it: sealed → 'refunded'; nonce spent
    by a foreign tx → 'needs_review_sweep'; never a second blind refund.
    """
    try:
        await _escrow_sweep(cfg, row, row["shop_ait_address"], reason, "refunding", "queued_fee_refund")
        return
    except Exception as e:  # noqa: BLE001 - refund sweep failure resolved by the resolver
        logger.error("Refund sweep errored for sell lock %s: %s", row["ait_tx_hash"], e)
    fresh = get_sell_lock_by_ait_tx_hash(row["ait_tx_hash"]) or {}
    if fresh.get("status") == "refunding":
        logger.error(
            "Sell lock %s: refund broadcast threw post-intent — the resolver will prove the outcome by nonce",
            row["ait_tx_hash"],
        )
    # else: pre-intent failure — the row keeps its status and retries next poll


# ---------------------------------------------------------------------------
# ETH release — ETH-9/9b machinery reused, no second "is the ETH out?"
# ---------------------------------------------------------------------------


async def _verify_sell_release_outcome(row: dict[str, Any]) -> tuple[str, str]:
    """(outcome, reason) for a sell lock's ETH release — the shared
    ETH-9b compose (deep receipt wins; nonce alone is never proof). The
    reason distinguishes an in-grace absence from a genuine verification
    problem so callers can pick the log level (ETH-15)."""
    fresh = get_sell_lock_by_ait_tx_hash(row["ait_tx_hash"])
    if not fresh:
        return "unknown", "verify_error"
    return await wdm._compose_release_outcome_detail(fresh)


async def _release_eth_for_lock(cfg: SellConfig, row: dict[str, Any], amount_eth: Decimal) -> None:
    """Send the ETH release for a sell lock (intent persisted pre-broadcast).

    ``amount_eth`` is the admission-priced amount — the caller's freshly
    computed value, since ``row`` may be a pre-update snapshot.
    """
    eth_address = row.get("shop_eth_address") or ""
    if amount_eth <= 0:
        raise RuntimeError(f"Sell lock {row['ait_tx_hash']} has no ETH amount to release")
    if not wdm._is_valid_eth_address(eth_address):
        raise RuntimeError(f"Sell lock {row['ait_tx_hash']} has no valid shop ETH address")

    # CAS predicate (#1918): the caller's snapshot may be stale (a sibling
    # write in this pass, or a fabricated status-patched row) — predicate
    # on the status the ledger holds right now.
    fresh = get_sell_lock_by_ait_tx_hash(row["ait_tx_hash"])
    prior_status = str(fresh["status"]) if fresh else str(row["status"])

    gas_price = await wdm._eth_gas_price()
    gas_limit = await wdm._release_gas_limit(eth_address, amount_eth)
    gas_cost = Decimal(gas_price * gas_limit) / Decimal(10**18)
    required = amount_eth + gas_cost
    balance = await wdm._eth_balance(wdm.ETH_WALLET_ADDRESS)
    available = balance - wdm._pending_eth_reserve()
    # The stricter of SELL_MAX_ETH_PER_TX and BRIDGE_MAX_PAYOUT_FRACTION binds
    # (the fraction shrinks as the float drains — operator decision (c)).
    fraction_cap = balance * cfg.max_payout_fraction
    if amount_eth > fraction_cap:
        update_sell_lock_status(
            row["ait_tx_hash"],
            "queued_reserve",
            error=f"{amount_eth} ETH exceeds BRIDGE_MAX_PAYOUT_FRACTION={cfg.max_payout_fraction} of float {balance}",
            expected_statuses={prior_status},
        )
        return
    if available - required < cfg.min_reserve_eth:
        deficit = required + cfg.min_reserve_eth - available
        update_sell_lock_status(
            row["ait_tx_hash"],
            "queued_reserve",
            error=f"deficit {deficit} ETH — need {required} + {cfg.min_reserve_eth} reserve, have {available}",
            expected_statuses={prior_status},
        )
        return

    from eth_account import Account as EthAccount

    key, error = wdm._validate_release_key()
    if not key:
        raise RuntimeError(error)
    account = EthAccount.from_key(key)
    async with wdm.ETH_RELEASE_NONCE_LOCK:
        # #1921: cross-process flock — an admin release-retry signs from the
        # same ETH_WALLET_ADDRESS nonce space; wait for it, never collide.
        async with wdm._eth_release_file_lock():
            nonce = await wdm._eth_nonce(wdm.ETH_WALLET_ADDRESS)
            raw, eth_tx_hash = wdm._sign_release_tx(account, eth_address, amount_eth, nonce, gas_price, gas_limit)

            persisted = await _update_lock_status_with_retry(
                row["ait_tx_hash"],
                "releasing",
                eth_tx_hash=eth_tx_hash,
                release_nonce=nonce,
                expected_statuses={prior_status},
            )
            if not persisted:
                # CAS lost (#1918): the row moved on since the snapshot — the
                # signed release must not broadcast for a state nobody owns.
                logger.warning(
                    "Sell lock %s: 'releasing' intent lost CAS (was %s) — row moved on; not broadcasting",
                    row["ait_tx_hash"],
                    prior_status,
                )
                return
            sent = await wdm._broadcast_release_tx(raw)
    if sent.lower() != eth_tx_hash.lower():
        logger.warning("Broadcast reported %s; keeping signed hash %s", sent, eth_tx_hash)
    # ETH-14: 'released' is written only on a verified receipt — the
    # inflight handler proves the outcome next poll; a reverted or dropped
    # release can never again be recorded as sent here.
    logger.info(
        "Sell lock %s: broadcast %s ETH to %s (tx %s, gas %d) — awaiting receipt proof",
        row["ait_tx_hash"],
        amount_eth,
        eth_address,
        eth_tx_hash,
        gas_limit,
    )


async def _resolve_lock_release_failure(cfg: SellConfig, row: dict[str, Any], exc: Exception) -> None:
    """Same rule as withdrawals: refund only on positive proof of no send."""
    # The snapshot status is stale by now: the 'releasing' intent write
    # landed before the broadcast that raised. Re-read so the CAS
    # predicates on the status the ledger actually holds (#1918).
    fresh = get_sell_lock_by_ait_tx_hash(row["ait_tx_hash"])
    expected = {fresh["status"]} if fresh else {row["status"]}
    outcome, _reason = await _verify_sell_release_outcome(row)
    if outcome == "sent":
        logger.warning("Sell lock %s: ETH release confirmed despite error (%s)", row["ait_tx_hash"], exc)
        try:
            await _update_lock_status_with_retry(row["ait_tx_hash"], "released", expected_statuses=expected)
        except Exception as persist_err:  # noqa: BLE001 - persist best-effort inside the confirmed-error path
            logger.error("Could not persist released for %s: %s", row["ait_tx_hash"], persist_err)
    elif outcome == "not_sent":
        # Release provably never landed — the row owes a refund but stays
        # open in 'refund_pending' so a deferred/failed sweep retries.
        update_sell_lock_status(
            row["ait_tx_hash"],
            "refund_pending",
            error=f"release failed: {exc}",
            expected_statuses=expected,
        )
        # The row just moved to refund_pending — hand the sweep the status
        # the ledger now holds or its own CAS would read the stale snapshot.
        await _refund_lock(cfg, {**row, "status": "refund_pending"}, f"release failed: {exc}")
    else:
        update_sell_lock_status(
            row["ait_tx_hash"],
            "needs_review",
            error=f"release outcome unverifiable: {exc}",
            expected_statuses=expected,
        )
        logger.error("Sell lock %s marked needs_review — release outcome unverifiable: %s", row["ait_tx_hash"], exc)


def _quote_admits_lock(row: dict[str, Any], quote: dict[str, Any]) -> bool:
    """Whether this row's quote admits it: 'expired' quotes still admit their
    lock — at the re-quoted live rate. A 'locked' quote is already bound:
    admission only when the bound lock IS this row (a queued_reserve/
    stale_price re-entry). Otherwise the earliest live sibling wins; a later
    'locked' sibling never blocks."""
    quote_id = str(quote["id"])
    bound_lock = get_sell_lock_by_quote_id(quote_id, statuses=_SELL_BINDING_STATUSES)
    bound_is_self = bool(bound_lock and bound_lock["ait_tx_hash"] == row["ait_tx_hash"])
    quote_ok = quote.get("status") in ("quoted", "expired") or (quote.get("status") == "locked" and bound_is_self)
    if quote_ok and quote.get("status") != "locked":
        live_sibling = get_sell_lock_by_quote_id(
            quote_id,
            exclude_ait_tx_hash=row["ait_tx_hash"],
            statuses=_SELL_BINDING_STATUSES,
            before_created_at=str(row.get("created_at") or ""),
        )
        quote_ok = not live_sibling
    return quote_ok


async def _price_lock_eth_amount(cfg: SellConfig, row: dict[str, Any], quote: dict[str, Any], quote_id: str) -> Decimal | None:
    """Persist the lock's ETH amount — quote rate or live re-quote for an
    expired quote. Returns ``None`` when the row was parked (stale feed)."""
    eth_amount = row.get("eth_amount")
    if eth_amount is not None:
        return Decimal(str(eth_amount))
    expired = True
    try:
        expired = utc_now() > parse_stored(quote.get("expires_at") or "")
    except (TypeError, ValueError):
        pass
    if expired:
        # Late lock on an expired quote: re-quote at the live feed.
        recomputed = await compute_sell_quote(Decimal(str(row["amount_ait"])))
        if recomputed is None:
            update_sell_lock_status(
                row["ait_tx_hash"],
                "stale_price",
                error="expired quote and feed unavailable",
                expected_statuses={row["status"]},
            )
            return None
        eth_amount = recomputed["eth_amount"]
        update_sell_quote_status(quote_id, "expired")
        update_sell_lock_status(
            row["ait_tx_hash"],
            "locked",
            eth_amount=eth_amount,
            requoted=1,
            error="requoted after expiry",
            expected_statuses={row["status"]},
        )
    else:
        eth_amount = _eth_for_lock_at_quote(Decimal(str(row["amount_ait"])), quote)
        update_sell_lock_status(
            row["ait_tx_hash"],
            "locked",
            eth_amount=eth_amount,
            expected_statuses={row["status"]},
        )
        update_sell_quote_status(quote_id, "locked")
    return Decimal(str(eth_amount))


async def _handle_locked(cfg: SellConfig, row: dict[str, Any]) -> None:
    """Admission path for a recorded lock: quote match → deadline →
    expiry/requote → feed freshness → caps → release."""
    # #1269: seal-depth gate — nothing is spent (ETH release or AIT refund)
    # until the inbound lock is buried SELL_SEAL_DEPTH blocks deep. A depth-0
    # lock can still reorg out; the row stays 'locked' and is rechecked next
    # poll. Head-fetch failure fails closed (skip this row this poll).
    locked_height = row.get("locked_height")
    try:
        head = await _chain_height()
    except Exception as e:  # noqa: BLE001 - height probe containment — release skipped
        logger.error("Could not read chain height for seal-depth check on %s: %s", row["ait_tx_hash"], e)
        return
    if locked_height is None or head - int(locked_height) < cfg.sell_seal_depth:
        return
    quote = get_sell_quote(str(row["quote_id"])) if row.get("quote_id") else None
    if quote is None or not _quote_admits_lock(row, quote):
        # No live quote — unmatched locks are orphan-refunded after the
        # window, never held. A second lock reusing an already-bound quote
        # lands here too.
        update_sell_lock_status(
            row["ait_tx_hash"],
            "orphaned",
            error="no live quote for lock",
            expected_statuses={row["status"]},
        )
        return
    quote_id = str(quote["id"])

    if _lock_age_seconds(row) > cfg.release_deadline_seconds:
        await _refund_lock(cfg, row, "release deadline passed")
        return

    eth_amount = await _price_lock_eth_amount(cfg, row, quote, quote_id)
    if eth_amount is None:
        return

    # Re-check feed freshness immediately before spending ETH.
    if await get_eth_prices_fresh() is None:
        update_sell_lock_status(
            row["ait_tx_hash"],
            "stale_price",
            error="price feed stale at release check",
            expected_statuses={row["status"]},
        )
        return

    amount_eth = Decimal(str(eth_amount))
    if amount_eth > cfg.max_eth_per_tx:
        update_sell_lock_status(
            row["ait_tx_hash"],
            "queued_reserve",
            error=f"{amount_eth} ETH exceeds SELL_MAX_ETH_PER_TX={cfg.max_eth_per_tx}",
            expected_statuses={row["status"]},
        )
        return
    since = (utc_now() - timedelta(hours=24)).isoformat()
    if get_sell_eth_committed_since(since) + amount_eth > cfg.max_eth_per_day:
        update_sell_lock_status(
            row["ait_tx_hash"],
            "queued_reserve",
            error="daily sell release cap reached",
            expected_statuses={row["status"]},
        )
        return

    try:
        await _release_eth_for_lock(cfg, row, amount_eth)
    except Exception as e:  # noqa: BLE001 - release failure resolved in-place, never raised into the poll
        logger.error("ETH release failed for sell lock %s: %s", row["ait_tx_hash"], e)
        await _resolve_lock_release_failure(cfg, row, e)


async def _handle_orphaned(cfg: SellConfig, row: dict[str, Any]) -> None:
    """Orphan lock (no live quote): refund once the chain has moved past the
    configured orphan window."""
    locked_height = row.get("locked_height")
    if locked_height is None:
        return
    try:
        height = await _chain_height()
    except Exception as e:  # noqa: BLE001 - height probe containment — orphan check skipped
        logger.error("Could not read chain height for orphan check on %s: %s", row["ait_tx_hash"], e)
        return
    if height - int(locked_height) >= cfg.orphan_blocks:
        await _refund_lock(cfg, row, "orphan lock — no matching quote")


async def _handle_inflight(cfg: SellConfig, row: dict[str, Any]) -> None:
    """'releasing'/'needs_review': the ETH-9b resume check — sent → released,
    proven unsent → refund_pending + refund sweep, unknown → stays."""
    outcome, reason = await _verify_sell_release_outcome(row)
    if outcome == "sent":
        await _update_lock_status_with_retry(row["ait_tx_hash"], "released", expected_statuses={row["status"]})
        logger.info("Sell lock %s: ETH release confirmed on chain", row["ait_tx_hash"])
    elif outcome == "not_sent":
        update_sell_lock_status(
            row["ait_tx_hash"],
            "refund_pending",
            error="release never reached the chain",
            expected_statuses={row["status"]},
        )
        await _refund_lock(cfg, {**row, "status": "refund_pending"}, "release never reached the chain")
    else:
        if row["status"] != "needs_review":
            update_sell_lock_status(
                row["ait_tx_hash"],
                "needs_review",
                error="release outcome unverifiable",
                expected_statuses={row["status"]},
            )
        age = wdm._release_intent_age_seconds(row)
        age_txt = f"{int(age)}s" if age != float("inf") else "unknown"
        if reason == "absent_in_grace":
            # Invisible-but-young is routine propagation lag, not an
            # incident — the parked row still surfaces at WARNING (ETH-15).
            logger.warning(
                "Sell lock %s (%s) not yet visible on-chain — inside absence grace; parked needs_review (age=%s)",
                row["ait_tx_hash"],
                row["status"],
                age_txt,
            )
        elif reason in ("chain_view", "nonce_pending") and age < wdm.ETH_RELEASE_ABSENCE_GRACE_SECONDS:
            # Pending/below-depth view on a just-broadcast release — a
            # normal delay (ETH-18). The row did change status, so it
            # still surfaces at WARNING; verify_error and a consumed
            # nonce keep ERROR regardless of age.
            logger.warning(
                "Sell lock %s (%s) not yet confirmed on-chain — reason=%s, age=%s (grace %ds); parked needs_review",
                row["ait_tx_hash"],
                row["status"],
                reason,
                age_txt,
                wdm.ETH_RELEASE_ABSENCE_GRACE_SECONDS,
            )
        else:
            logger.error(
                "Sell lock %s (%s) still unverifiable — needs review (reason=%s, age=%s)",
                row["ait_tx_hash"],
                row["status"],
                reason,
                age_txt,
            )


async def _handle_released(cfg: SellConfig, row: dict[str, Any]) -> None:
    """'released': re-verify the receipt each poll; on 'sent' settle the
    escrowed AIT to treasury; on 'not_sent' (reorg/dropped tx) refund."""
    outcome, _reason = await _verify_sell_release_outcome(row)
    if outcome == "sent":
        await _settle_lock(cfg, row)
    elif outcome == "not_sent":
        update_sell_lock_status(
            row["ait_tx_hash"],
            "refund_pending",
            error="release transaction dropped or reverted",
            expected_statuses={row["status"]},
        )
        await _refund_lock(cfg, {**row, "status": "refund_pending"}, "release transaction dropped or reverted")
    # 'unknown' keeps the row 'released' — re-checked next poll.


def _parked_refund_reason(row: dict[str, Any]) -> str:
    """The refund reason stored ahead of the parked fee-deficit marker."""
    error = str(row.get("error") or "")
    reason = error.split(_FEE_FLOAT_DEFICIT_MARK)[0].strip()
    return reason or "refund"


async def _handle_stale_price(cfg: SellConfig, row: dict[str, Any]) -> None:
    """Feed-stale park: re-admit at the live rate once the feed recovers;
    deadline still refunds while parked."""
    if await get_eth_prices_fresh() is not None:
        update_sell_lock_status(
            row["ait_tx_hash"],
            "locked",
            error="feed recovered",
            expected_statuses={row["status"]},
        )
        await _handle_locked(cfg, {**row, "status": "locked"})
    elif _lock_age_seconds(row) > cfg.release_deadline_seconds:
        await _refund_lock(cfg, row, "release deadline passed while feed stale")


async def _refund_pending_lock(cfg: SellConfig, row: dict[str, Any]) -> None:
    await _refund_lock(cfg, row, str(row.get("error") or "refund"))


async def _refund_queued_fee_lock(cfg: SellConfig, row: dict[str, Any]) -> None:
    await _refund_lock(cfg, row, _parked_refund_reason(row))


# Binding the function objects at import time is safe here: every handler is a
# module-level function defined above this line, nothing ever rebinds the
# module names (tests stub the DB/RPC seams, not the handlers), and the table
# is read-only after construction. _SELL_STATUS_HANDLERS must cover every
# _SELL_OPEN_STATUSES member except needs_review_sweep (deliberately terminal
# for the machine) — a test pins that.
_SELL_STATUS_HANDLERS: dict[str, Callable[[SellConfig, dict[str, Any]], Awaitable[None]]] = {
    "locked": _handle_locked,
    "queued_reserve": _handle_locked,
    "stale_price": _handle_stale_price,
    "orphaned": _handle_orphaned,
    "refund_pending": _refund_pending_lock,
    "queued_fee_settle": _settle_lock,
    "queued_fee_refund": _refund_queued_fee_lock,
    "releasing": _handle_inflight,
    "needs_review": _handle_inflight,
    "released": _handle_released,
    "settling": _resolve_escrow_sweep,
    "refunding": _resolve_escrow_sweep,
}


async def _process_sell_lock(cfg: SellConfig, row: dict[str, Any]) -> None:
    status = str(row.get("status"))
    if status == "needs_review_sweep":
        # Sweep-path review rows are terminal for the machine: the recorded
        # intent is undecidable (nonce consumed by a foreign tx, nonce or
        # signed blob missing), so only an explicit operator action may move
        # the row — routing it into the ETH-release check could re-release
        # or re-refund funds. See docs/ops/sell-escrow-runbook.md.
        return
    handler = _SELL_STATUS_HANDLERS.get(status)
    if handler is not None:
        await handler(cfg, row)
