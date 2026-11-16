"""Pure helpers and constants for the exchange handlers.

Module-level constants and functions extracted from ``exchange.py``
(issue #1860 phase 2): everything here is independent of the mixin and
of instance state. ``exchange.py`` re-imports the names it still uses
(and re-exports them for tests that import them from that module).
"""

import json
import os
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from aitbc.aitbc_logging import get_logger
from aitbc.utils.chain_id import resolve_chain_id
from aitbc.utils.decimal import to_decimal as _to_decimal

logger = get_logger(__name__)


# ── ETH-11 phase 2: signed orders on the hub exchange ─────────────────────
# Design: docs/design/eth8-exchange-page.md sections 1–6, 9. Decisions
# (price band, registered nodes, fee side, phase order) were DECIDED 14 Oct.
#
# Signing convention: canonical JSON (sorted keys, compact separators) ->
# keccak256 -> secp256k1 recover-and-compare. That is exactly what the chain
# RPC's ``verify_transaction_signature`` does; ``aitbc_chain`` is not
# importable from this service's venv, so the code calls the same underlying
# primitive (``aitbc.crypto.signature_recovery.verify_signature``) over the
# same message encoding — no new crypto is introduced.
#
# Revertibility: EXCHANGE_REQUIRE_SIGNED_ORDERS (default on, per design).
# When off, POST /api/orders behaves exactly as before phase 2 and the
# phase-2 routes (cancel/register/nodes/my-orders) answer 404 — they did
# not exist before.

EXCHANGE_ORDER_PAIR = "AIT/ETH"

# #1608: signed-envelope integer fields land in SQLite INTEGER columns and in
# ``account_nonce`` comparisons. Positivity alone let 2**63+ through to an
# OverflowError/500; bound every envelope integer to signed int64.
_SIGNED_INT64_MAX = (1 << 63) - 1


