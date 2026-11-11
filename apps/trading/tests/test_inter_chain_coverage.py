"""Coverage for the inter-chain service layer (v0.8.0 §B4-B6).

``test_v080_inter_chain.py`` ships empty ``TestChainDiscovery``,
``TestInterChainTradeLifecycle`` and ``TestMatchingEngine`` classes — the
services themselves had no behavioral coverage.  These tests exercise
``InterChainTradeService``, ``MatchingEngine`` and ``ChainDiscoveryService``
against an in-memory SQLite session, with the blockchain RPC client mocked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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


@pytest.fixture(autouse=True)
def _fleet_dns(monkeypatch):
    """#1523: register_chain now resolves endpoints through the fleet SSRF
    guard — fake DNS so the synthetic hostnames below resolve to a private
    fleet address (which the guard allows)."""
    import socket

    def _fake(*a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.9", 8202))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake)


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

    @pytest.mark.parametrize(
        "bad_endpoint",
        [
            "file:///etc/passwd",
            "gopher://internal:70/x",
            "ftp://chain:21",
            "chain-a:8202",
            "http://",
            "",
            "   ",
        ],
    )
    async def test_register_chain_rejects_non_http_endpoints(self, db_session, bad_endpoint):
        """#1539 — the stored endpoint is fetched later; only http(s)+host allowed."""
        svc = _discovery(db_session)
        with pytest.raises(ValueError, match="http"):
            await svc.register_chain("chain-bad", bad_endpoint)
        assert await svc.list_chains() == []

    async def test_register_chain_accepts_private_http_endpoints(self, db_session):
        """Fleet islands live on private ranges — those must still register."""
        svc = _discovery(db_session)
        entry = await svc.register_chain("chain-priv", "http://10.0.0.5:8202")
        assert entry.endpoint == "http://10.0.0.5:8202"

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


# ---------------------------------------------------------------------------
# Post-commit expiry regression (production sessions use expire_on_commit=True;
# the db_session fixture above disables it, which is why these paths 500'd)
# ---------------------------------------------------------------------------


