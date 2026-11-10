"""Regression tests — market job cancel auth + rating sync (#1634).

* ``POST /jobs/{id}/cancel`` ignored caller-supplied wallet signatures: a
  foreign signer was neither verified nor rejected. A presented signature
  must now verify AND belong to a job party; the unsigned API-key path stays
  for the operator tier.
* ``sync_ratings_from_remote`` trusted caller-supplied ``source_node`` and
  deduped reviewers case-sensitively.
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from market_service.domain.market import MarketJob, ServiceRating
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context

pytestmark = pytest.mark.asyncio


def _uid() -> str:
    return uuid4().hex[:8]


# ---------------------------------------------------------------------------
# cancel party signature
# ---------------------------------------------------------------------------


async def _seed_cancel_job() -> tuple[str, str, str]:
    """Return (job_id, buyer_private_key, provider_private_key) for a QUEUED job."""
    from aitbc.crypto.crypto import derive_ethereum_address

    buyer_key, provider_key = "0x" + "11" * 32, "0x" + "22" * 32
    async with get_session_context() as session:
        job_id = f"job_v6_cancel_{_uid()}"
        session.add(
            MarketJob(
                id=job_id,
                buyer_address=derive_ethereum_address(buyer_key),
                provider_address=derive_ethereum_address(provider_key),
                service_type="ipfs",
                state="QUEUED",
                offer_id="offer_x",
                payload={},
            )
        )
        await session.commit()
    return job_id, buyer_key, provider_key


def _cancel_signature(job_id: str, private_key: str, address: str) -> dict:
    from aitbc.market.job_request_signature import jobs_request_message
    from aitbc.utils.chain_id import resolve_chain_id
    from market_service.config import settings

    chain_id = settings.default_chain_id or resolve_chain_id()
    issued_at = int(time.time())
    from aitbc.crypto.crypto import sign_transaction_data

    return {
        "signer_address": address,
        "chain_id": chain_id,
        "issued_at": issued_at,
        "signature": sign_transaction_data(
            jobs_request_message(address, chain_id, issued_at, f"/v1/market/jobs/{job_id}/cancel"), private_key
        ),
    }


async def test_cancel_signed_by_job_party_succeeds():
    from fastapi.testclient import TestClient

    from aitbc.crypto.crypto import derive_ethereum_address
    from market_service.main import app

    job_id, buyer_key, _ = await _seed_cancel_job()
    proof = _cancel_signature(job_id, buyer_key, derive_ethereum_address(buyer_key))
    with TestClient(app) as client:
        r = client.post(f"/v1/market/jobs/{job_id}/cancel", json={"reason": "buyer_requested", **proof})
        assert r.status_code == 200
        assert r.json()["state"] == "CANCELED"


async def test_cancel_signed_by_non_party_is_403():
    from fastapi.testclient import TestClient

    from aitbc.crypto.crypto import derive_ethereum_address
    from market_service.main import app

    job_id, _, _ = await _seed_cancel_job()
    stranger_key = "0x" + "33" * 32
    proof = _cancel_signature(job_id, stranger_key, derive_ethereum_address(stranger_key))
    with TestClient(app) as client:
        r = client.post(f"/v1/market/jobs/{job_id}/cancel", json={"reason": "buyer_requested", **proof})
        assert r.status_code == 403
        # And the job must be untouched.
        async with get_session_context() as session:
            job = await session.get(MarketJob, job_id)
            assert job is not None and job.state == "QUEUED"


async def test_cancel_unsigned_api_key_path_still_works():
    from fastapi.testclient import TestClient

    from market_service.main import app

    job_id, _, _ = await _seed_cancel_job()
    with TestClient(app) as client:
        r = client.post(f"/v1/market/jobs/{job_id}/cancel", json={"reason": "buyer_requested"})
        assert r.status_code == 200
        assert r.json()["state"] == "CANCELED"


# ---------------------------------------------------------------------------
# rating sync hardening
# ---------------------------------------------------------------------------


async def test_rating_sync_dedupes_reviewer_case_insensitively():
    """'Rev_1' and 'rev_1' are the same reviewer — the second sync must not
    create a second rating row (#1634)."""
    async with get_session_context() as session:
        svc = MarketService(session)
        u = _uid()
        sid = f"svc_v6_{u}"
        base = {
            "service_id": sid,
            "rating": 4.0,
            "comment": "",
            "created_at": datetime.now(UTC).isoformat(),
            "source_node": "node-a",
        }
        out1 = await svc.sync_ratings_from_remote([{**base, "id": f"r1_{u}", "reviewer_id": "Rev_1"}])
        out2 = await svc.sync_ratings_from_remote([{**base, "id": f"r2_{u}", "reviewer_id": "rev_1"}])
        assert out1["synced"] == 1
        assert out2["synced"] == 0
        from sqlmodel import col, select

        rows = (await session.execute(select(ServiceRating).where(col(ServiceRating.service_id) == sid))).scalars().all()
        assert len(rows) == 1


async def test_rating_sync_source_node_is_sanitized():
    """Caller-supplied source_node is stored stripped and length-bounded
    (#1634)."""
    async with get_session_context() as session:
        svc = MarketService(session)
        u = _uid()
        sid = f"svc_v6b_{u}"
        out = await svc.sync_ratings_from_remote(
            [
                {
                    "id": f"r_{u}",
                    "service_id": sid,
                    "rating": 5.0,
                    "reviewer_id": f"rev_{u}",
                    "comment": "",
                    "created_at": datetime.now(UTC).isoformat(),
                    "source_node": "  " + "x" * 300 + "  ",
                }
            ]
        )
        assert out["synced"] == 1
        from sqlmodel import col, select

        row = (await session.execute(select(ServiceRating).where(col(ServiceRating.service_id) == sid))).scalar_one()
        assert row.source_node == "x" * 128
