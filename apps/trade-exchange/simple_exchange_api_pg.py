#!/usr/bin/env python3
"""AITBC Exchange API with PostgreSQL Support"""

from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import urllib.request
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from decimal import Decimal
import random

# PostgreSQL Configuration
PG_CONFIG = {
    "host": "localhost",
    "database": "aitbc_exchange",
    "user": "aitbc_user",
    "password": "aitbc_password",
    "port": 5432
}

def get_pg_connection():
    """Get PostgreSQL connection"""
    return psycopg2.connect(**PG_CONFIG)

def init_db():
    """Initialize PostgreSQL database"""
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()
        
        # Check if tables exist
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name IN ('trades', 'orders')
            )
        """)
        
        if not cursor.fetchone()[0]:
            print("Creating PostgreSQL tables...")
            create_pg_schema()
        
        conn.close()
    except Exception as e:
        print(f"Database initialization error: {e}")

def create_pg_schema():
    """Create PostgreSQL schema"""
    conn = get_pg_connection()
    cursor = conn.cursor()
    
    # Create trades table
    cursor.execute("""
        CREATE TABLE trades (
            id SERIAL PRIMARY KEY,
            amount NUMERIC(20, 8) NOT NULL,
            price NUMERIC(20, 8) NOT NULL,
            total NUMERIC(20, 8) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            tx_hash VARCHAR(66),
            maker_address VARCHAR(66),
            taker_address VARCHAR(66)
        )
    """)
    
    # Create orders table
    cursor.execute("""
        CREATE TABLE orders (
            id SERIAL PRIMARY KEY,
            order_type VARCHAR(4) NOT NULL CHECK (order_type IN ('BUY', 'SELL')),
            amount NUMERIC(20, 8) NOT NULL,
            price NUMERIC(20, 8) NOT NULL,
            total NUMERIC(20, 8) NOT NULL,
            remaining NUMERIC(20, 8) NOT NULL,
            filled NUMERIC(20, 8) DEFAULT 0,
            status VARCHAR(20) DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'FILLED', 'CANCELLED')),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            user_address VARCHAR(66),
            tx_hash VARCHAR(66)
        )
    """)
    
    # Create indexes
    cursor.execute("CREATE INDEX idx_trades_created_at ON trades(created_at DESC)")
    cursor.execute("CREATE INDEX idx_orders_type ON orders(order_type)")
    cursor.execute("CREATE INDEX idx_orders_price ON orders(price)")
    cursor.execute("CREATE INDEX idx_orders_status ON orders(status)")
    
    conn.commit()
    conn.close()

class ExchangeAPIHandler(BaseHTTPRequestHandler):
    def send_json_response(self, data, status=200):
        """Send JSON response"""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())
    
    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/api/health':
            self.health_check()
        elif self.path.startswith('/api/trades/recent'):
            parsed = urlparse(self.path)
            self.get_recent_trades(parsed)
        elif self.path.startswith('/api/orders/orderbook'):
            self.get_orderbook()
        elif self.path.startswith('/api/wallet/balance'):
            self.handle_wallet_balance()
        elif self.path == '/api/treasury-balance':
            self.handle_treasury_balance()
        else:
            self.send_error(404)
    
    def do_POST(self):
        """Handle POST requests"""
        if self.path == '/api/orders':
            self.handle_place_order()
        elif self.path == '/api/wallet/connect':
            self.handle_wallet_connect()
        else:
            self.send_error(404)
    
    def health_check(self):
        """Health check"""
        try:
            conn = get_pg_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()
            
            self.send_json_response({
                'status': 'ok',
                'database': 'postgresql',
                'timestamp': datetime.utcnow().isoformat()
            })
        except Exception as e:
            self.send_json_response({
                'status': 'error',
                'error': str(e)
            }, 500)
    
    def get_recent_trades(self, parsed):
        """Get recent trades from PostgreSQL"""
        try:
            conn = get_pg_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get limit from query params
            params = parse_qs(parsed.query)
            limit = int(params.get('limit', [10])[0])
            
            cursor.execute("""
                SELECT * FROM trades 
                ORDER BY created_at DESC 
                LIMIT %s
            """, (limit,))
            
            trades = []
            for row in cursor.fetchall():
                trades.append({
                    'id': row['id'],
                    'amount': float(row['amount']),
                    'price': float(row['price']),
                    'total': float(row['total']),
                    'created_at': row['created_at'].isoformat(),
                    'tx_hash': row['tx_hash']
                })
            
            cursor.close()
            conn.close()
            
            self.send_json_response(trades)
            
        except Exception as e:
            self.send_error(500, str(e))
    
    def get_orderbook(self):
        """Get order book from PostgreSQL"""
        try:
            conn = get_pg_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get sell orders (asks)
            cursor.execute("""
                SELECT * FROM orders 
                WHERE order_type = 'SELL' AND status = 'OPEN' AND remaining > 0
                ORDER BY price ASC, created_at ASC
                LIMIT 20
            """)
            sells = []
            for row in cursor.fetchall():
                sells.append({
                    'id': row['id'],
                    'amount': float(row['remaining']),
                    'price': float(row['price']),
                    'total': float(row['remaining'] * row['price'])
                })
            
            # Get buy orders (bids)
            cursor.execute("""
                SELECT * FROM orders 
                WHERE order_type = 'BUY' AND status = 'OPEN' AND remaining > 0
                ORDER BY price DESC, created_at ASC
                LIMIT 20
            """)
            buys = []
            for row in cursor.fetchall():
                buys.append({
                    'id': row['id'],
                    'amount': float(row['remaining']),
                    'price': float(row['price']),
                    'total': float(row['remaining'] * row['price'])
                })
            
            cursor.close()
            conn.close()
            
            self.send_json_response({
                'buys': buys,
                'sells': sells
            })
            
        except Exception as e:
            self.send_error(500, str(e))
    
    def handle_wallet_connect(self):
        """Handle wallet connection"""
        # Generate a mock wallet address for demo
        address = f"aitbc{''.join(random.choices('0123456789abcdef', k=64))}"
        
        self.send_json_response({
            "address": address,
            "status": "connected"
        })
    
    def handle_wallet_balance(self):
        """Handle wallet balance request"""
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        address = params.get('address', [''])[0]
        
        try:
            # Query blockchain for balance
            blockchain_url = f"http://localhost:9080/rpc/getBalance/{address}"
            with urllib.request.urlopen(blockchain_url) as response:
                balance_data = json.loads(response.read().decode())
                aitbc_balance = balance_data.get('balance', 0)
                nonce = balance_data.get('nonce', 0)
        except:
            aitbc_balance = 0
            nonce = 0
        
        self.send_json_response({
            "btc": "0.00000000",
            "aitbc": str(aitbc_balance),
            "address": address or "unknown",
            "nonce": nonce
        })
    
    def handle_treasury_balance(self):
        """Get exchange treasury balance"""
        try:
            treasury_address = "aitbcexchange00000000000000000000000000000000"
            blockchain_url = f"http://localhost:9080/rpc/getBalance/{treasury_address}"
            
            with urllib.request.urlopen(blockchain_url) as response:
                balance_data = json.loads(response.read().decode())
                treasury_balance = balance_data.get('balance', 0)
                
            self.send_json_response({
                "address": treasury_address,
                "balance": str(treasury_balance),
                "available_for_sale": str(treasury_balance),
                "source": "blockchain"
            })
        except Exception as e:
            self.send_error(500, str(e))
    
    def handle_place_order(self):
        """Handle placing an order"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            order_data = json.loads(post_data.decode())
            
            # Validate order data
            required_fields = ['order_type', 'amount', 'price']
            for field in required_fields:
                if field not in order_data:
                    self.send_json_response({
                        "error": f"Missing required field: {field}"
                    }, 400)
                    return
            
            # Insert order into PostgreSQL
            conn = get_pg_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO orders (order_type, amount, price, total, remaining, user_address)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, created_at
            """, (
                order_data['order_type'],
                Decimal(str(order_data['amount'])),
                Decimal(str(order_data['price'])),
                Decimal(str(order_data['amount'] * order_data['price'])),
                Decimal(str(order_data['amount'])),
                order_data.get('user_address', 'aitbcexchange00000000000000000000000000000000')
            ))
            
            result = cursor.fetchone()
            order_id = result[0]
            created_at = result[1]
            
            conn.commit()
            cursor.close()
            conn.close()
            
            self.send_json_response({
                "id": order_id,
                "order_type": order_data['order_type'],
                "amount": order_data['amount'],
                "price": order_data['price'],
                "status": "OPEN",
                "created_at": created_at.isoformat()
            })
            
        except Exception as e:
            self.send_json_response({
                "error": str(e)
            }, 500)

def run_server(port=3003):
    """Run the server"""
    init_db()
    
    server = HTTPServer(('localhost', port), ExchangeAPIHandler)
    print(f"""
╔═══════════════════════════════════════╗
║   AITBC Exchange API Server          ║
╠═══════════════════════════════════════╣
║  Server running at:                   ║
║  http://localhost:{port}               ║
║                                       ║
║  Database: PostgreSQL                  ║
║  Real trading API active!             ║
╚═══════════════════════════════════════╝
""")
    server.serve_forever()

if __name__ == "__main__":
    run_server()