def _is_int64(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= _SIGNED_INT64_MAX


# Server-side ceilings for public reads (#1543): the caller's ?limit= is
# clamped into [1, _MAX_PAGE_ROWS] — ``LIMIT -1`` is SQLite "unlimited".
_MAX_PAGE_ROWS = 500
# The node registry / participants board is a lookup table, not a feed —
# bound it generously so a corrupt or flooded registry cannot turn every
# orderbook/nodes request into a full-table scan.
_MAX_REGISTRY_ROWS = 5000

# The order envelope's field set is pinned by design section 1.
_ORDER_ENVELOPE_FIELDS = frozenset(
    {"side", "pair", "amount_ticks", "price_ticks", "expiry_height", "account_nonce", "chain_id"}
)
# Cancel/registration shapes are left open by the design; an ``action``
# discriminator keeps the envelope classes unambiguous.
_CANCEL_ENVELOPE_FIELDS = frozenset({"action", "order_id", "expiry_height", "account_nonce", "chain_id"})
_REGISTER_ENVELOPE_FIELDS = frozenset({"action", "address", "label", "account_nonce", "chain_id"})
# ETH-8 phase 3: the node's ETH payout address is set once, deliberately, by
# its own signed verb — the fixed order envelope (design section 1) never
# carries it. History is appended to payout_address_audit; a change applies
# to orders placed after the claim, never retroactively.
_PAYOUT_ENVELOPE_FIELDS = frozenset({"action", "eth_address", "account_nonce", "chain_id"})
_CANCEL_ACTION = "exchange_cancel"
_REGISTER_ACTION = "exchange_register"
_PAYOUT_ACTION = "exchange_set_payout"

# Mirrored settlement transitions on trades rows (phase 3): the wallet
# ledger is authoritative — the mirror only moves forward. The
# needs_review family can be entered from any live state and resumes along
# the release/refund lanes; terminal states accept nothing. Same-state
# re-posts are handled separately as no-op dedupes.
_TRADE_STATE_FORWARD: dict[str, frozenset[str]] = {
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

# Watchlist is flag-and-log only (decided 14 Oct): it never blocks or
# throttles an order — auto-blocking would be a separate operator decision.
_WATCHLIST_LOGGED: set[str] = set()


def _signed_orders_required() -> bool:
    """EXCHANGE_REQUIRE_SIGNED_ORDERS — signature enforcement is revertible."""
    return os.getenv("EXCHANGE_REQUIRE_SIGNED_ORDERS", "true").strip().lower() not in ("0", "false", "no", "off")


def _settlement_enabled() -> bool:
    """EXCHANGE_SETTLEMENT_ENABLED — every phase-3 code path is inert when
    unset. Fail closed: only an explicit 'true' turns settlement on."""
    return os.getenv("EXCHANGE_SETTLEMENT_ENABLED", "false").strip().lower() == "true"


# Addresses that can never be a payout destination: the zero and dead burn
# addresses, plus the hub's own operational accounts — a typo or hostile
# claim pointing at any of them would burn or loop the seller's proceeds.
_BLOCKED_PAYOUT_CONSTANTS = frozenset(
    {
        "0x0000000000000000000000000000000000000000",
        "0x000000000000000000000000000000000000dead",
    }
)
_BLOCKED_PAYOUT_ENVS = (
    "AIT_SELL_ESCROW",
    "BRIDGE_PAYOUT_ADDRESS",
    "GENESIS_WALLET_ADDRESS",
    "BRIDGE_ETH_ADDRESS",
    "SELL_TREASURY_ADDRESS",
)


def _payout_address_blocked(eth_address: str) -> bool:
    addr = eth_address.strip().lower()
    if addr in _BLOCKED_PAYOUT_CONSTANTS:
        return True
    return any(v.strip().lower() == addr for v in (os.getenv(e, "") for e in _BLOCKED_PAYOUT_ENVS) if v)


# Order side → env naming the destination its funding leg points at:
# SELL instructions send the lock to AIT_SELL_ESCROW; BUY prepay
# instructions send ETH to the bridge wallet BRIDGE_ETH_ADDRESS.
_SIDE_DESTINATION_ENV = {"SELL": "AIT_SELL_ESCROW", "BUY": "BRIDGE_ETH_ADDRESS"}


def _funding_destination(env_name: str) -> str | None:
    """The configured funding destination in env_name — an EIP-55
    checksummed address — or None when unset/empty/malformed.

    Shape+checksum only: unlike a payout target, the destination is
    allowed to equal a blocklisted env value (BRIDGE_ETH_ADDRESS is the
    bridge wallet itself), so the payout blocklist must not run here."""
    from eth_utils import is_checksum_address

    value = os.getenv(env_name, "").strip()
    return value if is_checksum_address(value) else None


def _prepaid_spendable(cursor, address: str) -> Decimal:
    """Node's spendable prepaid ETH: deposits − cumulative committed − open
    reservations. committed_eth is spent-or-owed minus returned (settled
    trades stay counted — that ETH is gone); an open debit's
    (amount − committed) stays reserved for the order's remaining fills.
    All Decimal — this is the money path."""
    deposits = Decimal(0)
    for (amt,) in cursor.execute("SELECT amount_eth FROM prepaid_deposits WHERE node_address = ?", (address,)):
        deposits += _to_decimal(amt)
    committed = Decimal(0)
    reserved = Decimal(0)
    for amt, comm, state in cursor.execute(
        "SELECT amount_eth, COALESCE(committed_eth, '0'), state FROM prepaid_debits WHERE node_address = ?",
        (address,),
    ):
        committed += _to_decimal(comm)
        if state == "open":
            reserved += _to_decimal(amt) - _to_decimal(comm)
    return deposits - committed - reserved


def _commit_trade_cost(cursor, buy_order_id: int, trade_total: Decimal) -> None:
    """Commit a matched trade's cost to the buy order's prepaid debit. A
    matched trade always settles or parks needs_review — it never
    un-happens — so the commitment lands inside the match transaction.
    committed_eth is cumulative spent-or-owed: settlement does NOT
    decrement (the ETH is gone); only a trade refund releases it."""
    row = cursor.execute(
        "SELECT COALESCE(committed_eth, '0') FROM prepaid_debits WHERE order_id = ?", (buy_order_id,)
    ).fetchone()
    if row is None:
        return  # defensive: a funded buy always has a debit row
    cursor.execute(
        "UPDATE prepaid_debits SET committed_eth = ? WHERE order_id = ?",
        (str(_to_decimal(row[0]) + trade_total), buy_order_id),
    )


def _close_buy_debit(cursor, order_id: int) -> None:
    """Close a buy order's open debit when the order is done filling:
    the uncommitted residual returns to spendable ('refunded'), a fully
    committed debit is 'consumed'. committed_eth keeps tracking live
    trades past close — they settle or refund against it."""
    row = cursor.execute(
        "SELECT amount_eth, COALESCE(committed_eth, '0'), state FROM prepaid_debits WHERE order_id = ?",
        (order_id,),
    ).fetchone()
    if row is None or row[2] != "open":
        return
    residual = _to_decimal(row[0]) - _to_decimal(row[1])
    cursor.execute(
        "UPDATE prepaid_debits SET state = ?, closed_at = ? WHERE order_id = ?",
        ("consumed" if residual <= 0 else "refunded", datetime.now(UTC).isoformat(), order_id),
    )


def _cancel_settlement_effects(cursor, order_id: int, result: dict) -> None:
    """Cancel ends the backing window; under settlement the uncommitted part
    of any prepaid debit refunds atomically in the caller's transaction."""
    if not _settlement_enabled():
        return
    cursor.execute("UPDATE orders SET funded_state = 'backing_expired' WHERE id = ?", (order_id,))
    deb = cursor.execute(
        "SELECT amount_eth, COALESCE(committed_eth, '0'), state FROM prepaid_debits WHERE order_id = ?",
        (order_id,),
    ).fetchone()
    if deb is not None and deb[2] == "open":
        result["refunded_eth"] = str(_to_decimal(deb[0]) - _to_decimal(deb[1]))
    _close_buy_debit(cursor, order_id)


def _exchange_chain_id() -> str:
    """Expected envelope chain_id: EXCHANGE_CHAIN_ID > CHAIN_ID > raise."""
    return os.getenv("EXCHANGE_CHAIN_ID") or resolve_chain_id()


# #1608: env-sourced decimals feed fee/price-band/min-order math. A NaN,
# negative, or absurd value must not reach that math — non-finite or
# negative input falls back to the default, and anything beyond this bound
# is clamped to it.
_ENV_DECIMAL_MAX = Decimal("1000000000000000")


def _env_decimal(name: str, default: str) -> Decimal:
    try:
        value = Decimal(os.getenv(name, default))
    except (InvalidOperation, ValueError):
        return Decimal(default)
    if not value.is_finite() or value < 0:
        return Decimal(default)
    if value > _ENV_DECIMAL_MAX:
        return _ENV_DECIMAL_MAX
    return value


def _canonical_envelope_json(envelope: dict) -> bytes:
    """Sorted-keys compact JSON — the repo's signing/verifying encoding."""
    return json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()


def _verify_envelope_signature(envelope: dict, signature: str, expected_address: str) -> bool:
    """keccak256(canonical JSON) -> secp256k1 recover == expected_address."""
    from eth_utils import keccak

    from aitbc.crypto.signature_recovery import SignatureMalformed, verify_signature

    msg_hash = keccak(_canonical_envelope_json(envelope))
    try:
        return bool(verify_signature(msg_hash, signature, expected_address))
    except SignatureMalformed as e:
        logger.warning("Malformed order signature: %s", e)
        return False
    except (ValueError, TypeError, KeyError, AttributeError, IndexError):
        # Not SignatureMalformed (which has its own line above): e.g. an
        # unexpected field type reaching the recovery primitives. A failed
        # check, not a crash — named families keep the except ratchet honest.
        logger.warning("Signature verification failed on bad input")
        return False
    except ImportError:
        logger.error("secp256k1 verification dependencies unavailable")
        return False


def _envelope_hash(envelope: dict) -> str:
    from eth_utils import keccak

    return str(keccak(_canonical_envelope_json(envelope)).hex())


def _short_addr(address: str | None) -> str | None:
    if not address:
        return None
    return address[:6] + "…" + address[-4:] if len(address) > 12 else address


# The sliding-window rate-limit buckets and helpers moved to handlers/base.py
# (#1678) so the market/bridge mixins share them; the names stay importable
# from this module for the tests that reach them via __globals__.


def _apply_exchange_fee(gross_ait: Decimal) -> tuple[Decimal, Decimal]:
    """(fee_ait, net_ait) — the ``apply_bridge_fee`` shape on EXCHANGE_FEE_PCT.

    DECIDED 14 Oct: fee rides the AIT leg to the seller, default 0 on
    testnet. Phase 2 moves no funds; the value is recorded on the trade row.
    """
    fee = (gross_ait * _env_decimal("EXCHANGE_FEE_PCT", "0")).quantize(Decimal("0.000001"))
    return fee, gross_ait - fee


# Positive-result cache for the oracle band so the polled orderbook endpoint
# does not pay an upstream HTTP call per read. Failures are never cached, so
# feed recovery is immediate; the band is key'd on the configured pct so a
# config change cannot serve a stale tuple.
_band_cache: dict[str, tuple[Decimal, tuple[Decimal, Decimal]] | float] = {}
BAND_CACHE_TTL_S = 60.0


def _row_to_order(row) -> dict:
    """Convert a database row to an order dict with Decimal monetary values."""
    return {
        "id": row[0],
        "order_type": row[1],
        "amount": row[2],
        "price": row[3],
        "total": row[4],
        "filled": row[5],
        "remaining": row[6],
        "status": row[7],
        "created_at": row[8],
        "user_address": row[9] if len(row) > 9 else None,
        "tx_hash": row[10] if len(row) > 10 else None,
    }
