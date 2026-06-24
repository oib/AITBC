"""Handler package — assembles ExchangeAPIHandler from domain mixins."""

import urllib.parse

from .base import BaseHandler
from .bridge import BridgeMixin
from .exchange import ExchangeMixin
from .marketplace import MarketplaceMixin
from .wallet import WalletAPIHandler


class ExchangeAPIHandler(BaseHandler, MarketplaceMixin, ExchangeMixin, BridgeMixin):
    """Main exchange API handler — dispatches to domain mixin methods."""

    def do_GET(self):
        """Handle GET requests"""
        # Validate path to prevent SSRF
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
            self.handle_treasury_balance()
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

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/v1/marketplace/orders/"):
            self.handle_marketplace_delete_order(path)
        elif path.startswith("/v1/marketplace/offers/"):
            self.handle_marketplace_delete_offer(path)
        else:
            self.send_error(404, "Not Found")


__all__ = ["BaseHandler", "ExchangeAPIHandler", "WalletAPIHandler"]
