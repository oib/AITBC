"""Coverage for the inter-chain service layer (v0.8.0 §B4-B6).

``test_v080_inter_chain.py`` ships empty ``TestChainDiscovery``,
``TestInterChainTradeLifecycle`` and ``TestMatchingEngine`` classes — the
services themselves had no behavioral coverage.  These tests exercise
``InterChainTradeService``, ``MatchingEngine`` and ``ChainDiscoveryService``
against an in-memory SQLite session, with the blockchain RPC client mocked.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


@pytest.fixture
async def db_session():
    """In-memory SQLite async session with all trading tables."""
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
        # Trading tables live on trading_metadata, not SQLModel.metadata
        # (see domain/base.py — coordinator-api defines the same table names).
        await conn.run_sync(trading_metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session

    await engine.dispose()


async def _make_trade(svc, **overrides):
    from trading_service.services.inter_chain_service import InterChainTradeService  # noqa: F401

    kwargs = {
        "source_chain": "chain-a",
        "dest_chain": "chain-b",
        "sender": "0xsender",
        "recipient": "0xrecipient",
        "amount": 100,
        "price": Decimal("1.5"),
    }
    kwargs.update(overrides)
    return await svc.create_trade(**kwargs)


# ---------------------------------------------------------------------------
# InterChainTradeService
# ---------------------------------------------------------------------------


class TestInterChainTradeService:
    async def test_create_and_get_trade(self, db_session):
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        trade = await _make_trade(svc, offer_id="offer-1", quantity=3)

        assert trade.trade_id.startswith("trade_")
        assert trade.status == "pending"
        assert trade.settlement_phase == "none"
        assert trade.offer_id == "offer-1"
        assert trade.price == Decimal("1.5")

        fetched = await svc.get_trade(trade.trade_id)
        assert fetched is not None
        assert fetched.trade_id == trade.trade_id
        assert await svc.get_trade("trade_missing") is None

    async def test_list_trades_filters_and_pagination(self, db_session):
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        t1 = await _make_trade(svc, source_chain="chain-a", dest_chain="chain-b", amount=10)
        t2 = await _make_trade(svc, source_chain="chain-b", dest_chain="chain-a", amount=20)
        t3 = await _make_trade(svc, source_chain="chain-a", dest_chain="chain-c", amount=30)

        all_trades = await svc.list_trades()
        assert {t.trade_id for t in all_trades} == {t1.trade_id, t2.trade_id, t3.trade_id}
        # Newest first
        assert all_trades[0].trade_id == t3.trade_id

        by_source = await svc.list_trades(source_chain="chain-a")
        assert {t.trade_id for t in by_source} == {t1.trade_id, t3.trade_id}

        by_pair = await svc.list_trades(source_chain="chain-a", dest_chain="chain-b")
        assert [t.trade_id for t in by_pair] == [t1.trade_id]

        page = await svc.list_trades(limit=1, offset=1)
        assert len(page) == 1
        assert page[0].trade_id == t2.trade_id

        # Unknown status filter returns empty, not everything
        assert await svc.list_trades(status="nonexistent") == []

    async def test_get_trade_status_shape(self, db_session):
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        trade = await _make_trade(svc)
        await svc.update_trade_status(trade.trade_id, "matched", matched_trade_id="trade_other")

        status = await svc.get_trade_status(trade.trade_id)
        assert status is not None
        assert status["trade_id"] == trade.trade_id
        assert status["status"] == "matched"
        assert status["matched_trade_id"] == "trade_other"
        assert status["source_chain"] == "chain-a"
        assert status["dest_chain"] == "chain-b"
        assert "updated_at" in status
        assert await svc.get_trade_status("trade_missing") is None

    async def test_update_trade_status_missing_trade(self, db_session):
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        assert await svc.update_trade_status("trade_missing", "completed") is None

    async def test_get_trade_history_terminal_only(self, db_session):
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        pending = await _make_trade(svc, source_chain="chain-a", dest_chain="chain-b")
        done = await _make_trade(svc, source_chain="chain-b", dest_chain="chain-a")
        await svc.update_trade_status(done.trade_id, "completed")
        failed = await _make_trade(svc, source_chain="chain-c", dest_chain="chain-a")
        await svc.update_trade_status(failed.trade_id, "failed")

        history = await svc.get_trade_history()
        ids = {t.trade_id for t in history}
        assert ids == {done.trade_id, failed.trade_id}
        assert pending.trade_id not in ids

        filtered = await svc.get_trade_history(source_chain="chain-b")
        assert [t.trade_id for t in filtered] == [done.trade_id]

        limited = await svc.get_trade_history(limit=1)
        assert len(limited) == 1

    @pytest.mark.xfail(
        strict=True,
        reason="TRADING-GUARD-2 (#1416): update_trade_status accepts arbitrary status strings "
        "with no transition guard or InterChainTradeStatus validation",
    )
    async def test_update_trade_status_rejects_invalid_status(self, db_session):
        """``InterChainTradeStatus`` defines the lifecycle
        (pending → matched → locked → confirmed → completed); bogus values
        like ``"bogus"`` or backward transitions (completed → pending) must
        be rejected. Currently any string is written verbatim."""
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        trade = await _make_trade(svc)
        await svc.update_trade_status(trade.trade_id, "completed")

        # Invalid status value must be refused
        result = await svc.update_trade_status(trade.trade_id, "bogus-status")
        assert result is None or result.status != "bogus-status"

        # Terminal → pending resurrection must be refused
        result = await svc.update_trade_status(trade.trade_id, "pending")
        assert result is None or result.status == "completed"


# ---------------------------------------------------------------------------
# MatchingEngine
# ---------------------------------------------------------------------------


def _engine(db_session):
    from trading_service.services.matching_engine import MatchingEngine

    return MatchingEngine(db_session)


class TestMatchingEngine:
    async def test_match_trade_not_found(self, db_session):
        engine = _engine(db_session)
        assert await engine.match_trade("trade_missing") is None

    async def test_match_trade_non_pending(self, db_session):
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        trade = await _make_trade(svc)
        await svc.update_trade_status(trade.trade_id, "completed")

        engine = _engine(db_session)
        result = await engine.match_trade(trade.trade_id)
        assert result is not None
        assert result["matched"] is False
        assert result["reason"] == "trade not pending"

    async def test_match_trade_no_counterparty(self, db_session):
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        trade = await _make_trade(svc)

        engine = _engine(db_session)
        result = await engine.match_trade(trade.trade_id)
        assert result is not None
        assert result["matched"] is False
        assert result["reason"] == "no matching trades"

    async def test_match_trade_happy_path(self, db_session):
        """A pending opposite-direction trade with equal amount matches."""
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        buy = await _make_trade(
            svc,
            source_chain="chain-a",
            dest_chain="chain-b",
            sender="0xbuyer",
            recipient="0xseller",
            amount=500,
        )
        sell = await _make_trade(
            svc,
            source_chain="chain-b",
            dest_chain="chain-a",
            sender="0xseller",
            recipient="0xbuyer",
            amount=500,
            price=Decimal("2.0"),
        )

        engine = _engine(db_session)
        result = await engine.match_trade(buy.trade_id)

        assert result is not None
        assert result["matched"] is True
        assert result["matched_trade_id"] == sell.trade_id

        # Both trades flipped to matched with cross-references
        await db_session.refresh(buy)
        await db_session.refresh(sell)
        assert buy.status == "matched"
        assert buy.matched_trade_id == sell.trade_id
        assert sell.status == "matched"
        assert sell.matched_trade_id == buy.trade_id

        # Counterparty can no longer be matched again
        again = await engine.match_trade(sell.trade_id)
        assert again is not None
        assert again["matched"] is False

    async def test_match_trade_price_time_priority(self, db_session):
        """Highest price wins; ties break on earliest creation."""
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        buy = await _make_trade(svc, source_chain="chain-a", dest_chain="chain-b", amount=100)
        cheap = await _make_trade(svc, source_chain="chain-b", dest_chain="chain-a", amount=100, price=Decimal("1.0"))
        dear = await _make_trade(svc, source_chain="chain-b", dest_chain="chain-a", amount=100, price=Decimal("9.0"))

        engine = _engine(db_session)
        result = await engine.match_trade(buy.trade_id)
        assert result is not None
        assert result["matched_trade_id"] == dear.trade_id
        # The cheaper counterparty stays pending
        await db_session.refresh(cheap)
        assert cheap.status == "pending"

    async def test_match_trade_ignores_amount_mismatch(self, db_session):
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        buy = await _make_trade(svc, source_chain="chain-a", dest_chain="chain-b", amount=100)
        await _make_trade(svc, source_chain="chain-b", dest_chain="chain-a", amount=999)

        engine = _engine(db_session)
        result = await engine.match_trade(buy.trade_id)
        assert result is not None
        assert result["matched"] is False

    @pytest.mark.xfail(
        strict=True,
        reason="TRADING-MATCH-1 (#1413): match_trade documents 'counterparty sender == this "
        "trade's recipient' but the query never checks parties — unrelated trades "
        "between the same chains with equal amount are matched",
    )
    async def test_match_trade_rejects_unrelated_counterparty(self, db_session):
        """Two trades between the same chains with equal amount but completely
        unrelated sender/recipient pairs must NOT match. The docstring at
        ``matching_engine.py:33-38`` lists the party criterion; the query at
        ``matching_engine.py:53-64`` omits it."""
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        buy = await _make_trade(
            svc,
            source_chain="chain-a",
            dest_chain="chain-b",
            sender="0xalice",
            recipient="0xbob",
            amount=100,
        )
        # Same chains reversed, same amount — but different parties entirely
        await _make_trade(
            svc,
            source_chain="chain-b",
            dest_chain="chain-a",
            sender="0xmallory",
            recipient="0xeve",
            amount=100,
        )

        engine = _engine(db_session)
        result = await engine.match_trade(buy.trade_id)
        assert result is not None
        assert result["matched"] is False

    async def test_match_all_pending(self, db_session):
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        a = await _make_trade(svc, source_chain="chain-a", dest_chain="chain-b", amount=10)
        b = await _make_trade(svc, source_chain="chain-b", dest_chain="chain-a", amount=10)
        c = await _make_trade(svc, source_chain="chain-a", dest_chain="chain-c", amount=10)

        engine = _engine(db_session)
        results = await engine.match_all_pending()

        matched_ids = {r["trade_id"] for r in results if r.get("matched")}
        assert a.trade_id in matched_ids or b.trade_id in matched_ids
        # Unmatched trade still shows up with matched=False
        assert any(r["trade_id"] == c.trade_id and r["matched"] is False for r in results)


# ---------------------------------------------------------------------------
# ChainDiscoveryService
# ---------------------------------------------------------------------------


def _discovery(db_session, blockchain_client=None):
    from trading_service.services.chain_discovery import ChainDiscoveryService

    return ChainDiscoveryService(db_session, blockchain_client=blockchain_client or MagicMock())


class TestChainDiscoveryService:
    async def test_register_and_list_chains(self, db_session):
        svc = _discovery(db_session)
        entry = await svc.register_chain("chain-a", "http://chain-a:8202")

        assert entry.chain_id == "chain-a"
        assert entry.endpoint == "http://chain-a:8202"
        assert entry.status == "active"

        chains = await svc.list_chains()
        assert [c.chain_id for c in chains] == ["chain-a"]

        # Re-registering the same chain updates endpoint and reactivates
        entry2 = await svc.register_chain("chain-a", "http://chain-a-new:8202")
        assert entry2.endpoint == "http://chain-a-new:8202"
        assert len(await svc.list_chains()) == 1

    async def test_list_chains_status_filter(self, db_session):
        from trading_service.domain.inter_chain import IslandRegistryEntry

        svc = _discovery(db_session)
        await svc.register_chain("chain-a", "http://a")
        db_session.add(IslandRegistryEntry(chain_id="chain-b", endpoint="http://b", status="inactive"))
        await db_session.commit()

        active = await svc.list_chains(status="active")
        assert [c.chain_id for c in active] == ["chain-a"]
        inactive = await svc.list_chains(status="inactive")
        assert [c.chain_id for c in inactive] == ["chain-b"]

    async def test_get_chain_missing(self, db_session):
        svc = _discovery(db_session)
        assert await svc.get_chain("nope") is None

    async def test_get_chain_health_unregistered(self, db_session):
        svc = _discovery(db_session)
        result = await svc.get_chain_health("nope")
        assert result == {"chain_id": "nope", "status": "not_registered"}

    async def test_get_chain_health_success(self, db_session, monkeypatch):
        """Health check queries the chain endpoint and marks it active."""

        svc = _discovery(db_session)
        await svc.register_chain("chain-a", "http://chain-a:8202")

        fake_client = MagicMock()
        fake_client.get_chain_health = AsyncMock(return_value={"healthy": True})
        fake_client.get_block_height = AsyncMock(return_value=1234)

        monkeypatch.setattr(
            "trading_service.services.chain_discovery.BlockchainClient",
            MagicMock(return_value=fake_client),
        )

        result = await svc.get_chain_health("chain-a")
        assert result["status"] == "active"
        assert result["block_height"] == 1234
        assert result["health"] == {"healthy": True}
        assert result["last_sync"]

        entry = await svc.get_chain("chain-a")
        assert entry.block_height == 1234
        assert entry.status == "active"

    async def test_get_chain_health_failure_marks_unreachable(self, db_session, monkeypatch):

        svc = _discovery(db_session)
        await svc.register_chain("chain-a", "http://chain-a:8202")

        fake_client = MagicMock()
        fake_client.get_chain_health = AsyncMock(side_effect=ConnectionError("refused"))
        fake_client.get_block_height = AsyncMock(return_value=0)

        monkeypatch.setattr(
            "trading_service.services.chain_discovery.BlockchainClient",
            MagicMock(return_value=fake_client),
        )

        result = await svc.get_chain_health("chain-a")
        assert result["status"] == "unreachable"
        assert "refused" in result["error"]

        entry = await svc.get_chain("chain-a")
        assert entry.status == "unreachable"

    async def test_sync_island_registry_mixed_results(self, db_session, monkeypatch):
        from trading_service.domain.inter_chain import IslandRegistryEntry

        svc = _discovery(db_session)
        await svc.register_chain("chain-ok", "http://ok")
        db_session.add(IslandRegistryEntry(chain_id="chain-bad", endpoint="http://bad", status="active"))
        await db_session.commit()

        heights = {"chain-ok": 777}

        class _FakeClient:
            def __init__(self, rpc_url: str, timeout: float) -> None:
                self._chain = rpc_url

            async def get_block_height(self, chain_id: str) -> int:
                if "bad" in self._chain:
                    raise ConnectionError("down")
                return heights[chain_id]

        monkeypatch.setattr("trading_service.services.chain_discovery.BlockchainClient", _FakeClient)

        results = await svc.sync_island_registry()
        assert results == {"synced": 1, "unreachable": 1, "total": 2}

        ok = await svc.get_chain("chain-ok")
        bad = await svc.get_chain("chain-bad")
        assert ok.status == "active"
        assert ok.block_height == 777
        assert bad.status == "unreachable"
