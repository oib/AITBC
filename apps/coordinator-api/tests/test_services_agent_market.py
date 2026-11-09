"""Service-layer tests for agent_coordination/services/agent_market.py
(#1289 round 7+) — AgentServiceMarket, the in-memory agent service market.

Covers service listing (price/description gates), request lifecycle
(pending→accepted→completed), dynamic pricing, market fee split, ratings,
guilds, search filters and analytics. initialize() is NOT called — it
spawns infinite background loops by design.

Documented-as-contract stubs: ``_get_agent_reputation`` returns a
hardcoded 1000 and ``_update_agent_reputation`` is a no-op, so the
reputation gates always pass and rating-driven reputation changes are
discarded (source comments mark both "simplified").

The defect originally pinned strict-xfail was fixed in #1319 (same
branch): ``rate_service`` now rejects re-rating a completed request.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from coordinator_api.contexts.agent_coordination.services.agent_market import (
    AgentServiceMarket,
    GuildStatus,
    RequestStatus,
    ServiceStatus,
    ServiceType,
)


@pytest.fixture
def market() -> AgentServiceMarket:
    return AgentServiceMarket(config={})


async def _list(market: AgentServiceMarket, agent_id: str = "agent-1", **overrides: Any):
    kwargs: dict[str, Any] = {
        "service_type": ServiceType.DATA_ANALYSIS,
        "name": "Data analysis service",
        "description": "Professional data analysis and reporting",
        "metadata": {},
        "base_price": Decimal("5.0"),
        "tags": ["data", "analytics"],
        "capabilities": ["pandas"],
        "requirements": [],
    }
    kwargs.update(overrides)
    return await market.list_service(agent_id, **kwargs)


async def _request(market: AgentServiceMarket, service_id: str, client_id: str = "client-1", **overrides: Any):
    kwargs: dict[str, Any] = {
        "budget": Decimal("10.0"),
        "requirements": "need it fast",
        "deadline": datetime.now(UTC) + timedelta(days=7),
    }
    kwargs.update(overrides)
    return await market.request_service(client_id, service_id, **kwargs)


class TestListService:
    async def test_list_happy_path(self, market: AgentServiceMarket) -> None:
        service = await _list(market)
        assert service.id
        assert service.agent_id == "agent-1"
        assert service.status == ServiceStatus.ACTIVE
        assert service.reputation == 1000  # stub
        assert service.availability["monday"] is True
        assert service.availability["saturday"] is False
        assert market.services[service.id] is service
        assert market.agent_services["agent-1"] == [service.id]
        assert market.services_by_type["data_analysis"] == [service.id]
        assert market.categories["data_analysis"].service_count == 1

    @pytest.mark.parametrize(
        "overrides,match",
        [
            ({"base_price": Decimal("0.0001")}, "below minimum"),
            ({"base_price": Decimal("1001")}, "above maximum"),
            ({"description": "short"}, "Description too short"),
            ({"description": ""}, "Description too short"),
        ],
    )
    async def test_list_validation(self, market: AgentServiceMarket, overrides: dict[str, Any], match: str) -> None:
        with pytest.raises(ValueError, match=match):
            await _list(market, **overrides)

    async def test_list_boundary_prices(self, market: AgentServiceMarket) -> None:
        lo = await _list(market, base_price=Decimal("0.001"))
        hi = await _list(market, base_price=Decimal("1000.0"))
        assert lo.base_price == Decimal("0.001")
        assert hi.base_price == Decimal("1000.0")


class TestRequestService:
    async def test_request_happy_path(self, market: AgentServiceMarket) -> None:
        service = await _list(market)
        req = await _request(market, service.id)
        assert req.status == RequestStatus.PENDING
        assert req.client_id == "client-1"
        assert req.payment == Decimal("0.0")
        assert market.client_requests["client-1"] == [req.id]

    async def test_request_unknown_service(self, market: AgentServiceMarket) -> None:
        with pytest.raises(ValueError, match="Service not found"):
            await _request(market, "svc_missing")

    async def test_request_budget_below_price(self, market: AgentServiceMarket) -> None:
        service = await _list(market, base_price=Decimal("5.0"))
        with pytest.raises(ValueError, match="Budget below"):
            await _request(market, service.id, budget=Decimal("4.99"))

    async def test_request_past_deadline(self, market: AgentServiceMarket) -> None:
        service = await _list(market)
        with pytest.raises(ValueError, match="Invalid deadline"):
            await _request(market, service.id, deadline=datetime.now(UTC) - timedelta(seconds=1))

    async def test_request_deadline_too_far(self, market: AgentServiceMarket) -> None:
        service = await _list(market)
        with pytest.raises(ValueError, match="too far"):
            await _request(market, service.id, deadline=datetime.now(UTC) + timedelta(days=366))

    async def test_request_inactive_service(self, market: AgentServiceMarket) -> None:
        service = await _list(market)
        service.status = ServiceStatus.SUSPENDED
        with pytest.raises(ValueError, match="not active"):
            await _request(market, service.id)


class TestAcceptComplete:
    async def _accepted(self, market: AgentServiceMarket):
        service = await _list(market, base_price=Decimal("5.0"))
        req = await _request(market, service.id, budget=Decimal("10.0"))
        await market.accept_request(req.id, "agent-1")
        return service, market.service_requests[req.id]

    async def test_accept_sets_payment_and_status(self, market: AgentServiceMarket) -> None:
        service, req = await self._accepted(market)
        assert req.status == RequestStatus.ACCEPTED
        assert req.assigned_agent == "agent-1"
        assert req.accepted_at is not None
        # dynamic price = 5.0 * rep(1.05) * demand(1.0) * rating(1.0) = 5.25, under budget
        assert req.payment == pytest.approx(Decimal("5.25"))

    async def test_accept_guards(self, market: AgentServiceMarket) -> None:
        service = await _list(market)
        req = await _request(market, service.id)
        with pytest.raises(ValueError, match="not found"):
            await market.accept_request("req_missing", "agent-1")
        with pytest.raises(ValueError, match="Not service provider"):
            await market.accept_request(req.id, "agent-2")
        await market.accept_request(req.id, "agent-1")
        with pytest.raises(ValueError, match="not pending"):
            await market.accept_request(req.id, "agent-1")

    async def test_complete_pays_agent_minus_fee(self, market: AgentServiceMarket) -> None:
        service, req = await self._accepted(market)
        assert await market.complete_request(req.id, "agent-1", {"out": 1}) is True
        assert req.status == RequestStatus.COMPLETED
        assert req.completed_at is not None
        assert req.results_hash is not None and len(req.results_hash) == 64
        # payment 5.25, fee 2.5% = 0.13125, agent gets 5.11875
        assert service.total_earnings == pytest.approx(Decimal("5.11875"))
        assert service.completed_jobs == 1
        assert market.categories["data_analysis"].total_volume == pytest.approx(Decimal("5.25"))

    async def test_complete_guards(self, market: AgentServiceMarket) -> None:
        service = await _list(market)
        req = await _request(market, service.id)
        with pytest.raises(ValueError, match="not accepted"):
            await market.complete_request(req.id, "agent-1", {})
        await market.accept_request(req.id, "agent-1")
        with pytest.raises(ValueError, match="Not assigned agent"):
            await market.complete_request(req.id, "agent-2", {})

    async def test_payment_capped_at_budget(self, market: AgentServiceMarket) -> None:
        # tiny budget just above base price: dynamic price (9.45) exceeds
        # budget (9.4) -> payment capped at budget
        service = await _list(market, base_price=Decimal("9.0"))
        req = await _request(market, service.id, budget=Decimal("9.4"))
        await market.accept_request(req.id, "agent-1")
        assert market.service_requests[req.id].payment == Decimal("9.4")


class TestRateService:
    async def _completed(self, market: AgentServiceMarket):
        service = await _list(market)
        req = await _request(market, service.id)
        await market.accept_request(req.id, "agent-1")
        await market.complete_request(req.id, "agent-1", {})
        return service, market.service_requests[req.id]

    async def test_rate_updates_average(self, market: AgentServiceMarket) -> None:
        service, req = await self._completed(market)
        assert await market.rate_service(req.id, "client-1", 5, "great") is True
        assert req.rating == 5
        assert req.review == "great"
        assert service.average_rating == pytest.approx(5.0)
        assert service.rating_count == 1

    async def test_rate_guards(self, market: AgentServiceMarket) -> None:
        service = await _list(market)
        req = await _request(market, service.id)
        with pytest.raises(ValueError, match="not completed"):
            await market.rate_service(req.id, "client-1", 5, "early")
        await market.accept_request(req.id, "agent-1")
        await market.complete_request(req.id, "agent-1", {})
        with pytest.raises(ValueError, match="Not request client"):
            await market.rate_service(req.id, "client-2", 5, "impostor")
        with pytest.raises(ValueError, match="Invalid rating"):
            await market.rate_service(req.id, "client-1", 0, "zero")
        with pytest.raises(ValueError, match="Invalid rating"):
            await market.rate_service(req.id, "client-1", 6, "six")

    async def test_rate_twice_rejected(self, market: AgentServiceMarket) -> None:
        service, req = await self._completed(market)
        await market.rate_service(req.id, "client-1", 5, "first")
        with pytest.raises(ValueError, match="already rated"):
            await market.rate_service(req.id, "client-1", 1, "second")
        assert service.rating_count == 1

    async def test_rating_reputation_change_is_discarded(self, market: AgentServiceMarket) -> None:
        """Documents the simplified stub: _update_agent_reputation is a no-op,
        so ratings never move agent reputation (always 1000)."""
        _, req = await self._completed(market)
        await market.rate_service(req.id, "client-1", 1, "bad")
        assert await market._get_agent_reputation("agent-1") == 1000


class TestGuilds:
    async def test_create_guild(self, market: AgentServiceMarket) -> None:
        guild = await market.create_guild(
            "founder-1",
            "Data Guild",
            "desc",
            ServiceType.DATA_ANALYSIS,
            requirements=[],
            benefits=[],
            guild_rules={},
        )
        assert guild.member_count == 1
        assert guild.founder == "founder-1"
        assert guild.members["founder-1"]["role"] == "founder"
        assert market.agent_guilds["founder-1"] == guild.id
        assert market.guilds_by_category["data_analysis"] == [guild.id]

    async def test_create_guild_guards(self, market: AgentServiceMarket) -> None:
        with pytest.raises(ValueError, match="Invalid guild name"):
            await market.create_guild("f", "ab", "d", ServiceType.DATA_ANALYSIS, [], [], {})

    async def test_join_guild(self, market: AgentServiceMarket) -> None:
        guild = await market.create_guild("founder-1", "Guild", "d", ServiceType.DATA_ANALYSIS, [], [], {})
        assert await market.join_guild("agent-2", guild.id) is True
        assert guild.member_count == 2
        assert guild.members["agent-2"]["role"] == "member"
        with pytest.raises(ValueError, match="Already a member"):
            await market.join_guild("agent-2", guild.id)
        with pytest.raises(ValueError, match="not found"):
            await market.join_guild("agent-3", "guild_missing")

    async def test_join_inactive_guild(self, market: AgentServiceMarket) -> None:
        guild = await market.create_guild("founder-1", "Guild", "d", ServiceType.DATA_ANALYSIS, [], [], {})
        guild.status = GuildStatus.INACTIVE
        with pytest.raises(ValueError, match="not active"):
            await market.join_guild("agent-2", guild.id)


class TestSearchAndQueries:
    async def test_search_filters_and_sort(self, market: AgentServiceMarket) -> None:
        cheap = await _list(market, name="Cheap data", base_price=Decimal("1.0"), tags=["budget"])
        pricey = await _list(
            market,
            agent_id="agent-2",
            name="Pricey research",
            service_type=ServiceType.RESEARCH,
            base_price=Decimal("50.0"),
            tags=["premium"],
        )
        # rate cheap service 5 stars via full lifecycle for sort check
        req = await _request(market, cheap.id)
        await market.accept_request(req.id, "agent-1")
        await market.complete_request(req.id, "agent-1", {})
        await market.rate_service(req.id, "client-1", 5, "love it")

        all_svcs = await market.search_services()
        assert len(all_svcs) == 2
        assert all_svcs[0].id == cheap.id  # rated 5.0 sorts first
        assert [s.id for s in await market.search_services(service_type=ServiceType.RESEARCH)] == [pricey.id]
        assert [s.id for s in await market.search_services(min_price=Decimal("10"))] == [pricey.id]
        assert [s.id for s in await market.search_services(max_price=Decimal("10"))] == [cheap.id]
        assert [s.id for s in await market.search_services(tags=["premium"])] == [pricey.id]
        assert [s.id for s in await market.search_services(query="pricey")] == [pricey.id]
        assert [s.id for s in await market.search_services(min_rating=4.0)] == [cheap.id]
        # limit/offset
        assert len(await market.search_services(limit=1)) == 1
        assert await market.search_services(offset=1, limit=1) != []

    async def test_get_agent_services_and_client_requests(self, market: AgentServiceMarket) -> None:
        service = await _list(market)
        svcs = await market.get_agent_services("agent-1")
        assert [s.id for s in svcs] == [service.id]
        assert await market.get_agent_services("ghost") == []
        req = await _request(market, service.id)
        reqs = await market.get_client_requests("client-1")
        assert [r.id for r in reqs] == [req.id]
        assert await market.get_client_requests("ghost") == []

    async def test_market_analytics(self, market: AgentServiceMarket) -> None:
        service = await _list(market, base_price=Decimal("5.0"))
        req = await _request(market, service.id)
        await market.accept_request(req.id, "agent-1")
        await market.complete_request(req.id, "agent-1", {})
        analytics = await market.get_market_analytics()
        assert analytics.total_services == 1
        assert analytics.active_services == 1
        assert analytics.total_requests == 1
        assert analytics.pending_requests == 0
        assert analytics.average_service_price == Decimal("5.0")
        assert analytics.popular_categories == ["data_analysis"]
        assert analytics.top_agents == ["agent-1"]

    async def test_dynamic_price_reputation_and_demand(self, market: AgentServiceMarket) -> None:
        service = await _list(market, base_price=Decimal("10.0"))
        # rep 1000 -> 1.05x; rating 0 -> 1.0x; jobs 0 -> 1.0x => 10.5
        price = await market._calculate_dynamic_price(service.id, Decimal("100"))
        assert price == pytest.approx(Decimal("10.5"))
        service.average_rating = 5.0  # 1 + 5/5*0.3 = 1.3
        service.completed_jobs = 20  # 1 + 20/100*0.5 = 1.1
        price = await market._calculate_dynamic_price(service.id, Decimal("100"))
        assert price == pytest.approx(Decimal("10.0") * Decimal("1.05") * Decimal("1.1") * Decimal("1.3"))
        # unknown service -> budget passthrough
        assert await market._calculate_dynamic_price("missing", Decimal("7")) == Decimal("7")
