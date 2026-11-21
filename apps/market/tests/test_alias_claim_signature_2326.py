"""#2326 residual: alias escrow claims need a buyer-wallet signature.

``POST /v1/market/jobs`` accepts caller-controlled ``payload.escrow_job_id``
and the user-tier ``MARKET_API_KEY`` is distributed to every CLI user — so
an unsigned request could squat a predictable escrow key and have the
victim's locked escrow authorize the squatter's shop token. Alias claims
(``payload.escrow_job_id`` present) now require a secp256k1 signature over
``(escrow_job_id, buyer_address)`` bound to ``/v1/market/jobs`` whose
recovered signer IS the declared buyer; the operator credential bypasses.
Self-bound jobs (no alias) are unchanged.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

pytestmark = pytest.mark.asyncio

USER_KEY = "user-tier-key"
OP_KEY = "operator-tier-key"

BUYER_KEY = "0x" + "44" * 32
OTHER_KEY = "0x" + "55" * 32
ESCROW_KEY = "coord_job_sig_1"


def _uid() -> str:
    return uuid4().hex[:8]


@pytest.fixture
def tiered_keys(monkeypatch: pytest.MonkeyPatch):
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


def _job_body(*, escrow_job_id: str | None = ESCROW_KEY, buyer: str, **extra) -> dict:
    payload = {"access_key": f"ak_{_uid()}", "access_secret": f"sec_{_uid()}"}
    if escrow_job_id:
        payload["escrow_job_id"] = escrow_job_id
    body = {
        "service_type": "whisper",
        "buyer_address": buyer,
        "provider_address": "0x" + "22" * 20,
        "payload": payload,
        "payment": {"amount": "1.0", "currency": "AITBC"},
    }
    body.update(extra)
    return body


def _signature_fields(buyer_key: str, *, escrow_job_id: str = ESCROW_KEY, buyer: str, issued_at: int | None = None):
    from aitbc.crypto.crypto import derive_ethereum_address, sign_transaction_data
    from aitbc.market.job_request_signature import jobs_request_message
    from aitbc.utils.chain_id import resolve_chain_id
    from market_service.config import settings

    addr = derive_ethereum_address(buyer_key)
    chain_id = settings.default_chain_id or resolve_chain_id()
    ts = issued_at if issued_at is not None else int(time.time())
    message = jobs_request_message(
        addr,
        chain_id,
        ts,
        "/v1/market/jobs",
        binding={"escrow_job_id": escrow_job_id, "buyer_address": buyer},
    )
    return {
        "signer_address": addr,
        "chain_id": chain_id,
        "issued_at": ts,
        "signature": sign_transaction_data(message, buyer_key),
    }


class TestAliasClaimSignatureRequired:
    async def test_unsigned_alias_claim_403(self, tiered_keys) -> None:
        from fastapi.testclient import TestClient
        from market_service.main import app

        from aitbc.crypto.crypto import derive_ethereum_address

        buyer = derive_ethereum_address(BUYER_KEY)
        with TestClient(app) as client:
            r = client.post("/v1/market/jobs", json=_job_body(buyer=buyer), headers=_headers(USER_KEY))
        assert r.status_code == 403, r.text
        assert "signature" in r.json()["error"]

    async def test_missing_buyer_address_403(self, tiered_keys) -> None:
        from fastapi.testclient import TestClient
        from market_service.main import app

        with TestClient(app) as client:
            r = client.post(
                "/v1/market/jobs",
                json=_job_body(escrow_job_id=ESCROW_KEY, buyer=""),
                headers=_headers(USER_KEY),
            )
        # Empty buyer_address fails the required-field check before signing.
        assert r.status_code in (400, 403), r.text

    async def test_valid_buyer_signature_200(self, tiered_keys) -> None:
        from fastapi.testclient import TestClient
        from market_service.main import app

        from aitbc.crypto.crypto import derive_ethereum_address

        buyer = derive_ethereum_address(BUYER_KEY)
        body = _job_body(buyer=buyer)
        body.update(_signature_fields(BUYER_KEY, buyer=buyer))
        with TestClient(app) as client:
            r = client.post("/v1/market/jobs", json=body, headers=_headers(USER_KEY))
        assert r.status_code == 200, r.text
        assert r.json()["job_id"]

    async def test_signature_for_different_escrow_key_403(self, tiered_keys) -> None:
        from fastapi.testclient import TestClient
        from market_service.main import app

        from aitbc.crypto.crypto import derive_ethereum_address

        buyer = derive_ethereum_address(BUYER_KEY)
        body = _job_body(buyer=buyer, escrow_job_id="coord_job_other")
        # Signed over ESCROW_KEY but claiming coord_job_other — binding mismatch.
        body.update(_signature_fields(BUYER_KEY, escrow_job_id=ESCROW_KEY, buyer=buyer))
        with TestClient(app) as client:
            r = client.post("/v1/market/jobs", json=body, headers=_headers(USER_KEY))
        assert r.status_code == 403, r.text

    async def test_signature_from_wrong_key_403(self, tiered_keys) -> None:
        from fastapi.testclient import TestClient
        from market_service.main import app

        from aitbc.crypto.crypto import derive_ethereum_address

        buyer = derive_ethereum_address(BUYER_KEY)
        body = _job_body(buyer=buyer)
        # Signed by OTHER_KEY but buyer_address names BUYER's address.
        body.update(_signature_fields(OTHER_KEY, buyer=buyer))
        with TestClient(app) as client:
            r = client.post("/v1/market/jobs", json=body, headers=_headers(USER_KEY))
        assert r.status_code == 403, r.text

    async def test_stale_issued_at_403(self, tiered_keys) -> None:
        from fastapi.testclient import TestClient
        from market_service.main import app

        from aitbc.crypto.crypto import derive_ethereum_address

        buyer = derive_ethereum_address(BUYER_KEY)
        body = _job_body(buyer=buyer)
        body.update(_signature_fields(BUYER_KEY, buyer=buyer, issued_at=int(time.time()) - 3600))
        with TestClient(app) as client:
            r = client.post("/v1/market/jobs", json=body, headers=_headers(USER_KEY))
        assert r.status_code == 403, r.text

    async def test_operator_key_bypasses_signature(self, tiered_keys) -> None:
        from fastapi.testclient import TestClient
        from market_service.main import app

        from aitbc.crypto.crypto import derive_ethereum_address

        buyer = derive_ethereum_address(BUYER_KEY)
        with TestClient(app) as client:
            r = client.post("/v1/market/jobs", json=_job_body(buyer=buyer), headers=_headers(OP_KEY))
        assert r.status_code == 200, r.text


class TestSelfBoundJobsUnaffected:
    async def test_plain_job_needs_no_signature(self, tiered_keys) -> None:
        from fastapi.testclient import TestClient
        from market_service.main import app

        from aitbc.crypto.crypto import derive_ethereum_address

        buyer = derive_ethereum_address(BUYER_KEY)
        with TestClient(app) as client:
            r = client.post(
                "/v1/market/jobs",
                json=_job_body(escrow_job_id=None, buyer=buyer),
                headers=_headers(USER_KEY),
            )
        assert r.status_code == 200, r.text
        assert r.json()["job_id"]
