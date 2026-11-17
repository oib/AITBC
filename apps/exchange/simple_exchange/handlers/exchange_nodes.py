"""Node-registry exchange handlers — signed node register/payout claims,
the participants board, and the settlement watchlist.

Split out of ``exchange.py`` verbatim; ``ExchangeMixin`` in the facade
inherits this mixin so every method stays reachable (and patchable) as
``ExchangeMixin.<name>``.
"""

import sqlite3
from datetime import UTC, datetime
from decimal import Decimal

from aitbc.aitbc_logging import get_logger

from ..db import connect_db
from .base import (
    _RATE_BUCKETS,  # noqa: F401 - tests clear rate buckets via __globals__
    _RATE_LOCK,  # noqa: F401 - tests clear rate buckets via __globals__
    _env_int,
    _rate_limit_hit,
)
from .exchange_helpers import (
    _MAX_REGISTRY_ROWS,
    _PAYOUT_ACTION,
    _PAYOUT_ENVELOPE_FIELDS,
    _REGISTER_ACTION,
    _REGISTER_ENVELOPE_FIELDS,
    _WATCHLIST_LOGGED,
    _env_decimal,
    _is_int64,
    _payout_address_blocked,
    _settlement_enabled,
    _short_addr,
    _signed_orders_required,
    get_db_path,
)

logger = get_logger(__name__)


class ExchangeNodesMixin:
    """Node registration, payout claims, participants board, watchlist."""

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
        if not _is_int64(envelope["account_nonce"]):
            self.send_error(400, "Invalid account_nonce")  # type: ignore[attr-defined]
            return
        self._commit_register(envelope, address, env_hash)

    def _commit_register(self, envelope, address, env_hash) -> None:
        conn = connect_db(get_db_path(), timeout=30)
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

    def handle_set_payout(self) -> None:
        """POST /api/exchange/nodes/payout — signed exchange_set_payout claim.

        ETH-8 phase 3 (dark): only exists under EXCHANGE_SETTLEMENT_ENABLED;
        flag-off answers 404 exactly like an unregistered route. The claimed
        address must be EIP-55 checksum form — a typo'd or lowercase address
        can never be accepted into the payout path.
        """
        if not _settlement_enabled():
            self.send_error(404, "Not Found")  # type: ignore[attr-defined]
            return
        if _rate_limit_hit(f"ip:{self._client_ip()}:payout", _env_int("EXCHANGE_REGISTER_PER_MIN", 5)):
            self.send_json_response({"error": "Rate limit reached"}, status=429)  # type: ignore[attr-defined]
            return
        data = self._read_json_body()  # type: ignore[attr-defined]
        if not data:
            self.send_error(400, "Missing request body")  # type: ignore[attr-defined]
            return
        verified = self._verify_signed_body(data, _PAYOUT_ENVELOPE_FIELDS)
        if verified is None:
            return
        envelope, address, env_hash = verified
        if envelope["action"] != _PAYOUT_ACTION:
            self.send_error(400, "Invalid set_payout action")  # type: ignore[attr-defined]
            return
        from eth_utils import is_checksum_address

        eth_address = envelope["eth_address"]
        if not isinstance(eth_address, str) or not is_checksum_address(eth_address):
            self.send_error(400, "Invalid eth_address (EIP-55 checksum form required)")  # type: ignore[attr-defined]
            return
        if _payout_address_blocked(eth_address):
            self.send_error(400, "Invalid eth_address (reserved address)")  # type: ignore[attr-defined]
            return
        if not _is_int64(envelope["account_nonce"]):
            self.send_error(400, "Invalid account_nonce")  # type: ignore[attr-defined]
            return
        self._commit_payout(envelope, address, env_hash, eth_address)

    def _commit_payout(self, envelope, address, env_hash, eth_address) -> None:
        conn = connect_db(get_db_path(), timeout=30)
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            row = cursor.execute("SELECT status, eth_address FROM node_registry WHERE address = ?", (address,)).fetchone()
            if row is None or row[0] != "registered":
                conn.rollback()
                self.send_json_response({"error": "Node not registered"}, status=403)  # type: ignore[attr-defined]
                return
            old_eth = row[1]
            if envelope["account_nonce"] != self._expected_nonce(cursor, address) or not self._claim_nonce(
                cursor, address, envelope["account_nonce"]
            ):
                conn.rollback()
                self.send_json_response({"error": "Stale account_nonce"}, status=409)  # type: ignore[attr-defined]
                return
            now = datetime.now(UTC).isoformat()
            cursor.execute(
                "UPDATE node_registry SET eth_address = ?, eth_address_set_at = ? WHERE address = ?",
                (eth_address, now, address),
            )
            cursor.execute(
                "INSERT INTO payout_address_audit (address, old_eth_address, new_eth_address, envelope_hash, changed_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (address, old_eth, eth_address, env_hash, now),
            )
            result = {
                "address": address,
                "status": "payout_set",
                "eth_address": eth_address,
                "previous_eth_address": old_eth,
                "applies_to": "orders placed after this claim",
                "next_nonce": envelope["account_nonce"] + 1,
            }
            conn.commit()
        except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, RuntimeError):
            conn.rollback()
            logger.exception("Payout address claim failed")
            self.send_json_response({"error": "Payout address claim failed"}, status=503)  # type: ignore[attr-defined]
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
        conn = connect_db(get_db_path())
        try:
            nodes = self._node_rows(conn)
        finally:
            conn.close()
        self.send_json_response({"nodes": nodes})  # type: ignore[attr-defined]

    def _node_rows(self, conn) -> list[dict]:
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT address, label, status, registered_at, eth_address FROM node_registry ORDER BY label LIMIT ?",
            (_MAX_REGISTRY_ROWS,),
        ).fetchall()
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
                # ETH-8 phase 3 (dark): the node's signed payout address —
                # deliberately public on the participants board.
                "eth_address": _short_addr(eth_address),
            }
            for address, label, status, registered_at, eth_address in rows
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

    # ── ETH-8 phase 3 (dark): internal settlement endpoint ───────────────
    # The wallet bridge's settlement monitor is the ONLY non-exchange writer
    # of exchange.db — and it writes through this endpoint, never SQL. Raw
    # peer must be loopback (the service binds 0.0.0.0 and nginx does not
    # proxy this path, so a leaked network path still fails closed), plus
    # the existing EXCHANGE_API_KEY. Flag unset → 404 like any unknown
    # route. Every event applies inside its own BEGIN IMMEDIATE and is
    # idempotent: re-posting a known fact is a no-op, never an error.

    def _raw_peer_ip(self) -> str:
        """The socket peer — never proxy headers. This endpoint trusts only
        the wire address."""
        peer = getattr(self, "client_address", None)
        if isinstance(peer, (tuple, list)) and peer:
            return str(peer[0])
        return ""

    def _peer_is_loopback(self) -> bool:
        import ipaddress

        try:
            addr = ipaddress.ip_address(self._raw_peer_ip())
        except ValueError:
            return False
        if isinstance(addr, ipaddress.IPv6Address):
            mapped = addr.ipv4_mapped
            if mapped is not None:
                addr = mapped
        return addr.is_loopback
