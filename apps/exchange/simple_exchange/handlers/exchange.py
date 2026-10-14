"""Trading, metrics, treasury, and health handlers.

Monetary arithmetic uses ``Decimal`` throughout (B2 backport from v0.10.3).
Order placement and matching occur within a single ``BEGIN IMMEDIATE``
transaction to prevent race conditions (B1 backport). All database
connections are closed via ``try/finally`` (B3 backport).
"""

import json
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from aitbc.aitbc_logging import get_logger
from aitbc.operations import BeginStatus, request_hash
from aitbc.utils.decimal import to_decimal as _to_decimal

from ..db import get_db_path, ticks_to_decimal, to_ticks
from .base import RPC_BASE_URL, RPC_TIMEOUT, _idempotency_key, get_operation_ledger

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
_EXCHANGE_CHAIN_DEFAULT = "ait-localnet"  # design section 1 literal

# The order envelope's field set is pinned by design section 1.
_ORDER_ENVELOPE_FIELDS = frozenset(
    {"side", "pair", "amount_ticks", "price_ticks", "expiry_height", "account_nonce", "chain_id"}
)
# Cancel/registration shapes are left open by the design; an ``action``
# discriminator keeps the envelope classes unambiguous.
_CANCEL_ENVELOPE_FIELDS = frozenset({"action", "order_id", "expiry_height", "account_nonce", "chain_id"})
_REGISTER_ENVELOPE_FIELDS = frozenset({"action", "address", "label", "account_nonce", "chain_id"})
_CANCEL_ACTION = "exchange_cancel"
_REGISTER_ACTION = "exchange_register"

# Watchlist is flag-and-log only (decided 14 Oct): it never blocks or
# throttles an order — auto-blocking would be a separate operator decision.
_WATCHLIST_LOGGED: set[str] = set()


def _signed_orders_required() -> bool:
    """EXCHANGE_REQUIRE_SIGNED_ORDERS — signature enforcement is revertible."""
    return os.getenv("EXCHANGE_REQUIRE_SIGNED_ORDERS", "true").strip().lower() not in ("0", "false", "no", "off")


def _exchange_chain_id() -> str:
    """Expected envelope chain_id: EXCHANGE_CHAIN_ID > CHAIN_ID > design literal."""
    return os.getenv("EXCHANGE_CHAIN_ID") or os.getenv("CHAIN_ID") or _EXCHANGE_CHAIN_DEFAULT


def _env_decimal(name: str, default: str) -> Decimal:
    try:
        return Decimal(os.getenv(name, default))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


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


# In-memory sliding-window buckets for the section-9 abuse limits. The
# handlers run on a ThreadPoolExecutor (main.py), so a lock guards the map;
# buckets are per-process state — restarting the service resets the windows,
# which the design accepts (limits exist to blunt spam, not to audit it).
_RATE_LOCK = threading.Lock()
_RATE_BUCKETS: dict[str, deque] = {}
_RATE_WINDOW_S = 60.0
_RATE_MAX_KEYS = 10_000


def _rate_limit_hit(key: str, per_minute: int) -> bool:
    """Record one event for ``key``; True when the window is already full."""
    if per_minute <= 0:
        return False
    now = time.monotonic()
    with _RATE_LOCK:
        if len(_RATE_BUCKETS) >= _RATE_MAX_KEYS:
            for k, bucket in list(_RATE_BUCKETS.items()):
                if not bucket or now - bucket[-1] > _RATE_WINDOW_S:
                    del _RATE_BUCKETS[k]
        dq = _RATE_BUCKETS.get(key)
        if dq is None:
            dq = deque()
            _RATE_BUCKETS[key] = dq
        while dq and now - dq[0] > _RATE_WINDOW_S:
            dq.popleft()
        if len(dq) >= per_minute:
            return True
        dq.append(now)
        return False


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


