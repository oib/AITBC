"""
API request handlers for exchange API.
"""

import json
import sqlite3
import urllib.parse
from http.server import BaseHTTPRequestHandler

from aitbc.aitbc_logging import get_logger

from .database import get_db_path

logger = get_logger(__name__)


class ExchangeAPIHandler(BaseHTTPRequestHandler):
    """Handle exchange API requests"""

    def do_GET(self):
        """Handle GET requests"""
        if not self.path or self.path.startswith(("//", "\\\\", "..")):
            self.send_error(400, "Invalid path")
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/health" or path == "/api/health":
            self.health_check()
        elif path.startswith("/api/trades/recent"):
            self.get_recent_trades(parsed)
        elif path.startswith("/api/orders/orderbook"):
            self.get_orderbook()
        elif path.startswith("/api/wallet/balance"):
            self.handle_wallet_balance()
        elif path == "/api/total-supply":
            self.handle_total_supply()
        elif path == "/api/treasury-balance":
            self.handle_treasury_balance()
        elif path == "/v1/marketplace/offers":
            self.handle_marketplace_offers(parsed)
        elif path.startswith("/v1/marketplace/offers/"):
            self.handle_marketplace_offer(path)
        elif path == "/v1/marketplace/orders":
            self.handle_marketplace_orders(parsed)
        elif path == "/metrics":
            self.handle_metrics()
        elif path == "/v1/bridge/price":
            self.handle_bridge_price(parsed)
        elif path == "/v1/bridge/status":
            self.handle_bridge_status(None)
        elif path.startswith("/v1/bridge/status/"):
            self.handle_bridge_status(path.split("/")[-1])
        elif path == "/v1/bridge/deposits":
            self.handle_bridge_deposits(parsed)
        elif path.startswith("/v1/bridge/deposit/"):
            self.handle_bridge_deposit_detail(path.split("/")[-1])
        elif path == "/v1/exchange/history":
            self.handle_exchange_history(parsed)
        elif path == "/exchange/price.json":
            self.handle_exchange_price_json()
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        """Handle POST requests"""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/orders":
            self.handle_place_order()
        elif path == "/api/wallet/connect":
            self.handle_wallet_connect()
        elif path == "/v1/marketplace/offers":
            self.handle_marketplace_create_offer()
        elif path.startswith("/v1/marketplace/offers/") and path.endswith("/book"):
            self.handle_marketplace_book_offer(path)
        elif path == "/v1/bridge/deposit":
            self.handle_bridge_deposit()
        elif path == "/v1/bridge/withdraw":
            self.handle_bridge_withdraw()
        elif path == "/v1/bridge/estimate":
            self.handle_bridge_estimate()
        else:
            self.send_error(404, "Not Found")

    def health_check(self):
        """Health check endpoint"""
        self.send_json_response({"status": "healthy", "service": "exchange-api"})

    def get_recent_trades(self, parsed):
        """Get recent trades"""
        limit = int(parsed.query.split("limit=")[1].split("&")[0]) if "limit=" in parsed.query else 10
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM trades ORDER BY created_at DESC LIMIT {limit}")
        trades = cursor.fetchall()
        conn.close()
        self.send_json_response({"trades": trades})

    def get_orderbook(self):
        """Get order book"""
        self.send_json_response({"bids": [], "asks": []})

    def handle_wallet_balance(self):
        """Handle wallet balance"""
        self.send_json_response({"btc": "0.12345678", "aitbc": "1000.50"})

    def handle_total_supply(self):
        """Handle total supply"""
        self.send_json_response({"total_supply": 1000000})

    def handle_treasury_balance(self):
        """Handle treasury balance"""
        self.send_json_response({"treasury_balance": 500000})

    def handle_marketplace_offers(self, parsed):
        """Handle marketplace offers"""
        self.send_json_response({"offers": []})

    def handle_marketplace_offer(self, path):
        """Handle marketplace offer detail"""
        self.send_json_response({"offer": {}})

    def handle_marketplace_orders(self, parsed):
        """Handle marketplace orders"""
        self.send_json_response({"orders": []})

    def handle_metrics(self):
        """Handle metrics"""
        self.send_json_response({"metrics": {}})

    def handle_bridge_price(self, parsed):
        """Handle bridge price"""
        self.send_json_response({"price": 0.00001})

    def handle_bridge_status(self, tx_id):
        """Handle bridge status"""
        self.send_json_response({"status": "pending"})

    def handle_bridge_deposits(self, parsed):
        """Handle bridge deposits"""
        self.send_json_response({"deposits": []})

    def handle_bridge_deposit_detail(self, deposit_id):
        """Handle bridge deposit detail"""
        self.send_json_response({"deposit": {}})

    def handle_exchange_history(self, parsed):
        """Handle exchange history"""
        self.send_json_response({"history": []})

    def handle_exchange_price_json(self):
        """Handle exchange price JSON"""
        self.send_json_response({"price": 0.00001})

    def handle_place_order(self):
        """Handle place order"""
        self.send_json_response({"order_id": "1", "status": "open"})

    def handle_wallet_connect(self):
        """Handle wallet connect"""
        import secrets

        mock_address = "aitbc" + secrets.token_hex(20)
        self.send_json_response({"address": mock_address, "status": "connected"})

    def handle_marketplace_create_offer(self):
        """Handle marketplace create offer"""
        self.send_json_response({"offer_id": "1", "status": "active"})

    def handle_marketplace_book_offer(self, path):
        """Handle marketplace book offer"""
        self.send_json_response({"status": "booked"})

    def handle_bridge_deposit(self):
        """Handle bridge deposit"""
        self.send_json_response({"deposit_id": "1", "status": "pending"})

    def handle_bridge_withdraw(self):
        """Handle bridge withdraw"""
        self.send_json_response({"withdraw_id": "1", "status": "pending"})

    def handle_bridge_estimate(self):
        """Handle bridge estimate"""
        self.send_json_response({"estimate": 100000})

    def send_json_response(self, data, status=200):
        """Send JSON response"""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


class WalletAPIHandler(BaseHTTPRequestHandler):
    """Handle wallet API requests"""

    def do_GET(self):
        """Handle GET requests"""
        if self.path.startswith("/api/wallet/balance"):
            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            address = params.get("address", [""])[0]

            self.send_json_response({"btc": "0.12345678", "aitbc": "1000.50", "address": address or "unknown"})
        else:
            self.send_error(404)

    def do_POST(self):
        """Handle POST requests"""
        if self.path == "/wallet/connect":
            import secrets

            mock_address = "aitbc" + secrets.token_hex(20)
            self.send_json_response({"address": mock_address, "status": "connected"})
        else:
            self.send_error(404)

    def send_json_response(self, data, status=200):
        """Send JSON response"""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
