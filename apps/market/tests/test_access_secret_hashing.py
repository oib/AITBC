"""Tests for at-rest hashing of IPFS rental / market-job access secrets.

The plaintext secret is a bearer credential the customer receives once at
purchase; the DB must store only its sha256 digest so a database leak does
not hand out working credentials. ``_migrate_access_secrets`` upgrades
rows written by pre-migration versions on startup.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from market_service.domain.market import IpfsRentalToken, MarketJob
from market_service.services.market_service import (
    MarketService,
    hash_access_secret,
    is_hashed_secret,
)
from market_service.storage import get_session_context


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with get_session_context() as session:
        yield session


def _unique(prefix: str) -> str:
    """Per-attempt unique key — pytest-rerunfailures retries share the session DB."""
    from uuid import uuid4

    return f"{prefix}_{uuid4().hex[:8]}"


def _token_data(access_key: str, secret: str) -> dict[str, Any]:
    return {
        "access_key": access_key,
        "access_secret": secret,
        "rental_id": f"rental_{access_key}",
        "offer_id": "offer-1",
        "cid": "QmTest",
        "buyer_address": "0xab0797Ae8cfF09B313c71cAb2f894B342b6e1d76",
        "provider_address": "0x241D3e44d42b6d4c270d0231780913f14386d90C",
        "escrow_contract_id": f"escrow_{access_key}",
        "status": "active",
    }


async def test_register_stores_digest_not_plaintext(session: AsyncSession) -> None:
    svc = MarketService(session)
    ak1 = _unique("ak1")
    await svc.register_ipfs_rental_token(_token_data(ak1, "plain-secret"))

    stored = await svc.get_ipfs_rental_token(ak1, "plain-secret")
    assert stored is not None

    row = await session.get(IpfsRentalToken, ak1)
    assert row is not None
    assert is_hashed_secret(row.access_secret)
    assert row.access_secret == hash_access_secret("plain-secret")
    assert "plain-secret" not in row.access_secret


async def test_wrong_secret_rejected(session: AsyncSession) -> None:
    svc = MarketService(session)
    ak2 = _unique("ak2")
    await svc.register_ipfs_rental_token(_token_data(ak2, "right-secret"))
    assert await svc.get_ipfs_rental_token(ak2, "wrong-secret") is None


async def test_upsert_rehashes_new_secret(session: AsyncSession) -> None:
    svc = MarketService(session)
    ak3 = _unique("ak3")
    await svc.register_ipfs_rental_token(_token_data(ak3, "first-secret"))
    await svc.register_ipfs_rental_token(_token_data(ak3, "second-secret"))

    assert await svc.get_ipfs_rental_token(ak3, "first-secret") is None
    assert await svc.get_ipfs_rental_token(ak3, "second-secret") is not None


async def test_legacy_plaintext_row_still_verifies(session: AsyncSession) -> None:
    """Rows written before the migration keep working until init_db rewrites them."""
    akl = _unique("akl")
    token = IpfsRentalToken(**_token_data(akl, "legacy-secret"))
    session.add(token)
    await session.commit()

    svc = MarketService(session)
    assert await svc.get_ipfs_rental_token(akl, "legacy-secret") is not None


async def test_job_payload_secret_hashed(session: AsyncSession) -> None:
    svc = MarketService(session)
    jak = _unique("jak")
    job = await svc.create_market_job(
        {
            "offer_id": "offer-1",
            "service_type": "ipfs",
            "buyer_address": "0xab0797Ae8cfF09B313c71cAb2f894B342b6e1d76",
            "provider_address": "0x241D3e44d42b6d4c270d0231780913f14386d90C",
            "payload": {
                "cid": "QmTest",
                "access_key": jak,
                "access_secret": "job-secret",
            },
        }
    )
    job_id = job["job_id"]

    row = await session.get(MarketJob, job_id)
    assert row is not None
    assert is_hashed_secret(row.payload["access_secret"])
    assert "job-secret" not in row.payload["access_secret"]

    assert await svc.get_market_job_access_token(jak, "job-secret") is not None
    assert await svc.get_market_job_access_token(jak, "nope") is None


async def test_migrate_access_secrets_upgrades_plaintext_rows(session: AsyncSession) -> None:
    """The startup migration hashes rows written by pre-migration versions."""
    from market_service import storage

    akm = _unique("akm")
    jakm = _unique("jakm")
    token = IpfsRentalToken(**_token_data(akm, "old-plaintext"))
    session.add(token)
    job = MarketJob(
        offer_id="offer-1",
        service_type="ipfs",
        buyer_address="0xab0797ae8cff09b313c71cab2f894b342b6e1d76",
        provider_address="0x241d3e44d42b6d4c270d0231780913f14386d90c",
        state="RUNNING",
        access_key=jakm,  # denormalized column — create_market_job copies it from payload
        payload={"cid": "QmX", "access_key": jakm, "access_secret": "old-job-secret"},
    )
    session.add(job)
    await session.commit()

    await storage._migrate_access_secrets()  # noqa: SLF001

    await session.refresh(token)
    await session.refresh(job)
    assert is_hashed_secret(token.access_secret)
    assert is_hashed_secret(job.payload["access_secret"])

    svc = MarketService(session)
    assert await svc.get_ipfs_rental_token(akm, "old-plaintext") is not None
    assert await svc.get_market_job_access_token(jakm, "old-job-secret") is not None


def test_access_endpoint_requires_api_key() -> None:
    """The job access endpoint must not serve credentials unauthenticated."""
    from fastapi.testclient import TestClient

    from market_service.main import app

    client = TestClient(app)
    response = client.get("/v1/market/jobs/some-job/access")
    # 401/403 = rejected with a configured key; 501 = no key configured
    # (APIKeyAuthenticator fails closed either way).
    assert response.status_code in (401, 403, 501)
