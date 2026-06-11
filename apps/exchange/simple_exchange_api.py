#!/usr/bin/env python3
"""
Simple FastAPI backend for the AITBC Trade Exchange (Python 3.13 compatible)
"""

import argparse
import json
import random
import sqlite3
import urllib.parse
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

from aitbc import get_logger
from aitbc.constants import DATA_DIR

logger = get_logger(__name__)

# Database setup
def get_db_path():
    """Get database path and ensure directory exists"""
    import os
    db_path = os.getenv("EXCHANGE_DATABASE_URL", f"sqlite:///{DATA_DIR}/data/exchange/exchange.db").replace("sqlite://///", "")

    # Create directory if it doesn't exist
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    return db_path

def init_db():
    """Initialize SQLite database"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            price REAL NOT NULL,
            total REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_type TEXT NOT NULL CHECK(order_type IN ('BUY', 'SELL')),
            amount REAL NOT NULL,
            price REAL NOT NULL,
            total REAL NOT NULL,
            filled REAL DEFAULT 0,
            remaining REAL NOT NULL,
            status TEXT DEFAULT 'open' CHECK(status IN ('open', 'filled', 'cancelled')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_address TEXT,
            tx_hash TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS marketplace_offers (
            id TEXT PRIMARY KEY,
            item TEXT NOT NULL,
            item_type TEXT NOT NULL,
            price REAL NOT NULL,
            wallet TEXT,
            status TEXT DEFAULT 'active',
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS marketplace_orders (
            id TEXT PRIMARY KEY,
            order_type TEXT NOT NULL,
            item TEXT NOT NULL,
            price REAL NOT NULL,
            wallet TEXT,
            status TEXT DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add columns if they don't exist (for existing databases)
    try:
        cursor.execute('ALTER TABLE orders ADD COLUMN user_address TEXT')
    except Exception:
        pass

    try:
        cursor.execute('ALTER TABLE orders ADD COLUMN tx_hash TEXT')
    except Exception:
        pass

    conn.commit()
    conn.close()

def create_mock_trades():
    """Create some mock trades"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if we have trades
    cursor.execute('SELECT COUNT(*) FROM trades')
    if cursor.fetchone()[0] > 0:
        conn.close()
        return

    # Create mock trades
    now = datetime.now(UTC)
    for i in range(20):
        amount = random.uniform(10, 500)
        price = random.uniform(0.000009, 0.000012)
        total = amount * price
        created_at = now - timedelta(minutes=random.randint(0, 60))

        cursor.execute('''
            INSERT INTO trades (amount, price, total, created_at)
            VALUES (?, ?, ?, ?)
        ''', (amount, price, total, created_at))

    conn.commit()
    conn.close()

class ExchangeAPIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests"""
        # Validate path to prevent SSRF
        if not self.path or self.path.startswith(('//', '\\\\', '..')):
            self.send_error(400, "Invalid path")
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == '/health' or path == '/api/health':
            self.health_check()
        elif path.startswith('/api/trades/recent'):
            self.get_recent_trades(parsed)
        elif path.startswith('/api/orders/orderbook'):
            self.get_orderbook()
        elif path.startswith('/api/wallet/balance'):
            self.handle_wallet_balance()
        elif path == '/api/total-supply':
            self.handle_total_supply()
        elif path == '/api/treasury-balance':
            self.handle_treasury_balance()
        elif path == '/v1/marketplace/offers':
            self.handle_marketplace_offers(parsed)
        elif path.startswith('/v1/marketplace/offers/'):
            self.handle_marketplace_offer(path)
        elif path == '/v1/marketplace/orders':
            self.handle_marketplace_orders(parsed)
        elif path == '/metrics':
            self.handle_metrics()
        elif path == '/v1/bridge/price':
            self.handle_bridge_price(parsed)
        elif path == '/v1/bridge/status':
            self.handle_bridge_status(None)
        elif path.startswith('/v1/bridge/status/'):
            self.handle_bridge_status(path.split('/')[-1])
        elif path == '/v1/bridge/deposits':
            self.handle_bridge_deposits(parsed)
        elif path.startswith('/v1/bridge/deposit/'):
            self.handle_bridge_deposit_detail(path.split('/')[-1])
        elif path == '/v1/exchange/history':
            self.handle_exchange_history(parsed)
        elif path == '/exchange/price.json':
            self.handle_exchange_price_json()
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        """Handle POST requests"""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == '/api/orders':
            self.handle_place_order()
        elif path == '/api/wallet/connect':
            self.handle_wallet_connect()
        elif path == '/v1/marketplace/offers':
            self.handle_marketplace_create_offer()
        elif path.startswith('/v1/marketplace/offers/') and path.endswith('/book'):
            self.handle_marketplace_book_offer(path)
        elif path == '/v1/bridge/deposit':
            self.handle_bridge_deposit()
        elif path == '/v1/bridge/withdraw':
            self.handle_bridge_withdraw()
        elif path == '/v1/bridge/estimate':
            self.handle_bridge_estimate()
        else:
            self.send_error(404, "Not Found")

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith('/v1/marketplace/orders/'):
            self.handle_marketplace_delete_order(path)
        elif path.startswith('/v1/marketplace/offers/'):
            self.handle_marketplace_delete_offer(path)
        else:
            self.send_error(404, "Not Found")

    def _read_json_body(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length <= 0:
            return {}
        post_data = self.rfile.read(content_length)
        if not post_data:
            return {}
        return json.loads(post_data.decode('utf-8'))

    def _new_marketplace_id(self, prefix):
        return f"{prefix}_{int(datetime.now(UTC).timestamp() * 1000)}{random.randint(100, 999)}"

    def _marketplace_offer_row(self, row):
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
        }

    def _marketplace_order_row(self, row):
        return {
            "id": row[0],
            "order_type": row[1],
            "item": row[2],
            "price": row[3],
            "wallet": row[4],
            "status": row[5],
            "created_at": row[6],
        }

    def handle_marketplace_offers(self, parsed):
        query = urllib.parse.parse_qs(parsed.query)
        status_filter = query.get('status', [None])[0]
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        if status_filter:
            cursor.execute('''
                SELECT id, item, item_type, price, wallet, status, description, created_at
                FROM marketplace_offers
                WHERE status = ?
                ORDER BY created_at DESC
            ''', (status_filter,))
        else:
            cursor.execute('''
                SELECT id, item, item_type, price, wallet, status, description, created_at
                FROM marketplace_offers
                ORDER BY created_at DESC
            ''')
        offers = [self._marketplace_offer_row(row) for row in cursor.fetchall()]
        conn.close()
        self.send_json_response(offers)

    def handle_marketplace_offer(self, path):
        offer_id = urllib.parse.unquote(path.rsplit('/', 1)[-1])
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, item, item_type, price, wallet, status, description, created_at
            FROM marketplace_offers
            WHERE id = ?
        ''', (offer_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            self.send_json_response(self._marketplace_offer_row(row))
        else:
            self.send_error(404, "Offer not found")

    def handle_marketplace_create_offer(self):
        try:
            data = self._read_json_body()
            item = data.get('item') or data.get('item_type') or 'service'
            item_type = data.get('item_type') or item
            price = float(data.get('price') or data.get('price_per_hour') or 0)
            wallet = data.get('wallet')
            description = data.get('description', '')
            offer_id = self._new_marketplace_id('offer')
            order_id = self._new_marketplace_id('order')
            db_path = get_db_path()
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO marketplace_offers (id, item, item_type, price, wallet, status, description)
                VALUES (?, ?, ?, ?, ?, 'active', ?)
            ''', (offer_id, item, item_type, price, wallet, description))
            cursor.execute('''
                INSERT INTO marketplace_orders (id, order_type, item, price, wallet, status)
                VALUES (?, 'SELL', ?, ?, ?, 'open')
            ''', (order_id, item, price, wallet))
            conn.commit()
            cursor.execute('''
                SELECT id, item, item_type, price, wallet, status, description, created_at
                FROM marketplace_offers
                WHERE id = ?
            ''', (offer_id,))
            offer = self._marketplace_offer_row(cursor.fetchone())
            conn.close()
            offer["order_id"] = order_id
            self.send_json_response(offer, status=201)
        except Exception as e:
            self.send_json_response({"success": False, "error": str(e)}, status=400)

    def handle_marketplace_book_offer(self, path):
        try:
            offer_id = urllib.parse.unquote(path[len('/v1/marketplace/offers/'): -len('/book')])
            data = self._read_json_body()
            wallet = data.get('wallet')
            db_path = get_db_path()
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT item, price
                FROM marketplace_offers
                WHERE id = ? OR item = ?
            ''', (offer_id, offer_id))
            row = cursor.fetchone()
            item = row[0] if row else offer_id
            price = float(data.get('price') or (row[1] if row else 0) or 0)
            order_id = self._new_marketplace_id('order')
            cursor.execute('''
                INSERT INTO marketplace_orders (id, order_type, item, price, wallet, status)
                VALUES (?, 'BUY', ?, ?, ?, 'open')
            ''', (order_id, item, price, wallet))
            conn.commit()
            cursor.execute('''
                SELECT id, order_type, item, price, wallet, status, created_at
                FROM marketplace_orders
                WHERE id = ?
            ''', (order_id,))
            order = self._marketplace_order_row(cursor.fetchone())
            conn.close()
            self.send_json_response({"success": True, "order": order, "order_id": order_id}, status=201)
        except Exception as e:
            self.send_json_response({"success": False, "error": str(e)}, status=400)

    def handle_marketplace_orders(self, parsed):
        query = urllib.parse.parse_qs(parsed.query)
        wallet = query.get('wallet', [None])[0]
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        if wallet:
            cursor.execute('''
                SELECT id, order_type, item, price, wallet, status, created_at
                FROM marketplace_orders
                WHERE wallet = ?
                ORDER BY created_at DESC
            ''', (wallet,))
        else:
            cursor.execute('''
                SELECT id, order_type, item, price, wallet, status, created_at
                FROM marketplace_orders
                ORDER BY created_at DESC
            ''')
        orders = [self._marketplace_order_row(row) for row in cursor.fetchall()]
        conn.close()
        self.send_json_response({"orders": orders})

    def handle_marketplace_delete_order(self, path):
        order_id = urllib.parse.unquote(path.rsplit('/', 1)[-1])
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE marketplace_orders SET status = 'cancelled' WHERE id = ?", (order_id,))
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        self.send_json_response({"success": True, "order_id": order_id, "deleted": deleted})

    def handle_marketplace_delete_offer(self, path):
        offer_id = urllib.parse.unquote(path.rsplit('/', 1)[-1])
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE marketplace_offers SET status = 'cancelled' WHERE id = ?", (offer_id,))
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        self.send_json_response({"success": True, "offer_id": offer_id, "deleted": deleted})

    def get_recent_trades(self, parsed):
        """Get recent trades"""
        query = urllib.parse.parse_qs(parsed.query)
        limit = int(query.get('limit', [20])[0])

        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, amount, price, total, created_at
            FROM trades
            ORDER BY created_at DESC
            LIMIT ?
        ''', (limit,))

        trades = []
        for row in cursor.fetchall():
            trades.append({
                'id': row[0],
                'amount': row[1],
                'price': row[2],
                'total': row[3],
                'created_at': row[4]
            })

        conn.close()

        self.send_json_response(trades)

    def get_orderbook(self):
        """Get order book"""
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get sell orders
        cursor.execute('''
            SELECT id, order_type, amount, price, total, filled, remaining, status, created_at
            FROM orders
            WHERE order_type = 'SELL' AND status = 'open'
            ORDER BY price ASC
            LIMIT 20
        ''')

        sells = []
        for row in cursor.fetchall():
            sells.append({
                'id': row[0],
                'order_type': row[1],
                'amount': row[2],
                'price': row[3],
                'total': row[4],
                'filled': row[5],
                'remaining': row[6],
                'status': row[7],
                'created_at': row[8]
            })

        # Get buy orders
        cursor.execute('''
            SELECT id, order_type, amount, price, total, filled, remaining, status, created_at
            FROM orders
            WHERE order_type = 'BUY' AND status = 'open'
            ORDER BY price DESC
            LIMIT 20
        ''')

        buys = []
        for row in cursor.fetchall():
            buys.append({
                'id': row[0],
                'order_type': row[1],
                'amount': row[2],
                'price': row[3],
                'total': row[4],
                'filled': row[5],
                'remaining': row[6],
                'status': row[7],
                'created_at': row[8]
            })

        conn.close()

        self.send_json_response({'buys': buys, 'sells': sells})

    def handle_place_order(self):
        """Place a new order on the blockchain"""
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        try:
            data = json.loads(post_data.decode('utf-8'))
            order_type = data.get('order_type')
            amount = data.get('amount')
            price = data.get('price')
            user_address = data.get('user_address')

            if not all([order_type, amount, price, user_address]):
                self.send_error(400, "Missing required fields")
                return

            if order_type not in ['BUY', 'SELL']:
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
                    "nonce": 0  # Would get actual nonce from wallet
                }

                # Send transaction to blockchain
                tx_url = "http://localhost:9080/rpc/sendTx"
                encoded_data = urllib.parse.urlencode(tx_data).encode('utf-8')

                req = urllib.request.Request(
                    tx_url,
                    data=encoded_data,
                    headers={'Content-Type': 'application/x-www-form-urlencoded'}
                )

                with urllib.request.urlopen(req) as response:
                    tx_result = json.loads(response.read().decode())

                # Store order in local database for orderbook
                total = amount * price

                db_path = get_db_path()
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                cursor.execute('''
                    INSERT INTO orders (order_type, amount, price, total, remaining, user_address, tx_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (order_type, amount, price, total, amount, user_address, tx_result.get('tx_hash', '')))

                order_id = cursor.lastrowid
                conn.commit()

                # Get the created order
                cursor.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
                row = cursor.fetchone()

                order = {
                    'id': row[0],
                    'order_type': row[1],
                    'amount': row[2],
                    'price': row[3],
                    'total': row[4],
                    'filled': row[5],
                    'remaining': row[6],
                    'status': row[7],
                    'created_at': row[8],
                    'user_address': row[9],
                    'tx_hash': row[10]
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

                cursor.execute('''
                    INSERT INTO orders (order_type, amount, price, total, remaining, user_address)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (order_type, amount, price, total, amount, user_address))

                order_id = cursor.lastrowid
                conn.commit()

                # Get the created order
                cursor.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
                row = cursor.fetchone()

                order = {
                    'id': row[0],
                    'order_type': row[1],
                    'amount': row[2],
                    'price': row[3],
                    'total': row[4],
                    'filled': row[5],
                    'remaining': row[6],
                    'status': row[7],
                    'created_at': row[8],
                    'user_address': row[9] if len(row) > 9 else None
                }

                conn.close()

                # Try to match orders
                self.match_orders(order)

                self.send_json_response(order)

        except Exception as e:
            # Fallback to hardcoded values if blockchain is down
            self.send_json_response({
                "total_supply": "21000000",
                "circulating_supply": "1000000",
                "treasury_balance": "0",
                "source": "fallback",
                "error": str(e)
            })

    def handle_treasury_balance(self):
        """Get exchange treasury balance from blockchain"""
        try:
            import json
            import urllib.request

            # Treasury address from genesis
            treasury_address = "aitbcexchange00000000000000000000000000000000"
            blockchain_url = f"http://localhost:9080/rpc/getBalance/{treasury_address}"

            try:
                with urllib.request.urlopen(blockchain_url) as response:
                    balance_data = json.loads(response.read().decode())
                    treasury_balance = balance_data.get('balance', 0)

                self.send_json_response({
                    "address": treasury_address,
                    "balance": str(treasury_balance),
                    "available_for_sale": str(treasury_balance),  # All treasury tokens available
                    "source": "blockchain"
                })
            except Exception:
                # If blockchain query fails, show the genesis amount
                self.send_json_response({
                    "address": treasury_address,
                    "balance": "10000000000000",  # 10 million in smallest units
                    "available_for_sale": "10000000000000",
                    "source": "genesis",
                    "note": "Genesis amount - blockchain may need restart"
                })

        except Exception as e:
            self.send_error(500, str(e))

    def health_check(self):
        """Health check"""
        self.send_json_response({
            'status': 'ok',
            'timestamp': datetime.now(UTC).isoformat()
        })

    def handle_metrics(self):
        """Prometheus metrics endpoint"""
        try:
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
            output = generate_latest()
            self.send_response(200)
            self.send_header('Content-Type', CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(output)
        except Exception as e:
            self.send_error(500, str(e))

    def handle_exchange_history(self, parsed):
        """GET /v1/exchange/history — return current ETH prices for USD and EUR"""
        try:
            import sys
            sys.path.insert(0, '/opt/aitbc')
            from aitbc.oracles.price_oracle import get_price_oracle
            
            oracle = get_price_oracle()
            eth_usd = oracle.get_price('ETH', 'USD')
            eth_eur = oracle.get_price('ETH', 'EUR')
            ait_usd = oracle.get_price('AIT', 'USD')
            
            # Calculate AIT/EUR from ETH prices
            ait_eur_price = None
            if eth_usd and eth_eur and ait_usd:
                ait_eur_price = (ait_usd.price * eth_eur.price) / eth_usd.price
            
            # Calculate ETH/AIT rate
            eth_ait_rate = (eth_usd.price / ait_usd.price) if eth_usd and ait_usd else 0
            
            self.send_json_response({
                'success': True,
                'current': {
                    'eth_usd': eth_usd.price if eth_usd else None,
                    'ait_usd': ait_usd.price if ait_usd else None,
                    'eth_eur': eth_eur.price if eth_eur else None,
                    'ait_eur': ait_eur_price,
                    'eth_ait_rate_usd': eth_ait_rate,
                    'timestamp': eth_usd.timestamp if eth_usd else None
                },
                'history': []
            })
        except Exception as e:
            self.send_json_response({'success': False, 'error': str(e)}, status=500)

    def handle_exchange_price_json(self):
        """GET /exchange/price.json — return simple AIT price in USD"""
        try:
            import sys
            sys.path.insert(0, '/opt/aitbc')
            from aitbc.oracles.price_oracle import get_price_oracle
            
            oracle = get_price_oracle()
            ait_usd = oracle.get_price('AIT', 'USD')
            
            if ait_usd:
                self.send_json_response({
                    'price': ait_usd.price,
                    'currency': 'USD',
                    'timestamp': ait_usd.timestamp
                })
            else:
                # Fallback to fixed price from config
                import os
                fixed_price = os.getenv('AIT_USD_FIXED_PRICE', '0.01')
                self.send_json_response({
                    'price': float(fixed_price),
                    'currency': 'USD',
                    'timestamp': datetime.now(UTC).isoformat(),
                    'source': 'fixed'
                })
        except Exception as e:
            self.send_json_response({'error': str(e)}, status=500)


    def handle_bridge_price(self, parsed):
        """GET /v1/bridge/price?base=ETH&quote=USD — oracle price feed"""
        import sys
        sys.path.insert(0, '/opt/aitbc')
        params = urllib.parse.parse_qs(parsed.query)
        base = params.get('base', ['ETH'])[0].upper()
        quote = params.get('quote', ['USD'])[0].upper()
        try:
            from aitbc.oracles.price_oracle import get_price_oracle
            result = get_price_oracle().get_price(base, quote)
            if result:
                self.send_json_response({
                    'pair': f'{result.base}/{result.quote}',
                    'price': result.price,
                    'source': result.source,
                    'timestamp': result.timestamp,
                })
            else:
                self.send_json_response({'error': f'No price available for {base}/{quote}'}, status=404)
        except Exception as e:
            self.send_json_response({'error': str(e)}, status=500)

    def handle_bridge_status(self, tx_id):
        """GET /v1/bridge/status[/{tx_id}]"""
        import os
        bridge_addr = os.getenv('BRIDGE_CONTRACT_ADDRESS')
        if tx_id:
            self.send_json_response({'tx_id': tx_id, 'status': 'pending', 'message': 'Bridge contract not yet deployed on-chain'})
        else:
            if bridge_addr:
                status = 'deployed'
                msg = 'Bridge contract deployed on-chain'
            else:
                status = 'configured'
                msg = 'Deploy bridge contract with: npx hardhat run contracts/scripts/deploy-bridge.js --network sepolia'
            deposit_addr = os.getenv('BRIDGE_ETH_ADDRESS')
            self.send_json_response({
                'bridge': 'CrossChainBridge',
                'status': status,
                'direction': 'ETH → AIT (deposits only)',
                'supported_chains': ['ethereum', 'aitbc'],
                'deposit_address': deposit_addr,
                'withdraw_address': None,
                'withdraw_enabled': False,
                'fee_rate': 0.005,
                'contract_address': bridge_addr,
                'message': msg,
                'note': 'Withdrawals (AIT → ETH) are currently disabled. Only ETH deposits to AIT are supported.'
            })

    def _read_json_body(self):
        import json
        length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def handle_bridge_deposit(self):
        """POST /v1/bridge/deposit — initiate ETH→AIT bridge deposit"""
        try:
            import os
            import sys
            sys.path.insert(0, '/opt/aitbc')
            from aitbc.oracles.price_oracle import get_price_oracle
            
            body = self._read_json_body()
            eth_amount = float(body.get('eth_amount', 0))
            ait_address = body.get('ait_address', '')
            
            if not eth_amount or not ait_address:
                self.send_json_response({'error': 'eth_amount and ait_address required'}, status=400)
                return
            
            # Get bridge configuration
            bridge_eth_address = os.getenv('BRIDGE_ETH_ADDRESS')
            min_eth_deposit = float(os.getenv('MIN_ETH_DEPOSIT', '0.001'))
            eth_network = os.getenv('ETH_NETWORK', 'sepolia')
            
            if not bridge_eth_address:
                self.send_json_response({'error': 'Bridge not configured - BRIDGE_ETH_ADDRESS not set'}, status=500)
                return
            
            # Validate minimum deposit
            if eth_amount < min_eth_deposit:
                self.send_json_response({
                    'error': f'Minimum deposit is {min_eth_deposit} ETH',
                    'min_deposit': min_eth_deposit
                }, status=400)
                return
            
            # Get prices for estimate
            oracle = get_price_oracle()
            eth_usd = oracle.get_price('ETH', 'USD')
            ait_usd = oracle.get_price('AIT', 'USD')
            
            # Calculate AIT amount
            ait_amount = None
            if eth_usd and ait_usd and ait_usd.price > 0:
                ait_amount = (eth_amount * eth_usd.price) / ait_usd.price
            
            # Calculate fee (0.5%)
            fee_eth = eth_amount * 0.005
            net_eth = eth_amount - fee_eth
            
            self.send_json_response({
                'status': 'ready',
                'message': 'Send ETH to the bridge address with your AIT address in transaction data',
                'instructions': {
                    'send_eth_to': bridge_eth_address,
                    'network': eth_network,
                    'amount_eth': eth_amount,
                    'transaction_data': ait_address,
                    'min_deposit': min_eth_deposit
                },
                'estimate': {
                    'eth_amount': eth_amount,
                    'fee_eth': round(fee_eth, 8),
                    'net_eth': round(net_eth, 8),
                    'estimated_ait_amount': round(ait_amount, 6) if ait_amount else None,
                    'eth_usd_price': eth_usd.price if eth_usd else None,
                    'ait_usd_price': ait_usd.price if ait_usd else None,
                    'ait_recipient': ait_address
                }
            }, status=200)
        except Exception as e:
            self.send_json_response({'error': str(e)}, status=500)

    def handle_bridge_withdraw(self):
        """POST /v1/bridge/withdraw — initiate AIT→ETH bridge withdrawal (DISABLED)"""
        try:
            import sys
            sys.path.insert(0, '/opt/aitbc')
            
            body = self._read_json_body()
            ait_amount = float(body.get('ait_amount', 0))
            eth_address = body.get('eth_address', '')
            
            if not ait_amount or not eth_address:
                self.send_json_response({'error': 'ait_amount and eth_address required'}, status=400)
                return
            
            # Feature is disabled
            self.send_json_response({
                'status': 'disabled',
                'message': 'AIT→ETH withdrawals are currently disabled. Only ETH→AIT deposits are supported.',
                'reason': 'Withdrawal functionality not yet enabled',
                'supported_direction': 'ETH → AIT (deposits only)',
                'deposit_endpoint': '/v1/bridge/deposit'
            }, status=503)
        except Exception as e:
            self.send_json_response({'error': str(e)}, status=500)

    def handle_bridge_deposits(self, parsed):
        """GET /v1/bridge/deposits — list bridge deposits"""
        try:
            import sys
            from urllib.parse import parse_qs
            sys.path.insert(0, '/opt/aitbc/apps/bridge-monitor/src')
            from bridge_monitor.storage import BridgeDepositStatus, count_deposits, get_deposits
            
            params = parse_qs(parsed.query)
            status_filter = params.get('status', [None])[0]
            limit = int(params.get('limit', [50])[0])
            offset = int(params.get('offset', [0])[0])
            
            status = None
            if status_filter:
                try:
                    status = BridgeDepositStatus(status_filter)
                except ValueError:
                    self.send_json_response({'error': f'Invalid status: {status_filter}'}, status=400)
                    return
            
            deposits = get_deposits(status=status, limit=limit, offset=offset)
            total = count_deposits(status=status)
            
            # Convert sqlite3.Row objects to dicts if needed
            deposits_list = []
            for d in deposits:
                if isinstance(d, dict):
                    deposits_list.append(d)
                else:
                    # sqlite3.Row object
                    deposits_list.append(dict(d))
            
            self.send_json_response({
                'deposits': deposits_list,
                'count': len(deposits_list),
                'total': total,
                'limit': limit,
                'offset': offset,
            })
        except Exception as e:
            self.send_json_response({'error': str(e)}, status=500)

    def handle_bridge_deposit_detail(self, tx_hash):
        """GET /v1/bridge/deposit/{tx_hash} — get deposit details"""
        try:
            import sys
            sys.path.insert(0, '/opt/aitbc/apps/bridge-monitor/src')
            from bridge_monitor.storage import get_deposit
            
            deposit = get_deposit(tx_hash)
            if not deposit:
                self.send_json_response({'error': 'Deposit not found'}, status=404)
                return
            
            self.send_json_response(deposit)
        except Exception as e:
            self.send_json_response({'error': str(e)}, status=500)

    def handle_bridge_estimate(self):
        """POST /v1/bridge/estimate — estimate AIT amount for ETH"""
        try:
            body = self._read_json_body()
            eth_amount = float(body.get('eth_amount', 0))
            
            if eth_amount <= 0:
                self.send_json_response({'error': 'eth_amount must be positive'}, status=400)
                return
            
            import sys
            sys.path.insert(0, '/opt/aitbc')
            from aitbc.oracles.price_oracle import get_price_oracle
            
            oracle = get_price_oracle()
            eth_usd_result = oracle.get_price('ETH', 'USD')
            ait_usd_result = oracle.get_price('AIT', 'USD')
            
            if not eth_usd_result or not ait_usd_result:
                self.send_json_response({'error': 'Cannot get oracle prices'}, status=503)
                return
            
            eth_usd = eth_usd_result.price
            ait_usd = ait_usd_result.price
            
            if ait_usd == 0:
                self.send_json_response({'error': 'AIT/USD price is zero'}, status=503)
                return
            
            ait_amount = (eth_amount * eth_usd) / ait_usd
            
            self.send_json_response({
                'eth_amount': eth_amount,
                'eth_usd_price': eth_usd,
                'ait_usd_price': ait_usd,
                'ait_amount': round(ait_amount, 6),
                'exchange_rate': round(ait_amount / eth_amount, 2),
            })
        except Exception as e:
            self.send_json_response({'error': str(e)}, status=500)

    def handle_wallet_balance(self):
        """Handle wallet balance request"""
        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        address = params.get('address', [''])[0]

        if not address:
            self.send_json_response({
                "btc": "0.00000000",
                "aitbc": "0.00",
                "address": "unknown"
            })
            return

        try:
            # Query real blockchain for balance
            import json
            import urllib.request

            # Get AITBC balance from blockchain
            blockchain_url = f"http://localhost:9080/rpc/getBalance/{address}"
            with urllib.request.urlopen(blockchain_url) as response:
                balance_data = json.loads(response.read().decode())

            # For BTC, we'll query a Bitcoin API (simplified for now)
            # In production, you'd integrate with a real Bitcoin node API
            btc_balance = "0.00000000"  # Placeholder - would query real Bitcoin network

            self.send_json_response({
                "btc": btc_balance,
                "aitbc": str(balance_data.get('balance', 0)),
                "address": address,
                "nonce": balance_data.get('nonce', 0)
            })
        except Exception:
            # Fallback to error if blockchain is down
            self.send_json_response({
                "btc": "0.00000000",
                "aitbc": "0.00",
                "address": address,
                "error": "Failed to fetch balance from blockchain"
            })

    def handle_wallet_connect(self):
        """Handle wallet connection request"""
        import secrets
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        mock_address = "aitbc" + secrets.token_hex(20)
        self.send_json_response({
            "address": mock_address,
            "status": "connected"
        })

    def send_json_response(self, data, status=200):
        """Send JSON response"""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

class WalletAPIHandler(BaseHTTPRequestHandler):
    """Handle wallet API requests"""

    def do_GET(self):
        """Handle GET requests"""
        if self.path.startswith('/api/wallet/balance'):
            # Parse address from query params
            from urllib.parse import parse_qs, urlparse
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            address = params.get('address', [''])[0]

            # Return mock balance for now
            self.send_json_response({
                "btc": "0.12345678",
                "aitbc": "1000.50",
                "address": address or "unknown"
            })
        else:
            self.send_error(404)

    def do_POST(self):
        """Handle POST requests"""
        if self.path == '/wallet/connect':
            import secrets
            mock_address = "aitbc" + secrets.token_hex(20)
            self.send_json_response({
                "address": mock_address,
                "status": "connected"
            })
        else:
            self.send_error(404)

    def send_json_response(self, data, status=200):
        """Send JSON response"""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

def run_server(port=8106):
    """Run the server"""
    init_db()
    # Removed mock trades - now using only real blockchain data

    server = HTTPServer(('localhost', port), ExchangeAPIHandler)
    logger.info("AITBC Exchange API Server started", port=port, url=f"http://localhost:{port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
        server.shutdown()
        server.server_close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='AITBC Exchange API Server')
    parser.add_argument('--port', type=int, default=8106, help='Port to run the server on')
    args = parser.parse_args()
    run_server(port=args.port)
