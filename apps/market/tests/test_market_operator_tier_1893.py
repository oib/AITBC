"""#1893 MARKET-SVC-BINDING-1 pins: the market API key is user-distributed,
so unsigned party actions must present the operator credential.

Pre-fix: ``MARKET_API_KEY`` alone could cancel/dispute/release/refund any
job, book offers as any wallet, and cancel any offer — the wallet signature
was optional. Now: party signature OR ``MARKET_OPERATOR_API_KEY``.
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from market_service.domain.market import MarketJob, MarketJobPayment, MarketOffer
from market_service.storage import get_session_context

pytestmark = pytest.mark.asyncio

USER_KEY = "user-tier-key"
OP_KEY = "operator-tier-key"


def _uid() -> str:
    return uuid4().hex[:8]


@pytest.fixture
def tiered_keys(monkeypatch: pytest.MonkeyPatch):
    """Auth enabled with distinct user/operator keys bound to the deps."""
    from market_service import main as market_main
    from market_service.config import settings

    monkeypatch.setattr(market_main._market_user_key_auth, "expected_key", USER_KEY)
    monkeypatch.setattr(market_main._market_operator_key_auth, "expected_key", OP_KEY)
    monkeypatch.setattr(settings, "api_key", USER_KEY)
    monkeypatch.setattr(settings, "operator_api_key", OP_KEY)
    market_main._market_user_key_auth.auth_enabled = True
    market_main._market_operator_key_auth.auth_enabled = True


def _headers(key: str) -> dict[str, str]:
    return {"X-Api-Key": key}


async def _seed_settle_job(state: str = "RUNNING") -> str:
    async with get_session_context() as session:
        job_id = f"job_1893_{_uid()}"
        payment = MarketJobPayment(
            job_id=job_id,
            amount=Decimal("1.0"),
            status="escrowed",
            escrowed_at=datetime.now(UTC).replace(tzinfo=None),
        )
        session.add(payment)
        await session.flush()
        session.add(
            MarketJob(
                id=job_id,
                buyer_address="0x" + "11" * 20,
                provider_address="0x" + "22" * 20,
                service_type="ipfs",
                state=state,
                offer_id="offer_x",
                payload={"provider_confirmed": True},
                payment_id=payment.id,
                payment_status="escrowed",
            )
        )
        await session.commit()
    return job_id


@pytest.fixture
def stub_escrow_rpc(monkeypatch: pytest.MonkeyPatch):
    from aitbc.market import BlockchainRPCClient

    async def _release(self, job_id: str, body: dict | None = None):
        return {"success": True, "tx_hash": f"0xrelease_{job_id}"}

    async def _refund(self, job_id: str, body: dict | None = None):
        return {"success": True, "tx_hash": f"0xrefund_{job_id}"}

    monkeypatch.setattr(BlockchainRPCClient, "release_escrow", _release)
    monkeypatch.setattr(BlockchainRPCClient, "refund_escrow", _refund)


class TestUnsignedUserKeyRefused:
    """The user-tier key alone must not move escrow or mutate objects."""

    @pytest.mark.parametrize("action", ["cancel", "dispute", "release", "refund"])
    async def test_unsigned_user_key_403(self, tiered_keys, stub_escrow_rpc, action: str) -> None:
        from fastapi.testclient import TestClient
        from market_service.main import app

        job_id = await _seed_settle_job(state="CANCELED" if action == "refund" else "RUNNING")
        with TestClient(app) as client:
            r = client.post(f"/v1/market/jobs/{job_id}/{action}", json={}, headers=_headers(USER_KEY))
        assert r.status_code == 403, r.text

    async def test_dispute_resolve_user_key_refused(self, tiered_keys) -> None:
        from fastapi.testclient import TestClient
        from market_service.main import app

        job_id = await _seed_settle_job()
        with TestClient(app) as client:
            r = client.post(f"/v1/market/jobs/{job_id}/dispute/resolve", headers=_headers(USER_KEY))
        assert r.status_code == 401

    async def test_book_unsigned_user_key_403(self, tiered_keys) -> None:
        from fastapi.testclient import TestClient
        from market_service.main import app

        with TestClient(app) as client:
            r = client.post(
                "/v1/market/offers/offer_x/book",
                json={"wallet": "0x" + "33" * 20, "amount": 1},
                headers=_headers(USER_KEY),
            )
        assert r.status_code == 403, r.text

    async def test_offer_cancel_unsigned_user_key_403(self, tiered_keys) -> None:
        from fastapi.testclient import TestClient
        from market_service.main import app

        offer_id = f"offer_{_uid()}"
        async with get_session_context() as session:
            session.add(
                MarketOffer(id=offer_id, provider="0x" + "55" * 20, capacity=1, price=Decimal("1"), status="available")
            )
            await session.commit()
        with TestClient(app) as client:
            r = client.post(f"/v1/market/offers/{offer_id}/cancel", headers=_headers(USER_KEY))
        assert r.status_code == 403, r.text


class TestOperatorKeyStillWorks:
    async def test_unsigned_operator_release_200(self, tiered_keys, stub_escrow_rpc) -> None:
        from fastapi.testclient import TestClient
        from market_service.main import app

        job_id = await _seed_settle_job()
        with TestClient(app) as client:
            r = client.post(f"/v1/market/jobs/{job_id}/release", json={}, headers=_headers(OP_KEY))
        assert r.status_code == 200, r.text
        assert r.json()["state"] == "RELEASED"

    async def test_dispute_resolve_operator_key_passes_gate(self, tiered_keys) -> None:
        from fastapi.testclient import TestClient
        from market_service.main import app

        job_id = await _seed_settle_job()
        with TestClient(app) as client:
            r = client.post(f"/v1/market/jobs/{job_id}/dispute/resolve", headers=_headers(OP_KEY))
        # gate passed; downstream may 404/200 — anything but 401/403
        assert r.status_code not in (401, 403), r.text


class TestPartySignatureStillWorks:
    async def test_party_signed_release_with_user_key(self, tiered_keys, stub_escrow_rpc) -> None:
        from aitbc.crypto.crypto import derive_ethereum_address, sign_transaction_data
        from aitbc.market.job_request_signature import jobs_request_message
        from aitbc.utils.chain_id import resolve_chain_id
        from fastapi.testclient import TestClient
        from market_service.config import settings
        from market_service.main import app

        buyer_key = "0x" + "44" * 32
        job_id = await _seed_settle_job()
        # rewrite the job's buyer to the signing key's address
        async with get_session_context() as session:
            job = await session.get(MarketJob, job_id)
            job.buyer_address = derive_ethereum_address(buyer_key)
            await session.commit()

        chain_id = settings.default_chain_id or resolve_chain_id()
        issued_at = int(time.time())
        addr = derive_ethereum_address(buyer_key)
        route = f"/v1/market/jobs/{job_id}/release"
        proof = {
            "signer_address": addr,
            "chain_id": chain_id,
            "issued_at": issued_at,
            "signature": sign_transaction_data(jobs_request_message(addr, chain_id, issued_at, route), buyer_key),
        }
        with TestClient(app) as client:
            r = client.post(f"/v1/market/jobs/{job_id}/release", json=proof, headers=_headers(USER_KEY))
        assert r.status_code == 200, r.text


class TestOperatorKeyDistinctness:
    """#1906: equal user/operator keys must warn at settings load."""

    def test_equal_keys_warn(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        from market_service.config import Settings

        monkeypatch.setenv("API_KEY", "same-key")
        monkeypatch.setenv("MARKET_OPERATOR_API_KEY", "same-key")
        with caplog.at_level(logging.WARNING, logger="market_service.config"):
            Settings()
        assert "MARKET_OPERATOR_API_KEY equals API_KEY" in caplog.text

    def test_distinct_keys_no_warn(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        from market_service.config import Settings

        monkeypatch.setenv("API_KEY", "user-key")
        monkeypatch.setenv("MARKET_OPERATOR_API_KEY", "op-key")
        with caplog.at_level(logging.WARNING, logger="market_service.config"):
            Settings()
        assert "MARKET_OPERATOR_API_KEY equals API_KEY" not in caplog.text
