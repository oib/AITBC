#!/usr/bin/env python3
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse


class Handler(BaseHTTPRequestHandler):
    def _json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Api-Key")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Api-Key")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/trades/recent":
            trades = [
                {"id": 1, "price": 0.00001, "amount": 1500, "created_at": "2026-01-21T17:00:00Z"},
                {"id": 2, "price": 0.0000095, "amount": 500, "created_at": "2026-01-21T16:55:00Z"},
            ]
            return self._json(trades)

        if path == "/api/orders/orderbook":
            orderbook = {
                "sells": [{"price": 0.00001, "remaining": 1500, "amount": 1500}],
                "buys": [{"price": 0.000009, "remaining": 1000, "amount": 1000}],
            }
            return self._json(orderbook)

        if path == "/api/wallet/balance":
            return self._json({"balance": 1000, "currency": "AITBC"})

        if path == "/api/treasury-balance":
            return self._json({
                "balance": 50000,
                "currency": "AITBC",
                "usd_value": 5000.00,
                "last_updated": "2026-01-21T18:00:00Z"
            })

        if path == "/api/exchange/wallet/info":
            return self._json({
                "address": "aitbc1exchange123456789",
                "balance": 1000,
                "currency": "AITBC",
                "total_transactions": 150,
                "status": "active",
                "transactions": [
                    {
                        "id": "txn_001",
                        "type": "deposit",
                        "amount": 500,
                        "timestamp": "2026-01-21T17:00:00Z",
                        "status": "completed"
                    },
                    {
                        "id": "txn_002", 
                        "type": "withdrawal",
                        "amount": 200,
                        "timestamp": "2026-01-21T16:30:00Z",
                        "status": "completed"
                    },
                    {
                        "id": "txn_003",
                        "type": "trade",
                        "amount": 100,
                        "timestamp": "2026-01-21T16:00:00Z",
                        "status": "completed"
                    }
                ]
            })

        return self._json({"detail": "Not Found"}, status=404)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/wallet/connect":
            resp = {
                "success": True,
                "address": "aitbc1wallet123456789",
                "message": "Wallet connected successfully",
            }
            return self._json(resp)

        return self._json({"detail": "Not Found"}, status=404)


def main():
    HTTPServer(("127.0.0.1", 8085), Handler).serve_forever()


if __name__ == "__main__":
    main()
