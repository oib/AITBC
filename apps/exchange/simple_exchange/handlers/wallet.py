"""Wallet API handler — balance and connect routes.

Queries the real wallet service (port 8108) for balance data instead of
returning mock values. The /wallet/connect endpoint requires the client
to provide their own wallet address — no mock address generation.
"""

import os

from .base import BaseHandler

WALLET_SERVICE_URL = os.getenv("WALLET_SERVICE_URL", "http://localhost:8108")


class WalletAPIHandler(BaseHandler):
    """Handle wallet API requests"""

    def do_GET(self):
        """Handle GET requests"""
        if self.path.startswith("/api/wallet/balance"):
            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            address = params.get("address", [""])[0]

            if not address:
                self.send_json_response({"error": "Wallet address is required"}, status=400)
                return

            # Query the real wallet service for balance
            try:
                import httpx

                with httpx.Client(timeout=10) as client:
                    resp = client.get(f"{WALLET_SERVICE_URL}/v1/wallets", params={"address": address})
                    if resp.status_code == 200:
                        data = resp.json()
                        wallets = data.get("wallets", [])
                        if wallets:
                            wallet = wallets[0]
                            self.send_json_response(
                                {
                                    "aitbc": wallet.get("balance", "0"),
                                    "address": address,
                                    "wallet_id": wallet.get("wallet_id", ""),
                                }
                            )
                        else:
                            self.send_json_response(
                                {"aitbc": "0", "address": address, "error": "Wallet not found"}, status=404
                            )
                    else:
                        self.send_json_response(
                            {
                                "error": f"Wallet service returned {resp.status_code}",
                                "address": address,
                            },
                            status=502,
                        )
            except Exception as e:
                self.send_json_response(
                    {
                        "error": f"Wallet service unavailable: {e}",
                        "address": address,
                    },
                    status=503,
                )
        else:
            self.send_error(404)

    def do_POST(self):
        """Handle POST requests"""
        if self.path == "/wallet/connect":
            # Read the request body to get the wallet address from the client
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b""

            import json

            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self.send_json_response({"error": "Invalid JSON body"}, status=400)
                return

            address = data.get("address")
            if not address:
                self.send_json_response({"error": "Wallet address is required in request body"}, status=400)
                return

            # Verify the wallet exists in the wallet service
            try:
                import httpx

                with httpx.Client(timeout=10) as client:
                    resp = client.get(f"{WALLET_SERVICE_URL}/v1/wallets", params={"address": address})
                    if resp.status_code == 200:
                        wallet_data = resp.json()
                        wallets = wallet_data.get("wallets", [])
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
                        self.send_json_response(
                            {
                                "error": f"Wallet service returned {resp.status_code}",
                                "address": address,
                            },
                            status=502,
                        )
            except Exception as e:
                self.send_json_response(
                    {
                        "error": f"Wallet service unavailable: {e}",
                        "address": address,
                    },
                    status=503,
                )
        else:
            self.send_error(404)
