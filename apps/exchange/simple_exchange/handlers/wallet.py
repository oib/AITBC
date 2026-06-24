"""Wallet API handler — balance and connect routes."""

from .base import BaseHandler


class WalletAPIHandler(BaseHandler):
    """Handle wallet API requests"""

    def do_GET(self):
        """Handle GET requests"""
        if self.path.startswith("/api/wallet/balance"):
            # Parse address from query params
            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            address = params.get("address", [""])[0]

            # Return mock balance for now
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
