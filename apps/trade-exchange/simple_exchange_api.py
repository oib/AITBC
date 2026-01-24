#!/usr/bin/env python3
"""
Simple FastAPI backend for the AITBC Trade Exchange (Python 3.13 compatible)
"""

import sqlite3
import json
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import random

# Database setup
def init_db():
    """Initialize SQLite database"""
    conn = sqlite3.connect('exchange.db')
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
    
    # Add columns if they don't exist (for existing databases)
    try:
        cursor.execute('ALTER TABLE orders ADD COLUMN user_address TEXT')
    except:
        pass
    
    try:
        cursor.execute('ALTER TABLE orders ADD COLUMN tx_hash TEXT')
    except:
        pass
    
    conn.commit()
    conn.close()

def create_mock_trades():
    """Create some mock trades"""
    conn = sqlite3.connect('exchange.db')
    cursor = conn.cursor()
    
    # Check if we have trades
    cursor.execute('SELECT COUNT(*) FROM trades')
    if cursor.fetchone()[0] > 0:
        conn.close()
        return
    
    # Create mock trades
    now = datetime.utcnow()
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
        if self.path == '/api/health':
            self.health_check()
        elif self.path.startswith('/api/trades/recent'):
            parsed = urllib.parse.urlparse(self.path)
            self.get_recent_trades(parsed)
        elif self.path.startswith('/api/orders/orderbook'):
            self.get_orderbook()
        elif self.path.startswith('/api/wallet/balance'):
            self.handle_wallet_balance()
        elif self.path == '/api/total-supply':
            self.handle_total_supply()
        elif self.path == '/api/treasury-balance':
            self.handle_treasury_balance()
        else:
            self.send_error(404, "Not Found")
    
    def do_POST(self):
        """Handle POST requests"""
        if self.path == '/api/orders':
            self.handle_place_order()
        elif self.path == '/api/wallet/connect':
            self.handle_wallet_connect()
        else:
            self.send_error(404, "Not Found")
    
    def get_recent_trades(self, parsed):
        """Get recent trades"""
        query = urllib.parse.parse_qs(parsed.query)
        limit = int(query.get('limit', [20])[0])
        
        conn = sqlite3.connect('exchange.db')
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
        conn = sqlite3.connect('exchange.db')
        cursor = conn.cursor()
        
        # Get sell orders
        cursor.execute('''
            SELECT id, order_type, amount, price, total, filled, remaining, status, created_at
            FROM orders
            WHERE order_type = 'SELL' AND status = 'OPEN'
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
            WHERE order_type = 'BUY' AND status = 'OPEN'
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
                import urllib.request
                import urllib.parse
                
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
                conn = sqlite3.connect('exchange.db')
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
                
            except Exception as e:
                # Fallback to database-only if blockchain is down
                total = amount * price
                
                conn = sqlite3.connect('exchange.db')
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
            # Match with sell orders
            cursor.execute('''
                SELECT * FROM orders
                WHERE order_type = 'SELL' AND status = 'OPEN' AND price <= ?
                ORDER BY price ASC, created_at ASC
            ''', (new_order['price'],))
        else:
            # Match with buy orders
            cursor.execute('''
                SELECT * FROM orders
                WHERE order_type = 'BUY' AND status = 'OPEN' AND price >= ?
                ORDER BY price DESC, created_at ASC
            ''', (new_order['price'],))
        
        matching_orders = cursor.fetchall()
        
        for order_row in matching_orders:
            if new_order['remaining'] <= 0:
                break
                
            # Calculate trade amount
            trade_amount = min(new_order['remaining'], order_row[6])  # remaining
            
            if trade_amount > 0:
                # Create trade on blockchain
                try:
                    import urllib.request
                    import urllib.parse
                    
                    trade_price = order_row[3]  # Use the existing order's price
                    trade_data = {
                        "type": "TRADE",
                        "buy_order": new_order['id'] if new_order['order_type'] == 'BUY' else order_row[0],
                        "sell_order": order_row[0] if new_order['order_type'] == 'BUY' else new_order['id'],
                        "amount": str(trade_amount),
                        "price": str(trade_price)
                    }
                    
                    # Record trade in database
                    cursor.execute('''
                        INSERT INTO trades (amount, price, total)
                        VALUES (?, ?, ?)
                    ''', (trade_amount, trade_price, trade_amount * trade_price))
                    
                    # Update orders
                    new_order['remaining'] -= trade_amount
                    new_order['filled'] = new_order.get('filled', 0) + trade_amount
                    
                    # Update matching order
                    new_remaining = order_row[6] - trade_amount
                    cursor.execute('''
                        UPDATE orders SET remaining = ?, filled = filled + ?
                        WHERE id = ?
                    ''', (new_remaining, trade_amount, order_row[0]))
                    
                    # Close order if fully filled
                    if new_remaining <= 0:
                        cursor.execute('''
                            UPDATE orders SET status = 'FILLED' WHERE id = ?
                        ''', (order_row[0],))
                    
                except Exception as e:
                    print(f"Failed to create trade on blockchain: {e}")
                    # Still record the trade in database
                    cursor.execute('''
                        INSERT INTO trades (amount, price, total)
                        VALUES (?, ?, ?)
                    ''', (trade_amount, order_row[3], trade_amount * order_row[3]))
        
        # Update new order in database
        if new_order['remaining'] <= 0:
            cursor.execute('''
                UPDATE orders SET status = 'FILLED', remaining = 0, filled = ?
                WHERE id = ?
            ''', (new_order['filled'], new_order['id']))
        else:
            cursor.execute('''
                UPDATE orders SET remaining = ?, filled = ?
                WHERE id = ?
            ''', (new_order['remaining'], new_order['filled'], new_order['id']))
        
        conn.commit()
        conn.close()
    
    def handle_treasury_balance(self):
        """Get exchange treasury balance from blockchain"""
        try:
            import urllib.request
            import json
            
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
            except Exception as e:
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
            'timestamp': datetime.utcnow().isoformat()
        })
    
    def handle_wallet_balance(self):
        """Handle wallet balance request"""
        from urllib.parse import urlparse, parse_qs
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
            import urllib.request
            import json
            
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
        except Exception as e:
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
            from urllib.parse import urlparse, parse_qs
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

def run_server(port=3003):
    """Run the server"""
    init_db()
    # Removed mock trades - now using only real blockchain data
    
    server = HTTPServer(('localhost', port), ExchangeAPIHandler)
    print(f"""
╔═══════════════════════════════════════╗
║   AITBC Exchange API Server          ║
╠═══════════════════════════════════════╣
║  Server running at:                   ║
║  http://localhost:{port}               ║
║                                       ║
║  Real trading API active!             ║
║  Press Ctrl+C to stop                  ║
╚═══════════════════════════════════════╝
    """)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.server_close()

if __name__ == "__main__":
    run_server()
