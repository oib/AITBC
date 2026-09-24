"""Tests for aitbc.oracles.price_oracle"""

import os
from decimal import Decimal
from unittest.mock import patch

from aitbc.oracles.price_oracle import (
    AIT_REFERENCE_PRICE_EUR,
    ChainlinkOracle,
    CoinGeckoOracle,
    PriceOracle,
    PriceResult,
    get_price_oracle,
)


class TestPriceResult:
    def test_creation(self):
        pr = PriceResult(base="ETH", quote="USD", price=Decimal("3000"), source="test")
        assert pr.base == "ETH"
        assert pr.price == Decimal("3000")

    def test_age_seconds(self):
        pr = PriceResult(base="ETH", quote="USD", price=Decimal("3000"), source="test")
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

    def test_cache_hit(self):
        oracle = CoinGeckoOracle()
        pr = PriceResult(base="ETH", quote="USD", price=Decimal("3000"), source="test")
        oracle._cache["ETH/USD"] = pr
        result = oracle.get_price("ETH", "USD")
        assert result is pr


class TestPriceOracle:
    def test_get_price_fixed_ait(self):
        oracle = PriceOracle()
        with patch.dict(os.environ, {"AIT_USD_FIXED_PRICE": "1.5"}):
            result = oracle.get_price("AIT", "USD")
        assert result is not None
        assert result.price == Decimal("1.5")
        assert result.source == "fixed"

    def test_get_price_invalid_fixed_ait(self):
        oracle = PriceOracle()
        with patch.dict(os.environ, {"AIT_USD_FIXED_PRICE": "invalid"}):
            result = oracle.get_price("AIT", "USD")
        assert result is None

    def test_get_price_ait_reference_default_eur(self):
        oracle = PriceOracle()
        with patch.dict(os.environ) as env:
            env.pop("AIT_EUR_FIXED_PRICE", None)
            env.pop("AIT_USD_FIXED_PRICE", None)
            result = oracle.get_price("AIT", "EUR")
        assert result is not None
        assert result.price == AIT_REFERENCE_PRICE_EUR
        assert result.source == "reference"

    def test_get_price_ait_reference_derives_usd(self):
        oracle = PriceOracle()
        eth_usd = PriceResult(base="ETH", quote="USD", price=Decimal("2600"), source="test")
        eth_eur = PriceResult(base="ETH", quote="EUR", price=Decimal("2400"), source="test")
        with patch.dict(os.environ) as env:
            env.pop("AIT_EUR_FIXED_PRICE", None)
            env.pop("AIT_USD_FIXED_PRICE", None)
            with patch.object(oracle._coingecko, "get_price", side_effect=[eth_usd, eth_eur]):
                result = oracle.get_price("AIT", "USD")
        assert result is not None
        assert result.price == Decimal("0.25") * Decimal("2600") / Decimal("2400")
        assert result.source == "derived"

    def test_get_price_ait_reference_derives_eth(self):
        oracle = PriceOracle()
        eth_usd = PriceResult(base="ETH", quote="USD", price=Decimal("2600"), source="test")
        eth_eur = PriceResult(base="ETH", quote="EUR", price=Decimal("2400"), source="test")
        with patch.dict(os.environ) as env:
            env.pop("AIT_EUR_FIXED_PRICE", None)
            env.pop("AIT_USD_FIXED_PRICE", None)
            with patch.object(oracle._coingecko, "get_price", side_effect=[eth_usd, eth_eur]):
                result = oracle.get_price("AIT", "ETH")
        assert result is not None
        assert result.price == Decimal("0.25") / Decimal("2400")
        assert result.source == "derived"

    def test_get_price_ait_reference_eth_oracle_down(self):
        oracle = PriceOracle()
        with patch.dict(os.environ) as env:
            env.pop("AIT_EUR_FIXED_PRICE", None)
            env.pop("AIT_USD_FIXED_PRICE", None)
            with patch.object(oracle._coingecko, "get_price", return_value=None):
                with patch.object(oracle._chainlink, "get_price", return_value=None):
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
        pr = PriceResult(base="ETH", quote="USD", price=Decimal("3000"), source="test")
        with patch.object(oracle, "get_price", return_value=pr):
            result = oracle.get_price_or_raise("ETH", "USD")
        assert result == pr

    def test_get_ait_price(self):
        oracle = PriceOracle()
        pr = PriceResult(base="AIT", quote="USD", price=Decimal("1"), source="test")
        with patch.object(oracle._coingecko, "get_price", return_value=pr):
            result = oracle.get_ait_price()
        assert result == Decimal("1")

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


def test_disk_cache_tolerates_non_utf8_file(tmp_path, monkeypatch):
    """A corrupt (e.g. compressed/encrypted) cache file must not kill the price path."""
    from aitbc.oracles.price_oracle import CoinGeckoOracle

    cache_file = tmp_path / "price_cache.json"
    cache_file.write_bytes(b"\x28\xb5\x2f\xfd\x60\x40")  # zstd magic, not JSON

    oracle = CoinGeckoOracle()
    monkeypatch.setattr(CoinGeckoOracle, "_disk_cache_path", str(cache_file))
    assert oracle._read_disk_cache() == {}
