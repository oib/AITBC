"""Market offer/order CRUD handlers.

B2 backport: Prices use Decimal (stored as TEXT) for exact arithmetic.
B3 backport: Database connections are closed via try/finally.
"""

import os
import secrets
import urllib.parse
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from aitbc.aitbc_logging import get_logger
from aitbc.operations import BeginStatus, request_hash
from aitbc.utils.decimal import to_decimal as _to_decimal

from ..db import connect_db, get_db_path
from .base import _env_int, _idempotency_key, get_operation_ledger, mutating_rate_limit_reached

logger = get_logger(__name__)

# #1675: marketplace prices are money. to_decimal() only guarantees *finite* —
# 0, negatives and absurd magnitudes (1e30) used to be stored verbatim as TEXT
# and later fed order math. Require strictly positive and cap at 1e15, the
# same ceiling trading's subscription price filter uses.
_MARKET_MAX_PRICE = Decimal("1000000000000000")


def _market_price_or_raise(value) -> Decimal:
    """Validate a caller-supplied marketplace price; ValueError -> HTTP 400."""
    try:
        price = _to_decimal(value)
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise ValueError("price must be a finite decimal") from exc
    if price <= 0:
        raise ValueError("price must be positive")
    if price > _MARKET_MAX_PRICE:
        raise ValueError(f"price must not exceed {_MARKET_MAX_PRICE}")
    return price


def _create_offer_price(data: dict) -> str:
    """Resolve the create-offer price field; ValueError -> HTTP 400 (#1675)."""
    price_raw = data.get("price")
    if price_raw is None:
        price_raw = data.get("price_per_hour")
    if price_raw is None:
        raise ValueError("price is required")
    return str(_market_price_or_raise(price_raw))


def _book_offer_price(data: dict, offer_price) -> str:
    """Buyer-supplied book price, bounded like offer prices (#1675).

    Absent/falsy falls back to the (already validated) offer price — the
    legacy ``or`` semantics; a truthy value must pass the same bounds.
    """
    price_raw = data.get("price")
    if price_raw:
        return str(_market_price_or_raise(price_raw))
    return str(offer_price)


# -- idempotency-ledger helpers (module-level so MagicMock-bound mixin tests
#    still exercise the real code; keeps the handlers under the C901 ratchet) --


def _op_begin(conn, idempotency_key, operation, payload):
    """Begin the ledger row inside the open transaction.

    Returns ``(begin, attempt)`` — ``begin`` is None when no
    Idempotency-Key was sent; ``attempt`` is only meaningful on an
    EXECUTE begin. On a non-EXECUTE outcome the caller must rollback
    and answer via ``_send_operation_result``.
    """
    if not idempotency_key:
        return None, 0
    begin = get_operation_ledger().begin(idempotency_key, operation, request_hash(payload), conn=conn)
    if begin.status is not BeginStatus.EXECUTE:
        return begin, 0
    return begin, begin.attempt


def _op_complete(idempotency_key, operation_attempt, result, *, response_status, conn) -> bool:
    """Complete the ledger row; True when there was nothing to complete."""
    if not idempotency_key:
        return True
    return get_operation_ledger().complete(
        idempotency_key, operation_attempt, result, response_status=response_status, conn=conn
    )


def _op_fail(idempotency_key, operation_attempt, message) -> None:
    """Fail the ledger row after a rolled-back transaction."""
    if idempotency_key and operation_attempt:
        get_operation_ledger().fail(idempotency_key, operation_attempt, message)


