"""Coverage for oracle_service (#1289 residual).

AggregatedPriceFeed / ChainlinkAdapter / OracleService on in-memory
state — no network. Strict xfails pin the dead-fetch defects minted as
#1361: the CoinGecko fallback references a nonexistent ``self._client``
(AttributeError swallowed by the broad except), and ChainlinkAdapter's
enabled path contains no RPC call at all — it returns None unconditionally.
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
async def test_stale_price_falls_back_to_last_known():
    feed = AggregatedPriceFeed()
    feed.set_manual_price("ETH/USD", Decimal("3000"))
    # Force staleness: last_update far in the past -> _fetch_price runs,
    # fails (no network/client), and the last known price is still returned.
    feed._last_update["ETH/USD"] = feed._last_update["ETH/USD"].replace(year=2020)
    price = await feed.get_price("ETH/USD", max_age_seconds=1)
    assert price is not None
    assert price.price == Decimal("3000")


@pytest.mark.asyncio
async def test_oracle_service_get_and_set_price():
    svc = OracleService()
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
# Strict xfails — dead-fetch defects (#1361)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="#1361: AggregatedPriceFeed._fetch_from_api uses self._client which is never defined — CoinGecko fallback always AttributeErrors",
)
def test_feed_has_http_client_for_api_fallback():
    feed = AggregatedPriceFeed()
    assert getattr(feed, "_client", None) is not None


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True, reason="#1361: ChainlinkAdapter.get_price returns None without any RPC call even when enabled=True"
)
async def test_chainlink_enabled_attempts_rpc():
    adapter = ChainlinkAdapter(enabled=True)
    adapter._client = type("FakeClient", (), {})()
    adapter._client.get = AsyncMock(return_value=None)
    adapter._client.post = AsyncMock(return_value=None)
    await adapter.get_price("ETH/USD")
    assert adapter._client.get.called or adapter._client.post.called
