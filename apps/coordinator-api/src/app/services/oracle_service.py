"""
Oracle Service - Real-time price feed aggregation

Provides price data from multiple sources:
- Chainlink Price Feeds (mainnet/testnet)
- Aggregated market data
- Manual price updates (admin)
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

import httpx
from aitbc.aitbc_logging import get_logger


logger = get_logger(__name__)


class PriceSource(Enum):
    """Sources of price data"""
    chainlink = "chainlink"
    aggregated = "aggregated"
    manual = "manual"
    cached = "cached"


@dataclass
class PriceData:
    """Price data point"""
    pair: str
    price: float
    source: PriceSource
    timestamp: datetime
    confidence: float
    round_id: Optional[int] = None
    block_number: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pair": self.pair,
            "price": self.price,
            "source": self.source.value,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
            "round_id": self.round_id,
            "block_number": self.block_number
        }


class ChainlinkAdapter:
    """
    Chainlink Price Feed adapter.
    
    Fetches prices from Chainlink oracles on Ethereum
    or other supported networks.
    """
    
    # Chainlink price feed addresses (Ethereum mainnet)
    PRICE_FEEDS = {
        "ETH/USD": "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419",
        "BTC/USD": "0xF4030086522a5bEEa4988F8cA5B36dbC97BeE88c",
        "LINK/USD": "0x2c1d072e956AFFC0D435Cb7AC38EF18d24d9127c",
        "DAI/USD": "0xAed0c38402a5d7df9586C690b38Fc32549649B6F",
        "USDC/USD": "0x8fFfFfd4AfB6115b954Bd326cbe7B4BA576818f6",
        "USDT/USD": "0x3E7d1eAB13ad0104d2750B8863b489D65364e32D",
        "AITBC/USD": None,  # Custom feed
    }
    
    # Chainlink ABI for latestRoundData
    ABI = [
        {
            "inputs": [],
            "name": "latestRoundData",
            "outputs": [
                {"internalType": "uint80", "name": "roundId", "type": "uint80"},
                {"internalType": "int256", "name": "answer", "type": "int256"},
                {"internalType": "uint256", "name": "startedAt", "type": "uint256"},
                {"internalType": "uint256", "name": "updatedAt", "type": "uint256"},
                {"internalType": "uint80", "name": "answeredInRound", "type": "uint80"}
            ],
            "stateMutability": "view",
            "type": "function"
        }
    ]
    
    def __init__(
        self,
        rpc_url: str = "https://ethereum-rpc.publicnode.com",
        enabled: bool = False
    ):
        self.rpc_url = rpc_url
        self.enabled = enabled
        self._client = httpx.AsyncClient(timeout=30.0)
        self._decimals = 8  # Chainlink feeds typically have 8 decimals
    
    async def get_price(self, pair: str) -> Optional[PriceData]:
        """Fetch price from Chainlink oracle"""
        if not self.enabled:
            return None
        
        feed_address = self.PRICE_FEEDS.get(pair)
        if not feed_address:
            logger.debug(f"No Chainlink feed for {pair}")
            return None
        
        try:
            # Call latestRoundData via eth_call
            # In production, use web3.py for full contract interaction
            
            # For now, simulate with HTTP call structure
            # Real implementation would use web3.eth.call()
            
            logger.debug(f"Fetching Chainlink price for {pair}")
            
            # Simplified: return None to indicate not available
            # Full implementation requires web3 library
            return None
            
        except Exception as e:
            logger.warning(f"Chainlink fetch failed for {pair}: {e}")
            return None
    
    async def get_all_prices(self) -> Dict[str, PriceData]:
        """Fetch all available prices from Chainlink"""
        if not self.enabled:
            return {}
        
        results = {}
        for pair in self.PRICE_FEEDS:
            price = await self.get_price(pair)
            if price:
                results[pair] = price
        
        return results


class AggregatedPriceFeed:
    """
    Aggregated price feed from multiple sources.
    
    Combines data from:
    - Chainlink (primary)
    - External APIs (CoinGecko, CoinMarketCap)
    - Local database
    """
    
    def __init__(self, session = None):
        self.chainlink = ChainlinkAdapter(enabled=False)  # Disabled by default
        self._prices: Dict[str, PriceData] = {}
        self._last_update: Dict[str, datetime] = {}
        self._update_interval = 300  # 5 minutes
        self._lock = asyncio.Lock()
        self.session = session
    
    async def get_price(
        self,
        pair: str,
        max_age_seconds: int = 300
    ) -> Optional[PriceData]:
        """
        Get price for a trading pair.
        
        Args:
            pair: Trading pair (e.g., "BTC/USD")
            max_age_seconds: Maximum age of cached price
        
        Returns:
            PriceData or None if not available
        """
        async with self._lock:
            # Check if cached price is fresh enough
            last_update = self._last_update.get(pair)
            if last_update:
                age = (datetime.now(timezone.utc) - last_update).total_seconds()
                if age < max_age_seconds:
                    return self._prices.get(pair)
            
            # Try to fetch fresh price
            price = await self._fetch_price(pair)
            if price:
                self._prices[pair] = price
                self._last_update[pair] = price.timestamp
                return price
            
            # Return cached price even if stale
            return self._prices.get(pair)
    
    async def get_all_prices(self) -> Dict[str, PriceData]:
        """Get all available prices"""
        # Update all prices
        pairs = ["BTC/USD", "ETH/USD", "LINK/USD", "USDC/USD", "AITBC/USD"]
        
        for pair in pairs:
            await self.get_price(pair)
        
        return dict(self._prices)
    
    async def _fetch_price(self, pair: str) -> Optional[PriceData]:
        """Fetch price from all sources"""
        # Try Chainlink first
        price = await self.chainlink.get_price(pair)
        if price:
            return price
        
        # Try external APIs
        price = await self._fetch_from_api(pair)
        if price:
            return price
        
        return None
    
    async def _fetch_from_api(self, pair: str) -> Optional[PriceData]:
        """Fetch price from external API (CoinGecko)"""
        try:
            # Map pair to CoinGecko ID
            coin_map = {
                "BTC/USD": "bitcoin",
                "ETH/USD": "ethereum",
                "LINK/USD": "chainlink",
                "USDC/USD": "usd-coin",
                "USDT/USD": "tether",
                "DAI/USD": "dai"
            }
            
            coin_id = coin_map.get(pair)
            if not coin_id:
                return None
            
            # For production, use CoinGecko API
            # For now, return None (no external dependency)
            logger.debug(f"CoinGecko fetch not implemented for {pair}")
            return None
            
        except Exception as e:
            logger.warning(f"API fetch failed for {pair}: {e}")
            return None
    
    def set_manual_price(
        self,
        pair: str,
        price: float,
        confidence: float = 1.0
    ) -> PriceData:
        """Set a manual price (admin override)"""
        data = PriceData(
            pair=pair,
            price=price,
            source=PriceSource.manual,
            timestamp=datetime.now(timezone.utc),
            confidence=confidence
        )
        
        self._prices[pair] = data
        self._last_update[pair] = data.timestamp
        
        logger.info(f"Manual price set: {pair} = {price}")
        return data


class OracleService:
    """
    Oracle service for the AITBC platform.
    
    Provides:
    - Real-time price feeds
    - Price history
    - Admin price setting
    - Multi-source aggregation
    """
    
    def __init__(self):
        self.feed = AggregatedPriceFeed()
        self._subscribers: List[Callable] = []
        self._running = False
        self._update_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start background price updates"""
        if self._running:
            return
        
        self._running = True
        self._update_task = asyncio.create_task(self._update_loop())
        logger.info("Oracle service started")
    
    def stop(self):
        """Stop background updates"""
        self._running = False
        if self._update_task:
            self._update_task.cancel()
        logger.info("Oracle service stopped")
    
    async def _update_loop(self):
        """Background loop for price updates"""
        while self._running:
            try:
                await self.feed.get_all_prices()
                await asyncio.sleep(60)  # Update every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Price update error: {e}")
                await asyncio.sleep(10)
    
    async def get_price(self, pair: str) -> Optional[Dict[str, Any]]:
        """Get current price for a pair"""
        price = await self.feed.get_price(pair)
        if price:
            return price.to_dict()
        return None
    
    async def get_all_prices(self) -> Dict[str, Dict[str, Any]]:
        """Get all available prices"""
        prices = await self.feed.get_all_prices()
        return {pair: data.to_dict() for pair, data in prices.items()}
    
    def set_price(
        self,
        pair: str,
        price: float,
        confidence: float = 1.0,
        source: str = "manual"
    ) -> Dict[str, Any]:
        """Set price manually (admin function)"""
        data = self.feed.set_manual_price(pair, price, confidence)
        
        # Notify subscribers
        for callback in self._subscribers:
            try:
                asyncio.create_task(callback(data))
            except Exception as e:
                logger.warning(f"Price subscriber error: {e}")
        
        return data.to_dict()
    
    def subscribe(self, callback: Callable):
        """Subscribe to price updates"""
        self._subscribers.append(callback)
    
    def unsubscribe(self, callback: Callable):
        """Unsubscribe from price updates"""
        if callback in self._subscribers:
            self._subscribers.remove(callback)


# Global instance
_oracle_service: Optional[OracleService] = None


def get_oracle_service() -> OracleService:
    """Get global oracle service instance"""
    global _oracle_service
    if _oracle_service is None:
        _oracle_service = OracleService()
    return _oracle_service