class MarketMixin:
    """Market offer and order management methods."""

    def _new_market_id(self, prefix):
        return f"{prefix}_{int(datetime.now(UTC).timestamp() * 1000)}{secrets.randbelow(900) + 100}"

    _MARKETPLACE_DEFAULT_TTL_SECONDS = 7 * 24 * 3600

    def _marketplace_ttl_seconds(self) -> int:
        """#1563: marketplace rows get a finite lifetime (MARKETPLACE_TTL_SECONDS,
        default 7d). Lazy expiry flips stale rows to 'expired' on access — there
        is no background sweeper in this service."""
        try:
            return max(60, int(os.environ.get("MARKETPLACE_TTL_SECONDS", str(self._MARKETPLACE_DEFAULT_TTL_SECONDS))))
        except (TypeError, ValueError):
            return self._MARKETPLACE_DEFAULT_TTL_SECONDS

    def _marketplace_expires_at(self) -> str:
        # Same 'YYYY-MM-DD HH:MM:SS' UTC shape SQLite's CURRENT_TIMESTAMP uses,
        # so lexicographic comparison against datetime('now') stays correct.
        return (datetime.now(UTC) + timedelta(seconds=self._marketplace_ttl_seconds())).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _expire_stale_market_rows(cursor) -> None:
        """#1563 lazy expiry: offers past expires_at become 'expired'; open orders
        past expires_at — or SELL orders whose offer already expired — follow.
        Call before reading or mutating marketplace rows; the caller commits."""
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """
            UPDATE marketplace_offers SET status = 'expired'
            WHERE status = 'active' AND expires_at IS NOT NULL AND expires_at < ?
            """,
            (now,),
        )
        cursor.execute(
            """
            UPDATE marketplace_orders SET status = 'expired'
            WHERE status = 'open' AND (
                (expires_at IS NOT NULL AND expires_at < ?)
                OR (order_type = 'SELL' AND offer_id IN (
                    SELECT id FROM marketplace_offers WHERE status = 'expired'
                ))
            )
            """,
            (now,),
        )

    def _market_offer_row(self, row):
        return {
            "id": row[0],
            "address": row[0],
            "item": row[1],
            "item_type": row[2],
            "model": row[2],
            "price": row[3],
            "price_per_hour": row[3],
            "wallet": row[4],
            "status": row[5],
            "description": row[6],
            "created_at": row[7],
            "deployed_at": row[7],
            "expires_at": row[8],
        }

    def _market_order_row(self, row):
        return {
            "id": row[0],
            "order_type": row[1],
            "item": row[2],
            "price": row[3],
            "wallet": row[4],
            "status": row[5],
            "created_at": row[6],
            "expires_at": row[7],
        }

    def handle_market_offers(self, parsed):
        query = urllib.parse.parse_qs(parsed.query)
        status_filter = query.get("status", [None])[0]
        try:
            limit = max(1, min(int(query.get("limit", ["200"])[0]), 1000))
        except (TypeError, ValueError):
            limit = 200
        conn = connect_db(get_db_path())
        try:
            cursor = conn.cursor()
            self._expire_stale_market_rows(cursor)
            conn.commit()
            if status_filter:
                cursor.execute(
                    """
                    SELECT id, item, item_type, price, wallet, status, description, created_at, expires_at
                    FROM marketplace_offers
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """,
                    (status_filter, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, item, item_type, price, wallet, status, description, created_at, expires_at
                    FROM marketplace_offers
                    ORDER BY created_at DESC
                    LIMIT ?
                """,
                    (limit,),
                )
            offers = [self._market_offer_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()
        self.send_json_response(offers)  # type: ignore[attr-defined]

    def handle_market_offer(self, path):
        offer_id = urllib.parse.unquote(path.rsplit("/", 1)[-1])
        conn = connect_db(get_db_path())
        try:
            cursor = conn.cursor()
            self._expire_stale_market_rows(cursor)
            conn.commit()
            cursor.execute(
                """
                SELECT id, item, item_type, price, wallet, status, description, created_at, expires_at
                FROM marketplace_offers
                WHERE id = ?
            """,
                (offer_id,),
            )
            row = cursor.fetchone()
        finally:
            conn.close()
        if row:
            self.send_json_response(self._market_offer_row(row))  # type: ignore[attr-defined]
        else:
            self.send_error(404, "Offer not found")  # type: ignore[attr-defined]

    def handle_market_create_offer(self):
        # #1678: marketplace mutations had no rate limiting — bound per IP.
        if mutating_rate_limit_reached(self, "market", _env_int("EXCHANGE_MUTATING_PER_MIN", 60)):
            return
        if not self._require_api_key():  # type: ignore[attr-defined]
            return
        try:
            data = self._read_json_body()  # type: ignore[attr-defined]
            item = data.get("item") or data.get("item_type") or "service"
            item_type = data.get("item_type") or item
            # B2: Use Decimal for price (stored as TEXT). #1675: price is
            # required and must be finite, > 0 and <= _MARKET_MAX_PRICE.
            price = _create_offer_price(data)
            wallet = data.get("wallet")
            description = data.get("description", "")
            idempotency_key = _idempotency_key(self)
            conn = connect_db(get_db_path())
            operation_attempt = 0
            try:
                # BEGIN IMMEDIATE: the ledger row and the offer/order rows commit
                # atomically — a crash before commit leaves no pending record.
                conn.execute("BEGIN IMMEDIATE")
                cursor = conn.cursor()
                self._expire_stale_market_rows(cursor)
                begin, operation_attempt = _op_begin(conn, idempotency_key, "market_create_offer", data)
                if begin is not None and begin.status is not BeginStatus.EXECUTE:
                    conn.rollback()
                    self._send_operation_result(begin)  # type: ignore[attr-defined]
                    return
                offer_id = self._new_market_id("offer")
                order_id = self._new_market_id("order")
                cursor.execute(
                    """
                    INSERT INTO marketplace_offers (id, item, item_type, price, wallet, status, description, expires_at)
                    VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                    (offer_id, item, item_type, price, wallet, description, self._marketplace_expires_at()),
                )
                cursor.execute(
                    """
                    INSERT INTO marketplace_orders (id, order_type, item, price, wallet, status, offer_id, expires_at)
                    VALUES (?, 'SELL', ?, ?, ?, 'open', ?, ?)
                """,
                    (order_id, item, price, wallet, offer_id, self._marketplace_expires_at()),
                )
                cursor.execute(
                    """
                    SELECT id, item, item_type, price, wallet, status, description, created_at, expires_at
                    FROM marketplace_offers
                    WHERE id = ?
                """,
                    (offer_id,),
                )
                offer = self._market_offer_row(cursor.fetchone())
                offer["order_id"] = order_id
                if not _op_complete(idempotency_key, operation_attempt, offer, response_status=201, conn=conn):
                    raise RuntimeError("operation lease superseded mid-transaction")
                conn.commit()
            except Exception:
                conn.rollback()
                _op_fail(idempotency_key, operation_attempt, "offer creation failed")
                raise
            finally:
                conn.close()
            self.send_json_response(offer, status=201)  # type: ignore[attr-defined]
        except Exception:
            logger.exception("Market offer creation failed")
            self.send_json_response({"success": False, "error": "Offer creation failed"}, status=400)  # type: ignore[attr-defined]

    def handle_market_book_offer(self, path):
        # #1678: marketplace mutations had no rate limiting — bound per IP.
        if mutating_rate_limit_reached(self, "market", _env_int("EXCHANGE_MUTATING_PER_MIN", 60)):
            return
        if not self._require_api_key():  # type: ignore[attr-defined]
            return
        try:
            offer_id = urllib.parse.unquote(path[len("/v1/market/offers/") : -len("/book")])
            data = self._read_json_body()  # type: ignore[attr-defined]
            wallet = data.get("wallet")
            idempotency_key = _idempotency_key(self)
            conn = connect_db(get_db_path())
            operation_attempt = 0
            try:
                conn.execute("BEGIN IMMEDIATE")
                cursor = conn.cursor()
                begin, operation_attempt = _op_begin(
                    conn, idempotency_key, "market_book_offer", {"offer_id": offer_id, "body": data}
                )
                if begin is not None and begin.status is not BeginStatus.EXECUTE:
                    conn.rollback()
                    self._send_operation_result(begin)  # type: ignore[attr-defined]
                    return
                self._expire_stale_market_rows(cursor)
                # Only an active offer may be booked (#1563): the old query
                # had no status filter and fell back to item=offer_id, so a
                # cancelled or nonexistent offer still produced a BUY order.
                cursor.execute(
                    """
                    SELECT id, item, price
                    FROM marketplace_offers
                    WHERE (id = ? OR item = ?) AND status = 'active'
                """,
                    (offer_id, offer_id),
                )
                row = cursor.fetchone()
                if row is None:
                    conn.rollback()
                    _op_fail(idempotency_key, operation_attempt, "offer not found or not active")
                    self.send_json_response({"success": False, "error": "Offer not found or not active"}, status=404)  # type: ignore[attr-defined]
                    return
                matched_offer_id, item, offer_price = row
                # B2: Use Decimal for price (stored as TEXT). #1675: an
                # explicit buyer price gets the same bounds as offer prices.
                price = _book_offer_price(data, offer_price)
                order_id = self._new_market_id("order")
                cursor.execute(
                    """
                    INSERT INTO marketplace_orders (id, order_type, item, price, wallet, status, offer_id, expires_at)
                    VALUES (?, 'BUY', ?, ?, ?, 'open', ?, ?)
                """,
                    (order_id, item, price, wallet, matched_offer_id, self._marketplace_expires_at()),
                )
                cursor.execute(
                    """
                    SELECT id, order_type, item, price, wallet, status, created_at, expires_at
                    FROM marketplace_orders
                    WHERE id = ?
                """,
                    (order_id,),
                )
                order = self._market_order_row(cursor.fetchone())
                response = {"success": True, "order": order, "order_id": order_id}
                if not _op_complete(idempotency_key, operation_attempt, response, response_status=201, conn=conn):
                    raise RuntimeError("operation lease superseded mid-transaction")
                conn.commit()
            except Exception:
                conn.rollback()
                _op_fail(idempotency_key, operation_attempt, "offer booking failed")
                raise
            finally:
                conn.close()
            self.send_json_response(response, status=201)  # type: ignore[attr-defined]
        except Exception:
            logger.exception("Market offer booking failed")
            self.send_json_response({"success": False, "error": "Booking failed"}, status=400)  # type: ignore[attr-defined]

    def handle_market_orders(self, parsed):
        query = urllib.parse.parse_qs(parsed.query)
        wallet = query.get("wallet", [None])[0]
        # Bounded public read — was an unbounded full-table scan (#1408).
        try:
            limit = max(1, min(int(query.get("limit", ["200"])[0]), 1000))
        except (TypeError, ValueError):
            limit = 200
        conn = connect_db(get_db_path())
        try:
            cursor = conn.cursor()
            self._expire_stale_market_rows(cursor)
            conn.commit()
            if wallet:
                cursor.execute(
                    """
                    SELECT id, order_type, item, price, wallet, status, created_at, expires_at
                    FROM marketplace_orders
                    WHERE wallet = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """,
                    (wallet, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, order_type, item, price, wallet, status, created_at, expires_at
                    FROM marketplace_orders
                    ORDER BY created_at DESC
                    LIMIT ?
                """,
                    (limit,),
                )
            orders = [self._market_order_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()
        self.send_json_response({"orders": orders})  # type: ignore[attr-defined]

    def handle_market_delete_order(self, parsed):
        # #1678: marketplace mutations had no rate limiting — bound per IP.
        if mutating_rate_limit_reached(self, "market", _env_int("EXCHANGE_MUTATING_PER_MIN", 60)):
            return
        if not self._require_api_key():  # type: ignore[attr-defined]
            return
        order_id = urllib.parse.unquote(parsed.path.rsplit("/", 1)[-1])
        query = urllib.parse.parse_qs(parsed.query)
        wallet = query.get("wallet", [None])[0]
        if not wallet:
            self.send_json_response({"success": False, "error": "wallet query parameter is required"}, status=400)  # type: ignore[attr-defined]
            return
        conn = connect_db(get_db_path())
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM marketplace_orders WHERE id = ? AND wallet = ?", (order_id, wallet))
            if not cursor.fetchone():
                self.send_json_response({"success": False, "error": "Order not found for this wallet"}, status=404)  # type: ignore[attr-defined]
                return
            cursor.execute(
                "UPDATE marketplace_orders SET status = 'cancelled' WHERE id = ? AND wallet = ?", (order_id, wallet)
            )
            conn.commit()
            deleted = cursor.rowcount
        finally:
            conn.close()
        self.send_json_response({"success": True, "order_id": order_id, "deleted": deleted})  # type: ignore[attr-defined]

    def handle_market_delete_offer(self, parsed):
        # #1678: marketplace mutations had no rate limiting — bound per IP.
        if mutating_rate_limit_reached(self, "market", _env_int("EXCHANGE_MUTATING_PER_MIN", 60)):
            return
        if not self._require_api_key():  # type: ignore[attr-defined]
            return
        offer_id = urllib.parse.unquote(parsed.path.rsplit("/", 1)[-1])
        query = urllib.parse.parse_qs(parsed.query)
        wallet = query.get("wallet", [None])[0]
        if not wallet:
            self.send_json_response({"success": False, "error": "wallet query parameter is required"}, status=400)  # type: ignore[attr-defined]
            return
        conn = connect_db(get_db_path())
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, item FROM marketplace_offers WHERE id = ? AND wallet = ?", (offer_id, wallet))
            offer_row = cursor.fetchone()
            if not offer_row:
                self.send_json_response({"success": False, "error": "Offer not found for this wallet"}, status=404)  # type: ignore[attr-defined]
                return
            cursor.execute(
                "UPDATE marketplace_offers SET status = 'cancelled' WHERE id = ? AND wallet = ?", (offer_id, wallet)
            )
            deleted = cursor.rowcount
            # Cascade (#1563): the SELL order auto-created with the offer must
            # not stay 'open' after its offer is cancelled. offer_id is the
            # durable link; rows predating the column fall back to the
            # item+wallet pair the order was created with.
            cursor.execute(
                """
                UPDATE marketplace_orders SET status = 'cancelled'
                WHERE status = 'open' AND order_type = 'SELL'
                  AND (offer_id = ? OR (offer_id IS NULL AND item = ? AND wallet IS ?))
                """,
                (offer_id, offer_row[1], wallet),
            )
            conn.commit()
        finally:
            conn.close()
        self.send_json_response({"success": True, "offer_id": offer_id, "deleted": deleted})  # type: ignore[attr-defined]
