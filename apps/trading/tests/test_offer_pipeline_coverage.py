"""Coverage for the offer pipeline services (v0.8.1/v0.8.2 §B2-B7, B18-B20).

``test_v081_offer_sync.py`` and ``test_v082_offer_subscription.py`` cover the
happy-path config/subscription surface; this file covers the pieces they
miss: ``OfferSearchService`` in-memory search, ``OfferNotificationService``
debounce batching, ``GossipClient`` payload decoding + in-memory pub/sub, and
the ``OfferSyncService`` discovery/filter paths — including several defects
found while reading (see the ``xfail`` markers).
"""

from __future__ import annotations

import asyncio
import base64
import gzip
import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from aitbc.trading.offer_cache import OfferCache
from aitbc.trading.offer_types import (
    OfferDiscoveryRequest,
    OfferSyncStatus,
    SyncedOffer,
)
from aitbc.trading.subscription_types import OfferEvent, OfferSubscription


@pytest.fixture
async def db_session():
    """In-memory SQLite session on ``trading_metadata`` (see domain/base.py)."""
    from trading_service.domain.base import trading_metadata
    from trading_service.domain.inter_chain import (  # noqa: F401 — register tables
        InterChainTrade,
        IslandRegistryEntry,
    )
    from trading_service.domain.trading import (  # noqa: F401 — register tables
        TradeAgreement,
        TradeMatch,
        TradeNegotiation,
        TradeRequest,
        TradeSettlement,
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(trading_metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session

    await engine.dispose()


def _offer(
    offer_id: str,
    chain_id: str = "chain-a",
    price: str = "1.0",
    service_type: str = "gpu_market",
    provider: str = "provider-x",
    status: str = "available",
    attributes: dict | None = None,
    last_synced: str | None = None,
) -> SyncedOffer:
    return SyncedOffer(
        offer_id=offer_id,
        chain_id=chain_id,
        provider=provider,
        service_type=service_type,
        price=Decimal(price),
        quantity=1,
        status=status,
        attributes=attributes or {},
        last_synced=last_synced if last_synced is not None else datetime.now(UTC).isoformat(),
        sync_status=OfferSyncStatus.FRESH.value,
        sync_confidence=1.0,
    )


def _event(offer: SyncedOffer | None, chain_id: str = "chain-a", event_type: str = "created") -> OfferEvent:
    return OfferEvent(
        event_type=event_type,
        offer_id=offer.offer_id if offer else "gone",
        chain_id=chain_id,
        offer=offer,
        timestamp=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# OfferSearchService (in-memory fallback — no external index in tests)
# ---------------------------------------------------------------------------


class TestOfferSearchService:
    def test_disabled_by_default_uses_memory(self):
        from trading_service.services.offer_search_service import OfferSearchService

        svc = OfferSearchService(enabled=False)
        assert svc.enabled is False

    def test_index_and_search_filters(self):
        from trading_service.services.offer_search_service import OfferSearchService

        svc = OfferSearchService(enabled=False)
        svc.index_offer(_offer("o1", chain_id="chain-a", price="1.0", provider="alpha"))
        svc.index_offer(_offer("o2", chain_id="chain-b", price="5.0", provider="beta", service_type="compute"))
        svc.index_offer(_offer("o3", chain_id="chain-a", price="3.0", provider="gamma"))

        # Sorted by price ascending
        assert [o.offer_id for o in svc.search()] == ["o1", "o3", "o2"]

        by_chain = svc.search(chain_id="chain-a")
        assert {o.offer_id for o in by_chain} == {"o1", "o3"}

        by_type = svc.search(service_type="compute")
        assert [o.offer_id for o in by_type] == ["o2"]

        by_price = svc.search(min_price=Decimal("2"), max_price=Decimal("4"))
        assert [o.offer_id for o in by_price] == ["o3"]

        by_text = svc.search(query="beta")
        assert [o.offer_id for o in by_text] == ["o2"]

        limited = svc.search(limit=2)
        assert len(limited) == 2

    def test_search_text_matches_attributes(self):
        from trading_service.services.offer_search_service import OfferSearchService

        svc = OfferSearchService(enabled=False)
        svc.index_offer(_offer("o1", attributes={"model": "H100", "region": "eu"}))
        assert [o.offer_id for o in svc.search(query="h100")] == ["o1"]
        assert svc.search(query="nonexistent") == []

    def test_delete_offer(self):
        from trading_service.services.offer_search_service import OfferSearchService

        svc = OfferSearchService(enabled=False)
        svc.index_offer(_offer("o1"))
        svc.delete_offer("o1")
        assert svc.search() == []
        # Deleting a missing id is a no-op
        svc.delete_offer("missing")

    def test_close_clears_state(self):
        from trading_service.services.offer_search_service import OfferSearchService

        svc = OfferSearchService(enabled=False)
        svc.index_offer(_offer("o1"))
        svc.close()
        assert svc.search() == []

    def test_unknown_backend_falls_back(self, monkeypatch):
        """An unrecognized backend name disables the index, never raises."""
        from trading_service.services.offer_search_service import OfferSearchService

        monkeypatch.setattr(
            "trading_service.services.offer_search_service.settings",
            MagicMock(
                offer_search_index_enabled=True,
                offer_search_index_url="http://unused",
                offer_search_index_backend="solr",
            ),
        )
        svc = OfferSearchService()
        assert svc.enabled is False


# ---------------------------------------------------------------------------
# OfferNotificationService — debounce batching
# ---------------------------------------------------------------------------


class TestOfferNotificationService:
    async def test_register_and_flush_debounced_batch(self):
        from trading_service.services.offer_notification_service import OfferNotificationService

        svc = OfferNotificationService(debounce_ms=20)
        received: list = []

        async def _cb(notification):
            received.append(notification)

        await svc.register_subscriber("sub-1", OfferSubscription(chain_id="chain-a"), _cb)
        assert svc.subscriber_count == 1

        offer = _offer("o1", chain_id="chain-a")
        await svc.process_event(_event(offer))
        await svc.process_event(_event(_offer("o2", chain_id="chain-a")))
        # Different chain must not match
        await svc.process_event(_event(_offer("o3", chain_id="chain-b"), chain_id="chain-b"))

        await asyncio.sleep(0.1)
        assert len(received) == 1
        note = received[0]
        assert note.batch_size == 2
        assert note.chain_id == "chain-a"
        assert {e.offer_id for e in note.events} == {"o1", "o2"}

        subs = svc.get_subscriptions()
        assert subs["sub-1"]["pending_events"] == 0

        await svc.close()

    async def test_debounce_resets_on_new_events(self):
        from trading_service.services.offer_notification_service import OfferNotificationService

        svc = OfferNotificationService(debounce_ms=60)
        received: list = []

        def _cb(notification):
            received.append(notification)

        await svc.register_subscriber("sub-1", OfferSubscription(chain_id="chain-a"), _cb)

        await svc.process_event(_event(_offer("o1", chain_id="chain-a")))
        await asyncio.sleep(0.04)
        # Second event inside the window resets the timer
        await svc.process_event(_event(_offer("o2", chain_id="chain-a")))
        await asyncio.sleep(0.04)
        assert received == []
        await asyncio.sleep(0.06)
        assert len(received) == 1
        assert received[0].batch_size == 2

        await svc.close()

    async def test_unregister_cancels_pending_flush(self):
        from trading_service.services.offer_notification_service import OfferNotificationService

        svc = OfferNotificationService(debounce_ms=30)
        received: list = []

        await svc.register_subscriber("sub-1", OfferSubscription(chain_id="chain-a"), lambda n: received.append(n))
        await svc.process_event(_event(_offer("o1", chain_id="chain-a")))
        await svc.unregister_subscriber("sub-1")

        assert svc.subscriber_count == 0
        await asyncio.sleep(0.08)
        assert received == []
        await svc.close()

    async def test_flush_all_drains_pending(self):
        from trading_service.services.offer_notification_service import OfferNotificationService

        svc = OfferNotificationService(debounce_ms=60_000)
        received: list = []

        await svc.register_subscriber("sub-1", OfferSubscription(chain_id="chain-a"), lambda n: received.append(n))
        await svc.process_event(_event(_offer("o1", chain_id="chain-a")))
        await svc.flush_all()

        assert len(received) == 1
        await svc.close()

    async def test_callback_exception_is_swallowed(self):
        from trading_service.services.offer_notification_service import OfferNotificationService

        svc = OfferNotificationService(debounce_ms=10)

        def _boom(_notification):
            raise RuntimeError("ws gone")

        await svc.register_subscriber("sub-1", OfferSubscription(chain_id="chain-a"), _boom)
        await svc.process_event(_event(_offer("o1", chain_id="chain-a")))
        await asyncio.sleep(0.05)
        await svc.close()


# ---------------------------------------------------------------------------
# GossipClient — payload decoding + in-memory pub/sub
# ---------------------------------------------------------------------------


class TestGossipPayloadDecoding:
    def test_plain_json_string(self):
        from trading_service.services.gossip_client import _decode_payload

        assert _decode_payload('{"a": 1}') == {"a": 1}

    def test_gz_prefixed_payload(self):
        from trading_service.services.gossip_client import COMPRESSION_PREFIX, _decode_payload

        blob = base64.b64encode(gzip.compress(json.dumps({"x": [1, 2]}).encode())).decode()
        assert _decode_payload(f"{COMPRESSION_PREFIX}{blob}") == {"x": [1, 2]}

    def test_corrupt_gz_falls_back_to_raw(self):
        from trading_service.services.gossip_client import COMPRESSION_PREFIX, _decode_payload

        # Valid prefix, undecodable body → raw string returned, no raise
        assert _decode_payload(f"{COMPRESSION_PREFIX}!!!not-base64!!!") == f"{COMPRESSION_PREFIX}!!!not-base64!!!"

    def test_non_string_passthrough(self):
        from trading_service.services.gossip_client import _decode_payload

        assert _decode_payload(42) == 42
        assert _decode_payload({"already": "dict"}) == {"already": "dict"}
        assert _decode_payload(b'{"b": 2}') == {"b": 2}


class TestGossipClientInMemory:
    async def test_publish_local_delivers_to_subscribers(self):
        from trading_service.services.gossip_client import GossipClient

        client = GossipClient(backend="memory")
        await client.start()
        assert client.started
        assert not client.using_redis

        sub = await client.subscribe("offers.chain-a")
        await client.publish_local("offers.chain-a", {"event_type": "created"})
        msg = await asyncio.wait_for(sub.queue.get(), timeout=1)
        assert msg == {"event_type": "created"}

        sub.close()
        await client.stop()

    async def test_subscribe_scopes_topics(self):
        from trading_service.services.gossip_client import GossipClient

        client = GossipClient(backend="memory")
        await client.start()
        sub_a = await client.subscribe("offers.chain-a")
        sub_b = await client.subscribe("offers.chain-b")

        await client.publish_local("offers.chain-b", "only-b")
        assert await asyncio.wait_for(sub_b.queue.get(), timeout=1) == "only-b"
        assert sub_a.queue.empty()

        await client.stop()

    async def test_stop_clears_subscriptions(self):
        from trading_service.services.gossip_client import GossipClient

        client = GossipClient(backend="memory")
        await client.start()
        sub = await client.subscribe("offers.chain-a")
        await client.stop()
        assert not client.started
        # After stop, publishing reaches no one and does not raise
        await client.publish_local("offers.chain-a", "x")
        sub.close()


# ---------------------------------------------------------------------------
# OfferSyncService — discovery, filters, sync bookkeeping
# ---------------------------------------------------------------------------


def _sync_service(cache: OfferCache | None = None) -> object:
    from trading_service.services.offer_sync_service import OfferSyncService

    blockchain = AsyncMock()
    blockchain.query_offers = AsyncMock(return_value=[])
    session = AsyncMock()
    return OfferSyncService(session=session, cache=cache or OfferCache(), blockchain_client=blockchain)


class TestOfferSyncDiscovery:
    async def test_discover_offers_filters_and_ranks(self):
        svc = _sync_service()
        svc.cache.set_offer(_offer("cheap", chain_id="chain-a", price="1.0"), ttl=300)
        svc.cache.set_offer(_offer("dear", chain_id="chain-a", price="5.0"), ttl=300)
        svc.cache.set_offer(_offer("other-type", chain_id="chain-a", price="0.5", service_type="compute"), ttl=300)
        svc.cache.set_offer(_offer("other-chain", chain_id="chain-b", price="0.1"), ttl=300)

        request = OfferDiscoveryRequest(source_chain="chain-a", service_type="gpu_market")
        result = await svc.discover_offers(request)

        assert [o.offer_id for o in result.offers] == ["cheap", "dear"]
        assert result.total_count == 2
        assert result.chains_searched == ["chain-a"]
        assert result.sync_triggered is False

    async def test_discover_offers_price_filters(self):
        svc = _sync_service()
        svc.cache.set_offer(_offer("o1", chain_id="chain-a", price="1.0"), ttl=300)
        svc.cache.set_offer(_offer("o2", chain_id="chain-a", price="5.0"), ttl=300)

        request = OfferDiscoveryRequest(source_chain="chain-a", min_price=Decimal("2"), max_price=Decimal("9"))
        result = await svc.discover_offers(request)
        assert [o.offer_id for o in result.offers] == ["o2"]

    async def test_discover_offers_gpu_model_filter(self):
        svc = _sync_service()
        svc.cache.set_offer(_offer("h100", chain_id="chain-a", attributes={"model": "NVIDIA H100"}), ttl=300)
        svc.cache.set_offer(_offer("a100", chain_id="chain-a", attributes={"model": "NVIDIA A100"}), ttl=300)

        request = OfferDiscoveryRequest(source_chain="chain-a", gpu_model="h100")
        result = await svc.discover_offers(request)
        assert [o.offer_id for o in result.offers] == ["h100"]

    async def test_discover_offers_limit(self):
        svc = _sync_service()
        for i in range(5):
            svc.cache.set_offer(_offer(f"o{i}", chain_id="chain-a", price=str(i)), ttl=300)

        request = OfferDiscoveryRequest(source_chain="chain-a", limit=2)
        result = await svc.discover_offers(request)
        assert len(result.offers) == 2

    async def test_discover_offers_total_count_is_pre_limit(self):
        svc = _sync_service()
        for i in range(5):
            svc.cache.set_offer(_offer(f"o{i}", chain_id="chain-a", price=str(i)), ttl=300)

        request = OfferDiscoveryRequest(source_chain="chain-a", limit=2)
        result = await svc.discover_offers(request)
        assert len(result.offers) == 2
        assert result.total_count == 5

    async def test_discover_offers_without_source_chain_searches_all(self):
        svc = _sync_service()
        svc.cache.set_offer(_offer("o1", chain_id="chain-a"), ttl=300)
        svc.cache.set_offer(_offer("o2", chain_id="chain-b"), ttl=300)

        result = await svc.discover_offers(OfferDiscoveryRequest())
        assert {o.offer_id for o in result.offers} == {"o1", "o2"}

    async def test_get_cached_offers_filters_and_limit(self):
        svc = _sync_service()
        svc.cache.set_offer(_offer("o1", chain_id="chain-a", price="1.0"), ttl=300)
        svc.cache.set_offer(_offer("o2", chain_id="chain-a", price="2.0", status="reserved"), ttl=300)
        svc.cache.set_offer(_offer("o3", chain_id="chain-b"), ttl=300)

        offers = svc.get_cached_offers(chain_id="chain-a")
        assert {o.offer_id for o in offers} == {"o1", "o2"}

        reserved = svc.get_cached_offers(chain_id="chain-a", status="reserved")
        assert [o.offer_id for o in reserved] == ["o2"]

        limited = svc.get_cached_offers(chain_id="chain-a", limit=1)
        assert len(limited) == 1

    async def test_sync_chain_success_and_error_paths(self):
        """sync_chain caches offers from the chain RPC and records metadata."""
        from trading_service.services.offer_sync_service import OfferSyncService

        blockchain = AsyncMock()
        blockchain.query_offers = AsyncMock(
            return_value=[
                {"gpu_id": "gpu-1", "provider": "p1", "price": "2.5", "capacity": 4, "status": "available"},
                {"id": "gpu-2", "owner": "p2", "price": 1.5, "quantity": 2},
                {"no_id_field": True},  # skipped — no offer id
            ]
        )
        svc = OfferSyncService(session=AsyncMock(), cache=OfferCache(), blockchain_client=blockchain)

        result = await svc.sync_chain("chain-a")
        assert result["chain_id"] == "chain-a"
        assert result["synced"] == 2
        assert "error" not in result

        cached = svc.cache.get_offer("gpu-1")
        assert cached is not None
        assert cached.chain_id == "chain-a"
        assert cached.price == Decimal("2.5")
        assert cached.quantity == 4

        # Source-chain-wins: an offer already cached under another chain is not overwritten
        _offer("gpu-1", chain_id="chain-b", price="9.0")
        other = OfferSyncService(session=AsyncMock(), cache=svc.cache, blockchain_client=blockchain)
        await other.sync_chain("chain-b")
        # gpu-1 already exists from chain-a → chain-b copy skipped
        assert svc.cache.get_offer("gpu-1").chain_id == "chain-a"

        # Error path returns an error dict, never raises
        blockchain.query_offers = AsyncMock(side_effect=RuntimeError("rpc down"))
        result = await svc.sync_chain("chain-a")
        assert result["synced"] == 0
        assert "rpc down" in result["error"]

    async def test_sync_status_entry_tracked(self):

        svc = _sync_service()
        await svc.sync_chain("chain-a")
        entries = svc.get_sync_status()
        assert len(entries) == 1
        assert entries[0].chain_id == "chain-a"
        assert entries[0].is_syncing is False

    async def test_sync_all_chains_fallback(self):
        """With no active island registry rows, sync falls back to default chain."""
        svc = _sync_service()
        scalars = MagicMock()
        scalars.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars
        svc.session.execute = AsyncMock(return_value=result_mock)

        results = await svc.sync_all_chains()
        assert len(results) == 1
        assert results[0]["chain_id"]

    async def test_sync_all_chains_registered(self, db_session):
        """Only ``status == 'active'`` registry rows are synced (SQL filter)."""
        from trading_service.domain.inter_chain import IslandRegistryEntry
        from trading_service.services.offer_sync_service import OfferSyncService

        db_session.add(IslandRegistryEntry(chain_id="chain-a", endpoint="http://a", status="active"))
        db_session.add(IslandRegistryEntry(chain_id="chain-b", endpoint="http://b", status="inactive"))
        await db_session.commit()

        blockchain = AsyncMock()
        blockchain.query_offers = AsyncMock(return_value=[])
        svc = OfferSyncService(session=db_session, cache=OfferCache(), blockchain_client=blockchain)

        results = await svc.sync_all_chains()
        assert [r["chain_id"] for r in results] == ["chain-a"]

    async def test_discover_offers_excludes_dead_statuses(self):
        """#1567: deactivated/inactive offers are cached but never discoverable."""
        svc = _sync_service()
        svc.cache.set_offer(_offer("live", chain_id="chain-a", status="available"), ttl=300)
        svc.cache.set_offer(_offer("dead", chain_id="chain-a", status="deactivated"), ttl=300)
        svc.cache.set_offer(_offer("gone", chain_id="chain-a", status="expired"), ttl=300)

        result = await svc.discover_offers(OfferDiscoveryRequest(source_chain="chain-a"))
        assert [o.offer_id for o in result.offers] == ["live"]

        # The cache listing hides them too unless asked for explicitly.
        cached = svc.get_cached_offers(chain_id="chain-a")
        assert {o.offer_id for o in cached} == {"live"}
        explicit = svc.get_cached_offers(chain_id="chain-a", status="deactivated")
        assert [o.offer_id for o in explicit] == ["dead"]

    async def test_sync_chain_is_single_flight(self):
        """#1567: a second sync_chain while one runs is skipped, not queued."""
        from trading_service.services.offer_sync_service import OfferSyncService

        gate = asyncio.Event()

        async def _slow_query(**kwargs):
            await gate.wait()
            return []

        blockchain = AsyncMock()
        blockchain.query_offers = AsyncMock(side_effect=_slow_query)
        svc = OfferSyncService(session=AsyncMock(), cache=OfferCache(), blockchain_client=blockchain)

        first = asyncio.create_task(svc.sync_chain("chain-a"))
        await asyncio.sleep(0)  # let the first sync reach the RPC await
        second = await svc.sync_chain("chain-a")
        assert second["skipped"] == "sync_in_progress"
        assert second["synced"] == 0

        gate.set()
        first_result = await first
        assert "error" not in first_result
        # After completion a fresh sync runs normally.
        third = await svc.sync_chain("chain-a")
        assert "skipped" not in third


# ---------------------------------------------------------------------------
# OfferCache staleness — naive/aware datetime mixing
# ---------------------------------------------------------------------------


class TestOfferCacheStaleness:
    async def test_stale_check_tolerates_naive_timestamp(self):
        cache = OfferCache()
        cache.set_offer(
            _offer("naive", chain_id="chain-a", last_synced="2020-01-01T00:00:00"),
            ttl=300,
        )
        # Should report the offer as stale, not crash
        stale = cache.get_stale_offers("chain-a")
        assert "naive" in stale

    async def test_stale_check_aware_timestamp(self):
        cache = OfferCache()
        fresh = _offer("fresh", chain_id="chain-a")
        cache.set_offer(fresh, ttl=300)
        assert cache.get_stale_offers("chain-a") == []

        old = _offer("old", chain_id="chain-a", last_synced="2020-01-01T00:00:00+00:00")
        cache.set_offer(old, ttl=300)
        assert "old" in cache.get_stale_offers("chain-a")

    async def test_delete_and_chain_index(self):
        cache = OfferCache()
        cache.set_offer(_offer("o1", chain_id="chain-a"), ttl=300)
        cache.set_offer(_offer("o2", chain_id="chain-a"), ttl=300)
        assert {o.offer_id for o in cache.list_offers_by_chain("chain-a")} == {"o1", "o2"}

        cache.delete_offer("o1", "chain-a")
        assert cache.get_offer("o1") is None
        assert [o.offer_id for o in cache.list_offers_by_chain("chain-a")] == ["o2"]


# ---------------------------------------------------------------------------
# #1567 residuals — chain-namespaced keys + deletion reconciliation
# ---------------------------------------------------------------------------


class TestOfferCacheChainNamespacing:
    """offer:{chain_id}:{offer_id} keys: the same offer_id on two chains is
    two distinct entries — chain B's sync can no longer overwrite chain A's."""

    async def test_same_offer_id_coexists_per_chain(self):
        cache = OfferCache()
        cache.set_offer(_offer("shared", chain_id="chain-a", price="1.0"), ttl=300)
        cache.set_offer(_offer("shared", chain_id="chain-b", price="9.0"), ttl=300)

        a = cache.get_offer("shared", "chain-a")
        b = cache.get_offer("shared", "chain-b")
        assert a is not None and a.price == Decimal("1.0")
        assert b is not None and b.price == Decimal("9.0")

        assert [o.chain_id for o in cache.list_offers_by_chain("chain-a")] == ["chain-a"]
        assert [o.chain_id for o in cache.list_offers_by_chain("chain-b")] == ["chain-b"]

    async def test_delete_offer_is_chain_scoped(self):
        cache = OfferCache()
        cache.set_offer(_offer("shared", chain_id="chain-a"), ttl=300)
        cache.set_offer(_offer("shared", chain_id="chain-b"), ttl=300)

        cache.delete_offer("shared", "chain-a")
        assert cache.get_offer("shared", "chain-a") is None
        assert cache.get_offer("shared", "chain-b") is not None

    async def test_chainless_lookup_finds_namespaced_offer(self):
        """get_offer(offer_id) without a chain still resolves via the registry."""
        cache = OfferCache()
        cache.set_offer(_offer("solo", chain_id="chain-b"), ttl=300)
        found = cache.get_offer("solo")
        assert found is not None and found.chain_id == "chain-b"


class TestSyncDeletionReconciliation:
    """#1567: sync_chain removes cached offers the chain no longer reports —
    but only when the response is known complete (below the page limit)."""

    async def test_sync_deletes_offers_absent_from_response(self):
        from trading_service.services.offer_sync_service import OfferSyncService

        cache = OfferCache()
        cache.set_offer(_offer("gone", chain_id="chain-a"), ttl=300)
        cache.set_offer(_offer("kept", chain_id="chain-a"), ttl=300)
        cache.set_offer(_offer("other-chain", chain_id="chain-b"), ttl=300)

        blockchain = AsyncMock()
        blockchain.query_offers = AsyncMock(
            return_value=[{"gpu_id": "kept", "provider": "p", "price": "1.0", "status": "available"}]
        )
        svc = OfferSyncService(session=AsyncMock(), cache=cache, blockchain_client=blockchain)
        result = await svc.sync_chain("chain-a")

        assert result["deleted"] == 1
        assert cache.get_offer("gone", "chain-a") is None
        assert cache.get_offer("kept", "chain-a") is not None
        # Other chains' namespaces are untouched.
        assert cache.get_offer("other-chain", "chain-b") is not None

    async def test_sync_empty_response_clears_chain(self):
        """A chain reporting zero offers has genuinely deregistered them all."""
        from trading_service.services.offer_sync_service import OfferSyncService

        cache = OfferCache()
        cache.set_offer(_offer("dropped", chain_id="chain-a"), ttl=300)

        blockchain = AsyncMock()
        blockchain.query_offers = AsyncMock(return_value=[])
        svc = OfferSyncService(session=AsyncMock(), cache=cache, blockchain_client=blockchain)
        result = await svc.sync_chain("chain-a")

        assert result["deleted"] == 1
        assert cache.list_offers_by_chain("chain-a") == []

    async def test_sync_at_page_limit_skips_reconciliation(self):
        """A full page may be truncated — deleting then would drop live offers."""
        from trading_service.services.offer_sync_service import OfferSyncService

        cache = OfferCache()
        cache.set_offer(_offer("maybe-gone", chain_id="chain-a"), ttl=300)

        blockchain = AsyncMock()
        blockchain.query_offers = AsyncMock(return_value=[{"gpu_id": f"g{i}", "price": "1.0"} for i in range(500)])
        svc = OfferSyncService(session=AsyncMock(), cache=cache, blockchain_client=blockchain)
        result = await svc.sync_chain("chain-a")

        assert result["deleted"] == 0
        assert cache.get_offer("maybe-gone", "chain-a") is not None

    async def test_sync_error_never_deletes(self):
        """A failed sync must not reconcile — the response proves nothing."""
        from trading_service.services.offer_sync_service import OfferSyncService

        cache = OfferCache()
        cache.set_offer(_offer("safe", chain_id="chain-a"), ttl=300)

        blockchain = AsyncMock()
        blockchain.query_offers = AsyncMock(side_effect=RuntimeError("rpc down"))
        svc = OfferSyncService(session=AsyncMock(), cache=cache, blockchain_client=blockchain)
        result = await svc.sync_chain("chain-a")

        assert "error" in result
        assert cache.get_offer("safe", "chain-a") is not None


class TestDiscoverOffersCrossChainDedup:
    """#1677: discovery dedups on (chain_id, offer_id). Post-#1567 the same
    offer_id on two chains is two distinct offers — a bare offer_id dedup
    silently dropped every chain but the first."""

    async def test_same_offer_id_on_two_chains_both_discoverable(self):
        cache = OfferCache()
        cache.set_offer(_offer("shared", chain_id="chain-a", price="1.0"), ttl=300)
        cache.set_offer(_offer("shared", chain_id="chain-b", price="9.0"), ttl=300)
        svc = _sync_service(cache)

        result = await svc.discover_offers(OfferDiscoveryRequest())

        assert {(o.chain_id, o.offer_id) for o in result.offers} == {
            ("chain-a", "shared"),
            ("chain-b", "shared"),
        }
        assert result.total_count == 2
        # Ranked by price: chain-a's 1.0 offer precedes chain-b's 9.0.
        assert [o.chain_id for o in result.offers] == ["chain-a", "chain-b"]

    async def test_list_offers_by_type_keeps_cross_chain_duplicates(self):
        cache = OfferCache()
        cache.set_offer(_offer("shared", chain_id="chain-a", service_type="gpu_market"), ttl=300)
        cache.set_offer(_offer("shared", chain_id="chain-b", service_type="gpu_market"), ttl=300)

        offers = cache.list_offers_by_type("gpu_market")

        assert {(o.chain_id, o.offer_id) for o in offers} == {
            ("chain-a", "shared"),
            ("chain-b", "shared"),
        }

    async def test_dedup_preserves_full_offer_schema(self):
        """#1677 + #1635 merged pin: the (chain_id, offer_id) dedup key must not
        drop schema fields — every surviving offer keeps its full attribute
        set, sync metadata, and wire-folded descriptive keys end to end
        (legacy node wire → ``from_dict`` → cache roundtrip → discovery dedup).
        """

        # Faithful legacy node market-listing wire shape (listing_id /
        # seller_address / item_type / status "active") plus descriptive keys
        # that ``SyncedOffer.from_dict`` folds into ``attributes``.
        def _legacy_wire(chain_hint: str) -> dict:
            return {
                "listing_id": "tx_shared",
                "seller_address": f"0xSeller{chain_hint}",
                "item_type": "GPU",
                "price": "0.05",
                "capacity": 8,
                "status": "active",
                "gpu_model": "NVIDIA H100",
                "endpoint": f"http://10.0.0.{chain_hint[-1] if chain_hint[-1].isdigit() else '5'}:11434",
                "region": "eu",
            }

        cache = OfferCache()
        offers_in: dict[str, SyncedOffer] = {}
        for chain_id in ("chain-a", "chain-b"):
            wire = _legacy_wire(chain_id)
            offer = SyncedOffer.from_dict(wire)
            offer.chain_id = chain_id  # node payload carries no chain_id; envelope backfills it
            offers_in[chain_id] = offer
            cache.set_offer(offer, ttl=300)

        svc = _sync_service(cache)
        result = await svc.discover_offers(OfferDiscoveryRequest())

        assert {(o.chain_id, o.offer_id) for o in result.offers} == {
            ("chain-a", "tx_shared"),
            ("chain-b", "tx_shared"),
        }
        for offer in result.offers:
            # Core schema fields survive the cache roundtrip + dedup intact.
            assert offer.offer_id == "tx_shared"
            assert offer.provider == f"0xSeller{offer.chain_id}"
            assert offer.service_type == "GPU"
            assert offer.price == Decimal("0.05")
            assert offer.quantity == 8
            assert offer.status == "available"  # "active" normalized (#1635)
            assert offer.sync_status == "fresh"
            assert offer.sync_confidence == 1.0
            # Wire-folded attributes survive — subscription filters depend on them.
            assert offer.attributes["gpu_model"] == "NVIDIA H100"
            assert offer.attributes["region"] == "eu"
            assert offer.attributes["endpoint"].startswith("http://10.0.0.")
            # to_dict/from_dict roundtrip keeps the same field set.
            assert SyncedOffer.from_dict(offer.to_dict()).attributes == offer.attributes
