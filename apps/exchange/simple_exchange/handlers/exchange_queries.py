"""Read-side exchange handlers — order book, trades, my-orders, treasury,
history/price, and wallet balance/connect.

Split out of ``exchange.py`` verbatim; ``ExchangeMixin`` in the facade
inherits this mixin so every method stays reachable (and patchable) as
``ExchangeMixin.<name>``.
"""

import http.client
import urllib.parse
from decimal import Decimal, InvalidOperation
from pathlib import Path

from aitbc.aitbc_logging import get_logger
from aitbc.utils.decimal import to_decimal as _to_decimal
from aitbc_errors import AITBCError

# File-relative repo root — see handlers/bridge.py for why (no /opt/aitbc hardcode).
_REPO_ROOT = str(Path(__file__).resolve().parents[4])

from ..db import connect_db
from .base import RPC_BASE_URL, RPC_TIMEOUT, _env_int, _rate_limit_hit, mutating_rate_limit_reached
from .exchange_helpers import (
    _MAX_PAGE_ROWS,
    _MAX_REGISTRY_ROWS,
    _settlement_enabled,
    _short_addr,
    _signed_orders_required,
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


class ExchangeQueriesMixin:
    """Order-book/trade reads, account reads, treasury, history, wallet."""

    def _registry_labels(self, cursor) -> dict[str, str]:
        """address -> label for registered/seeded nodes (display on the board)."""
        rows = cursor.execute(
            "SELECT address, label FROM node_registry WHERE status IN ('seeded', 'registered') LIMIT ?",
            (_MAX_REGISTRY_ROWS,),
        ).fetchall()
        return dict(rows)

    def get_recent_trades(self, parsed):
        """Get recent trades"""
        query = urllib.parse.parse_qs(parsed.query)
        try:
            limit = int(query.get("limit", [20])[0])
        except (TypeError, ValueError):
            limit = 20
        # Clamp: limit=-1 is SQLite "unlimited" and any huge value was an
        # unbounded read on a public endpoint (#1543).
        limit = max(1, min(limit, _MAX_PAGE_ROWS))

        conn = connect_db(get_db_path())
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
        conn = connect_db(get_db_path())
        try:
            cursor = conn.cursor()
            labels = self._registry_labels(cursor)
            band = self._ait_eth_band()

            # Phase 3 (dark): under settlement the book shows only matchable
            # orders — an unfunded row must not inflate visible depth.
            funded_pred = "AND funded_state = 'funded'" if _settlement_enabled() else ""

            # Sell orders — integer ticks sort; TEXT '10' would sort below '2'.
            # funded_pred is a fixed literal fragment, never input
            cursor.execute(f"""
                SELECT id, order_type, amount, price, total, filled, remaining, status, created_at,
                       user_address, expiry_height, funded_state
                FROM orders
                WHERE order_type = 'SELL' AND status = 'open' {funded_pred}
                ORDER BY price_ticks ASC, id ASC
                LIMIT 20
            """)  # nosec
            sells = [self._orderbook_row(row, labels, band) for row in cursor.fetchall()]

            # Buy orders — integer ticks, then id for deterministic FIFO ties.
            # same fixed fragment
            cursor.execute(f"""
                SELECT id, order_type, amount, price, total, filled, remaining, status, created_at,
                       user_address, expiry_height, funded_state
                FROM orders
                WHERE order_type = 'BUY' AND status = 'open' {funded_pred}
                ORDER BY price_ticks DESC, id ASC
                LIMIT 20
            """)  # nosec
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
        conn = connect_db(get_db_path())
        try:
            cursor = conn.cursor()
            registry = cursor.execute("SELECT label, status FROM node_registry WHERE address = ?", (address,)).fetchone()
            # total rides along unexposed — the BUY funding block needs it.
            settlement = _settlement_enabled()
            orders = []
            for row in cursor.execute(
                "SELECT id, order_type, amount, price, filled, remaining, status, created_at,"
                " expiry_height, funded_state, total FROM orders WHERE user_address = ?"
                " ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, id DESC LIMIT 100",
                (address,),
            ).fetchall():
                order = {
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
                # CLI-1: under settlement an open unfunded row carries its
                # funding instruction so 'order fund' can re-read it; flag-off
                # responses stay byte-identical (no 'funding' key at all).
                if settlement and order["status"] == "open" and order["funded_state"] == "unfunded":
                    order["funding"] = self._funding_block(cursor, {**order, "total": row[10]}, address)
                orders.append(order)
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
                # RPC_BASE_URL is validated (module-level startswith http(s):// check in base.py) before this call
                with urllib.request.urlopen(blockchain_url, timeout=RPC_TIMEOUT) as response:  # nosec B310
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
            except _OPS_ERRORS:
                # No fabricated fallback: a treasury figure must come from the chain or not
                # be served at all.
                self.send_json_response(  # type: ignore[attr-defined]
                    {"error": "Treasury balance unavailable — blockchain RPC unreachable"}, status=503
                )

        except _OPS_ERRORS:
            self.send_error(500, "Internal server error")  # type: ignore[attr-defined]

    def handle_exchange_history(self, parsed):
        """GET /v1/exchange/history — return current ETH and AIT prices for USD and EUR"""
        try:
            import sys

            sys.path.insert(0, _REPO_ROOT)
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

            sys.path.insert(0, _REPO_ROOT)
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
            # RPC_BASE_URL is validated (module-level startswith http(s):// check in base.py) before this call
            with urllib.request.urlopen(blockchain_url, timeout=RPC_TIMEOUT) as response:  # nosec B310
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
        except _OPS_ERRORS:
            # Fail loudly if the blockchain is unreachable — no fabricated fallback.
            self.send_json_response(  # type: ignore[attr-defined]
                {"error": "Failed to fetch balance from blockchain", "address": address}, status=503
            )

    def handle_wallet_connect(self):
        """Handle wallet connection request.

        Requires the client to provide their wallet address in the request
        body. No mock address is generated.
        """
        # #1678: outbound wallet-service lookup per call — bound it.
        if mutating_rate_limit_reached(self, "wallet-connect", _env_int("EXCHANGE_MUTATING_PER_MIN", 60)):
            return
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
