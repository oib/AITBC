"""Handler package — assembles ExchangeAPIHandler from domain mixins."""

import urllib.parse

from .base import BaseHandler
from .bridge import BridgeMixin
from .exchange import ExchangeMixin
from .market import MarketMixin
from .wallet import WalletAPIHandler


class ExchangeAPIHandler(BaseHandler, MarketMixin, ExchangeMixin, BridgeMixin):
    """Main exchange API handler — dispatches to domain mixin methods."""

    def do_GET(self):
        """Handle GET requests"""
        # Validate path to prevent SSRF
        if not self.path or self.path.startswith(("//", "\\\\", "..")):
            self.send_error(400, "Invalid path")
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        # Legacy public spelling stays live until its removal is approved.
        if path == "/v1/marketplace" or path.startswith("/v1/marketplace/"):
            path = "/v1/market" + path[len("/v1/marketplace") :]

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
        elif path == "/v1/market/offers":
            self.handle_market_offers(parsed)
        elif path.startswith("/v1/market/offers/"):
            self.handle_market_offer(path)
        elif path == "/v1/market/orders":
            self.handle_market_orders(parsed)
        elif path == "/metrics":
            self.handle_metrics()
        elif path in ("/v1/cross-chain/rates", "/cross-chain/rates"):
            self.handle_cross_chain_rates()
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
        # Legacy public spelling stays live until its removal is approved.
        if path == "/v1/marketplace" or path.startswith("/v1/marketplace/"):
            path = "/v1/market" + path[len("/v1/marketplace") :]

        if path == "/api/orders":
            self.handle_place_order()
        elif path == "/api/wallet/connect":
            self.handle_wallet_connect()
        elif path == "/v1/market/offers":
            self.handle_market_create_offer()
        elif path.startswith("/v1/market/offers/") and path.endswith("/book"):
            self.handle_market_book_offer(path)
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
        # Legacy public spelling stays live until its removal is approved.
        if path == "/v1/marketplace" or path.startswith("/v1/marketplace/"):
            path = "/v1/market" + path[len("/v1/marketplace") :]

        if path.startswith("/v1/market/orders/"):
            self.handle_market_delete_order(parsed)
        elif path.startswith("/v1/market/offers/"):
            self.handle_market_delete_offer(parsed)
        else:
            self.send_error(404, "Not Found")


__all__ = ["BaseHandler", "ExchangeAPIHandler", "WalletAPIHandler"]
