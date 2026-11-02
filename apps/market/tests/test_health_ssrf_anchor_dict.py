"""Phase-0 pin for MARKET-HEALTH-SSRF-ANCHOR-DICT-1 (#819, LOW).

Two findings:

1. ``GET /v1/market/offer/{plugin_id}/health`` POSTs/GETs the provider-
   registered ``health_url`` — any wallet can register a service, so an
   anonymous caller can aim the market service at LAN/loopback/metadata
   endpoints (blind SSRF, same class as #800). Desired: the URL is
   resolved+validated like the miner download fix — non-global addresses
   refused before the request. FAILS on current main: the outbound
   request is attempted.

2. ``MarketService._anchor_negatives`` is a CLASS attribute shared by
   every instance, written at every unresolvable anchor probe and never
   evicted — entries are compared by deadline (:800) but never deleted
   (:828 only writes), so churned signable registrations grow process
   memory unboundedly. Desired: expired entries are evicted (or the map
   is instance-scoped + bounded). FAILS on current main: an expired
   entry persists through a resolve pass.
"""

import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from market_service.domain.market import SoftwareService
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with get_session_context() as s:
        yield s


class TestHealthUrlSsrf:
    @pytest.mark.asyncio
    async def test_loopback_health_url_is_refused(self, session):
        svc = MarketService(session)
        svc_row = SoftwareService(
            plugin_id="svc-ssrf-1",
            service_type="ffmpeg",
            health_url="http://127.0.0.1:9/api/v0/version",
        )
        session.add(svc_row)
        await session.commit()

        attempted: list[str] = []

        class SpyClient:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return None

            async def post(self, url, **kw):
                attempted.append(str(url))
                m = MagicMock()
                m.raise_for_status = MagicMock()
                m.json = MagicMock(return_value={})
                m.status_code = 200
                m.text = ""
                return m

            async def get(self, url, **kw):
                attempted.append(str(url))
                m = MagicMock()
                m.raise_for_status = MagicMock()
                m.status_code = 200
                return m

        import httpx as _httpx

        orig = _httpx.AsyncClient
        try:
            _httpx.AsyncClient = SpyClient  # type: ignore[assignment]
            result = await svc.check_software_offer_health("svc-ssrf-1")
        finally:
            _httpx.AsyncClient = orig  # type: ignore[assignment]

        assert not attempted, f"health check attempted an outbound request to a loopback target: {attempted}"
        assert result.get("healthy") is not True


class TestAnchorNegativesEviction:
    @pytest.mark.asyncio
    async def test_expired_negative_entries_are_evicted(self, session):
        svc = MarketService(session)
        key = ("offer-x", "0xBinding")
        svc._anchor_negatives[key] = time.monotonic() - 1  # already expired
        svc._rpc_client.query_transactions = AsyncMock(return_value=[])
        await svc._resolve_offer_anchors(
            [{"offer_id": "offer-x", "provider": "0xProvider", "chain_id": "ait-testchain"}],
            "ait-testchain",
        )
        assert key not in svc._anchor_negatives, (
            "expired anchor-negative entry survived a resolve pass — the class-level map never evicts"
        )
