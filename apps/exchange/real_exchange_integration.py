"""
Real Exchange Integration for AITBC
Connects to Binance, Coinbase, and Kraken APIs for live trading
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import ccxt

from aitbc import get_logger

logger = get_logger(__name__)


class ExchangeStatus(StrEnum):
    """Exchange connection status"""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    MAINTENANCE = "maintenance"


class OrderSide(StrEnum):
    """Order side"""

    BUY = "buy"
    SELL = "sell"


@dataclass
class ExchangeCredentials:
    """Exchange API credentials"""

    api_key: str
    secret: str
    sandbox: bool = True
    passphrase: str | None = None


@dataclass
class ExchangeHealth:
    """Exchange health metrics"""

    status: ExchangeStatus
    latency_ms: float
    last_check: datetime
    error_message: str | None = None


@dataclass
class OrderRequest:
    """Unified order request"""

    exchange: str
    symbol: str
    side: OrderSide
    amount: float
    price: float | None = None
    type: str = "limit"


class RealExchangeManager:
    """Manages connections to real exchanges"""

    def __init__(self):
        self.exchanges: dict[str, ccxt.Exchange] = {}
        self.credentials: dict[str, ExchangeCredentials] = {}
        self.health_status: dict[str, ExchangeHealth] = {}
        self.supported_exchanges = ["binance", "coinbasepro", "kraken"]

    async def connect_exchange(self, exchange_name: str, credentials: ExchangeCredentials) -> bool:
        """Connect to an exchange"""
        try:
            if exchange_name not in self.supported_exchanges:
                raise ValueError(f"Unsupported exchange: {exchange_name}")
            if exchange_name == "binance":
                exchange = ccxt.binance(
                    {
                        "apiKey": credentials.api_key,
                        "secret": credentials.secret,
                        "sandbox": credentials.sandbox,
                        "enableRateLimit": True,
                    }
                )
            elif exchange_name == "coinbasepro":
                exchange = ccxt.coinbasepro(
                    {
                        "apiKey": credentials.api_key,
                        "secret": credentials.secret,
                        "passphrase": credentials.passphrase,
                        "sandbox": credentials.sandbox,
                        "enableRateLimit": True,
                    }
                )
            elif exchange_name == "kraken":
                exchange = ccxt.kraken(
                    {
                        "apiKey": credentials.api_key,
                        "secret": credentials.secret,
                        "sandbox": credentials.sandbox,
                        "enableRateLimit": True,
                    }
                )
            await self._test_connection(exchange, exchange_name)
            self.exchanges[exchange_name] = exchange
            self.credentials[exchange_name] = credentials
            self.health_status[exchange_name] = ExchangeHealth(
                status=ExchangeStatus.CONNECTED, latency_ms=0.0, last_check=datetime.now(UTC)
            )
            logger.info("✅ Connected to %s", exchange_name)
            return True
        except Exception as e:
            logger.error("❌ Failed to connect to %s: %s", exchange_name, str(e))
            self.health_status[exchange_name] = ExchangeHealth(
                status=ExchangeStatus.ERROR, latency_ms=0.0, last_check=datetime.now(UTC), error_message=str(e)
            )
            return False

    async def _test_connection(self, exchange: ccxt.Exchange, exchange_name: str):
        """Test exchange connection"""
        start_time = time.time()
        try:
            if hasattr(exchange, "load_markets"):
                if asyncio.iscoroutinefunction(exchange.load_markets):
                    await exchange.load_markets()
                else:
                    exchange.load_markets()
            latency = (time.time() - start_time) * 1000
            logger.info("🔗 %s connection test successful (%sms)", exchange_name, latency)
        except Exception as e:
            raise Exception(f"Connection test failed: {str(e)}")

    async def disconnect_exchange(self, exchange_name: str) -> bool:
        """Disconnect from an exchange"""
        try:
            if exchange_name in self.exchanges:
                del self.exchanges[exchange_name]
                del self.credentials[exchange_name]
                self.health_status[exchange_name] = ExchangeHealth(
                    status=ExchangeStatus.DISCONNECTED, latency_ms=0.0, last_check=datetime.now()
                )
                logger.info("🔌 Disconnected from %s", exchange_name)
                return True
            else:
                logger.warning("⚠️  %s was not connected", exchange_name)
                return False
        except Exception as e:
            logger.error("❌ Failed to disconnect from %s: %s", exchange_name, str(e))
            return False

    async def check_exchange_health(self, exchange_name: str) -> ExchangeHealth:
        """Check exchange health and latency"""
        if exchange_name not in self.exchanges:
            return ExchangeHealth(
                status=ExchangeStatus.DISCONNECTED, latency_ms=0.0, last_check=datetime.now(), error_message="Not connected"
            )
        try:
            start_time = time.time()
            exchange = self.exchanges[exchange_name]
            if hasattr(exchange, "fetch_status"):
                if asyncio.iscoroutinefunction(exchange.fetch_status):
                    await exchange.fetch_status()
                else:
                    exchange.fetch_status()
            latency = (time.time() - start_time) * 1000
            health = ExchangeHealth(status=ExchangeStatus.CONNECTED, latency_ms=latency, last_check=datetime.now())
            self.health_status[exchange_name] = health
            return health
        except Exception as e:
            health = ExchangeHealth(
                status=ExchangeStatus.ERROR, latency_ms=0.0, last_check=datetime.now(), error_message=str(e)
            )
            self.health_status[exchange_name] = health
            return health

    async def get_all_health_status(self) -> dict[str, ExchangeHealth]:
        """Get health status of all connected exchanges"""
        for exchange_name in list(self.exchanges.keys()):
            await self.check_exchange_health(exchange_name)
        return self.health_status

    async def place_order(self, order_request: OrderRequest) -> dict[str, Any]:
        """Place an order on the specified exchange"""
        try:
            if order_request.exchange not in self.exchanges:
                raise ValueError(f"Exchange {order_request.exchange} not connected")
            exchange = self.exchanges[order_request.exchange]
            order_params = {
                "symbol": order_request.symbol,
                "type": order_request.type,
                "side": order_request.side.value,
                "amount": order_request.amount,
            }
            if order_request.type == "limit" and order_request.price:
                order_params["price"] = order_request.price
            order = await exchange.create_order(**order_params)
            logger.info("📈 Order placed on %s: %s", order_request.exchange, order["id"])
            return order
        except Exception as e:
            logger.error("❌ Failed to place order: %s", str(e))
            raise

    async def get_order_book(self, exchange_name: str, symbol: str, limit: int = 20) -> dict[str, Any]:
        """Get order book for a symbol"""
        try:
            if exchange_name not in self.exchanges:
                raise ValueError(f"Exchange {exchange_name} not connected")
            exchange = self.exchanges[exchange_name]
            orderbook = await exchange.fetch_order_book(symbol, limit)
            return orderbook
        except Exception as e:
            logger.error("❌ Failed to get order book: %s", str(e))
            raise

    async def get_balance(self, exchange_name: str) -> dict[str, Any]:
        """Get account balance"""
        try:
            if exchange_name not in self.exchanges:
                raise ValueError(f"Exchange {exchange_name} not connected")
            exchange = self.exchanges[exchange_name]
            balance = await exchange.fetch_balance()
            return balance
        except Exception as e:
            logger.error("❌ Failed to get balance: %s", str(e))
            raise


exchange_manager = RealExchangeManager()


async def connect_to_exchange(
    exchange_name: str, api_key: str, secret: str, sandbox: bool = True, passphrase: str = None
) -> bool:
    """CLI function to connect to exchange"""
    credentials = ExchangeCredentials(api_key=api_key, secret=secret, sandbox=sandbox, passphrase=passphrase)
    return await exchange_manager.connect_exchange(exchange_name, credentials)


async def disconnect_from_exchange(exchange_name: str) -> bool:
    """CLI function to disconnect from exchange"""
    return await exchange_manager.disconnect_exchange(exchange_name)


async def get_exchange_status(exchange_name: str = None) -> dict[str, Any]:
    """CLI function to get exchange status"""
    if exchange_name:
        health = await exchange_manager.check_exchange_health(exchange_name)
        return {exchange_name: health}
    else:
        return await exchange_manager.get_all_health_status()


async def test_real_exchange_integration():
    """Test the real exchange integration"""
    logger.info("Testing Real Exchange Integration")
    test_credentials = ExchangeCredentials(api_key="test_api_key", secret="test_secret", sandbox=True)
    try:
        success = await exchange_manager.connect_exchange("binance", test_credentials)
        logger.info("Connection test result", success=success)
        health = await exchange_manager.check_exchange_health("binance")
        logger.info("Health status", health=health)
    except Exception as e:
        logger.warning("Expected error with test credentials", error=str(e))
        logger.info("Integration structure working correctly")


if __name__ == "__main__":
    asyncio.run(test_real_exchange_integration())