class ExchangeMixin:
    """Trading, metrics, treasury, health, and wallet-balance methods."""

    def _registry_labels(self, cursor) -> dict[str, str]:
        """address -> label for registered/seeded nodes (display on the board)."""
        rows = cursor.execute("SELECT address, label FROM node_registry WHERE status IN ('seeded', 'registered')").fetchall()
        return dict(rows)

    def get_recent_trades(self, parsed):
        """Get recent trades"""
        query = urllib.parse.parse_qs(parsed.query)
        limit = int(query.get("limit", [20])[0])

        conn = sqlite3.connect(get_db_path())
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, amount, price, total, created_at, buyer_address, seller_address, fee_ait
                FROM trades
                ORDER BY created_at DESC
                LIMIT ?
            """,
                (limit,),
            )
            labels = self._registry_labels(cursor)

            trades = []
            for row in cursor.fetchall():
                buyer_addr, seller_addr = row[5], row[6]
                trades.append(
                    {
                        "id": row[0],
                        "amount": row[1],
                        "price": row[2],
                        "total": row[3],
                        "created_at": row[4],
                        "buyer_label": labels.get(buyer_addr) if buyer_addr else None,
                        "seller_label": labels.get(seller_addr) if seller_addr else None,
                        "buyer": _short_addr(buyer_addr),
                        "seller": _short_addr(seller_addr),
                        "fee_ait": row[7],
                    }
                )
        finally:
            conn.close()

        self.send_json_response(trades)  # type: ignore[attr-defined]

    def _orderbook_row(self, row, labels: dict, band: tuple | None) -> dict:
        """One ladder row plus the phase-2 annotations (node label, band flag)."""
        price_dec = _to_decimal(row[3])
        out_of_band = None
        if band is not None:
            out_of_band = not (band[0] <= price_dec <= band[1])
        # user_address is legacy free-text on pre-phase-2 rows — publish only a
        # registry label or a shortened 0x address, never arbitrary strings.
        raw_addr = row[9] if isinstance(row[9], str) and row[9].startswith("0x") else None
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
            "node": labels.get(row[9]) or _short_addr(raw_addr),
            "expiry_height": row[10],
            "funded_state": row[11],
            "out_of_band": out_of_band,
        }

    def get_orderbook(self):
        """Get order book"""
        conn = sqlite3.connect(get_db_path())
        try:
            cursor = conn.cursor()
            labels = self._registry_labels(cursor)
            band = self._ait_eth_band()

            # Sell orders — integer ticks sort; TEXT '10' would sort below '2'.
            cursor.execute("""
                SELECT id, order_type, amount, price, total, filled, remaining, status, created_at,
                       user_address, expiry_height, funded_state
                FROM orders
                WHERE order_type = 'SELL' AND status = 'open'
                ORDER BY price_ticks ASC, id ASC
                LIMIT 20
            """)
            sells = [self._orderbook_row(row, labels, band) for row in cursor.fetchall()]

            # Buy orders — integer ticks, then id for deterministic FIFO ties.
            cursor.execute("""
                SELECT id, order_type, amount, price, total, filled, remaining, status, created_at,
                       user_address, expiry_height, funded_state
                FROM orders
                WHERE order_type = 'BUY' AND status = 'open'
                ORDER BY price_ticks DESC, id ASC
                LIMIT 20
            """)
            buys = [self._orderbook_row(row, labels, band) for row in cursor.fetchall()]
        finally:
            conn.close()

        # Per-level depth sums for the ladder (design section 8). Aggregation
        # happens in Python on the already-fetched rows — the tick math is
        # exact and the 20-row page size keeps it trivial.
        response: dict = {"buys": buys, "sells": sells, "levels": {"bids": [], "asks": []}}
        if band is not None:
            response["price_band"] = {"low": str(band[0]), "high": str(band[1])}
        for side_key, rows in (("bids", buys), ("asks", sells)):
            depth: dict[str, dict] = {}
            for row in rows:
                level = depth.setdefault(row["price"], {"price": row["price"], "depth": Decimal(0)})
                level["depth"] += _to_decimal(row["remaining"])
            response["levels"][side_key] = [
                {"price": lvl["price"], "depth": format(lvl["depth"], "f")} for lvl in depth.values()
            ]
        self.send_json_response(response)  # type: ignore[attr-defined]

    def _parse_order_payload(self, data: dict):
        """Validate an order POST body; send_error and return None on rejection.

        Returns ``(order_type, user_address, amount, price, total,
        amount_ticks, price_ticks)`` — Decimals for display/total and fixed-point
        ticks for SQL predicates.
        """
        order_type = data.get("order_type")
        amount_raw = data.get("amount")
        price_raw = data.get("price")
        user_address = data.get("user_address")

        if not all([order_type, amount_raw, price_raw, user_address]):
            self.send_error(400, "Missing required fields")  # type: ignore[attr-defined]
            return None

        if order_type not in ["BUY", "SELL"]:
            self.send_error(400, "Invalid order type")  # type: ignore[attr-defined]
            return None

        # B2: Convert to Decimal for exact monetary arithmetic
        try:
            amount_dec = _to_decimal(amount_raw)
            price_dec = _to_decimal(price_raw)
        except Exception:
            self.send_error(400, "Invalid amount or price")  # type: ignore[attr-defined]
            return None

        if amount_dec <= 0 or price_dec <= 0:
            self.send_error(400, "Amount and price must be positive")  # type: ignore[attr-defined]
            return None

        total_dec = amount_dec * price_dec

        # Fixed-point check: amount and price must be exactly representable
        # at 8 decimal places, or the integer tick columns cannot be
        # written and SQL matching would silently misorder this order.
        # `total` (amount*price) may legitimately carry >8 decimals and
        # stays TEXT-only — it never appears in a SQL predicate.
        try:
            amount_ticks = to_ticks(amount_dec)
            price_ticks = to_ticks(price_dec)
        except ValueError:
            self.send_error(400, "Amount or price exceeds 8-decimal precision")  # type: ignore[attr-defined]
            return None

        return order_type, user_address, amount_dec, price_dec, total_dec, amount_ticks, price_ticks

    def handle_place_order(self):
        """Place a new order.

        ETH-11 phase 2: when ``EXCHANGE_REQUIRE_SIGNED_ORDERS`` is on (the
        default), the body must carry a signed order envelope — see
        ``_place_order_signed``. When the flag is off the endpoint behaves
        exactly as it did before phase 2 (unsigned, unregistered — kept for
        revertibility, per the design's rollout section).

        B1 fix: The order insert and matching logic run within a single
        ``BEGIN IMMEDIATE`` transaction. This acquires the SQLite write lock
        before reading open orders, preventing two concurrent requests from
        matching the same counterparty order (double-spend risk).

        B2 fix: All monetary values (amount, price, total, filled, remaining)
        are stored as TEXT (Decimal-as-string) for exact arithmetic. No float
        rounding drift.

        B3 fix: Database connections are closed via try/finally.

        Auth: with enforcement on, the signed envelope IS the credential —
        registered node's secp256k1 signature, verified before any DB write
        (design section 9). The legacy unsigned path keeps X-Api-Key.
        """
        data = self._read_json_body()  # type: ignore[attr-defined]
        if _signed_orders_required():
            if not isinstance(data, dict) or not data:
                # No body = no signature material → auth failure, not a
                # malformed-order failure (keeps the 401 boundary test
                # semantics: an unauthenticated write is Unauthorized).
                self.send_error(401, "Signature required")  # type: ignore[attr-defined]
                return
            self._place_order_signed(data)
        else:
            self._place_order_unsigned(data)

    def _place_order_unsigned(self, data):
        """Pre-phase-2 placement path: free-text user_address, no envelope."""
        # Auth before the body check — the pre-phase-2 boundary contract:
        # a request without a key is Unauthorized even when the body is empty.
        if not self._require_api_key():  # type: ignore[attr-defined]
            return
        if not data:
            self.send_error(400, "Missing request body")  # type: ignore[attr-defined]
            return
        try:
            parsed = self._parse_order_payload(data)
            if parsed is None:
                return
            order_type, user_address, amount_dec, price_dec, total_dec, amount_ticks, price_ticks = parsed

            # Orders used to be broadcast to the chain via POST /rpc/sendTx, but the
            # node removed that endpoint and its replacement (/rpc/transaction)
            # requires a wallet-signed transaction the exchange cannot produce for
            # the user. Orders are therefore database-only and tx_hash stays empty.
            tx_hash = ""

            # B1: Insert order and match within a single transaction.
            # BEGIN IMMEDIATE acquires the write lock before we read open orders,
            # preventing concurrent requests from double-matching the same counterparty.
            conn = sqlite3.connect(get_db_path(), timeout=30)
            operation_attempt = 0
            idempotency_key = _idempotency_key(self)
            try:
                conn.execute("BEGIN IMMEDIATE")
                cursor = conn.cursor()

                # The ledger row shares this transaction: commit persists the
                # order and its idempotency record atomically, and a crash
                # before commit rolls both back so a replay starts clean.
                if idempotency_key:
                    begin = get_operation_ledger().begin(idempotency_key, "place_order", request_hash(data), conn=conn)
                    if begin.status is not BeginStatus.EXECUTE:
                        conn.rollback()
                        self._send_operation_result(begin)  # type: ignore[attr-defined]
                        return
                    operation_attempt = begin.attempt

                # Store order in local database for orderbook (B2: TEXT for the
                # exact display value; tick columns carry the same values as
                # fixed-point integers for SQL comparison and ordering).
                cursor.execute(
                    """
                    INSERT INTO orders (order_type, amount, price, total, remaining, user_address, tx_hash,
                                        amount_ticks, price_ticks, filled_ticks, remaining_ticks)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        order_type,
                        str(amount_dec),
                        str(price_dec),
                        str(total_dec),
                        str(amount_dec),
                        user_address,
                        tx_hash,
                        amount_ticks,
                        price_ticks,
                        0,
                        amount_ticks,
                    ),
                )

                order_id = cursor.lastrowid

                # Get the created order
                cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
                row = cursor.fetchone()
                order = _row_to_order(row)

                # B1: Match within the same transaction (holds the write lock)
                self._match_orders_in_txn(cursor, order)

                if idempotency_key and not get_operation_ledger().complete(
                    idempotency_key, operation_attempt, order, conn=conn
                ):
                    raise RuntimeError("operation lease superseded mid-transaction")
                conn.commit()
            except Exception:
                conn.rollback()
                if idempotency_key and operation_attempt:
                    get_operation_ledger().fail(idempotency_key, operation_attempt, "order placement failed")
                raise
            finally:
                conn.close()

            self.send_json_response(order)  # type: ignore[attr-defined]

        except Exception:
            # Blockchain is down — return an honest error, not fake supply
            # numbers. The exception stays in the log; its text carries RPC
            # URLs and internals that must not reach the caller.
            logger.exception("Blockchain RPC unavailable")
            self.send_json_response(  # type: ignore[attr-defined]
                {
                    "error": "Blockchain RPC unavailable",
                    "source": "error",
                },
                status=503,
            )

    # ── ETH-11 phase 2 — signed orders (design sections 1–6, 9) ──────────

    def _client_ip(self) -> str:
        """Client IP for per-IP rate buckets.

        The service sits behind nginx which sets ``X-Real-IP $remote_addr``.
        The forwarded header is trusted only when the direct peer is in
        ``EXCHANGE_TRUSTED_PROXIES`` (default loopback) — otherwise the raw
        header is client-spoofable and ignored.
        """
        request = getattr(self, "request", None)
        client = getattr(request, "client", None)
        peer = getattr(client, "host", None)
        if not (isinstance(peer, str) and peer):
            return "unknown"
        trusted = {a.strip() for a in os.getenv("EXCHANGE_TRUSTED_PROXIES", "127.0.0.1,::1").split(",") if a.strip()}
        if peer in trusted:
            headers = getattr(self, "headers", None)
            get_header = getattr(headers, "get", None)
            if callable(get_header):
                real = get_header("x-real-ip") or get_header("X-Real-IP")
                if isinstance(real, str) and real.strip():
                    return real.strip()
        return peer

    def _chain_head_height(self) -> int | None:
        """Current chain height for expiry checks; None when the node RPC is down."""
        try:
            head = self._rpc_get("/rpc/head")  # type: ignore[attr-defined]
            height = head.get("height")
            return height if isinstance(height, int) else None
        except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError):
            return None

    def _ait_eth_band(self) -> tuple[Decimal, Decimal] | None:
        """(low, high) allowed price ticks around the oracle AIT/ETH rate.

        Returns None when the feed is unavailable or stale — placements then
        answer 503 like the quote endpoint (design section 3). Env-pinned
        prices count as fresh, matching the wallet's get_eth_prices_meta
        convention; otherwise the underlying ETH feed ages are checked
        against BRIDGE_PRICE_MAX_AGE.
        """
        band_pct = _env_decimal("EXCHANGE_PRICE_BAND_PCT", "0.10")
        now = time.monotonic()
        cached = _band_cache.get("band")
        cached_at = _band_cache.get("t")
        if (
            isinstance(cached, tuple)
            and isinstance(cached_at, float)
            and cached[0] == band_pct
            and now - cached_at < BAND_CACHE_TTL_S
        ):
            return cached[1]
        rate = self._ait_eth_rate()
        if rate is None or rate <= 0:
            return None
        band = (rate * (Decimal(1) - band_pct), rate * (Decimal(1) + band_pct))
        _band_cache["band"] = (band_pct, band)
        _band_cache["t"] = now
        return band

    def _ait_eth_rate(self) -> Decimal | None:
        """The ETH-per-AIT reference rate, or None when no fresh source exists."""
        ait_usd_pin = os.getenv("AIT_USD_FIXED_PRICE")
        ait_eur_pin = os.getenv("AIT_EUR_FIXED_PRICE")
        eth_usd_pin = os.getenv("ETH_USD_FIXED_PRICE")
        eth_eur_pin = os.getenv("ETH_EUR_FIXED_PRICE")
        if ait_usd_pin and eth_usd_pin:
            try:
                return Decimal(ait_usd_pin) / Decimal(eth_usd_pin)
            except (InvalidOperation, ZeroDivisionError):
                return None
        if ait_eur_pin and eth_eur_pin:
            try:
                return Decimal(ait_eur_pin) / Decimal(eth_eur_pin)
            except (InvalidOperation, ZeroDivisionError):
                return None
        try:
            from aitbc.oracles.price_oracle import get_price_oracle

            oracle = get_price_oracle()
            ait_eth = oracle.get_price("AIT", "ETH")
            eth_usd = oracle.get_price("ETH", "USD")
            eth_eur = oracle.get_price("ETH", "EUR")
        except (ImportError, AttributeError, RuntimeError, ValueError, TypeError):
            logger.exception("Price oracle call failed")
            return None
        if not (ait_eth and eth_usd and eth_eur):
            return None
        max_age = _env_decimal("BRIDGE_PRICE_MAX_AGE", "7200")
        oldest = min(res.timestamp for res in (ait_eth, eth_usd, eth_eur))
        if Decimal(str(time.time() - oldest)) > max_age:
            logger.warning("Exchange price feed stale — refusing to price the order band")
            return None
        return Decimal(str(ait_eth.price))

    def _verify_signed_body(self, data: dict, fields: frozenset):
        """Parse + verify ``{envelope, signature, user_address}``; deny and None on failure.

        Signature verification happens before any DB write: unsigned garbage
        costs a 401, per design section 9. A structurally wrong envelope that
        still arrives signed is a 400.
        """
        envelope = data.get("envelope")
        signature = data.get("signature")
        user_address = data.get("user_address")
        if not isinstance(envelope, dict) or not isinstance(signature, str) or not signature.strip():
            self.send_error(401, "Signature required")  # type: ignore[attr-defined]
            return None
        if not isinstance(user_address, str) or not user_address:
            self.send_error(400, "user_address required")  # type: ignore[attr-defined]
            return None
        if set(envelope.keys()) != fields:
            self.send_error(400, "Envelope fields invalid")  # type: ignore[attr-defined]
            return None
        if envelope.get("chain_id") != _exchange_chain_id():
            self.send_error(400, "chain_id mismatch")  # type: ignore[attr-defined]
            return None
        from aitbc.crypto.signature_recovery import canonical_address

        address = canonical_address(user_address)
        if not _verify_envelope_signature(envelope, signature, address):
            self.send_error(401, "Invalid signature")  # type: ignore[attr-defined]
            return None
        return envelope, address, _envelope_hash(envelope)

    def _registry_status(self, cursor, address: str) -> str | None:
        row = cursor.execute("SELECT status FROM node_registry WHERE address = ?", (address,)).fetchone()
        return row[0] if row else None

    @staticmethod
    def _expected_nonce(cursor, address: str) -> int:
        row = cursor.execute("SELECT next_nonce FROM order_nonces WHERE address = ?", (address,)).fetchone()
        return row[0] if row else 0

    @staticmethod
    def _claim_nonce(cursor, address: str, expected: int) -> bool:
        """Advance the exchange-scoped counter atomically; False on replay/race."""
        cursor.execute("INSERT OR IGNORE INTO order_nonces (address, next_nonce) VALUES (?, 0)", (address,))
        cursor.execute(
            "UPDATE order_nonces SET next_nonce = next_nonce + 1 WHERE address = ? AND next_nonce = ?",
            (address, expected),
        )
        return bool(cursor.rowcount == 1)

    def _order_envelope_error(self, envelope: dict) -> str | None:
        """Field-level checks on a verified order envelope; None = clean."""
        if envelope["side"] not in ("BUY", "SELL"):
            return "Invalid side"
        if envelope["pair"] != EXCHANGE_ORDER_PAIR:
            return "Invalid pair"
        for field in ("amount_ticks", "price_ticks", "expiry_height", "account_nonce"):
            value = envelope[field]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                return f"Invalid {field}"
        if envelope["amount_ticks"] <= 0 or envelope["price_ticks"] <= 0:
            return "Amount and price must be positive"
        return None

    def _cancel_envelope_error(self, envelope: dict) -> str | None:
        """Field-level checks on a verified cancel envelope; None = clean."""
        if envelope["action"] != _CANCEL_ACTION:
            return "Invalid cancel action"
        for field in ("order_id", "account_nonce", "expiry_height"):
            if not isinstance(envelope[field], int) or isinstance(envelope[field], bool):
                return f"Invalid {field}"
        return None

    def _live_head_if_unexpired(self, expiry_height: int, what: str) -> int | None:
        """Head-vs-expiry guard; the chain head when live, else None after 503/400."""
        head = self._chain_head_height()
        if head is None:
            self.send_json_response({"error": "Chain head unavailable"}, status=503)  # type: ignore[attr-defined]
            return None
        if expiry_height <= head:
            self.send_json_response({"error": f"{what} envelope expired"}, status=400)  # type: ignore[attr-defined]
            return None
        return head

    def _signed_order_limits(self, envelope: dict) -> str | None:
        """Non-DB limits on a verified placement (band, min size); None = clean."""
        amount = ticks_to_decimal(envelope["amount_ticks"])
        if amount < _env_decimal("EXCHANGE_MIN_ORDER_AIT", "1"):
            return "Below minimum order size"
        price = ticks_to_decimal(envelope["price_ticks"])
        band = self._ait_eth_band()
        if band is None:
            return "FEED_STALE"
        if not (band[0] <= price <= band[1]):
            return "Price outside oracle band"
        return None

    def _place_order_signed(self, data: dict) -> None:
        """POST /api/orders under EXCHANGE_REQUIRE_SIGNED_ORDERS (default on)."""
        # Per-IP bucket runs before the secp256k1 verify — that is the
        # expensive call a flood would abuse. The per-address bucket needs the
        # recovered signer, so it runs right after verification.
        max_per_min = _env_int("EXCHANGE_MAX_ORDERS_PER_MIN", 20)
        if _rate_limit_hit(f"ip:{self._client_ip()}", max_per_min):
            self.send_json_response({"error": "Order rate limit reached"}, status=429)  # type: ignore[attr-defined]
            return
        verified = self._verify_signed_body(data, _ORDER_ENVELOPE_FIELDS)
        if verified is None:
            return
        envelope, address, env_hash = verified
        if _rate_limit_hit(f"addr:{address}", max_per_min):
            self.send_json_response({"error": "Order rate limit reached"}, status=429)  # type: ignore[attr-defined]
            return
        field_error = self._order_envelope_error(envelope)
        if field_error is not None:
            self.send_error(400, field_error)  # type: ignore[attr-defined]
            return
        head = self._live_head_if_unexpired(envelope["expiry_height"], "Order")
        if head is None:
            return
        limit_error = self._signed_order_limits(envelope)
        if limit_error == "FEED_STALE":
            self.send_json_response({"error": "Price feed unavailable"}, status=503)  # type: ignore[attr-defined]
            return
        if limit_error is not None:
            self.send_error(400, limit_error)  # type: ignore[attr-defined]
            return
        self._commit_signed_order(data, envelope, address, env_hash, head)

    def _signed_order_gate(self, cursor, address, env_hash, envelope, head):
        """In-transaction checks; ``(status, payload)`` short-circuit or None to proceed.

        Byte-identical resubmits (design section 11) dedupe BEFORE the nonce
        gate: the first attempt already consumed the envelope's nonce, so a
        replay would die as a stale-nonce 409 instead of returning its row.
        """
        if self._registry_status(cursor, address) != "registered":
            return 403, {"error": "Node not registered"}
        existing = self._order_by_envelope(cursor, address, env_hash)
        if existing is not None:
            return 200, existing
        if envelope["account_nonce"] != self._expected_nonce(cursor, address) or not self._claim_nonce(
            cursor, address, envelope["account_nonce"]
        ):
            return 409, {"error": "Stale account_nonce"}
        self._expire_open_orders(cursor, head)
        cap_error = self._book_capacity_error(cursor, address)
        if cap_error is not None:
            return 429, {"error": cap_error}
        return None

    def _commit_signed_order(self, data, envelope, address, env_hash, head) -> None:
        """Insert + match a verified order under BEGIN IMMEDIATE."""
        conn = sqlite3.connect(get_db_path(), timeout=30)
        operation_attempt = 0
        idempotency_key = _idempotency_key(self)
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            if idempotency_key:
                begin = get_operation_ledger().begin(idempotency_key, "place_order", request_hash(data), conn=conn)
                if begin.status is not BeginStatus.EXECUTE:
                    conn.rollback()
                    self._send_operation_result(begin)  # type: ignore[attr-defined]
                    return
                operation_attempt = begin.attempt
            gate = self._signed_order_gate(cursor, address, env_hash, envelope, head)
            if gate is not None:
                conn.rollback()
                self.send_json_response(gate[1], status=gate[0])  # type: ignore[attr-defined]
                return
            order = self._insert_signed_order(cursor, envelope, address, env_hash, str(data["signature"]))
            if order is None:
                # Unreachable after the gate's dedupe check barring a same-hash
                # interleave — belt-and-braces behind the UNIQUE index.
                conn.rollback()
                existing = self._order_by_envelope(cursor, address, env_hash)
                self.send_json_response(existing or {"error": "Duplicate envelope"})  # type: ignore[attr-defined]
                return
            self._match_orders_in_txn(cursor, order, head_height=head, guard_address=address)
            if idempotency_key and not get_operation_ledger().complete(idempotency_key, operation_attempt, order, conn=conn):
                raise RuntimeError("operation lease superseded mid-transaction")
            conn.commit()
        except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, RuntimeError):
            conn.rollback()
            if idempotency_key and operation_attempt:
                get_operation_ledger().fail(idempotency_key, operation_attempt, "order placement failed")
            logger.exception("Signed order placement failed")
            self.send_json_response({"error": "Order placement failed"}, status=503)  # type: ignore[attr-defined]
            return
        finally:
            conn.close()
        self.send_json_response(order)  # type: ignore[attr-defined]

    def _insert_signed_order(self, cursor, envelope, address, env_hash, signature):
        """INSERT the signed order; None when (address, envelope_hash) already exists."""
        order_type = envelope["side"]
        amount_dec = ticks_to_decimal(envelope["amount_ticks"])
        price_dec = ticks_to_decimal(envelope["price_ticks"])
        total_dec = amount_dec * price_dec
        try:
            cursor.execute(
                """
                INSERT INTO orders (order_type, amount, price, total, remaining, user_address, tx_hash,
                                    amount_ticks, price_ticks, filled_ticks, remaining_ticks,
                                    signature, envelope_hash, account_nonce, expiry_height, funded_state)
                VALUES (?, ?, ?, ?, ?, ?, '', ?, ?, 0, ?, ?, ?, ?, ?, 'unfunded')
                """,
                (
                    order_type,
                    str(amount_dec),
                    str(price_dec),
                    str(total_dec),
                    str(amount_dec),
                    address,
                    envelope["amount_ticks"],
                    envelope["price_ticks"],
                    envelope["amount_ticks"],
                    signature,
                    env_hash,
                    envelope["account_nonce"],
                    envelope["expiry_height"],
                ),
            )
        except sqlite3.IntegrityError:
            # UNIQUE(user_address, envelope_hash): a byte-identical resubmit is
            # a no-op — the caller returns the recorded row (design section 11).
            if cursor.execute(
                "SELECT 1 FROM orders WHERE user_address = ? AND envelope_hash = ?", (address, env_hash)
            ).fetchone():
                return None
            raise
        order_id = cursor.lastrowid
        return {
            "id": order_id,
            "order_type": order_type,
            "amount": str(amount_dec),
            "price": str(price_dec),
            "total": str(total_dec),
            "filled": "0",
            "remaining": str(amount_dec),
            "status": "open",
            "user_address": address,
            "tx_hash": "",
            "envelope_hash": env_hash,
            "expiry_height": envelope["expiry_height"],
            "funded_state": "unfunded",
        }

    def _order_by_envelope(self, cursor, address, env_hash):
        """Fetch the recorded order for a byte-identical resubmit."""
        row = cursor.execute(
            """
            SELECT id, order_type, amount, price, total, filled, remaining, status, created_at,
                   user_address, tx_hash, envelope_hash, expiry_height, funded_state
            FROM orders WHERE user_address = ? AND envelope_hash = ?
            """,
            (address, env_hash),
        ).fetchone()
        if row is None:
            return None
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
            "user_address": row[9],
            "tx_hash": row[10],
            "envelope_hash": row[11],
            "expiry_height": row[12],
            "funded_state": row[13],
        }

    def _book_capacity_error(self, cursor, address: str) -> str | None:
        """Section-9 caps: per-node open orders and total book rows."""
        open_for_node = cursor.execute(
            "SELECT COUNT(*) FROM orders WHERE user_address = ? AND status = 'open'", (address,)
        ).fetchone()[0]
        if open_for_node >= _env_int("EXCHANGE_MAX_OPEN_PER_NODE", 50):
            return "Open-order limit reached"
        open_total = cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'open'").fetchone()[0]
        if open_total >= _env_int("EXCHANGE_MAX_BOOK_ROWS", 5000):
            return "Order book capacity reached"
        return None

    @staticmethod
    def _expire_open_orders(cursor, head: int) -> None:
        """Lazily flip expired open orders at match-scan time (design section 6)."""
        cursor.execute(
            "UPDATE orders SET status = 'expired' WHERE status = 'open' AND expiry_height IS NOT NULL AND expiry_height <= ?",
            (head,),
        )

    def handle_cancel_order(self, order_id_str: str) -> None:
        """POST /api/orders/<id>/cancel — signed cancel (design section 6)."""
        if not _signed_orders_required():
            self.send_error(404, "Not Found")  # type: ignore[attr-defined]
            return
        data = self._read_json_body()  # type: ignore[attr-defined]
        if not data:
            self.send_error(400, "Missing request body")  # type: ignore[attr-defined]
            return
        verified = self._verify_signed_body(data, _CANCEL_ENVELOPE_FIELDS)
        if verified is None:
            return
        envelope, address, _env_hash = verified
        field_error = self._cancel_envelope_error(envelope)
        if field_error is not None:
            self.send_error(400, field_error)  # type: ignore[attr-defined]
            return
        try:
            path_id = int(order_id_str)
        except ValueError:
            self.send_error(404, "Not Found")  # type: ignore[attr-defined]
            return
        if envelope["order_id"] != path_id:
            self.send_error(400, "order_id mismatch")  # type: ignore[attr-defined]
            return
        if self._live_head_if_unexpired(envelope["expiry_height"], "Cancel") is None:
            return
        self._commit_cancel(data, envelope, address, path_id)

    def _commit_cancel(self, data, envelope, address, order_id) -> None:
        conn = sqlite3.connect(get_db_path(), timeout=30)
        operation_attempt = 0
        idempotency_key = _idempotency_key(self)
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            if idempotency_key:
                begin = get_operation_ledger().begin(idempotency_key, "cancel_order", request_hash(data), conn=conn)
                if begin.status is not BeginStatus.EXECUTE:
                    conn.rollback()
                    self._send_operation_result(begin)  # type: ignore[attr-defined]
                    return
                operation_attempt = begin.attempt
            row = cursor.execute("SELECT user_address, status FROM orders WHERE id = ?", (order_id,)).fetchone()
            if row is None:
                conn.rollback()
                self.send_json_response({"error": "Order not found"}, status=404)  # type: ignore[attr-defined]
                return
            owner, status = row[0], row[1]
            if not owner or owner.lower() != address.lower():
                conn.rollback()
                self.send_json_response({"error": "Not the order owner"}, status=403)  # type: ignore[attr-defined]
                return
            if status != "open":
                # Same write lock decides the race: whoever commits first wins
                # and the loser reads the committed state — deterministic 409.
                conn.rollback()
                self.send_json_response(  # type: ignore[attr-defined]
                    {"error": f"Order not cancellable ({status})"}, status=409
                )
                return
            if envelope["account_nonce"] != self._expected_nonce(cursor, address) or not self._claim_nonce(
                cursor, address, envelope["account_nonce"]
            ):
                conn.rollback()
                self.send_json_response({"error": "Stale account_nonce"}, status=409)  # type: ignore[attr-defined]
                return
            cursor.execute(
                "UPDATE orders SET status = 'cancelled', cancelled_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(), order_id),
            )
            result = {"id": order_id, "status": "cancelled"}
            if idempotency_key and not get_operation_ledger().complete(idempotency_key, operation_attempt, result, conn=conn):
                raise RuntimeError("operation lease superseded mid-transaction")
            conn.commit()
        except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, RuntimeError):
            conn.rollback()
            if idempotency_key and operation_attempt:
                get_operation_ledger().fail(idempotency_key, operation_attempt, "order cancel failed")
            logger.exception("Order cancel failed")
            self.send_json_response({"error": "Order cancel failed"}, status=503)  # type: ignore[attr-defined]
            return
        finally:
            conn.close()
        self.send_json_response(result)  # type: ignore[attr-defined]

    def handle_node_register(self) -> None:
        """POST /api/exchange/nodes — claim a seeded registry row by signature."""
        if not _signed_orders_required():
            self.send_error(404, "Not Found")  # type: ignore[attr-defined]
            return
        if _rate_limit_hit(f"ip:{self._client_ip()}:reg", _env_int("EXCHANGE_REGISTER_PER_MIN", 5)):
            self.send_json_response({"error": "Rate limit reached"}, status=429)  # type: ignore[attr-defined]
            return
        data = self._read_json_body()  # type: ignore[attr-defined]
        if not data:
            self.send_error(400, "Missing request body")  # type: ignore[attr-defined]
            return
        verified = self._verify_signed_body(data, _REGISTER_ENVELOPE_FIELDS)
        if verified is None:
            return
        envelope, address, env_hash = verified
        if envelope["action"] != _REGISTER_ACTION:
            self.send_error(400, "Invalid register action")  # type: ignore[attr-defined]
            return
        if envelope["address"] != address:
            self.send_error(400, "Envelope address mismatch")  # type: ignore[attr-defined]
            return
        if not isinstance(envelope["label"], str) or not envelope["label"].strip():
            self.send_error(400, "Invalid label")  # type: ignore[attr-defined]
            return
        if not isinstance(envelope["account_nonce"], int) or isinstance(envelope["account_nonce"], bool):
            self.send_error(400, "Invalid account_nonce")  # type: ignore[attr-defined]
            return
        self._commit_register(envelope, address, env_hash)

    def _commit_register(self, envelope, address, env_hash) -> None:
        conn = sqlite3.connect(get_db_path(), timeout=30)
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            row = cursor.execute("SELECT label, status FROM node_registry WHERE address = ?", (address,)).fetchone()
            if row is None:
                conn.rollback()
                self.send_json_response({"error": "Address not in registry seed"}, status=403)  # type: ignore[attr-defined]
                return
            if row[1] != "seeded":
                conn.rollback()
                self.send_json_response({"error": "Node already registered"}, status=409)  # type: ignore[attr-defined]
                return
            if envelope["label"].strip() != row[0]:
                conn.rollback()
                self.send_json_response({"error": "Label is pinned by the registry seed"}, status=400)  # type: ignore[attr-defined]
                return
            if envelope["account_nonce"] != self._expected_nonce(cursor, address) or not self._claim_nonce(
                cursor, address, envelope["account_nonce"]
            ):
                conn.rollback()
                self.send_json_response({"error": "Stale account_nonce"}, status=409)  # type: ignore[attr-defined]
                return
            cursor.execute(
                "UPDATE node_registry SET status = 'registered', registered_tx = ?, registered_at = ? WHERE address = ?",
                (env_hash, datetime.now(UTC).isoformat(), address),
            )
            result = {
                "address": address,
                "label": row[0],
                "status": "registered",
                "next_nonce": envelope["account_nonce"] + 1,
            }
            conn.commit()
        except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, RuntimeError):
            conn.rollback()
            logger.exception("Node registration failed")
            self.send_json_response({"error": "Registration failed"}, status=503)  # type: ignore[attr-defined]
            return
        finally:
            conn.close()
        self.send_json_response(result)  # type: ignore[attr-defined]

    def handle_exchange_nodes(self) -> None:
        """GET /api/exchange/nodes — the participants board (design section 4/8)."""
        if not _signed_orders_required():
            self.send_error(404, "Not Found")  # type: ignore[attr-defined]
            return
        if _rate_limit_hit(f"read:{self._client_ip()}", _env_int("EXCHANGE_READS_PER_MIN", 60)):
            self.send_json_response({"error": "Rate limit reached"}, status=429)  # type: ignore[attr-defined]
            return
        conn = sqlite3.connect(get_db_path())
        try:
            nodes = self._node_rows(conn)
        finally:
            conn.close()
        self.send_json_response({"nodes": nodes})  # type: ignore[attr-defined]

    def _node_rows(self, conn) -> list[dict]:
        cursor = conn.cursor()
        rows = cursor.execute("SELECT address, label, status, registered_at FROM node_registry ORDER BY label").fetchall()
        open_counts = dict(
            cursor.execute(
                "SELECT user_address, COUNT(*) FROM orders WHERE status = 'open' AND user_address IS NOT NULL GROUP BY user_address"
            ).fetchall()
        )
        watchlisted = self._watchlisted_addresses(cursor)
        return [
            {
                "label": label,
                "address": _short_addr(address),
                "status": status,
                "registered_at": registered_at,
                "open_orders": open_counts.get(address, 0),
                "watchlisted": address in watchlisted,
            }
            for address, label, status, registered_at in rows
        ]

    @staticmethod
    def _watchlisted_addresses(cursor) -> set:
        """Cancel-ratio flag (section 9): flag-only, never blocks an order.

        Flags an address once it has at least ``EXCHANGE_WATCHLIST_MIN_PLACEMENTS``
        placements (default 10 — a one-order-then-cancel user is normal) with
        cancels/placements strictly above ``EXCHANGE_CANCEL_RATIO`` (0.9) inside
        ``EXCHANGE_WATCHLIST_WINDOW_S`` seconds (default 24 h).
        """
        window_s = _env_int("EXCHANGE_WATCHLIST_WINDOW_S", 24 * 3600)
        cutoff = datetime.now(UTC).timestamp() - window_s
        cutoff_iso = datetime.fromtimestamp(cutoff, UTC).isoformat()
        placed = dict(
            cursor.execute(
                "SELECT user_address, COUNT(*) FROM orders WHERE user_address IS NOT NULL AND created_at > ? GROUP BY user_address",
                (cutoff_iso,),
            ).fetchall()
        )
        cancelled = dict(
            cursor.execute(
                "SELECT user_address, COUNT(*) FROM orders WHERE user_address IS NOT NULL AND cancelled_at IS NOT NULL AND cancelled_at > ? GROUP BY user_address",
                (cutoff_iso,),
            ).fetchall()
        )
        ratio = _env_decimal("EXCHANGE_CANCEL_RATIO", "0.9")
        min_placed = _env_int("EXCHANGE_WATCHLIST_MIN_PLACEMENTS", 10)
        flagged = {
            addr
            for addr, placed_count in placed.items()
            if placed_count >= min_placed and Decimal(cancelled.get(addr, 0)) / placed_count > ratio
        }
        for addr in sorted(flagged - _WATCHLIST_LOGGED):
            logger.warning("exchange watchlist: %s flagged (cancel ratio > %s in %ss window)", addr, ratio, window_s)
            _WATCHLIST_LOGGED.add(addr)
        return flagged

    def handle_my_orders(self, parsed) -> None:
        """GET /api/exchange/my-orders?addr= — one wallet's orders + next nonce."""
        if not _signed_orders_required():
            self.send_error(404, "Not Found")  # type: ignore[attr-defined]
            return
        if _rate_limit_hit(f"read:{self._client_ip()}", _env_int("EXCHANGE_READS_PER_MIN", 60)):
            self.send_json_response({"error": "Rate limit reached"}, status=429)  # type: ignore[attr-defined]
            return
        query = urllib.parse.parse_qs(parsed.query)
        raw_addr = (query.get("addr") or [""])[0]
        if not raw_addr:
            self.send_json_response({"error": "addr parameter required"}, status=400)  # type: ignore[attr-defined]
            return
        from aitbc.crypto.signature_recovery import canonical_address

        address = canonical_address(raw_addr)
        conn = sqlite3.connect(get_db_path())
        try:
            cursor = conn.cursor()
            registry = cursor.execute("SELECT label, status FROM node_registry WHERE address = ?", (address,)).fetchone()
            orders = [
                {
                    "id": row[0],
                    "order_type": row[1],
                    "amount": row[2],
                    "price": row[3],
                    "filled": row[4],
                    "remaining": row[5],
                    "status": row[6],
                    "created_at": row[7],
                    "expiry_height": row[8],
                    "funded_state": row[9],
                }
                for row in cursor.execute(
                    "SELECT id, order_type, amount, price, filled, remaining, status, created_at,"
                    " expiry_height, funded_state FROM orders WHERE user_address = ?"
                    " ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, id DESC LIMIT 100",
                    (address,),
                ).fetchall()
            ]
            next_nonce = self._expected_nonce(cursor, address)
        finally:
            conn.close()
        self.send_json_response(  # type: ignore[attr-defined]
            {
                "address": address,
                "label": registry[0] if registry else None,
                "registered": bool(registry and registry[1] == "registered"),
                "next_nonce": next_nonce,
                "orders": orders,
            }
        )

    def handle_treasury_balance(self):
        """Get exchange treasury balance from blockchain"""
        if not self._require_api_key():  # type: ignore[attr-defined]
            return
        try:
            import json
            import urllib.request

            # Treasury address from genesis
            treasury_address = "aitbcexchange00000000000000000000000000000000"
            blockchain_url = f"{RPC_BASE_URL}/rpc/getBalance/{treasury_address}"

            try:
                with urllib.request.urlopen(blockchain_url, timeout=RPC_TIMEOUT) as response:  # nosec B310 - RPC_BASE_URL is validated (module-level startswith http(s):// check in base.py) before this call
                    balance_data = json.loads(response.read().decode())
                    treasury_balance = balance_data.get("balance", 0)

                self.send_json_response(  # type: ignore[attr-defined]
                    {
                        "address": treasury_address,
                        "balance": str(treasury_balance),
                        "available_for_sale": str(treasury_balance),  # All treasury tokens available
                        "source": "blockchain",
                    }
                )
            except Exception:
                # No fabricated fallback: a treasury figure must come from the chain or not
                # be served at all.
                self.send_json_response(  # type: ignore[attr-defined]
                    {"error": "Treasury balance unavailable — blockchain RPC unreachable"}, status=503
                )

        except Exception:
            self.send_error(500, "Internal server error")  # type: ignore[attr-defined]

    def health_check(self):
        """Health check"""
        self.send_json_response({"status": "ok", "timestamp": datetime.now(UTC).isoformat()})  # type: ignore[attr-defined]

    def ready_check(self):
        """Readiness probe — 503 while an enabled required feature is unavailable.

        The order book needs only its own database. The bridge deposit/withdraw
        surface is enabled by default and additionally needs the deposits store
        the bridge-monitor service initializes; deployments that do not run the
        bridge should set BRIDGE_DEPOSIT_ENABLED=false rather than be reported
        ready with dead endpoints.
        """
        from aitbc.health_checks import run_readiness_checks

        from ..config import bridge_config

        checks = {"database": _check_exchange_db}
        if bridge_config.deposit_enabled or bridge_config.withdraw_enabled:
            checks["bridge_storage"] = _check_bridge_storage
        failed = run_readiness_checks(checks)
        if failed:
            self.send_json_response(  # type: ignore[attr-defined]
                {"status": "not_ready", "error": "readiness check failed", "failed": failed}, status=503
            )
            return
        self.send_json_response(  # type: ignore[attr-defined]
            {"status": "ready", "checks": sorted(checks), "timestamp": datetime.now(UTC).isoformat()}
        )

    def handle_metrics(self):
        """Prometheus metrics endpoint"""
        try:
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

            output = generate_latest()
            self.send_response(200)  # type: ignore[attr-defined]
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)  # type: ignore[attr-defined]
            self.end_headers()  # type: ignore[attr-defined]
            self.wfile.write(output)  # type: ignore[attr-defined]
        except Exception:
            self.send_error(500, "Internal server error")  # type: ignore[attr-defined]

    def handle_exchange_history(self, parsed):
        """GET /v1/exchange/history — return current ETH and AIT prices for USD and EUR"""
        try:
            import sys

            sys.path.insert(0, "/opt/aitbc")
            from aitbc.oracles.price_oracle import get_price_oracle

            oracle = get_price_oracle()
            eth_usd = oracle.get_price("ETH", "USD")
            eth_eur = oracle.get_price("ETH", "EUR")
            ait_usd = oracle.get_price("AIT", "USD")
            ait_eur = oracle.get_price("AIT", "EUR")

            # Fallback: derive AIT/EUR from USD if oracle didn't return it directly
            ait_eur_price = ait_eur.price if ait_eur else None
            if ait_eur_price is None and eth_usd and eth_eur and ait_usd:
                ait_eur_price = (ait_usd.price * eth_eur.price) / eth_usd.price

            # Calculate ETH/AIT rate
            eth_ait_rate = (eth_usd.price / ait_usd.price) if eth_usd and ait_usd else 0

            self.send_json_response(  # type: ignore[attr-defined]
                {
                    "success": True,
                    "current": {
                        "eth_usd": eth_usd.price if eth_usd else None,
                        "ait_usd": ait_usd.price if ait_usd else None,
                        "eth_eur": eth_eur.price if eth_eur else None,
                        "ait_eur": ait_eur_price,
                        "eth_ait_rate_usd": eth_ait_rate,
                        "timestamp": eth_usd.timestamp if eth_usd else None,
                    },
                    "history": [],
                }
            )
        except Exception:
            logger.exception("Exchange history request failed")
            self.send_json_response({"success": False, "error": "Exchange history unavailable"}, status=500)  # type: ignore[attr-defined]

    def handle_exchange_price_json(self):
        """GET /exchange/price.json — return AIT price in USD, EUR, and ETH equivalent"""
        try:
            import sys

            sys.path.insert(0, "/opt/aitbc")
            from aitbc.oracles.price_oracle import get_price_oracle

            oracle = get_price_oracle()
            ait_usd = oracle.get_price("AIT", "USD")
            ait_eur = oracle.get_price("AIT", "EUR")
            ait_eth = oracle.get_price("AIT", "ETH")
            eth_eur = oracle.get_price("ETH", "EUR")

            if ait_usd or ait_eur:
                self.send_json_response(  # type: ignore[attr-defined]
                    {
                        "price_usd": ait_usd.price if ait_usd else None,
                        "price_eur": ait_eur.price if ait_eur else None,
                        "price_eth": ait_eth.price if ait_eth else None,
                        "eth_eur": eth_eur.price if eth_eur else None,
                        "currency": "USD",
                        "timestamp": (ait_usd or ait_eur).timestamp,  # type: ignore[union-attr]
                        "source": (ait_usd or ait_eur).source,  # type: ignore[union-attr]
                    }
                )
            else:
                self.send_json_response({"error": "Price unavailable"}, status=503)  # type: ignore[attr-defined]
        except Exception:
            logger.exception("AIT price fetch failed")
            self.send_json_response({"error": "Price unavailable"}, status=503)  # type: ignore[attr-defined]

    def handle_wallet_balance(self):
        """Handle wallet balance request"""
        if not self._require_api_key():  # type: ignore[attr-defined]
            return
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(self.path)  # type: ignore[attr-defined]
        params = parse_qs(parsed.query)
        address = params.get("address", [""])[0]

        if not address:
            self.send_json_response({"error": "Wallet address is required"}, status=400)  # type: ignore[attr-defined]
            return

        try:
            # Query real blockchain for balance
            import json
            import urllib.request

            # Get AITBC balance from blockchain
            blockchain_url = f"{RPC_BASE_URL}/rpc/balance/{address}"
            with urllib.request.urlopen(blockchain_url, timeout=RPC_TIMEOUT) as response:  # nosec B310 - RPC_BASE_URL is validated (module-level startswith http(s):// check in base.py) before this call
                balance_data = json.loads(response.read().decode())

            # ETH balance is not queried — no Ethereum RPC is wired to this service, so no
            # `eth` field is returned rather than a fabricated zero.
            self.send_json_response(  # type: ignore[attr-defined]
                {
                    "aitbc": str(balance_data.get("balance", 0)),
                    "address": address,
                    "nonce": balance_data.get("nonce", 0),
                }
            )
        except Exception:
            # Fail loudly if the blockchain is unreachable — no fabricated fallback.
            self.send_json_response(  # type: ignore[attr-defined]
                {"error": "Failed to fetch balance from blockchain", "address": address}, status=503
            )

    def handle_wallet_connect(self):
        """Handle wallet connection request.

        Requires the client to provide their wallet address in the request
        body. No mock address is generated.
        """
        if not self._require_api_key():  # type: ignore[attr-defined]
            return

        body = self._read_json_body()  # type: ignore[attr-defined]
        if body is None:
            return

        address = body.get("address")
        if not address:
            self.send_json_response({"error": "Wallet address is required in request body"}, status=400)  # type: ignore[attr-defined]
            return

        # Verify the wallet exists via the wallet service
        import os

        wallet_url = os.getenv("WALLET_SERVICE_URL", "http://localhost:8108")
        try:
            import httpx

            from .wallet import wallet_auth_headers

            with httpx.Client(timeout=10) as client:
                resp = client.get(f"{wallet_url}/v1/wallets", params={"address": address}, headers=wallet_auth_headers())
                if resp.status_code == 200:
                    wallets = resp.json().get("wallets", [])
                    if wallets:
                        self.send_json_response(  # type: ignore[attr-defined]
                            {
                                "address": address,
                                "status": "connected",
                                "wallet_id": wallets[0].get("wallet_id", ""),
                            }
                        )
                    else:
                        self.send_json_response({"error": "Wallet not found", "address": address}, status=404)  # type: ignore[attr-defined]
                else:
                    self.send_json_response({"error": f"Wallet service error: {resp.status_code}"}, status=502)  # type: ignore[attr-defined]
        except Exception:
            logger.exception("Wallet service call failed")
            self.send_json_response({"error": "Wallet service unavailable"}, status=503)  # type: ignore[attr-defined]

    def _match_orders_in_txn(
        self, cursor, order: dict, head_height: int | None = None, guard_address: str | None = None
    ) -> None:
        """Match a new order against existing open orders within an existing transaction.

        B1 fix: This runs within the caller's transaction (which holds the
        write lock via ``BEGIN IMMEDIATE``). The matching read+update is
        atomic with the order insert, preventing concurrent double-matching.

        B2 fix: All monetary arithmetic uses Decimal. Values are stored as
        TEXT (Decimal-as-string) in the database.

        ETH-11 phase 2: when ``head_height`` is given, open orders whose
        ``expiry_height`` has passed are flipped to ``expired`` first (the
        lazy expiry from design section 6). When ``guard_address`` is given,
        rows belonging to the same address are never matched (self-match
        prevention — design sections 6/9). Both are left off by the unsigned
        legacy path so flag-off behavior is unchanged.

        Args:
            cursor: SQLite cursor within an active transaction.
            order: The new order dict (mutated in place with updated filled/remaining/status).
            head_height: current chain height for the lazy expiry sweep.
            guard_address: canonical address that must not be its own counterparty.
        """
        if not order or "order_type" not in order:
            return

        new_type = order["order_type"]
        new_price = _to_decimal(order["price"])
        new_price_ticks = to_ticks(new_price)
        new_remaining = _to_decimal(order["remaining"])
        new_id = order.get("id")

        if head_height is not None:
            self._expire_open_orders(cursor, head_height)

        # Find matching orders (opposite side, price-compatible). Comparisons
        # and ordering run on the integer tick columns — the TEXT price column
        # compares lexically ('10' < '2') and must never appear in a predicate.
        # id ASC is the deterministic tiebreak; created_at is second-granularity
        # and ties on orders placed within the same second. The self-match
        # guard compares case-insensitively: stored addresses may be legacy
        # free-text, signed orders write the canonical EIP-55 form.
        self_guard = "AND (user_address IS NULL OR LOWER(user_address) != LOWER(?))" if guard_address else ""
        if new_type == "BUY":
            # Match against SELL orders with price <= our buy price
            cursor.execute(
                f"""
                SELECT id, order_type, amount, price, total, filled, remaining, status, created_at, user_address, tx_hash
                FROM orders
                WHERE order_type = 'SELL' AND status = 'open' AND price_ticks <= ? {self_guard}
                ORDER BY price_ticks ASC, id ASC
                """,  # nosec B608 - self_guard is a fixed literal fragment, never input
                (new_price_ticks, guard_address) if guard_address else (new_price_ticks,),
            )
        else:
            # Match against BUY orders with price >= our sell price
            cursor.execute(
                f"""
                SELECT id, order_type, amount, price, total, filled, remaining, status, created_at, user_address, tx_hash
                FROM orders
                WHERE order_type = 'BUY' AND status = 'open' AND price_ticks >= ? {self_guard}
                ORDER BY price_ticks DESC, id ASC
                """,  # nosec B608 - same fixed fragment
                (new_price_ticks, guard_address) if guard_address else (new_price_ticks,),
            )

        matching_orders = cursor.fetchall()

        for match_row in matching_orders:
            if new_remaining <= 0:
                break

            match_id = match_row[0]
            match_remaining = _to_decimal(match_row[6])
            match_price = _to_decimal(match_row[3])
            match_filled = _to_decimal(match_row[5])

            if match_remaining <= 0:
                continue

            # B2: Calculate trade quantity with Decimal (exact arithmetic)
            trade_qty = min(new_remaining, match_remaining)
            trade_total = trade_qty * match_price

            # Buyer/seller attribution (phase 2): the tape row names the two
            # sides so the page can print node labels. fee_ait records the
            # EXCHANGE_FEE_PCT knob's value at match time (default 0 on
            # testnet, DECIDED 14 Oct) — phase 2 moves no funds, this is the
            # ledger column only.
            fee_ait, _net_ait = _apply_exchange_fee(trade_qty)
            buyer_addr = order.get("user_address") if new_type == "BUY" else match_row[9]
            seller_addr = match_row[9] if new_type == "BUY" else order.get("user_address")
            cursor.execute(
                """
                INSERT INTO trades (amount, price, total, created_at, buyer_address, seller_address, fee_ait)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(trade_qty),
                    str(match_price),
                    str(trade_total),
                    datetime.now(UTC).isoformat(),
                    buyer_addr,
                    seller_addr,
                    str(fee_ait),
                ),
            )

            # Update the matching order (B2: Decimal arithmetic, store as TEXT)
            new_match_filled = match_filled + trade_qty
            new_match_remaining = match_remaining - trade_qty
            new_match_status = "filled" if new_match_remaining <= 0 else "open"

            cursor.execute(
                """
                UPDATE orders SET filled = ?, remaining = ?, status = ?,
                    filled_ticks = ?, remaining_ticks = ?
                WHERE id = ?
                """,
                (
                    str(new_match_filled),
                    str(new_match_remaining),
                    new_match_status,
                    to_ticks(new_match_filled),
                    to_ticks(new_match_remaining),
                    match_id,
                ),
            )

            # Update the new order (in-memory)
            new_remaining -= trade_qty
            order["filled"] = str(_to_decimal(order.get("filled", 0)) + trade_qty)
            order["remaining"] = str(new_remaining)

            if new_remaining <= 0:
                order["status"] = "filled"

        # Update the new order in the database (B2: store as TEXT)
        if new_id:
            cursor.execute(
                """
                UPDATE orders SET filled = ?, remaining = ?, status = ?,
                    filled_ticks = ?, remaining_ticks = ?
                WHERE id = ?
                """,
                (
                    str(order.get("filled", 0)),
                    str(order.get("remaining", 0)),
                    order.get("status", "open"),
                    to_ticks(_to_decimal(order.get("filled", 0))),
                    to_ticks(_to_decimal(order.get("remaining", 0))),
                    new_id,
                ),
            )

    def match_orders(self, order: dict) -> None:
        """Match a new order against existing open orders (standalone transaction).

        This is a backward-compatible wrapper that opens its own transaction
        with ``BEGIN IMMEDIATE``. Prefer ``_match_orders_in_txn`` when the
        caller already holds a transaction (e.g., ``handle_place_order``).

        B1 fix: Uses ``BEGIN IMMEDIATE`` to acquire the write lock before
        reading open orders, preventing concurrent double-matching.

        B3 fix: Connection is closed via try/finally.
        """
        if not order or "order_type" not in order:
            return

        conn = sqlite3.connect(get_db_path(), timeout=30)
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            self._match_orders_in_txn(cursor, order)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _check_exchange_db() -> None:
    """The exchange database answers a trivial query."""
    conn = sqlite3.connect(get_db_path())
    try:
        conn.execute("SELECT 1")
    finally:
        conn.close()


def _check_bridge_storage() -> None:
    """The bridge monitor's deposits store exists and has its schema.

    Created by the bridge-monitor service, not this one — a missing file or
    missing table means deposits cannot be served, so readiness fails.
    """
    from aitbc.constants import DATA_DIR

    path = Path(DATA_DIR) / "bridge_deposits.db"
    if not path.exists():
        raise RuntimeError("bridge deposits database not initialized")
    conn = sqlite3.connect(path)
    try:
        row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bridge_deposits'").fetchone()
        if row is None:
            raise RuntimeError("bridge deposits table missing")
    finally:
        conn.close()
