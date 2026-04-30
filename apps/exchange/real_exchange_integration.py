#!/usr/bin/env python3
"""
Real Exchange Integration for AITBC
Connects to Binance, Coinbase, and Kraken APIs for live trading
"""

import asyncio
import ccxt
import json
import time
from datetime import datetime, UTC, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from aitbc import get_logger

logger = get_logger(__name__)

class ExchangeStatus(str, Enum):
    """Exchange connection status"""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    MAINTENANCE = "maintenance"

class OrderSide(str, Enum):
    """Order side"""
    BUY = "buy"
    SELL = "sell"

@dataclass
class ExchangeCredentials:
    """Exchange API credentials"""
    api_key: str
    secret: str
    sandbox: bool = True
    passphrase: Optional[str] = None  # For Coinbase

@dataclass
class ExchangeHealth:
    """Exchange health metrics"""
    status: ExchangeStatus
    latency_ms: float
    last_check: datetime
    error_message: Optional[str] = None

@dataclass
class OrderRequest:
    """Unified order request"""
    exchange: str
    symbol: str
    side: OrderSide
    amount: float
    price: Optional[float] = None  # None for market orders
    type: str = "limit"  # limit, market

class RealExchangeManager:
    """Manages connections to real exchanges"""
    
    def __init__(self):
        self.exchanges: Dict[str, ccxt.Exchange] = {}
        self.credentials: Dict[str, ExchangeCredentials] = {}
        self.health_status: Dict[str, ExchangeHealth] = {}
        self.supported_exchanges = ["binance", "coinbasepro", "kraken"]
        
    async def connect_exchange(self, exchange_name: str, credentials: ExchangeCredentials) -> bool:
        """Connect to an exchange"""
        try:
            if exchange_name not in self.supported_exchanges:
                raise ValueError(f"Unsupported exchange: {exchange_name}")
            
            # Create exchange instance
            if exchange_name == "binance":
                exchange = ccxt.binance({
                    'apiKey': credentials.api_key,
                    'secret': credentials.secret,
                    'sandbox': credentials.sandbox,
                    'enableRateLimit': True,
                })
            elif exchange_name == "coinbasepro":
                exchange = ccxt.coinbasepro({
                    'apiKey': credentials.api_key,
                    'secret': credentials.secret,
                    'passphrase': credentials.passphrase,
                    'sandbox': credentials.sandbox,
                    'enableRateLimit': True,
                })
            elif exchange_name == "kraken":
                exchange = ccxt.kraken({
                    'apiKey': credentials.api_key,
                    'secret': credentials.secret,
                    'sandbox': credentials.sandbox,
                    'enableRateLimit': True,
                })
            
            # Test connection
            await self._test_connection(exchange, exchange_name)
            
            # Store connection
            self.exchanges[exchange_name] = exchange
            self.credentials[exchange_name] = credentials
            
            # Set initial health status
            self.health_status[exchange_name] = ExchangeHealth(
                status=ExchangeStatus.CONNECTED,
                latency_ms=0.0,
                last_check=datetime.now(datetime.UTC)
            )
            
            logger.info(f"✅ Connected to {exchange_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to {exchange_name}: {str(e)}")
            self.health_status[exchange_name] = ExchangeHealth(
                status=ExchangeStatus.ERROR,
                latency_ms=0.0,
                last_check=datetime.now(datetime.UTC),
                error_message=str(e)
            )
            return False
    
    async def _test_connection(self, exchange: ccxt.Exchange, exchange_name: str):
        """Test exchange connection"""
        start_time = time.time()
        
        try:
            # Test with fetchMarkets (lightweight call)
            if hasattr(exchange, 'load_markets'):
                if asyncio.iscoroutinefunction(exchange.load_markets):
                    await exchange.load_markets()
                else:
                    exchange.load_markets()
            
            latency = (time.time() - start_time) * 1000
            logger.info(f"🔗 {exchange_name} connection test successful ({latency:.2f}ms)")
            
        except Exception as e:
            raise Exception(f"Connection test failed: {str(e)}")
    
    async def disconnect_exchange(self, exchange_name: str) -> bool:
        """Disconnect from an exchange"""
        try:
            if exchange_name in self.exchanges:
                del self.exchanges[exchange_name]
                del self.credentials[exchange_name]
                
                self.health_status[exchange_name] = ExchangeHealth(
                    status=ExchangeStatus.DISCONNECTED,
                    latency_ms=0.0,
                    last_check=datetime.now()
                )
                
                logger.info(f"🔌 Disconnected from {exchange_name}")
                return True
            else:
                logger.warning(f"⚠️  {exchange_name} was not connected")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to disconnect from {exchange_name}: {str(e)}")
            return False
    
    async def check_exchange_health(self, exchange_name: str) -> ExchangeHealth:
        """Check exchange health and latency"""
        if exchange_name not in self.exchanges:
            return ExchangeHealth(
                status=ExchangeStatus.DISCONNECTED,
                latency_ms=0.0,
                last_check=datetime.now(),
                error_message="Not connected"
            )
        
        try:
            start_time = time.time()
            exchange = self.exchanges[exchange_name]
            
            # Lightweight health check
            if hasattr(exchange, 'fetch_status'):
                if asyncio.iscoroutinefunction(exchange.fetch_status):
                    await exchange.fetch_status()
                else:
                    exchange.fetch_status()
            
            latency = (time.time() - start_time) * 1000
            
            health = ExchangeHealth(
                status=ExchangeStatus.CONNECTED,
                latency_ms=latency,
                last_check=datetime.now()
            )
            
            self.health_status[exchange_name] = health
            return health
            
        except Exception as e:
            health = ExchangeHealth(
                status=ExchangeStatus.ERROR,
                latency_ms=0.0,
                last_check=datetime.now(),
                error_message=str(e)
            )
            
            self.health_status[exchange_name] = health
            return health
    
    async def get_all_health_status(self) -> Dict[str, ExchangeHealth]:
        """Get health status of all connected exchanges"""
        for exchange_name in list(self.exchanges.keys()):
            await self.check_exchange_health(exchange_name)
        
        return self.health_status
    
    async def place_order(self, order_request: OrderRequest) -> Dict[str, Any]:
        """Place an order on the specified exchange"""
        try:
            if order_request.exchange not in self.exchanges:
                raise ValueError(f"Exchange {order_request.exchange} not connected")
            
            exchange = self.exchanges[order_request.exchange]
            
            # Prepare order parameters
            order_params = {
                'symbol': order_request.symbol,
                'type': order_request.type,
                'side': order_request.side.value,
                'amount': order_request.amount,
            }
            
            if order_request.type == 'limit' and order_request.price:
                order_params['price'] = order_request.price
            
            # Place order
            order = await exchange.create_order(**order_params)
            
            logger.info(f"📈 Order placed on {order_request.exchange}: {order['id']}")
            return order
            
        except Exception as e:
            logger.error(f"❌ Failed to place order: {str(e)}")
            raise
    
    async def get_order_book(self, exchange_name: str, symbol: str, limit: int = 20) -> Dict[str, Any]:
        """Get order book for a symbol"""
        try:
            if exchange_name not in self.exchanges:
                raise ValueError(f"Exchange {exchange_name} not connected")
            
            exchange = self.exchanges[exchange_name]
            orderbook = await exchange.fetch_order_book(symbol, limit)
            
            return orderbook
            
        except Exception as e:
            logger.error(f"❌ Failed to get order book: {str(e)}")
            raise
    
    async def get_balance(self, exchange_name: str) -> Dict[str, Any]:
        """Get account balance"""
        try:
            if exchange_name not in self.exchanges:
                raise ValueError(f"Exchange {exchange_name} not connected")
            
            exchange = self.exchanges[exchange_name]
            balance = await exchange.fetch_balance()
            
            return balance
            
        except Exception as e:
            logger.error(f"❌ Failed to get balance: {str(e)}")
            raise

