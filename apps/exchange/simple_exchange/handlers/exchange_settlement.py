"""Settlement-side exchange handlers — signed order cancel and the internal
settlement event intake (prepaid credit, order funded/backing expiry,
debit refund, trade state).

Split out of ``exchange.py`` verbatim; ``ExchangeMixin`` in the facade
inherits this mixin so every method stays reachable (and patchable) as
``ExchangeMixin.<name>``.
"""

import sqlite3
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from aitbc.aitbc_logging import get_logger
from aitbc.operations import BeginStatus, request_hash
from aitbc.utils.decimal import to_decimal as _to_decimal

from ..db import _SETTLEMENT_STATES, connect_db, to_ticks
from .base import _env_int, _idempotency_key, _rate_limit_hit, get_operation_ledger
from .exchange_helpers import (
    _CANCEL_ENVELOPE_FIELDS,
    _TRADE_STATE_FORWARD,
    _apply_exchange_fee,
    _cancel_settlement_effects,
    _close_buy_debit,
    _prepaid_spendable,
    _settlement_enabled,
    _signed_orders_required,
    get_db_path,
)

logger = get_logger(__name__)


class ExchangeSettlementMixin:
    """Signed cancel commit and typed internal settlement events."""

    def handle_cancel_order(self, order_id_str: str) -> None:
        """POST /api/orders/<id>/cancel — signed cancel (design section 6)."""
        if not _signed_orders_required():
            self.send_error(404, "Not Found")  # type: ignore[attr-defined]
            return
        # #1678: signed cancel costs a secp256k1 verify like placement — same
        # per-IP budget, checked before the body is even read.
        max_per_min = _env_int("EXCHANGE_MAX_ORDERS_PER_MIN", 20)
        if _rate_limit_hit(f"ip:{self._client_ip()}:cancel", max_per_min):
            self.send_json_response({"error": "Order cancel rate limit reached"}, status=429)  # type: ignore[attr-defined]
            return
        data = self._read_json_body()  # type: ignore[attr-defined]
        if not data:
            self.send_error(400, "Missing request body")  # type: ignore[attr-defined]
            return
        verified = self._verify_signed_body(data, _CANCEL_ENVELOPE_FIELDS)
        if verified is None:
            return
        envelope, address, _env_hash = verified
        if _rate_limit_hit(f"addr:{address}:cancel", max_per_min):
            self.send_json_response({"error": "Order cancel rate limit reached"}, status=429)  # type: ignore[attr-defined]
            return
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
        conn = connect_db(get_db_path(), timeout=30)
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
            _cancel_settlement_effects(cursor, order_id, result)
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

    def handle_internal_settlement(self) -> None:
        """POST /api/internal/exchange-settlement — typed settlement events."""
        if not _settlement_enabled():
            # 503, not 404: the wallet monitor maps a 404 to "order gone" and
            # refunds the lock — a flag-off exchange must read as retryable.
            self.send_json_response({"error": "exchange settlement disabled"}, status=503)  # type: ignore[attr-defined]
            return
        if not self._peer_is_loopback():
            self.send_error(403, "Forbidden")  # type: ignore[attr-defined]
            return
        headers = getattr(self, "headers", None)
        if headers is None or headers.get("X-Forwarded-For") or headers.get("X-Real-IP"):
            # A proxy hop always stamps one of these — refuse so a future
            # nginx rule can never expose this endpoint through loopback.
            self.send_error(403, "Forbidden")  # type: ignore[attr-defined]
            return
        if not self._require_api_key():  # type: ignore[attr-defined]
            return
        data = self._read_json_body()  # type: ignore[attr-defined]
        if not data:
            self.send_error(400, "Missing request body")  # type: ignore[attr-defined]
            return
        dispatch = {
            "prepaid_credit": self._event_prepaid_credit,
            "order_funded": self._event_order_funded,
            "order_backing_expired": self._event_order_backing_expired,
            "debit_refund": self._event_debit_refund,
            "trade_state": self._event_trade_state,
        }
        handler = dispatch.get(str(data.get("event")))
        if handler is None:
            self.send_error(400, "Unknown settlement event")  # type: ignore[attr-defined]
            return
        handler(data)

    def _internal_txn(self, work):
        """Open a BEGIN IMMEDIATE transaction around an event application.
        ``work(cursor)`` returns the response dict or (status, payload) on a
        refused event — refusals roll back like the request paths do."""
        conn = connect_db(get_db_path(), timeout=30)
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            outcome = work(cursor)
            if isinstance(outcome, tuple):
                conn.rollback()
                self.send_json_response(outcome[1], status=outcome[0])  # type: ignore[attr-defined]
                return
            conn.commit()
        except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, RuntimeError):
            conn.rollback()
            logger.exception("Internal settlement event failed")
            self.send_json_response({"error": "Settlement event failed"}, status=503)  # type: ignore[attr-defined]
            return
        finally:
            conn.close()
        self.send_json_response(outcome)  # type: ignore[attr-defined]

    def _event_prepaid_credit(self, data: dict) -> None:
        """Credit a node-tagged ETH deposit, then fund the node's still-open
        unfunded BUYs (id order) while the spendable covers them —
        re-matching each in the same transaction."""
        from aitbc.crypto.signature_recovery import canonical_address

        tx_hash = str(data.get("eth_tx_hash") or "")
        head = data.get("head")
        try:
            # The monitor derives this from tag text a user typed — any case.
            # Orders and the registry store the canonical EIP-55 form.
            node = canonical_address(str(data.get("node_address") or ""), strict=True)
        except ValueError:
            self.send_error(400, "prepaid_credit requires a 0x + 40-hex node_address")  # type: ignore[attr-defined]
            return
        try:
            amount = _to_decimal(data.get("amount_eth"))
        except (InvalidOperation, ValueError, TypeError):
            amount = Decimal(0)
        if not tx_hash or amount <= 0:
            self.send_error(400, "prepaid_credit requires node_address, amount_eth > 0, eth_tx_hash")  # type: ignore[attr-defined]
            return

        def work(cursor):
            status_row = cursor.execute("SELECT status FROM node_registry WHERE address = ?", (node,)).fetchone()
            if status_row is None or status_row[0] != "registered":
                # Unattributable deposit — the monitor records it for operator
                # handling; crediting it would strand ETH no order can draw on.
                return 409, {"error": "node_address is not a registered exchange node"}
            cursor.execute(
                "INSERT OR IGNORE INTO prepaid_deposits (node_address, amount_eth, eth_tx_hash) VALUES (?, ?, ?)",
                (node, str(amount), tx_hash),
            )
            credited = cursor.rowcount > 0
            funded: list[int] = []
            for oid, total in cursor.execute(
                "SELECT id, total FROM orders WHERE user_address = ? AND order_type = 'BUY' "
                "AND status = 'open' AND funded_state = 'unfunded' ORDER BY id",
                (node,),
            ).fetchall():
                cost = _to_decimal(total)
                if _prepaid_spendable(cursor, node) < cost:
                    continue
                cursor.execute(
                    "INSERT INTO prepaid_debits (node_address, order_id, amount_eth, state) VALUES (?, ?, ?, 'open')",
                    (node, oid, str(cost)),
                )
                cursor.execute(
                    "UPDATE orders SET funded_state = 'funded', funded_at = ? WHERE id = ?",
                    (datetime.now(UTC).isoformat(), oid),
                )
                row = cursor.execute("SELECT price, remaining, filled FROM orders WHERE id = ?", (oid,)).fetchone()
                order = {
                    "id": oid,
                    "order_type": "BUY",
                    "price": row[0],
                    "remaining": row[1],
                    "filled": row[2],
                    "status": "open",
                    "funded_state": "funded",
                    "user_address": node,
                }
                self._match_orders_in_txn(
                    cursor, order, head_height=head if isinstance(head, int) else None, guard_address=node
                )
                funded.append(oid)
            return {"ok": True, "credited": credited, "funded_orders": funded}

        self._internal_txn(work)

    def _event_order_funded(self, data: dict) -> None:
        """A SELL's escrow lock landed: flip it to 'funded' when the recorded
        lock covers remaining + fee, then re-run matching inside the same
        transaction."""
        order_id = data.get("order_id")
        locked = data.get("locked_ticks")
        backing = str(data.get("backing_tx_hash") or "")
        head = data.get("head")
        if (
            not isinstance(order_id, int)
            or isinstance(order_id, bool)
            or not isinstance(locked, int)
            or isinstance(locked, bool)
        ):
            self.send_error(400, "order_funded requires integer order_id and locked_ticks")  # type: ignore[attr-defined]
            return

        def work(cursor):
            row = cursor.execute(
                "SELECT order_type, status, funded_state, price, remaining, filled, user_address FROM orders WHERE id = ?",
                (order_id,),
            ).fetchone()
            if row is None:
                return 404, {"error": "Order not found"}
            if row[1] != "open" or row[2] != "unfunded":
                return {"ok": True, "order_id": order_id, "funded_state": row[2], "unchanged": True}
            if row[0] != "SELL":
                return 400, {"error": "order_funded applies to SELL orders (escrow lock)"}
            remaining = _to_decimal(row[4])
            required = to_ticks(remaining + _apply_exchange_fee(remaining)[0])
            if locked < required:
                return 409, {"error": f"Lock below required cover ({locked} < {required} ticks)"}
            cursor.execute(
                "UPDATE orders SET funded_state = 'funded', locked_ticks = ?, backing_tx_hash = ?, funded_at = ? WHERE id = ?",
                (locked, backing, datetime.now(UTC).isoformat(), order_id),
            )
            order = {
                "id": order_id,
                "order_type": "SELL",
                "price": row[3],
                "remaining": row[4],
                "filled": row[5],
                "status": "open",
                "funded_state": "funded",
                "user_address": row[6],
            }
            self._match_orders_in_txn(cursor, order, head_height=head if isinstance(head, int) else None, guard_address=row[6])
            return {"ok": True, "order_id": order_id, "funded_state": "funded", "order": order}

        self._internal_txn(work)

    def _event_order_backing_expired(self, data: dict) -> None:
        """The monitor can no longer prove an order's backing — mark it and
        release any open prepaid debit (same txn)."""
        order_id = data.get("order_id")
        if not isinstance(order_id, int) or isinstance(order_id, bool):
            self.send_error(400, "order_backing_expired requires integer order_id")  # type: ignore[attr-defined]
            return

        def work(cursor):
            row = cursor.execute("SELECT funded_state FROM orders WHERE id = ?", (order_id,)).fetchone()
            if row is None:
                return 404, {"error": "Order not found"}
            cursor.execute("UPDATE orders SET funded_state = 'backing_expired' WHERE id = ?", (order_id,))
            _close_buy_debit(cursor, order_id)
            return {"ok": True, "order_id": order_id, "funded_state": "backing_expired", "was": row[0]}

        self._internal_txn(work)

    def _event_debit_refund(self, data: dict) -> None:
        """Close a buy order's open debit — the uncommitted residual returns
        to spendable. Idempotent: a closed debit is a no-op."""
        order_id = data.get("order_id")
        if not isinstance(order_id, int) or isinstance(order_id, bool):
            self.send_error(400, "debit_refund requires integer order_id")  # type: ignore[attr-defined]
            return

        def work(cursor):
            deb = cursor.execute(
                "SELECT amount_eth, COALESCE(committed_eth, '0'), state FROM prepaid_debits WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            if deb is None:
                return 404, {"error": "No prepaid debit for order"}
            refunded = str(_to_decimal(deb[0]) - _to_decimal(deb[1])) if deb[2] == "open" else None
            _close_buy_debit(cursor, order_id)
            return {"ok": True, "order_id": order_id, "refunded_eth": refunded, "was": deb[2]}

        self._internal_txn(work)

    def _event_trade_state(self, data: dict) -> None:
        """Mirror the wallet ledger's settlement state onto the tape row —
        forward-only; a 'refunded' trade releases its committed ETH back to
        the buyer's prepaid balance (a 'settled' trade deliberately does NOT:
        committed is cumulative, the ETH is gone)."""
        trade_id = data.get("trade_id")
        state = str(data.get("state") or "")
        if not isinstance(trade_id, int) or isinstance(trade_id, bool) or state not in _SETTLEMENT_STATES:
            self.send_error(400, "trade_state requires integer trade_id and a valid state")  # type: ignore[attr-defined]
            return

        def work(cursor):
            row = cursor.execute(
                "SELECT settlement_state, buy_order_id, total FROM trades WHERE id = ?", (trade_id,)
            ).fetchone()
            if row is None:
                return 404, {"error": "Trade not found"}
            current = row[0]
            if current is None:
                return 409, {"error": "Trade is not in the settlement machine"}
            if current == state:
                return {"ok": True, "trade_id": trade_id, "settlement_state": state, "unchanged": True}
            if state not in _TRADE_STATE_FORWARD.get(current, frozenset()):
                return 409, {"error": f"settlement_state cannot move {current} -> {state}"}
            cursor.execute(
                "UPDATE trades SET settlement_state = ?, "
                "settlement_eth_tx_hash = COALESCE(?, settlement_eth_tx_hash), "
                "settlement_ait_tx_hash = COALESCE(?, settlement_ait_tx_hash), "
                "settlement_fee_tx_hash = COALESCE(?, settlement_fee_tx_hash) WHERE id = ?",
                (state, data.get("eth_tx_hash"), data.get("ait_tx_hash"), data.get("fee_tx_hash"), trade_id),
            )
            released = None
            if state == "refunded" and row[1] is not None:
                deb = cursor.execute(
                    "SELECT COALESCE(committed_eth, '0') FROM prepaid_debits WHERE order_id = ?", (row[1],)
                ).fetchone()
                if deb is not None:
                    new_committed = _to_decimal(deb[0]) - _to_decimal(row[2])
                    if new_committed < 0:
                        logger.warning("trade %s refund underflowed committed_eth — clamped", trade_id)
                        new_committed = Decimal(0)
                    released = str(_to_decimal(deb[0]) - new_committed)
                    cursor.execute(
                        "UPDATE prepaid_debits SET committed_eth = ? WHERE order_id = ?", (str(new_committed), row[1])
                    )
            return {"ok": True, "trade_id": trade_id, "settlement_state": state, "released_eth": released}

        self._internal_txn(work)