@pytest.fixture
async def expiring_session():
    """Same schema as db_session but with expire_on_commit=True — the
    production default that triggered MissingGreenlet on post-commit reads."""
    from trading_service.domain.base import trading_metadata
    from trading_service.domain.inter_chain import (  # noqa: F401
        InterChainTrade,
        IslandRegistryEntry,
    )
    from trading_service.domain.trading import (  # noqa: F401
        TradeAgreement,
        TradeMatch,
        TradeNegotiation,
        TradeRequest,
        TradeSettlement,
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(trading_metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=True) as session:
        yield session

    await engine.dispose()


class TestPostCommitExpiry:
    """#1411 residual — match_trade and get_chain_health read ORM attrs after
    commit; with expire_on_commit=True those reads raised MissingGreenlet and
    returned 500 AFTER the state change had already committed."""

    async def test_match_trade_happy_path_expiring_session(self, expiring_session):
        from trading_service.services.inter_chain_service import InterChainTradeService
        from trading_service.services.matching_engine import MatchingEngine

        svc = InterChainTradeService(expiring_session)
        buy = await _make_trade(
            svc,
            source_chain="chain-a",
            dest_chain="chain-b",
            sender="0xbuyer",
            recipient="0xseller",
            amount=500,
        )
        buy_id = buy.trade_id  # capture before the next commit expires it
        sell = await _make_trade(
            svc,
            source_chain="chain-b",
            dest_chain="chain-a",
            sender="0xseller",
            recipient="0xbuyer",
            amount=500,
            price=Decimal("2.0"),
        )
        sell_id = sell.trade_id

        engine = MatchingEngine(expiring_session)
        result = await engine.match_trade(buy_id)

        assert result is not None
        assert result["matched"] is True
        assert result["matched_trade_id"] == sell_id
        assert result["source_chain"] == "chain-a"
        assert result["price"] == Decimal("2.0")

    async def test_get_chain_health_expiring_session(self, expiring_session, monkeypatch):
        svc = _discovery(expiring_session)
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
        assert result["endpoint"] == "http://chain-a:8202"
        assert result["last_sync"]


# ---------------------------------------------------------------------------
# #1562 residuals: trade expiry, match claim race, settle claim-then-call
# ---------------------------------------------------------------------------


class TestTradeExpiry:
    async def test_create_trade_stamps_expires_at(self, db_session):
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        trade = await _make_trade(svc)
        assert trade.expires_at is not None
        assert trade.expires_at > trade.created_at.replace(tzinfo=None)

    async def test_stale_pending_trade_expires_lazily(self, db_session):
        """A pending trade past expires_at flips to 'cancelled' on read."""
        from sqlalchemy import update as sa_update

        from trading_service.domain.inter_chain import InterChainTrade
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        trade = await _make_trade(svc)
        past = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
        await db_session.execute(
            sa_update(InterChainTrade).where(InterChainTrade.trade_id == trade.trade_id).values(expires_at=past)
        )
        await db_session.commit()

        trades = await svc.list_trades()
        assert trades[0].status == "cancelled"
        fresh = await svc.get_trade(trade.trade_id)
        assert fresh is not None and fresh.status == "cancelled"

    async def test_legacy_null_expires_at_falls_back_to_created_at(self, db_session):
        """Rows predating the column (NULL expires_at) still expire via TTL."""
        from sqlalchemy import update as sa_update

        from trading_service.domain.inter_chain import InterChainTrade
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        trade = await _make_trade(svc)
        old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
        await db_session.execute(
            sa_update(InterChainTrade)
            .where(InterChainTrade.trade_id == trade.trade_id)
            .values(expires_at=None, created_at=old)
        )
        await db_session.commit()

        await svc.list_trades()
        fresh = await svc.get_trade(trade.trade_id)
        assert fresh is not None and fresh.status == "cancelled"

    async def test_expired_trade_cannot_match(self, db_session):
        """An expired pending trade is cancelled before match selection."""
        from sqlalchemy import update as sa_update

        from trading_service.domain.inter_chain import InterChainTrade
        from trading_service.services.inter_chain_service import InterChainTradeService
        from trading_service.services.matching_engine import MatchingEngine

        svc = InterChainTradeService(db_session)
        buy = await _make_trade(svc, source_chain="chain-a", dest_chain="chain-b", amount=100)
        sell = await _make_trade(
            svc, source_chain="chain-b", dest_chain="chain-a", sender="0xrecipient", recipient="0xsender", amount=100
        )
        past = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
        await db_session.execute(
            sa_update(InterChainTrade).where(InterChainTrade.trade_id == buy.trade_id).values(expires_at=past)
        )
        await db_session.commit()

        engine = MatchingEngine(db_session)
        result = await engine.match_trade(buy.trade_id)
        assert result is not None
        # Trade expired -> cancelled, so it reports not-pending, never matched.
        assert result["matched"] is False
        await db_session.refresh(sell)
        assert sell.status == "pending"


class TestSettleClaim:
    async def _escrowed_trade(self, svc, session):
        trade = await _make_trade(svc)
        trade.escrow_id = "esc-1"
        trade.settlement_phase = "escrow_created"
        await session.commit()
        return trade

    async def test_fresh_settling_marker_refuses_with_409(self, db_session, monkeypatch):
        """#1562: a second settle while the claim is fresh must not reach the RPC."""
        from trading_service.routers import settlement as settlement_router
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        trade = await self._escrowed_trade(svc, db_session)
        trade.settlement_phase = "settling"
        trade.updated_at = datetime.now(UTC)
        await db_session.commit()

        called = False

        class _FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def settle(self, escrow_id, secret):
                nonlocal called
                called = True
                return {"ok": True}

        monkeypatch.setattr(settlement_router, "_get_settlement_client", lambda: _FakeClient())
        resp = await settlement_router.settle_trade(trade.trade_id, secret="s3cr3t", svc=svc)
        assert resp.status_code == 409
        assert called is False
        await db_session.refresh(trade)
        assert trade.settlement_phase == "settling"

    async def test_stale_settling_marker_is_reclaimed(self, db_session, monkeypatch):
        """#1562: a marker older than the TTL means the caller died — retry proceeds."""
        from trading_service.routers import settlement as settlement_router
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        trade = await self._escrowed_trade(svc, db_session)
        trade.settlement_phase = "settling"
        trade.updated_at = datetime.now(UTC) - timedelta(seconds=600)
        await db_session.commit()

        class _FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def settle(self, escrow_id, secret):
                return {"ok": True}

        monkeypatch.setattr(settlement_router, "_get_settlement_client", lambda: _FakeClient())
        resp = await settlement_router.settle_trade(trade.trade_id, secret="s3cr3t", svc=svc)
        assert resp["result"] == {"ok": True}
        await db_session.refresh(trade)
        assert trade.settlement_phase == "settled"

    async def test_failed_settle_releases_claim(self, db_session, monkeypatch):
        """#1562: RPC failure restores the prior phase so the trade can retry."""
        from trading_service.routers import settlement as settlement_router
        from trading_service.services.inter_chain_service import InterChainTradeService

        svc = InterChainTradeService(db_session)
        trade = await self._escrowed_trade(svc, db_session)

        class _FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def settle(self, escrow_id, secret):
                raise RuntimeError("rpc down")

        monkeypatch.setattr(settlement_router, "_get_settlement_client", lambda: _FakeClient())
        resp = await settlement_router.settle_trade(trade.trade_id, secret="s3cr3t", svc=svc)
        assert resp.status_code == 502
        await db_session.refresh(trade)
        assert trade.settlement_phase == "escrow_created"


class TestInputHardening:
    """#1608: non-finite money inputs get client errors, not 500s."""

    async def test_create_trade_rejects_nan_price(self):
        from fastapi import HTTPException

        from trading_service.routers.inter_chain import create_inter_chain_trade

        class _Svc:
            async def create_trade(self, **kwargs):  # pragma: no cover - must not be reached
                raise AssertionError("create_trade must not run for NaN price")

        with pytest.raises(HTTPException) as exc:
            await create_inter_chain_trade(
                svc=_Svc(),
                source_chain="a",
                dest_chain="b",
                sender="0xs",
                recipient="0xr",
                amount=1,
                price=Decimal("NaN"),
            )
        assert exc.value.status_code == 400

    def test_search_offers_rejects_nan_price_bound(self):
        from trading_service.routers.subscriptions import search_offers

        resp = search_offers(min_price=Decimal("NaN"))
        assert resp.status_code == 400

    def test_exchange_rates_mirror_configured_fee(self, monkeypatch):
        """#1608: fee_percent reports EXCHANGE_FEE_PCT, not a hardcoded 0.5."""
        from trading_service.routers import exchange_compat

        monkeypatch.setenv("EXCHANGE_FEE_PCT", "0.005")
        assert exchange_compat.get_exchange_rates()["fee_percent"] == Decimal("0.005")
        monkeypatch.setenv("EXCHANGE_FEE_PCT", "nan")
        assert exchange_compat.get_exchange_rates()["fee_percent"] == Decimal("0")
        monkeypatch.delenv("EXCHANGE_FEE_PCT", raising=False)
        assert exchange_compat.get_exchange_rates()["fee_percent"] == Decimal("0")

    async def test_create_exchange_payment_rejects_nan(self):
        """#1608: NaN amounts must 400 before arithmetic, not 500 on compare."""
        from fastapi import HTTPException

        from trading_service.routers.exchange_compat import ExchangePaymentRequest, create_exchange_payment

        # Pydantic rejects NaN at the edge (422); model_construct bypasses
        # validation to pin the route-level guard for programmatic callers.
        req = ExchangePaymentRequest.model_construct(user_id="u", aitbc_amount=Decimal("NaN"), eth_amount=Decimal("0.001"))
        with pytest.raises(HTTPException) as exc:
            await create_exchange_payment(
                payment_request=req,
                background_tasks=MagicMock(),
                request=MagicMock(),
                session=MagicMock(),
            )
        assert exc.value.status_code == 400
