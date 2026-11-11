"""SHOP-TOKEN-REUSE-1 (#1817): shop access tokens must not work on terminal jobs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import pytest
from fastapi.testclient import TestClient

from market_service.domain.market import MarketJob, SoftwareService
from market_service.main import app
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context

_TERMINAL = ("COMPLETED", "RELEASED", "EXPIRED", "CANCELED", "REFUNDED", "FAILED")
_ACTIVE = ("QUEUED", "RUNNING")


async def _seed_access_job(session, *, tag: str, state: str) -> tuple[str, str]:
    svc = MarketService(session)
    ak = f"ak_{tag}"
    secret = f"sec_{tag}"
    session.add(SoftwareService(service_type="ipfs", offer_id="offer-1"))
    await session.commit()
    created = await svc.create_market_job(
        {
            "offer_id": "offer-1",
            "service_type": "ipfs",
            "buyer_address": "0xab0797Ae8cfF09B313c71cAb2f894B342b6e1d76",
            "provider_address": "0x241D3e44d42b6d4c270d0231780913f14386d90C",
            "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
            "payload": {"cid": "QmTest", "access_key": ak, "access_secret": secret},
        }
    )
    job = await session.get(MarketJob, created["job_id"])
    assert job is not None
    job.state = state
    session.add(job)
    await session.commit()
    return ak, secret


@pytest.mark.asyncio
@pytest.mark.parametrize("state", _TERMINAL)
async def test_access_token_denied_for_terminal_job_states(state: str) -> None:
    async with get_session_context() as session:
        svc = MarketService(session)
        ak, secret = await _seed_access_job(session, tag=state.lower(), state=state)
        assert await svc.get_market_job_access_token(ak, secret) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("state", _ACTIVE)
async def test_access_token_allowed_for_active_job_states(state: str) -> None:
    async with get_session_context() as session:
        svc = MarketService(session)
        ak, secret = await _seed_access_job(session, tag=state.lower(), state=state)
        tok = await svc.get_market_job_access_token(ak, secret)
        assert tok is not None
        assert tok.get("cid") == "QmTest"


@pytest.mark.asyncio
async def test_market_access_http_replay_after_completed_returns_404() -> None:
    """Replayed shop verify call against a completed job must not mint access."""
    async with get_session_context() as session:
        ak, secret = await _seed_access_job(session, tag="httpreplay", state="COMPLETED")

    client = TestClient(app)
    ok = client.get(f"/v1/market/access/{ak}", headers={"X-Access-Secret": secret})
    assert ok.status_code == 404

    # Second identical call — no credential reuse on terminal jobs.
    again = client.get(f"/v1/market/access/{ak}", headers={"X-Access-Secret": secret})
    assert again.status_code == 404
    assert again.json().get("error")
