"""health_url guard and the anchor-negatives bound (Refs #819).

The Phase-0 pin (test_health_ssrf_anchor_dict.py) covers the loopback refusal
and the eviction of one expired entry. These cover the rest of the contract:
which targets are refused, the same-host opt-in, a public target still probed,
the reply not echoing resolved addresses, and the size cap.
"""

import asyncio
import socket
import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from market_service.domain.market import SoftwareService
from market_service.services import market_service as ms
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with get_session_context() as s:
        yield s


def _spy_client(attempted: list[str]):
    class SpyClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, **kw):
            attempted.append(str(url))
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            return resp

    return SpyClient


async def _health(session: AsyncSession, url: str) -> tuple[dict, list[str]]:
    plugin_id = f"svc-guard-{uuid4().hex[:12]}"
    session.add(SoftwareService(plugin_id=plugin_id, service_type="ffmpeg", health_url=url))
    await session.commit()
    attempted: list[str] = []
    with patch.object(httpx, "AsyncClient", _spy_client(attempted)):
        result = await MarketService(session).check_software_offer_health(plugin_id)
    return result, attempted


def _answer(*addresses: str):
    return AsyncMock(return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 80)) for a in addresses])


class TestHealthUrlGuard:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1:9/health",
            "http://10.1.223.136/ffmpeg/health",
            "http://192.168.1.5:8230/health",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]:8000/health",
            "http://0.0.0.0:8000/health",
            "file:///etc/passwd",
            "ftp://example.com/health",
            "http:///health",
        ],
    )
    async def test_non_public_or_non_http_targets_are_refused(self, session, url):
        result, attempted = await _health(session, url)
        assert not attempted
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_public_address_is_still_probed(self, session):
        result, attempted = await _health(session, "http://93.184.216.34/health")
        assert attempted == ["http://93.184.216.34/health"]
        assert result["healthy"] is True

    @pytest.mark.asyncio
    async def test_hostname_resolving_to_a_private_address_is_refused_without_echoing_it(self, session):
        with patch.object(asyncio.get_running_loop(), "getaddrinfo", new=_answer("10.0.0.7")):
            result, attempted = await _health(session, "http://shop.example.test/health")
        assert not attempted
        assert result["healthy"] is False
        assert "10.0.0.7" not in str(result), "reply must not reveal what a host resolved to"

    @pytest.mark.asyncio
    async def test_one_private_answer_among_public_ones_refuses_the_host(self, session):
        with patch.object(asyncio.get_running_loop(), "getaddrinfo", new=_answer("93.184.216.34", "10.0.0.7")):
            result, attempted = await _health(session, "http://mixed.example.test/health")
        assert not attempted
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_unresolvable_host_is_refused(self, session):
        with patch.object(asyncio.get_running_loop(), "getaddrinfo", new=AsyncMock(side_effect=OSError("nxdomain"))):
            result, attempted = await _health(session, "http://nowhere.example.test/health")
        assert not attempted
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_same_host_target_needs_the_explicit_opt_in(self, session, monkeypatch):
        monkeypatch.setenv(ms._HEALTH_ALLOWED_TARGETS_ENV, "localhost:8110, 127.0.0.1:8230")
        result, attempted = await _health(session, "http://localhost:8110/health")
        assert attempted == ["http://localhost:8110/health"]
        assert result["healthy"] is True
        # another port on the same host is not covered by the entry
        result, attempted = await _health(session, "http://localhost:9999/health")
        assert not attempted
        assert result["healthy"] is False


class TestAnchorNegativesBound:
    def test_eviction_drops_only_expired_entries(self, monkeypatch):
        monkeypatch.setattr(MarketService, "_anchor_negatives", {})
        now = time.monotonic()
        MarketService._anchor_negatives[("expired", "b")] = now - 1
        MarketService._anchor_negatives[("due", "b")] = now
        MarketService._anchor_negatives[("live", "b")] = now + 60
        MarketService._evict_anchor_negatives(now)
        assert set(MarketService._anchor_negatives) == {("live", "b")}

    def test_map_is_capped_and_keeps_the_latest_deadlines(self, monkeypatch):
        monkeypatch.setattr(ms, "_ANCHOR_NEGATIVES_MAX", 5)
        monkeypatch.setattr(MarketService, "_anchor_negatives", {})
        now = time.monotonic()
        for i in range(8):
            MarketService._remember_anchor_negative((f"k{i}", "b"), now + 100 + i)
        assert len(MarketService._anchor_negatives) == 5
        assert set(MarketService._anchor_negatives) == {(f"k{i}", "b") for i in range(3, 8)}
