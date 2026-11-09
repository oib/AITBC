"""Coverage for oracle_service (#1289 residual).

AggregatedPriceFeed / ChainlinkAdapter / OracleService on in-memory
state — no network. #1361 dead-fetch defects are fixed: the feed owns a
real ``self._client`` for the CoinGecko fallback, and ChainlinkAdapter's
enabled path performs an actual eth_call latestRoundData() RPC.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from coordinator_api.contexts.blockchain.services.oracle_service import (
    AggregatedPriceFeed,
    ChainlinkAdapter,
    OracleService,
    PriceData,
    PriceSource,
)


# ---------------------------------------------------------------------------
# Passing pins
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chainlink_disabled_returns_none():
    adapter = ChainlinkAdapter(enabled=False)
    assert await adapter.get_price("ETH/USD") is None
    assert await adapter.get_all_prices() == {}


@pytest.mark.asyncio
async def test_unmapped_pair_returns_none():
    feed = AggregatedPriceFeed()
    # "FOO/USD" is in no coin_map and has no Chainlink feed -> None, no cache.
    assert await feed.get_price("FOO/USD") is None


@pytest.mark.asyncio
async def test_manual_price_cached_within_max_age():
    feed = AggregatedPriceFeed()
    feed.set_manual_price("ETH/USD", Decimal("3000"), confidence=1.0)
    price = await feed.get_price("ETH/USD", max_age_seconds=300)
    assert price is not None
    assert price.price == Decimal("3000")
    assert price.source == PriceSource.manual


@pytest.mark.asyncio
async def test_stale_price_falls_back_to_last_known(monkeypatch):
    feed = AggregatedPriceFeed()
    feed.set_manual_price("ETH/USD", Decimal("3000"))
    # Force staleness and a failing upstream: last_update far in the past ->
    # _fetch_price runs, both sources return None, last known price returned.
    # (Post-#1361 the CoinGecko fallback is real — mock it to fail so the
    # test stays hermetic instead of depending on network availability.)
    feed._last_update["ETH/USD"] = feed._last_update["ETH/USD"].replace(year=2020)
    monkeypatch.setattr(feed, "_fetch_from_api", AsyncMock(return_value=None))
    price = await feed.get_price("ETH/USD", max_age_seconds=1)
    assert price is not None
    assert price.price == Decimal("3000")


@pytest.mark.asyncio
async def test_oracle_service_get_and_set_price(monkeypatch):
    svc = OracleService()
    # Keep hermetic: the live CoinGecko fallback (post-#1361) would return a
    # real price here; stub it so the empty-state assertion stays meaningful.
    monkeypatch.setattr(svc.feed, "_fetch_from_api", AsyncMock(return_value=None))
    assert await svc.get_price("ETH/USD") is None
    data = await svc.set_price("ETH/USD", Decimal("3000"), confidence=0.9)
    assert data["pair"] == "ETH/USD"
    assert data["price"] == "3000" or Decimal(str(data["price"])) == Decimal("3000")
    got = await svc.get_price("ETH/USD")
    assert got is not None
    assert got["source"] == "manual"


@pytest.mark.asyncio
async def test_oracle_subscribe_unsubscribe():
    svc = OracleService()
    calls = []

    async def cb(data):
        calls.append(data)

    await svc.subscribe(cb)
    assert cb in svc._subscribers
    await svc.unsubscribe(cb)
    assert cb not in svc._subscribers
    # unsubscribing twice is a no-op, not an error
    await svc.unsubscribe(cb)


@pytest.mark.asyncio
async def test_price_data_to_dict_shape():
    pd = PriceData(
        pair="ETH/USD", price=Decimal("1.5"), source=PriceSource.manual, timestamp=datetime.now(UTC), confidence=1.0
    )
    d = pd.to_dict()
    assert d["pair"] == "ETH/USD"
    assert "price" in d and "source" in d


# ---------------------------------------------------------------------------
# Regression pins — #1361 dead-fetch fixes
# ---------------------------------------------------------------------------


def test_feed_has_http_client_for_api_fallback():
    feed = AggregatedPriceFeed()
    assert getattr(feed, "_client", None) is not None


@pytest.mark.asyncio
async def test_chainlink_enabled_attempts_rpc():
    adapter = ChainlinkAdapter(enabled=True)
    adapter._client = type("FakeClient", (), {})()
    adapter._client.get = AsyncMock(return_value=None)
    adapter._client.post = AsyncMock(return_value=None)
    await adapter.get_price("ETH/USD")
    assert adapter._client.get.called or adapter._client.post.called


@pytest.mark.asyncio
async def test_fetch_from_api_returns_price_on_success():
    """#1361: the CoinGecko fallback actually fetches when the client works."""
    feed = AggregatedPriceFeed()

    class _Resp:
        status_code = 200

        def json(self):
            return {"ethereum": {"usd": 3000.0, "usd_24h_change": 1.2}}

    feed._client.get = AsyncMock(return_value=_Resp())
    price = await feed._fetch_from_api("ETH/USD")
    assert price is not None
    assert price.pair == "ETH/USD"
    assert price.price == Decimal("3000.0")
    assert price.source == PriceSource.aggregated
    feed._client.get.assert_called_once()
