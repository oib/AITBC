"""Tests for aitbc.oracles.price_oracle"""

import os
from unittest.mock import patch

from aitbc.oracles.price_oracle import (
    ChainlinkOracle,
    CoinGeckoOracle,
    PriceOracle,
    PriceResult,
    get_price_oracle,
)


class TestPriceResult:
    def test_creation(self):
        pr = PriceResult(base="ETH", quote="USD", price=3000.0, source="test")
        assert pr.base == "ETH"
        assert pr.price == 3000.0

    def test_age_seconds(self):
        pr = PriceResult(base="ETH", quote="USD", price=3000.0, source="test")
        assert pr.age_seconds() >= 0


class TestChainlinkOracle:
    def test_get_price_unknown_pair(self):
        oracle = ChainlinkOracle()
        result = oracle.get_price("UNKNOWN", "USD")
        assert result is None

    def test_get_price_no_client(self):
        oracle = ChainlinkOracle()
        with patch("aitbc.ethereum_rpc.get_ethereum_client", side_effect=Exception("no client")):
            result = oracle.get_price("ETH", "USD")
        assert result is None


class TestCoinGeckoOracle:
    def test_get_price_unknown_coin(self):
        oracle = CoinGeckoOracle()
        result = oracle.get_price("UNKNOWN", "USD")
        assert result is None

    def test_get_price_network_error(self):
        oracle = CoinGeckoOracle()
        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            result = oracle.get_price("ETH", "USD")
        assert result is None

    def test_cache_hit(self):
        oracle = CoinGeckoOracle()
        pr = PriceResult(base="ETH", quote="USD", price=3000.0, source="test")
        oracle._cache["ETH/USD"] = pr
        result = oracle.get_price("ETH", "USD")
        assert result is pr


class TestPriceOracle:
    def test_get_price_fixed_ait(self):
        oracle = PriceOracle()
        with patch.dict(os.environ, {"AIT_USD_FIXED_PRICE": "1.5"}):
            result = oracle.get_price("AIT", "USD")
        assert result is not None
        assert result.price == 1.5
        assert result.source == "fixed"

    def test_get_price_invalid_fixed_ait(self):
        oracle = PriceOracle()
        with patch.dict(os.environ, {"AIT_USD_FIXED_PRICE": "invalid"}):
            result = oracle.get_price("AIT", "USD")
        assert result is None

    def test_get_price_chainlink_fallback(self):
        oracle = PriceOracle()
        with patch.object(oracle._chainlink, "get_price", return_value=None):
            with patch.object(oracle._coingecko, "get_price", return_value=None):
                result = oracle.get_price("ETH", "USD")
        assert result is None

    def test_get_price_or_raise_success(self):
        oracle = PriceOracle()
        pr = PriceResult(base="ETH", quote="USD", price=3000.0, source="test")
        with patch.object(oracle, "get_price", return_value=pr):
            result = oracle.get_price_or_raise("ETH", "USD")
        assert result == pr

    def test_get_ait_price(self):
        oracle = PriceOracle()
        pr = PriceResult(base="AIT", quote="USD", price=1.0, source="test")
        with patch.object(oracle._coingecko, "get_price", return_value=pr):
            result = oracle.get_ait_price()
        assert result == 1.0

    def test_get_ait_price_none(self):
        oracle = PriceOracle()
        with patch.object(oracle._coingecko, "get_price", return_value=None):
            result = oracle.get_ait_price()
        assert result is None

    def test_health_check(self):
        oracle = PriceOracle()
        with patch.object(oracle._coingecko, "get_price", return_value=None):
            with patch.object(oracle._chainlink, "get_price", return_value=None):
                result = oracle.health_check()
        assert result["coingecko"]["status"] == "unavailable"
        assert "unavailable" in result["chainlink"]["status"]


class TestSingleton:
    def test_get_price_oracle(self):
        o1 = get_price_oracle()
        o2 = get_price_oracle()
        assert o1 is o2
