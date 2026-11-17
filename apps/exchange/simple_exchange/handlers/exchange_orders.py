"""Order placement handlers — unsigned and signed order pipeline.

Split out of ``exchange.py`` verbatim; ``ExchangeMixin`` in the facade
inherits this mixin so every method stays reachable (and patchable) as
``ExchangeMixin.<name>``.
"""

import os
import sqlite3
import time
import http.client
import urllib.error
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from aitbc.aitbc_logging import get_logger
from aitbc.operations import BeginStatus, request_hash
from aitbc.utils.decimal import to_decimal as _to_decimal
from aitbc_errors import AITBCError

from ..db import connect_db, ticks_to_decimal, to_ticks
from .base import _env_int, _idempotency_key, _rate_limit_hit, get_operation_ledger
from .exchange_helpers import (
    BAND_CACHE_TTL_S,
    EXCHANGE_ORDER_PAIR,
    _CANCEL_ACTION,
    _ORDER_ENVELOPE_FIELDS,
    _SIDE_DESTINATION_ENV,
    _apply_exchange_fee,
    _band_cache,
    _close_buy_debit,
    _envelope_hash,
    _env_decimal,
    _exchange_chain_id,
    _funding_destination,
    _is_int64,
    _prepaid_spendable,
    _row_to_order,
    _settlement_enabled,
    _signed_orders_required,
    _verify_envelope_signature,
    get_db_path,
)

logger = get_logger(__name__)

# Expected failure surface for the handler-level fallbacks below: lazy
# imports (ImportError), RPC/filesystem I/O (OSError covers urllib errors,
# socket and timeout failures), request/JSON decode and Decimal conversion
# (ValueError/InvalidOperation), and data-shape errors. RuntimeError covers
# abort-style raises a handler re-aborts with; genuine BaseExceptions still
# propagate (#1862).
_OPS_ERRORS = (
    ImportError,
    OSError,
    ValueError,
    InvalidOperation,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    http.client.HTTPException,
    AITBCError,
)


