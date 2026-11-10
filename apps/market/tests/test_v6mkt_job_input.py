"""Regression tests — market job input robustness (#1449).

* pin-confirm accepted negative/non-integer ``size`` and persisted it into
  ``job.payload`` where usage analytics sum it.
* the signed public job view built ``{canonical_address(...)}`` over stored
  addresses — one malformed legacy value 500'd the route.
* ``payload.size`` values predating the write-side validation must not 500
  or skew ``get_market_job_usage``.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from market_service.domain.market import MarketJob
from market_service.services.market_service import MarketService, _isoformat
from market_service.storage import get_session_context

pytestmark = pytest.mark.asyncio


def _uid() -> str:
    return uuid4().hex[:8]


async def test_pin_confirm_rejects_bad_size():
    from fastapi.testclient import TestClient

    from market_service.main import app

    async with get_session_context() as session:
        job_id = f"job_v6_pin_{_uid()}"
        session.add(
            MarketJob(
                id=job_id,
                buyer_address="0xab0797Ae8cfF09B313c71cAb2f894B342b6e1d76",
                provider_address="0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2",
                service_type="ipfs",
                state="QUEUED",
                offer_id="offer_x",
                payload={},
            )
        )
        await session.commit()
    with TestClient(app) as client:
        for bad in (-5, "lots", True, 1.5):
            r = client.post(f"/v1/market/jobs/{job_id}/pin-confirm", json={"size": bad})
            assert r.status_code == 400, f"size={bad!r} -> {r.status_code}"
        r = client.post(f"/v1/market/jobs/{job_id}/pin-confirm", json={"size": 42})
        assert r.status_code == 200


async def test_signed_job_view_tolerates_malformed_stored_address():
    """A job row whose stored address cannot canonicalize must still serve
    the authorised view instead of 500ing — the parties check skips
    unparseable stored addresses (#1449)."""
    from fastapi.testclient import TestClient

    from aitbc.crypto.crypto import derive_ethereum_address, sign_transaction_data
    from aitbc.market.job_request_signature import jobs_request_message
    from aitbc.utils.chain_id import resolve_chain_id
    from market_service.config import settings
    from market_service.main import app

    private_key = "0x" + "44" * 32
    provider = derive_ethereum_address(private_key)
    chain_id = settings.default_chain_id or resolve_chain_id()

    async with get_session_context() as session:
        job_id = f"job_v6_bad_{_uid()}"
        session.add(
            MarketJob(
                id=job_id,
                buyer_address="not-an-address!!!",
                provider_address=provider,
                service_type="ipfs",
                state="QUEUED",
                offer_id="offer_x",
                payload={},
            )
        )
        await session.commit()

    issued_at = int(time.time())
    signature = sign_transaction_data(
        jobs_request_message(provider, chain_id, issued_at, f"/v1/market/jobs/{job_id}"), private_key
    )
    with TestClient(app) as client:
        r = client.get(
            f"/v1/market/jobs/{job_id}",
            params={
                "signer_address": provider,
                "chain_id": chain_id,
                "issued_at": issued_at,
                "signature": signature,
            },
        )
        assert r.status_code == 200


async def test_isoformat_tolerates_non_datetime_values():
    """_isoformat degrades legacy non-datetime column values instead of
    raising inside the public serializers (#1449)."""
    assert _isoformat(None) is None
    assert _isoformat("2025-01-01") == "2025-01-01"
    assert _isoformat(123) == "123"
    dt = datetime(2025, 1, 2, 3, 4, 5)
    assert _isoformat(dt) == dt.isoformat()


async def test_job_usage_tolerates_malformed_payload_size():
    """Legacy/corrupt payload.size values must not 500 or skew the usage
    total (#1449): non-numeric rows are skipped, negatives clamp to 0."""
    async with get_session_context() as session:
        u = _uid()
        offer_id = f"offer_v6_usage_{u}"
        buyer = "0xab0797Ae8cfF09B313c71cAb2f894B342b6e1d76"
        for i, size in enumerate(["lots", -5, 10, None]):
            session.add(
                MarketJob(
                    id=f"job_v6_usage_{u}_{i}",
                    buyer_address=buyer,
                    provider_address="0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2",
                    service_type="ipfs",
                    state="RUNNING",
                    offer_id=offer_id,
                    payload={"size": size},
                )
            )
        await session.commit()
        svc = MarketService(session)
        assert await svc.get_market_job_usage(buyer, offer_id) == 10