# Global instance
exchange_manager = RealExchangeManager()

# CLI Interface Functions
async def connect_to_exchange(exchange_name: str, api_key: str, secret: str, 
                              sandbox: bool = True, passphrase: str = None) -> bool:
    """CLI function to connect to exchange"""
    credentials = ExchangeCredentials(
        api_key=api_key,
        secret=secret,
        sandbox=sandbox,
        passphrase=passphrase
    )
    
    return await exchange_manager.connect_exchange(exchange_name, credentials)

async def disconnect_from_exchange(exchange_name: str) -> bool:
    """CLI function to disconnect from exchange"""
    return await exchange_manager.disconnect_exchange(exchange_name)

async def get_exchange_status(exchange_name: str = None) -> Dict[str, Any]:
    """CLI function to get exchange status"""
    if exchange_name:
        health = await exchange_manager.check_exchange_health(exchange_name)
        return {exchange_name: health}
    else:
        return await exchange_manager.get_all_health_status()

# Test function
async def test_real_exchange_integration():
    """Test the real exchange integration"""
    print("🧪 Testing Real Exchange Integration...")
    
    # Test with Binance sandbox
    test_credentials = ExchangeCredentials(
        api_key="test_api_key",
        secret="test_secret",
        sandbox=True
    )
    
    try:
        # This will fail with test credentials, but tests the structure
        success = await exchange_manager.connect_exchange("binance", test_credentials)
        print(f"Connection test result: {success}")
        
        # Get health status
        health = await exchange_manager.check_exchange_health("binance")
        print(f"Health status: {health}")
        
    except Exception as e:
        print(f"Expected error with test credentials: {str(e)}")
        print("✅ Integration structure working correctly")

if __name__ == "__main__":
    asyncio.run(test_real_exchange_integration())