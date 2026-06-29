"""Unit tests for the aitbc.trading offer sync SDK (v0.8.1 §A4).

Covers:
- Offer sync types (OfferSyncStatus, OfferSyncConfig, SyncedOffer,
  OfferDiscoveryRequest, OfferDiscoveryResult, OfferSyncStatusEntry,
  OfferSyncTrigger)
- OfferSyncClient init + async context manager + mocked REST methods
- OfferCache init + get/set/delete/list + staleness detection + sync metadata

No real trading service, Redis, or blockchain node required — all HTTP
calls are stubbed with AsyncMock and RedisCache is mocked.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from aitbc.trading.offer_cache import OfferCache
from aitbc.trading.offer_client import OfferSyncClient
from aitbc.trading.offer_types import (
    OfferDiscoveryRequest,
    OfferDiscoveryResult,
    OfferSyncConfig,
    OfferSyncStatus,
    OfferSyncStatusEntry,
    OfferSyncTrigger,
    SyncedOffer,
)

RPC_URL = "http://localhost:8104"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _mock_response(
    status_code: int = 200,
    json_data: dict | list | None = None,
) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(f"HTTP {status_code}", request=MagicMock(), response=resp)
    return resp


def _sample_synced_offer(
    offer_id: str = "offer_001",
    chain_id: str = "ait-hub",
    last_synced: str | None = None,
    service_type: str = "gpu_marketplace",
) -> SyncedOffer:
    return SyncedOffer(
        offer_id=offer_id,
        chain_id=chain_id,
        provider="provider_1",
        service_type=service_type,
        price=0.05,
        quantity=10,
        status="available",
        attributes={"gpu_model": "A100", "region": "us-east"},
        last_synced=last_synced if last_synced is not None else datetime.now(UTC).isoformat(),
        sync_status="fresh",
        sync_confidence=1.0,
    )


def _sample_discovery_request() -> OfferDiscoveryRequest:
    return OfferDiscoveryRequest(
        source_chain="ait-hub",
        dest_chain="ait-island1",
        service_type="gpu_marketplace",
        min_price=0.01,
        max_price=0.10,
        region="us-east",
        gpu_model="A100",
        limit=50,
        offset=10,
    )


# ---------------------------------------------------------------------------
# OfferSyncStatus enum
# ---------------------------------------------------------------------------


class TestOfferSyncStatus:
    def test_values(self) -> None:
        assert OfferSyncStatus.FRESH == "fresh"
        assert OfferSyncStatus.STALE == "stale"
        assert OfferSyncStatus.SYNCING == "syncing"
        assert OfferSyncStatus.ERROR == "error"

    def test_str_conversion(self) -> None:
        assert str(OfferSyncStatus.FRESH) == "fresh"
        assert str(OfferSyncStatus.STALE) == "stale"

    def test_from_string(self) -> None:
        assert OfferSyncStatus("fresh") == OfferSyncStatus.FRESH
        assert OfferSyncStatus("stale") == OfferSyncStatus.STALE


# ---------------------------------------------------------------------------
# OfferSyncConfig
# ---------------------------------------------------------------------------


class TestOfferSyncConfig:
    def test_defaults(self) -> None:
        cfg = OfferSyncConfig()
        assert cfg.sync_enabled is True
        assert cfg.sync_interval_seconds == 60
        assert cfg.staleness_threshold_seconds == 300
        assert cfg.max_bandwidth_kbps == 100
        assert cfg.cache_ttl_seconds == 300
        assert cfg.per_chain_staleness == {}

    def test_custom_values(self) -> None:
        cfg = OfferSyncConfig(
            sync_enabled=False,
            sync_interval_seconds=120,
            staleness_threshold_seconds=600,
            max_bandwidth_kbps=200,
            cache_ttl_seconds=600,
            per_chain_staleness={"ait-hub": 300, "ait-island1": 1800},
        )
        assert cfg.sync_enabled is False
        assert cfg.sync_interval_seconds == 120
        assert cfg.staleness_threshold_seconds == 600
        assert cfg.per_chain_staleness == {"ait-hub": 300, "ait-island1": 1800}

    def test_get_staleness_for_chain_default(self) -> None:
        cfg = OfferSyncConfig(staleness_threshold_seconds=300)
        assert cfg.get_staleness_for_chain("unknown-chain") == 300

    def test_get_staleness_for_chain_override(self) -> None:
        cfg = OfferSyncConfig(
            staleness_threshold_seconds=300,
            per_chain_staleness={"ait-island1": 1800},
        )
        assert cfg.get_staleness_for_chain("ait-island1") == 1800
        assert cfg.get_staleness_for_chain("ait-hub") == 300


# ---------------------------------------------------------------------------
# SyncedOffer
# ---------------------------------------------------------------------------


class TestSyncedOffer:
    def test_defaults(self) -> None:
        offer = SyncedOffer(
            offer_id="o1",
            chain_id="ait-hub",
            provider="p1",
            service_type="gpu_marketplace",
            price=0.05,
            quantity=10,
            status="available",
        )
        assert offer.attributes == {}
        assert offer.last_synced == ""
        assert offer.sync_status == "fresh"
        assert offer.sync_confidence == 1.0

    def test_to_dict(self) -> None:
        offer = _sample_synced_offer()
        d = offer.to_dict()
        assert d["offer_id"] == "offer_001"
        assert d["chain_id"] == "ait-hub"
        assert d["service_type"] == "gpu_marketplace"
        assert d["price"] == 0.05
        assert d["status"] == "available"
        assert d["sync_status"] == "fresh"
        assert d["sync_confidence"] == 1.0

    def test_from_dict(self) -> None:
        d = {
            "offer_id": "offer_002",
            "chain_id": "ait-island1",
            "provider": "provider_2",
            "service_type": "compute",
            "price": 0.10,
            "quantity": 5,
            "status": "reserved",
            "attributes": {"gpu_model": "H100"},
            "last_synced": "2026-06-29T12:00:00+00:00",
            "sync_status": "stale",
            "sync_confidence": 0.5,
        }
        offer = SyncedOffer.from_dict(d)
        assert offer.offer_id == "offer_002"
        assert offer.chain_id == "ait-island1"
        assert offer.service_type == "compute"
        assert offer.price == 0.10
        assert offer.status == "reserved"
        assert offer.sync_status == "stale"
        assert offer.sync_confidence == 0.5
        assert offer.attributes == {"gpu_model": "H100"}

    def test_from_dict_defaults(self) -> None:
        offer = SyncedOffer.from_dict({"offer_id": "o3", "chain_id": "ait-hub"})
        assert offer.offer_id == "o3"
        assert offer.provider == ""
        assert offer.price == 0.0
        assert offer.quantity == 0
        assert offer.status == "available"
        assert offer.sync_status == "fresh"
        assert offer.sync_confidence == 1.0

    def test_roundtrip(self) -> None:
        offer = _sample_synced_offer()
        d = offer.to_dict()
        restored = SyncedOffer.from_dict(d)
        assert restored.offer_id == offer.offer_id
        assert restored.chain_id == offer.chain_id
        assert restored.price == offer.price
        assert restored.sync_status == offer.sync_status


# ---------------------------------------------------------------------------
# OfferDiscoveryRequest
# ---------------------------------------------------------------------------


class TestOfferDiscoveryRequest:
    def test_defaults(self) -> None:
        req = OfferDiscoveryRequest()
        assert req.source_chain is None
        assert req.dest_chain is None
        assert req.service_type is None
        assert req.min_price is None
        assert req.max_price is None
        assert req.region is None
        assert req.gpu_model is None
        assert req.limit == 100
        assert req.offset == 0

    def test_to_params_minimal(self) -> None:
        req = OfferDiscoveryRequest()
        params = req.to_params()
        assert params == {"limit": 100, "offset": 0}

    def test_to_params_full(self) -> None:
        req = _sample_discovery_request()
        params = req.to_params()
        assert params["source_chain"] == "ait-hub"
        assert params["dest_chain"] == "ait-island1"
        assert params["service_type"] == "gpu_marketplace"
        assert params["min_price"] == 0.01
        assert params["max_price"] == 0.10
        assert params["region"] == "us-east"
        assert params["gpu_model"] == "A100"
        assert params["limit"] == 50
        assert params["offset"] == 10

    def test_to_params_none_excluded(self) -> None:
        req = OfferDiscoveryRequest(service_type="compute")
        params = req.to_params()
        assert "service_type" in params
        assert "source_chain" not in params
        assert "dest_chain" not in params


# ---------------------------------------------------------------------------
# OfferDiscoveryResult
# ---------------------------------------------------------------------------


class TestOfferDiscoveryResult:
    def test_defaults(self) -> None:
        result = OfferDiscoveryResult()
        assert result.offers == []
        assert result.total_count == 0
        assert result.chains_searched == []
        assert result.stale_count == 0
        assert result.sync_triggered is False

    def test_with_offers(self) -> None:
        offers = [_sample_synced_offer("o1"), _sample_synced_offer("o2", "ait-island1")]
        result = OfferDiscoveryResult(
            offers=offers,
            total_count=2,
            chains_searched=["ait-hub", "ait-island1"],
            stale_count=1,
            sync_triggered=True,
        )
        assert len(result.offers) == 2
        assert result.total_count == 2
        assert result.chains_searched == ["ait-hub", "ait-island1"]
        assert result.stale_count == 1
        assert result.sync_triggered is True


# ---------------------------------------------------------------------------
# OfferSyncStatusEntry
# ---------------------------------------------------------------------------


class TestOfferSyncStatusEntry:
    def test_defaults(self) -> None:
        entry = OfferSyncStatusEntry(chain_id="ait-hub")
        assert entry.chain_id == "ait-hub"
        assert entry.last_sync == ""
        assert entry.offer_count == 0
        assert entry.stale_count == 0
        assert entry.error_count == 0
        assert entry.is_syncing is False
        assert entry.last_error == ""

    def test_with_values(self) -> None:
        entry = OfferSyncStatusEntry(
            chain_id="ait-island1",
            last_sync="2026-06-29T12:00:00+00:00",
            offer_count=42,
            stale_count=3,
            error_count=1,
            is_syncing=True,
            last_error="connection timeout",
        )
        assert entry.chain_id == "ait-island1"
        assert entry.offer_count == 42
        assert entry.stale_count == 3
        assert entry.is_syncing is True
        assert entry.last_error == "connection timeout"


# ---------------------------------------------------------------------------
# OfferSyncTrigger
# ---------------------------------------------------------------------------


class TestOfferSyncTrigger:
    def test_defaults(self) -> None:
        trigger = OfferSyncTrigger()
        assert trigger.chain_id is None
        assert trigger.service_type is None
        assert trigger.force is False

    def test_to_dict_defaults(self) -> None:
        trigger = OfferSyncTrigger()
        assert trigger.to_dict() == {"force": False}

    def test_to_dict_with_chain(self) -> None:
        trigger = OfferSyncTrigger(chain_id="ait-hub", force=True)
        d = trigger.to_dict()
        assert d["chain_id"] == "ait-hub"
        assert d["force"] is True

    def test_to_dict_with_service_type(self) -> None:
        trigger = OfferSyncTrigger(service_type="gpu_marketplace")
        d = trigger.to_dict()
        assert d["service_type"] == "gpu_marketplace"
        assert d["force"] is False


# ---------------------------------------------------------------------------
# OfferSyncClient
# ---------------------------------------------------------------------------


class TestOfferSyncClientInit:
    def test_defaults(self) -> None:
        client = OfferSyncClient()
        assert client.rpc_url == "http://localhost:8104"
        assert client._client is None

    def test_custom_url(self) -> None:
        client = OfferSyncClient(rpc_url="http://trading:8104", timeout=60)
        assert client.rpc_url == "http://trading:8104"
        assert client._timeout == 60

    def test_ensure_client_creates_lazy(self) -> None:
        client = OfferSyncClient()
        c = client._ensure_client()
        assert c is not None
        assert client._client is not None


class TestOfferSyncClientAsync:
    async def test_aenter_aexit(self) -> None:
        async with OfferSyncClient() as client:
            assert client._client is not None
        assert client._client is None

    async def test_close(self) -> None:
        client = OfferSyncClient()
        client._ensure_client()
        assert client._client is not None
        await client.close()
        assert client._client is None

    async def test_close_when_not_initialized(self) -> None:
        client = OfferSyncClient()
        await client.close()  # should not raise
        assert client._client is None


class TestOfferSyncClientDiscover:
    async def test_discover_offers_success(self) -> None:
        client = OfferSyncClient()
        mock_resp = _mock_response(
            json_data={
                "offers": [
                    {
                        "offer_id": "o1",
                        "chain_id": "ait-hub",
                        "provider": "p1",
                        "service_type": "gpu_marketplace",
                        "price": 0.05,
                        "quantity": 10,
                        "status": "available",
                    }
                ],
                "total_count": 1,
                "chains_searched": ["ait-hub"],
                "stale_count": 0,
                "sync_triggered": False,
            }
        )
        client._ensure_client = MagicMock()
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        client._ensure_client.return_value = mock_http

        result = await client.discover_offers(OfferDiscoveryRequest())
        assert isinstance(result, OfferDiscoveryResult)
        assert len(result.offers) == 1
        assert result.offers[0].offer_id == "o1"
        assert result.total_count == 1
        assert result.chains_searched == ["ait-hub"]
        assert result.sync_triggered is False

    async def test_discover_offers_empty(self) -> None:
        client = OfferSyncClient()
        mock_resp = _mock_response(json_data={"offers": [], "total_count": 0})
        client._ensure_client = MagicMock()
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        client._ensure_client.return_value = mock_http

        result = await client.discover_offers(OfferDiscoveryRequest())
        assert result.offers == []
        assert result.total_count == 0

    async def test_discover_offers_http_error(self) -> None:
        client = OfferSyncClient()
        mock_resp = _mock_response(status_code=500)
        client._ensure_client = MagicMock()
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        client._ensure_client.return_value = mock_http

        with pytest.raises(httpx.HTTPStatusError):
            await client.discover_offers(OfferDiscoveryRequest())


class TestOfferSyncClientSync:
    async def test_sync_offers_success(self) -> None:
        client = OfferSyncClient()
        mock_resp = _mock_response(json_data={"synced_chains": ["ait-hub"], "offers_synced": 42})
        client._ensure_client = MagicMock()
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        client._ensure_client.return_value = mock_http

        result = await client.sync_offers(OfferSyncTrigger(chain_id="ait-hub"))
        assert result["synced_chains"] == ["ait-hub"]
        assert result["offers_synced"] == 42

    async def test_sync_offers_all_chains(self) -> None:
        client = OfferSyncClient()
        mock_resp = _mock_response(json_data={"synced_chains": ["ait-hub", "ait-island1"], "offers_synced": 100})
        client._ensure_client = MagicMock()
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        client._ensure_client.return_value = mock_http

        result = await client.sync_offers(OfferSyncTrigger())
        assert len(result["synced_chains"]) == 2


class TestOfferSyncClientSyncStatus:
    async def test_get_sync_status_list(self) -> None:
        client = OfferSyncClient()
        mock_resp = _mock_response(
            json_data=[
                {
                    "chain_id": "ait-hub",
                    "last_sync": "2026-06-29T12:00:00+00:00",
                    "offer_count": 42,
                    "stale_count": 3,
                    "error_count": 0,
                    "is_syncing": False,
                    "last_error": "",
                }
            ]
        )
        client._ensure_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_resp)
        client._ensure_client.return_value = mock_http

        entries = await client.get_sync_status()
        assert len(entries) == 1
        assert entries[0].chain_id == "ait-hub"
        assert entries[0].offer_count == 42
        assert entries[0].stale_count == 3

    async def test_get_sync_status_wrapped(self) -> None:
        client = OfferSyncClient()
        mock_resp = _mock_response(
            json_data={
                "chains": [
                    {"chain_id": "ait-island1", "offer_count": 10, "is_syncing": True},
                ]
            }
        )
        client._ensure_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_resp)
        client._ensure_client.return_value = mock_http

        entries = await client.get_sync_status()
        assert len(entries) == 1
        assert entries[0].chain_id == "ait-island1"
        assert entries[0].is_syncing is True

    async def test_get_sync_status_empty(self) -> None:
        client = OfferSyncClient()
        mock_resp = _mock_response(json_data=[])
        client._ensure_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_resp)
        client._ensure_client.return_value = mock_http

        entries = await client.get_sync_status()
        assert entries == []


class TestOfferSyncClientCachedOffers:
    async def test_get_cached_offers_list(self) -> None:
        client = OfferSyncClient()
        mock_resp = _mock_response(
            json_data=[
                {
                    "offer_id": "o1",
                    "chain_id": "ait-hub",
                    "provider": "p1",
                    "service_type": "gpu_marketplace",
                    "price": 0.05,
                    "quantity": 10,
                    "status": "available",
                }
            ]
        )
        client._ensure_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_resp)
        client._ensure_client.return_value = mock_http

        offers = await client.get_cached_offers(chain_id="ait-hub")
        assert len(offers) == 1
        assert offers[0].offer_id == "o1"

    async def test_get_cached_offers_wrapped(self) -> None:
        client = OfferSyncClient()
        mock_resp = _mock_response(
            json_data={
                "offers": [
                    {"offer_id": "o2", "chain_id": "ait-island1", "service_type": "compute"},
                ]
            }
        )
        client._ensure_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_resp)
        client._ensure_client.return_value = mock_http

        offers = await client.get_cached_offers(service_type="compute")
        assert len(offers) == 1
        assert offers[0].service_type == "compute"


# ---------------------------------------------------------------------------
# OfferCache
# ---------------------------------------------------------------------------


def _make_cache(redis_available: bool = False) -> OfferCache:
    """Create an OfferCache with a mocked RedisCache."""
    with patch("aitbc.trading.offer_cache.RedisCache") as mock_class:
        mock_instance = MagicMock()
        mock_instance.is_available.return_value = redis_available
        mock_instance.get.return_value = None
        mock_instance.set.return_value = True
        mock_instance.delete.return_value = True
        mock_class.return_value = mock_instance
        cache = OfferCache()
    return cache


class TestOfferCacheInit:
    def test_defaults(self) -> None:
        cache = _make_cache()
        assert cache._config is not None
        assert cache._cache is not None

    def test_with_config(self) -> None:
        cfg = OfferSyncConfig(cache_ttl_seconds=600, staleness_threshold_seconds=1800)
        with patch("aitbc.trading.offer_cache.RedisCache"):
            cache = OfferCache(config=cfg)
        assert cache._config.cache_ttl_seconds == 600
        assert cache._config.staleness_threshold_seconds == 1800

    def test_is_available_true(self) -> None:
        cache = _make_cache(redis_available=True)
        assert cache.is_available() is True

    def test_is_available_false(self) -> None:
        cache = _make_cache(redis_available=False)
        assert cache.is_available() is False


class TestOfferCacheGetSet:
    def test_set_and_get_offer(self) -> None:
        cache = _make_cache()
        offer = _sample_synced_offer()
        cache.set_offer(offer)
        # set_offer calls set twice (offer + chain index)
        assert cache._cache.set.call_count == 2

        # Mock the get to return the stored offer
        cache._cache.get.return_value = json.dumps(offer.to_dict())
        result = cache.get_offer("offer_001")
        assert result is not None
        assert result.offer_id == "offer_001"
        assert result.chain_id == "ait-hub"

    def test_get_offer_not_found(self) -> None:
        cache = _make_cache()
        cache._cache.get.return_value = None
        result = cache.get_offer("nonexistent")
        assert result is None

    def test_get_offer_invalid_json(self) -> None:
        cache = _make_cache()
        cache._cache.get.return_value = "not valid json"
        result = cache.get_offer("bad_offer")
        assert result is None

    def test_get_offer_dict_input(self) -> None:
        """If RedisCache returns a dict (in-memory mode), handle it."""
        cache = _make_cache()
        offer = _sample_synced_offer()
        cache._cache.get.return_value = offer.to_dict()
        result = cache.get_offer("offer_001")
        assert result is not None
        assert result.offer_id == "offer_001"

    def test_delete_offer(self) -> None:
        cache = _make_cache()
        # Mock get_offer to return an offer so chain_id is known
        offer = _sample_synced_offer()
        cache._cache.get.return_value = json.dumps(offer.to_dict())
        cache.delete_offer("offer_001")
        # delete called for offer key + chain index
        assert cache._cache.delete.call_count >= 1

    def test_delete_offer_with_explicit_chain(self) -> None:
        cache = _make_cache()
        cache._cache.get.return_value = None  # offer not found
        cache.delete_offer("offer_001", chain_id="ait-hub")
        assert cache._cache.delete.call_count >= 1


class TestOfferCacheList:
    def test_list_offers_by_chain(self) -> None:
        cache = _make_cache()
        offer = _sample_synced_offer()
        # Mock chain index to return offer IDs
        cache._cache.get.side_effect = lambda key: (
            json.dumps(["offer_001"]) if "offers" in key else json.dumps(offer.to_dict())
        )
        result = cache.list_offers_by_chain("ait-hub")
        assert len(result) == 1
        assert result[0].offer_id == "offer_001"

    def test_list_offers_by_chain_empty(self) -> None:
        cache = _make_cache()
        cache._cache.get.return_value = None
        result = cache.list_offers_by_chain("ait-hub")
        assert result == []

    def test_list_offers_by_type(self) -> None:
        cache = _make_cache()
        offer = _sample_synced_offer()
        # Mock _get_known_chains to return ["ait-hub"]
        cache._get_known_chains = MagicMock(return_value=["ait-hub"])
        cache._cache.get.side_effect = lambda key: (
            json.dumps(["offer_001"]) if "offers" in key else json.dumps(offer.to_dict())
        )
        result = cache.list_offers_by_type("gpu_marketplace")
        assert len(result) == 1
        assert result[0].service_type == "gpu_marketplace"

    def test_list_offers_by_type_no_match(self) -> None:
        cache = _make_cache()
        offer = _sample_synced_offer(service_type="compute")
        cache._get_known_chains = MagicMock(return_value=["ait-hub"])
        cache._cache.get.side_effect = lambda key: (
            json.dumps(["offer_001"]) if "offers" in key else json.dumps(offer.to_dict())
        )
        result = cache.list_offers_by_type("gpu_marketplace")
        assert result == []


class TestOfferCacheStaleness:
    def test_is_stale_fresh(self) -> None:
        cache = _make_cache()
        offer = _sample_synced_offer(last_synced=datetime.now(UTC).isoformat())
        cache._cache.get.return_value = json.dumps(offer.to_dict())
        assert cache.is_stale("offer_001") is False

    def test_is_stale_old(self) -> None:
        cache = _make_cache()
        old_time = (datetime.now(UTC) - timedelta(seconds=600)).isoformat()
        offer = _sample_synced_offer(last_synced=old_time)
        cache._cache.get.return_value = json.dumps(offer.to_dict())
        assert cache.is_stale("offer_001") is True

    def test_is_stale_not_found(self) -> None:
        cache = _make_cache()
        cache._cache.get.return_value = None
        assert cache.is_stale("nonexistent") is True

    def test_is_stale_no_timestamp(self) -> None:
        cache = _make_cache()
        offer = _sample_synced_offer(last_synced="")
        cache._cache.get.return_value = json.dumps(offer.to_dict())
        assert cache.is_stale("offer_001") is True

    def test_is_stale_invalid_timestamp(self) -> None:
        cache = _make_cache()
        offer = _sample_synced_offer(last_synced="not-a-timestamp")
        cache._cache.get.return_value = json.dumps(offer.to_dict())
        assert cache.is_stale("offer_001") is True

    def test_is_stale_per_chain_threshold(self) -> None:
        cfg = OfferSyncConfig(
            staleness_threshold_seconds=300,
            per_chain_staleness={"ait-island1": 3600},
        )
        with patch("aitbc.trading.offer_cache.RedisCache"):
            cache = OfferCache(config=cfg)
        # 30 min old offer on slow chain (3600s threshold) → fresh
        old_time = (datetime.now(UTC) - timedelta(seconds=1800)).isoformat()
        offer = _sample_synced_offer(chain_id="ait-island1", last_synced=old_time)
        cache._cache.get.return_value = json.dumps(offer.to_dict())
        assert cache.is_stale("offer_001") is False

    def test_get_stale_offers(self) -> None:
        cache = _make_cache()
        old_time = (datetime.now(UTC) - timedelta(seconds=600)).isoformat()
        stale_offer = _sample_synced_offer(last_synced=old_time)
        fresh_offer = _sample_synced_offer(
            offer_id="offer_002",
            last_synced=datetime.now(UTC).isoformat(),
        )
        cache._get_known_chains = MagicMock(return_value=["ait-hub"])
        offers_map = {"offer_001": stale_offer, "offer_002": fresh_offer}

        def get_side_effect(key: str) -> str | None:
            if "offers" in key:
                return json.dumps(["offer_001", "offer_002"])
            for oid, o in offers_map.items():
                if key.endswith(oid):
                    return json.dumps(o.to_dict())
            return None

        cache._cache.get.side_effect = get_side_effect
        stale = cache.get_stale_offers(chain_id="ait-hub")
        assert "offer_001" in stale
        assert "offer_002" not in stale


class TestOfferCacheSyncMetadata:
    def test_get_sync_metadata_empty(self) -> None:
        cache = _make_cache()
        cache._cache.get.return_value = None
        meta = cache.get_sync_metadata("ait-hub")
        assert meta["chain_id"] == "ait-hub"
        assert meta["last_sync"] == ""
        assert meta["offer_count"] == 0
        assert meta["stale_count"] == 0
        assert meta["is_syncing"] is False

    def test_get_sync_metadata_existing(self) -> None:
        cache = _make_cache()
        meta_data = {
            "chain_id": "ait-hub",
            "last_sync": "2026-06-29T12:00:00+00:00",
            "offer_count": 42,
            "is_syncing": True,
        }
        cache._cache.get.return_value = json.dumps(meta_data)
        meta = cache.get_sync_metadata("ait-hub")
        assert meta["chain_id"] == "ait-hub"
        assert meta["last_sync"] == "2026-06-29T12:00:00+00:00"
        assert meta["offer_count"] == 42
        assert meta["is_syncing"] is True

    def test_set_sync_metadata(self) -> None:
        cache = _make_cache()
        cache._cache.get.return_value = None  # no offers in chain
        cache.set_sync_metadata("ait-hub", {"last_sync": "2026-06-29T12:00:00+00:00"})
        cache._cache.set.assert_called()
        args = cache._cache.set.call_args
        stored = json.loads(args[0][1])
        assert stored["last_sync"] == "2026-06-29T12:00:00+00:00"
        assert stored["chain_id"] == "ait-hub"
        assert stored["offer_count"] == 0

    def test_mark_syncing_true(self) -> None:
        cache = _make_cache()
        cache._cache.get.return_value = None
        cache.mark_syncing("ait-hub", True)
        cache._cache.set.assert_called()

    def test_mark_syncing_false(self) -> None:
        cache = _make_cache()
        cache._cache.get.return_value = None
        cache.mark_syncing("ait-hub", False)
        cache._cache.set.assert_called()


class TestOfferCacheClear:
    def test_clear_chain(self) -> None:
        cache = _make_cache()
        # Mock chain index to return 2 offers
        cache._cache.get.return_value = json.dumps(["o1", "o2"])
        count = cache.clear_chain("ait-hub")
        assert count == 2
        # delete called for each offer + chain index + chain meta
        assert cache._cache.delete.call_count >= 3
