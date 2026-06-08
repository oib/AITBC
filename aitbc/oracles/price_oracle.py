"""
Price feed oracle for AITBC bridge operations.

Priority order:
  1. Chainlink on-chain feeds (requires ETH_RPC_URL)
  2. CoinGecko REST API (public, no key required - fallback)

Usage:
    oracle = get_price_oracle()
    price = oracle.get_price("ETH", "USD")
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

from aitbc import get_logger

logger = get_logger(__name__)

# ── Chainlink feed addresses (Ethereum mainnet) ───────────────────────────────
CHAINLINK_FEEDS_MAINNET: dict[str, str] = {
    "ETH/USD":  "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419",
    "BTC/USD":  "0xF4030086522a5bEEa4988F8cA5B36dbC97BeE88c",
    "LINK/USD": "0x2c1d072e956AFFC0D435Cb7AC308d97936Ed4a28",
    "USDT/USD": "0x3E7d1eAB13ad0104d2750B8863b489D65364e32D",
}

# Chainlink AggregatorV3Interface ABI (minimal — latestRoundData only)
_CHAINLINK_ABI = [
    {
        "inputs": [],
        "name": "latestRoundData",
        "outputs": [
            {"name": "roundId", "type": "uint80"},
            {"name": "answer", "type": "int256"},
            {"name": "startedAt", "type": "uint256"},
            {"name": "updatedAt", "type": "uint256"},
            {"name": "answeredInRound", "type": "uint80"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# CoinGecko coin ID mapping
_COINGECKO_IDS: dict[str, str] = {
    "ETH":  "ethereum",
    "BTC":  "bitcoin",
    "LINK": "chainlink",
    "USDT": "tether",
    "USDC": "usd-coin",
    "BNB":  "binancecoin",
    "AIT":  "aitbc",
}

_COINGECKO_BASE = "https://api.coingecko.com/api/v3"


@dataclass
class PriceResult:
    base: str
    quote: str
    price: float
    source: str
    timestamp: float = field(default_factory=time.time)
    raw: dict[str, Any] = field(default_factory=dict)

    def age_seconds(self) -> float:
        return time.time() - self.timestamp


class ChainlinkOracle:
    """Reads prices from Chainlink on-chain aggregators."""

    def __init__(self, feeds: dict[str, str] | None = None):
        self.feeds = feeds or CHAINLINK_FEEDS_MAINNET

    def get_price(self, base: str, quote: str = "USD") -> PriceResult | None:
        pair = f"{base}/{quote}"
        feed_addr = self.feeds.get(pair)
        if not feed_addr:
            logger.debug("No Chainlink feed for pair: %s", pair)
            return None
        try:
            from aitbc.ethereum_rpc import get_ethereum_client
            client = get_ethereum_client()
            decimals = client.call_contract(feed_addr, _CHAINLINK_ABI, "decimals")
            round_data = client.call_contract(feed_addr, _CHAINLINK_ABI, "latestRoundData")
            answer = round_data[1]
            updated_at = round_data[3]
            price = answer / (10 ** decimals)
            return PriceResult(
                base=base,
                quote=quote,
                price=price,
                source="chainlink",
                timestamp=float(updated_at),
                raw={"feed": feed_addr, "round_id": round_data[0], "answer": answer},
            )
        except Exception as e:
            logger.debug("Chainlink price fetch failed for %s: %s", pair, e)
            return None


class CoinGeckoOracle:
    """Reads prices from CoinGecko public REST API (no key required)."""

    _cache: dict[str, PriceResult] = {}
    _cache_ttl: int = 60  # seconds

    def get_price(self, base: str, quote: str = "USD") -> PriceResult | None:
        cache_key = f"{base}/{quote}"
        cached = self._cache.get(cache_key)
        if cached and cached.age_seconds() < self._cache_ttl:
            return cached

        coin_id = _COINGECKO_IDS.get(base.upper())
        if not coin_id:
            logger.debug("No CoinGecko ID for token: %s", base)
            return None

        vs_currency = quote.lower()
        try:
            import urllib.request
            import json
            url = f"{_COINGECKO_BASE}/simple/price?ids={coin_id}&vs_currencies={vs_currency}&include_last_updated_at=true"
            req = urllib.request.Request(url, headers={"User-Agent": "aitbc-oracle/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            if coin_id not in data:
                return None

            entry = data[coin_id]
            price = entry.get(vs_currency)
            if price is None:
                return None

            result = PriceResult(
                base=base.upper(),
                quote=quote.upper(),
                price=float(price),
                source="coingecko",
                timestamp=float(entry.get("last_updated_at", time.time())),
                raw=entry,
            )
            self._cache[cache_key] = result
            return result
        except Exception as e:
            logger.warning("CoinGecko price fetch failed for %s: %s", cache_key, e)
            return None


class PriceOracle:
    """
    Composite price oracle with automatic source fallback.
    Priority: Chainlink → CoinGecko
    """

    def __init__(self):
        self._chainlink = ChainlinkOracle()
        self._coingecko = CoinGeckoOracle()

    def get_price(self, base: str, quote: str = "USD") -> PriceResult | None:
        """Get price, trying Chainlink first then CoinGecko."""
        # Special case: AIT/USD fixed price from environment
        if base.upper() == "AIT" and quote.upper() == "USD":
            fixed_price = os.getenv("AIT_USD_FIXED_PRICE")
            if fixed_price:
                try:
                    price = float(fixed_price)
                    logger.debug("Using fixed AIT/USD price: %s", price)
                    return PriceResult(base, quote, price, "fixed", time.time(), {"source": "fixed_price"})
                except ValueError:
                    logger.warning("Invalid AIT_USD_FIXED_PRICE: %s", fixed_price)
        
        result = self._chainlink.get_price(base, quote)
        if result is not None:
            logger.debug("Price from Chainlink %s/%s: %s", base, quote, result.price)
            return result

        result = self._coingecko.get_price(base, quote)
        if result is not None:
            logger.debug("Price from CoinGecko %s/%s: %s", base, quote, result.price)
            return result

        logger.warning("No price available for pair: %s/%s", base, quote)
        return None

    def get_price_or_raise(self, base: str, quote: str = "USD") -> PriceResult:
        result = self.get_price(base, quote)
        if result is None:
            raise ValueError(f"No price feed available for {base}/{quote}")
        return result

    def get_ait_price(self) -> float | None:
        """Get AIT/USD price (CoinGecko only — not on Chainlink mainnet feeds)."""
        result = self._coingecko.get_price("AIT", "USD")
        return result.price if result else None

    def health_check(self) -> dict[str, Any]:
        """Return status of each oracle source."""
        eth_cg = self._coingecko.get_price("ETH", "USD")
        eth_cl = self._chainlink.get_price("ETH", "USD")
        return {
            "coingecko": {
                "status": "ok" if eth_cg else "unavailable",
                "eth_usd": eth_cg.price if eth_cg else None,
                "source": "coingecko",
            },
            "chainlink": {
                "status": "ok" if eth_cl else "unavailable (needs ETH_RPC_URL)",
                "eth_usd": eth_cl.price if eth_cl else None,
                "source": "chainlink",
            },
        }


# Global singleton
_oracle: PriceOracle | None = None


def get_price_oracle() -> PriceOracle:
    global _oracle
    if _oracle is None:
        _oracle = PriceOracle()
    return _oracle
