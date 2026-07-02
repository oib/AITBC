"""Trading, metrics, treasury, and health handlers."""

import json
import sqlite3
import urllib.parse
from datetime import UTC, datetime

from ..db import get_db_path
from .base import RPC_BASE_URL, RPC_TIMEOUT


class ExchangeMixin:
    """Trading, metrics, treasury, health, and wallet-balance methods."""

    def get_recent_trades(self, parsed):
        """Get recent trades"""
        query = urllib.parse.parse_qs(parsed.query)
        limit = int(query.get("limit", [20])[0])

        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, amount, price, total, created_at
            FROM trades
            ORDER BY created_at DESC
            LIMIT ?
        """,
            (limit,),
        )

        trades = []
        for row in cursor.fetchall():
            trades.append({"id": row[0], "amount": row[1], "price": row[2], "total": row[3], "created_at": row[4]})

        conn.close()

        self.send_json_response(trades)

    def get_orderbook(self):
        """Get order book"""
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get sell orders
        cursor.execute("""
            SELECT id, order_type, amount, price, total, filled, remaining, status, created_at
            FROM orders
            WHERE order_type = 'SELL' AND status = 'open'
            ORDER BY price ASC
            LIMIT 20
        """)

        sells = []
        for row in cursor.fetchall():
            sells.append(
                {
                    "id": row[0],
                    "order_type": row[1],
                    "amount": row[2],
                    "price": row[3],
                    "total": row[4],
                    "filled": row[5],
                    "remaining": row[6],
                    "status": row[7],
                    "created_at": row[8],
                }
            )

        # Get buy orders
        cursor.execute("""
            SELECT id, order_type, amount, price, total, filled, remaining, status, created_at
            FROM orders
            WHERE order_type = 'BUY' AND status = 'open'
            ORDER BY price DESC
            LIMIT 20
        """)

        buys = []
        for row in cursor.fetchall():
            buys.append(
                {
                    "id": row[0],
                    "order_type": row[1],
                    "amount": row[2],
                    "price": row[3],
                    "total": row[4],
                    "filled": row[5],
                    "remaining": row[6],
                    "status": row[7],
                    "created_at": row[8],
                }
            )

        conn.close()

        self.send_json_response({"buys": buys, "sells": sells})

    def handle_place_order(self):
        """Place a new order on the blockchain"""
        if not self._require_api_key():
            return
        data = self._read_json_body()
        if not data:
            self.send_error(400, "Missing request body")
            return

        try:
            order_type = data.get("order_type")
            amount = data.get("amount")
            price = data.get("price")
            user_address = data.get("user_address")

            if not all([order_type, amount, price, user_address]):
                self.send_error(400, "Missing required fields")
                return

            if order_type not in ["BUY", "SELL"]:
                self.send_error(400, "Invalid order type")
                return

            # Create order transaction on blockchain
            try:
                import urllib.parse
                import urllib.request

                # Prepare transaction data
                tx_data = {
                    "from": user_address,
                    "type": "ORDER",
                    "order_type": order_type,
                    "amount": str(amount),
                    "price": str(price),
                    "nonce": 0,  # Would get actual nonce from wallet
                }

                # Send transaction to blockchain
                tx_url = f"{RPC_BASE_URL}/rpc/sendTx"
                encoded_data = urllib.parse.urlencode(tx_data).encode("utf-8")

                req = urllib.request.Request(
                    tx_url, data=encoded_data, headers={"Content-Type": "application/x-www-form-urlencoded"}
                )

                with urllib.request.urlopen(req, timeout=RPC_TIMEOUT) as response:
                    tx_result = json.loads(response.read().decode())

                # Store order in local database for orderbook
                total = amount * price

                db_path = get_db_path()
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO orders (order_type, amount, price, total, remaining, user_address, tx_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (order_type, amount, price, total, amount, user_address, tx_result.get("tx_hash", "")),
                )

                order_id = cursor.lastrowid
                conn.commit()

                # Get the created order
                cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
                row = cursor.fetchone()

                order = {
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
                }

                conn.close()

                # Try to match orders
                self.match_orders(order)

                self.send_json_response(order)

            except Exception:
                # Fallback to database-only if blockchain is down
                total = amount * price

                db_path = get_db_path()
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO orders (order_type, amount, price, total, remaining, user_address)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (order_type, amount, price, total, amount, user_address),
                )

                order_id = cursor.lastrowid
                conn.commit()

                # Get the created order
                cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
                row = cursor.fetchone()

                order = {
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
                }

                conn.close()

                # Try to match orders
                self.match_orders(order)

                self.send_json_response(order)

        except Exception as e:
            # Blockchain is down — return an honest error, not fake supply numbers
            self.send_json_response(
                {
                    "error": f"Blockchain RPC unavailable: {e}",
                    "source": "error",
                },
                status=503,
            )

    def handle_treasury_balance(self):
        """Get exchange treasury balance from blockchain"""
        if not self._require_api_key():
            return
        try:
            import json
            import urllib.request

            # Treasury address from genesis
            treasury_address = "aitbcexchange00000000000000000000000000000000"
            blockchain_url = f"{RPC_BASE_URL}/rpc/getBalance/{treasury_address}"

            try:
                with urllib.request.urlopen(blockchain_url, timeout=RPC_TIMEOUT) as response:
                    balance_data = json.loads(response.read().decode())
                    treasury_balance = balance_data.get("balance", 0)

                self.send_json_response(
                    {
                        "address": treasury_address,
                        "balance": str(treasury_balance),
                        "available_for_sale": str(treasury_balance),  # All treasury tokens available
                        "source": "blockchain",
                    }
                )
            except Exception:
                # If blockchain query fails, show the genesis amount
                self.send_json_response(
                    {
                        "address": treasury_address,
                        "balance": "10000000000000",  # 10 million in smallest units
                        "available_for_sale": "10000000000000",
                        "source": "genesis",
                        "note": "Genesis amount - blockchain may need restart",
                    }
                )

        except Exception:
            self.send_error(500, "Internal server error")

    def health_check(self):
        """Health check"""
        self.send_json_response({"status": "ok", "timestamp": datetime.now(UTC).isoformat()})

    def handle_metrics(self):
        """Prometheus metrics endpoint"""
        try:
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

            output = generate_latest()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(output)
        except Exception:
            self.send_error(500, "Internal server error")

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

            self.send_json_response(
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
        except Exception as e:
            self.send_json_response({"success": False, "error": str(e)}, status=500)

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
                self.send_json_response(
                    {
                        "price_usd": ait_usd.price if ait_usd else None,
                        "price_eur": ait_eur.price if ait_eur else None,
                        "price_eth": ait_eth.price if ait_eth else None,
                        "eth_eur": eth_eur.price if eth_eur else None,
                        "currency": "USD",
                        "timestamp": (ait_usd or ait_eur).timestamp,
                        "source": (ait_usd or ait_eur).source,
                    }
                )
            else:
                self.send_json_response({"error": "Price unavailable"}, status=503)
        except Exception as e:
            self.send_json_response({"error": str(e)}, status=500)

    def handle_wallet_balance(self):
        """Handle wallet balance request"""
        if not self._require_api_key():
            return
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        address = params.get("address", [""])[0]

        if not address:
            self.send_json_response({"btc": "0.00000000", "aitbc": "0.00", "address": "unknown"})
            return

        try:
            # Query real blockchain for balance
            import json
            import urllib.request

            # Get AITBC balance from blockchain
            blockchain_url = f"{RPC_BASE_URL}/rpc/getBalance/{address}"
            with urllib.request.urlopen(blockchain_url, timeout=RPC_TIMEOUT) as response:
                balance_data = json.loads(response.read().decode())

            # For BTC, we'll query a Bitcoin API (simplified for now)
            # In production, you'd integrate with a real Bitcoin node API
            btc_balance = "0.00000000"  # Placeholder - would query real Bitcoin network

            self.send_json_response(
                {
                    "btc": btc_balance,
                    "aitbc": str(balance_data.get("balance", 0)),
                    "address": address,
                    "nonce": balance_data.get("nonce", 0),
                }
            )
        except Exception:
            # Fallback to error if blockchain is down
            self.send_json_response(
                {"btc": "0.00000000", "aitbc": "0.00", "address": address, "error": "Failed to fetch balance from blockchain"}
            )

    def handle_wallet_connect(self):
        """Handle wallet connection request.

        Requires the client to provide their wallet address in the request
        body. No mock address is generated.
        """
        if not self._require_api_key():
            return

        body = self._read_json_body()
        if body is None:
            return

        address = body.get("address")
        if not address:
            self.send_json_response({"error": "Wallet address is required in request body"}, status=400)
            return

        # Verify the wallet exists via the wallet service
        import os

        wallet_url = os.getenv("WALLET_SERVICE_URL", "http://localhost:8108")
        try:
            import httpx

            with httpx.Client(timeout=10) as client:
                resp = client.get(f"{wallet_url}/v1/wallets", params={"address": address})
                if resp.status_code == 200:
                    wallets = resp.json().get("wallets", [])
                    if wallets:
                        self.send_json_response(
                            {
                                "address": address,
                                "status": "connected",
                                "wallet_id": wallets[0].get("wallet_id", ""),
                            }
                        )
                    else:
                        self.send_json_response({"error": "Wallet not found", "address": address}, status=404)
                else:
                    self.send_json_response({"error": f"Wallet service error: {resp.status_code}"}, status=502)
        except Exception as e:
            self.send_json_response({"error": f"Wallet service unavailable: {e}"}, status=503)

    def match_orders(self, order):
        """Match a new order against existing open orders in the database.

        Implements a simple price-time priority matching engine:
        - A BUY order matches SELL orders with price <= buy price
        - A SELL order matches BUY orders with price >= sell price
        Matched trades are recorded in the trades table.
        """
        import sqlite3

        from .db import get_db_path

        if not order or "order_type" not in order:
            return

        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        new_type = order["order_type"]
        new_price = order["price"]
        new_remaining = order["remaining"]
        new_id = order.get("id")

        # Find matching orders (opposite side, price-compatible)
        if new_type == "BUY":
            # Match against SELL orders with price <= our buy price
            cursor.execute(
                """
                SELECT id, order_type, amount, price, total, filled, remaining, status, created_at, user_address, tx_hash
                FROM orders
                WHERE order_type = 'SELL' AND status = 'open' AND price <= ?
                ORDER BY price ASC, created_at ASC
                """,
                (new_price,),
            )
        else:
            # Match against BUY orders with price >= our sell price
            cursor.execute(
                """
                SELECT id, order_type, amount, price, total, filled, remaining, status, created_at, user_address, tx_hash
                FROM orders
                WHERE order_type = 'BUY' AND status = 'open' AND price >= ?
                ORDER BY price DESC, created_at ASC
                """,
                (new_price,),
            )

        matching_orders = cursor.fetchall()

        for match_row in matching_orders:
            if new_remaining <= 0:
                break

            match_id = match_row[0]
            match_remaining = match_row[6]
            match_price = match_row[3]

            if match_remaining <= 0:
                continue

            # Calculate trade quantity
            trade_qty = min(new_remaining, match_remaining)
            trade_total = trade_qty * match_price

            # Record the trade
            cursor.execute(
                """
                INSERT INTO trades (amount, price, total, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (trade_qty, match_price, trade_total, datetime.now(UTC).isoformat()),
            )

            # Update the matching order
            new_match_filled = match_row[5] + trade_qty
            new_match_remaining = match_remaining - trade_qty
            new_match_status = "filled" if new_match_remaining <= 0 else "open"

            cursor.execute(
                """
                UPDATE orders SET filled = ?, remaining = ?, status = ?
                WHERE id = ?
                """,
                (new_match_filled, new_match_remaining, new_match_status, match_id),
            )

            # Update the new order
            new_remaining -= trade_qty
            order["filled"] = order.get("filled", 0) + trade_qty
            order["remaining"] = new_remaining

            if new_remaining <= 0:
                order["status"] = "filled"

        # Update the new order in the database
        if new_id:
            cursor.execute(
                """
                UPDATE orders SET filled = ?, remaining = ?, status = ?
                WHERE id = ?
                """,
                (order.get("filled", 0), order.get("remaining", 0), order.get("status", "open"), new_id),
            )

        conn.commit()
        conn.close()