class ExchangeOrdersMixin:
    """Order placement: payload validation, unsigned + signed commit paths."""

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
        except _OPS_ERRORS:
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

            unsigned_expiry = self._unsigned_order_expiry_height()

            # B1: Insert order and match within a single transaction.
            # BEGIN IMMEDIATE acquires the write lock before we read open orders,
            # preventing concurrent requests from double-matching the same counterparty.
            conn = connect_db(get_db_path(), timeout=30)
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
                                        amount_ticks, price_ticks, filled_ticks, remaining_ticks, expiry_height)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        unsigned_expiry,
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

    def _unsigned_order_expiry_height(self) -> int | None:
        """expiry_height for an unsigned-path order (#1554).

        head + EXCHANGE_UNSIGNED_ORDER_TTL_BLOCKS when the chain head is
        reachable; None when the RPC is down — the flag-off path tolerates
        a dead RPC by design and the NULL residual is documented on #1554.
        """
        head = self._chain_head_height()
        if not isinstance(head, int):
            logger.warning(
                "Unsigned order placed without expiry_height — chain head unavailable; "
                "order will not auto-expire (#1554 flag-off residual)"
            )
            return None
        return head + _env_int("EXCHANGE_UNSIGNED_ORDER_TTL_BLOCKS", 100_000)

    def _chain_head_height(self) -> int | None:
        """Current chain height for expiry checks; None when the node RPC is down."""
        try:
            head = self._rpc_get("/rpc/head")  # type: ignore[attr-defined]
            height = head.get("height")
            return height if isinstance(height, int) else None
        except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError, http.client.HTTPException):
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
            if not _is_int64(envelope[field]):
                return f"Invalid {field}"
        if envelope["amount_ticks"] <= 0 or envelope["price_ticks"] <= 0:
            return "Amount and price must be positive"
        return None

    def _cancel_envelope_error(self, envelope: dict) -> str | None:
        """Field-level checks on a verified cancel envelope; None = clean."""
        if envelope["action"] != _CANCEL_ACTION:
            return "Invalid cancel action"
        for field in ("order_id", "account_nonce", "expiry_height"):
            if not _is_int64(envelope[field]):
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
        # ETH-8 phase 3 (dark): under settlement the side's funding
        # destination must be a configured EIP-55 address — unset/malformed
        # would emit an instruction telling the node to send value nowhere.
        # Both refusals run before the nonce claim: a refused order never
        # burns the account nonce.
        if _settlement_enabled():
            dest_env = _SIDE_DESTINATION_ENV.get(envelope["side"])
            if dest_env is not None and _funding_destination(dest_env) is None:
                return 503, {"error": f"Exchange settlement misconfigured: {dest_env} is unset or not an EIP-55 address"}
            if envelope["side"] == "SELL":
                eth_row = cursor.execute("SELECT eth_address FROM node_registry WHERE address = ?", (address,)).fetchone()
                if eth_row is None or not eth_row[0]:
                    return 409, {"error": "SELL requires a registered payout address (exchange_set_payout)"}
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
        conn = connect_db(get_db_path(), timeout=30)
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
            if _settlement_enabled():
                self._fund_order_in_txn(cursor, order, envelope, address)
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

    @staticmethod
    def _funding_block(cursor, order: dict, address: str) -> dict:
        """The funding instruction for an unfunded order — the read-side twin
        of the blocks ``_fund_order_in_txn`` attaches at placement (used by
        my-orders so a node can re-read its instruction later). Read-only: no
        payout snapshot, no prepaid debit. ``required_ait`` covers
        remaining + fee, the bound ``order_funded`` enforces at lock time.
        """
        if order["order_type"] == "SELL":
            remaining = _to_decimal(order["remaining"])
            required = remaining + _apply_exchange_fee(remaining)[0]
            return {
                "type": "ait_lock",
                "state": "unfunded",
                "escrow": os.getenv("AIT_SELL_ESCROW", ""),
                "payload": f"sell_quote={order['id']}",
                "required_ait": str(required),
            }
        cost = _to_decimal(order["total"])
        spendable = _prepaid_spendable(cursor, address)
        # needed_eth is a display hint: deposits since placement may cover the
        # shortfall — clamp at 0 rather than claim a negative top-up.
        return {
            "type": "eth_prepay",
            "state": "unfunded",
            "needed_eth": str(max(Decimal("0"), cost - spendable)),
            "tag": f"EXCHANGE_DEPOSIT:{address}",
            "bridge_eth_address": os.getenv("BRIDGE_ETH_ADDRESS", ""),
        }

    def _fund_order_in_txn(self, cursor, order: dict, envelope: dict, address: str) -> None:
        """ETH-8 phase 3 (dark): attach backing to a fresh signed order
        inside the placement transaction. Only runs under
        EXCHANGE_SETTLEMENT_ENABLED; flag-off callers never reach here.

        - SELL: snapshots the registry payout address onto the order and
          stays 'unfunded' — the node still has to send its escrow lock
          (payload sell_quote=<order_id>, covering amount + fee). The
          response carries the lock instruction.
        - BUY: debits prepaid ETH for the full notional now when the
          spendable balance covers it ('funded'); otherwise 'unfunded'
          with the prepay instruction (EXCHANGE_DEPOSIT tag).
        """
        if order["order_type"] == "SELL":
            eth_row = cursor.execute("SELECT eth_address FROM node_registry WHERE address = ?", (address,)).fetchone()
            seller_eth = eth_row[0] if eth_row else None
            cursor.execute("UPDATE orders SET seller_eth_address = ? WHERE id = ?", (seller_eth, order["id"]))
            order["funding"] = self._funding_block(cursor, order, address)
            return
        # BUY: cost is the full notional (remaining fills draw from the same
        # debit as trades commit).
        cost = _to_decimal(order["total"])
        spendable = _prepaid_spendable(cursor, address)
        if spendable >= cost:
            cursor.execute(
                "INSERT INTO prepaid_debits (node_address, order_id, amount_eth, state) VALUES (?, ?, ?, 'open')",
                (address, order["id"], str(cost)),
            )
            cursor.execute(
                "UPDATE orders SET funded_state = 'funded', funded_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(), order["id"]),
            )
            order["funded_state"] = "funded"
            order["funding"] = {"type": "eth_prepaid", "state": "funded", "debited_eth": str(cost)}
        else:
            order["funding"] = self._funding_block(cursor, order, address)

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
        if not _settlement_enabled():
            return
        # The order's backing window ended with it — funded or not. Any
        # still-open prepaid debit releases its uncommitted part inside the
        # same write transaction; committed ETH stays earmarked for the
        # trades that already matched.
        cursor.execute(
            "UPDATE orders SET funded_state = 'backing_expired' WHERE status = 'expired' AND funded_state != 'backing_expired'"
        )
        for (oid,) in cursor.execute(
            "SELECT o.id FROM orders o JOIN prepaid_debits d ON d.order_id = o.id "
            "WHERE o.status = 'expired' AND o.order_type = 'BUY' AND d.state = 'open'"
        ).fetchall():
            _close_buy_debit(cursor, oid)
