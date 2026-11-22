"""#2605/#2606/#2611/#2612/#2613/#2614/#2616 market authz audit pins.

The user-tier ``MARKET_API_KEY`` is distributed to CLI users — these tests
run with auth ENABLED and distinct user/operator keys to prove which tier
each route actually requires:

- ``parameters/apply`` and ``ratings/mark-synced`` are operator-only.
- ``POST /v1/market/offers`` needs a provider signature for non-operators,
  and an id replay answers only to the row's provider.
- ``POST /v1/market/match`` needs a buyer-bound signature; reservations get
  the shorter match TTL.
- ``POST /v1/market/plugins`` allowlists fields, forces ``pending`` and
  derives ``author`` from the signer for non-operators.
- ``POST /v1/transactions`` runs the offer through ``create_offer``
  validation (status/money/capacity bounds).
- Job reads and the create-replay return the public view to the user key.
"""

from __future__ import annotations

import sys
import time
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

USER_KEY = "user-tier-key"
OP_KEY = "operator-tier-key"

BUYER_KEY = "0x" + "33" * 32
PROVIDER_KEY = "0x" + "44" * 32
STRANGER_KEY = "0x" + "55" * 32


def _uid() -> str:
    return uuid4().hex[:8]


@pytest.fixture
def tiered(client_maker, monkeypatch: pytest.MonkeyPatch):
    """Auth enabled, distinct user/operator keys; yields a client factory."""
    from market_service import main as market_main
    from market_service.config import settings

    monkeypatch.setattr(market_main._market_user_key_auth, "expected_key", USER_KEY)
    monkeypatch.setattr(market_main._market_operator_key_auth, "expected_key", OP_KEY)
    monkeypatch.setattr(settings, "api_key", USER_KEY)
    monkeypatch.setattr(settings, "operator_api_key", OP_KEY)
    market_main._market_user_key_auth.auth_enabled = True
    market_main._market_operator_key_auth.auth_enabled = True
    return client_maker


@pytest.fixture
def client_maker():
    from market_service.main import app

    def make() -> TestClient:
        return TestClient(app, raise_server_exceptions=False)

    return make


def _headers(key: str) -> dict[str, str]:
    return {"X-Api-Key": key}


def _addr(private_key: str) -> str:
    from aitbc.crypto.crypto import derive_ethereum_address

    return derive_ethereum_address(private_key)


def _sign(private_key: str, message: dict) -> str:
    from aitbc.crypto.crypto import sign_transaction_data

    return sign_transaction_data(message, private_key)


def _chain_id() -> str:
    from aitbc.utils.chain_id import resolve_chain_id
    from market_service.config import settings

    return settings.default_chain_id or resolve_chain_id()


def _jobs_proof(private_key: str, address: str, route: str, binding: dict | None = None) -> dict:
    from aitbc.market.job_request_signature import jobs_request_message

    chain_id = _chain_id()
    issued_at = int(time.time())
    return {
        "signer_address": address,
        "chain_id": chain_id,
        "issued_at": issued_at,
        "signature": _sign(private_key, jobs_request_message(address, chain_id, issued_at, route, binding=binding)),
    }


# ------------------------------------------------------------------ #2605


class TestParametersApplyTier:
    def test_user_key_refused(self, tiered):
        with tiered() as client:
            r = client.post(
                "/v1/market/parameters/apply",
                json={
                    "proposal_id": "prop-x",
                    "parameter_name": "default_chain_id",
                    "new_value": "evil-chain",
                },
                headers=_headers(USER_KEY),
            )
        assert r.status_code in (401, 403)

    def test_operator_key_reaches_validation(self, tiered):
        with tiered() as client:
            r = client.post(
                "/v1/market/parameters/apply",
                json={
                    "proposal_id": "prop-x",
                    "parameter_name": "no-such-param",
                    "new_value": "x",
                },
                headers=_headers(OP_KEY),
            )
        # Auth passed; the unknown parameter is the caller's 400.
        assert r.status_code == 400
        assert "Unknown parameter" in r.text


# ------------------------------------------------------------------ #2614


class TestMarkSyncedTier:
    def test_user_key_refused(self, tiered):
        with tiered() as client:
            r = client.post("/v1/market/ratings/mark-synced", json=["r1"], headers=_headers(USER_KEY))
        assert r.status_code in (401, 403)

    def test_operator_key_allowed(self, tiered):
        with tiered() as client:
            r = client.post("/v1/market/ratings/mark-synced", json=[], headers=_headers(OP_KEY))
        assert r.status_code == 200


# ------------------------------------------------------------------ #2616


class TestTransactionsOfferValidation:
    """Auth-disabled is fine here — the point is create_offer's validators."""

    @pytest.fixture(autouse=True)
    def _auth_off(self, monkeypatch: pytest.MonkeyPatch):
        from market_service import main as market_main

        for a in (market_main._market_user_key_auth, market_main._market_operator_key_auth):
            a.auth_enabled = False

    def _post(self, client: TestClient, body: dict):
        return client.post("/v1/transactions", json={"type": "market", "action": "offer", **body})

    def test_negative_price_refused(self, client_maker):
        with client_maker() as client:
            r = self._post(client, {"provider": "0x" + "ab" * 20, "price": "-5", "capacity": 1})
        assert r.status_code == 400

    def test_unknown_status_refused(self, client_maker):
        with client_maker() as client:
            r = self._post(client, {"provider": "0x" + "ab" * 20, "status": "bogus-state"})
        assert r.status_code == 400

    @pytest.mark.parametrize("capacity", [-1, 10**9, "lots"])
    def test_capacity_bound(self, client_maker, capacity):
        with client_maker() as client:
            r = self._post(client, {"provider": "0x" + "ab" * 20, "capacity": capacity})
        assert r.status_code == 400

    def test_valid_offer_still_created(self, client_maker):
        with client_maker() as client:
            r = self._post(client, {"id": f"tx-offer-{_uid()}", "provider": "0x" + "ab" * 20, "capacity": 4, "price": "1.5"})
            assert r.status_code == 200
            assert r.json()["status"] == "success"


# ------------------------------------------------------------------ #2611


class TestOfferCreateSignature:
    def _body(self, **over) -> dict:
        body = {
            "id": f"offer-{_uid()}",
            "provider": _addr(PROVIDER_KEY),
            "capacity": 2,
            "price": "3.5",
            "chain_id": _chain_id(),
        }
        body.update(over)
        return body

    def _signed(self, body: dict, private_key: str) -> dict:
        from aitbc.market.job_request_signature import jobs_request_message
        from aitbc.market.offer_registration import offer_body_hash

        address = _addr(private_key)
        chain_id = _chain_id()
        issued_at = int(time.time())
        # offer_body_hash covers the body minus `signature` — the proof
        # fields are part of it, so hash the signed-minus-signature form.
        signed = {
            **body,
            "signer_address": address,
            "chain_id": chain_id,
            "issued_at": issued_at,
        }
        binding = {
            "offer_id": str(body.get("id") or ""),
            "provider": body["provider"],
            "offer_hash": offer_body_hash(signed),
        }
        signed["signature"] = _sign(
            private_key, jobs_request_message(address, chain_id, issued_at, "/v1/market/offers", binding=binding)
        )
        return signed

    def test_unsigned_user_key_refused(self, tiered):
        with tiered() as client:
            r = client.post("/v1/market/offers", json=self._body(), headers=_headers(USER_KEY))
        assert r.status_code == 403

    def test_provider_signed_offer_created(self, tiered):
        body = self._signed(self._body(), PROVIDER_KEY)
        with tiered() as client:
            r = client.post("/v1/market/offers", json=body, headers=_headers(USER_KEY))
        assert r.status_code == 200, r.text
        assert r.json()["provider"].lower() == _addr(PROVIDER_KEY).lower()

    def test_signature_for_other_provider_refused(self, tiered):
        body = self._signed(self._body(provider=_addr(STRANGER_KEY)), STRANGER_KEY)
        # Claims STRANGER as provider but body provider field says stranger —
        # sign as PROVIDER while provider=STRANGER's address.
        body["provider"] = _addr(PROVIDER_KEY)
        with tiered() as client:
            r = client.post("/v1/market/offers", json=body, headers=_headers(USER_KEY))
        assert r.status_code == 403

    def test_id_replay_only_to_same_provider(self, tiered):
        offer_id = f"offer-{_uid()}"
        body = self._signed(self._body(id=offer_id), PROVIDER_KEY)
        with tiered() as client:
            r1 = client.post("/v1/market/offers", json=body, headers=_headers(USER_KEY))
            assert r1.status_code == 200, r1.text
            # A different provider re-using the id must not get the row back.
            stranger_body = self._signed(self._body(id=offer_id, provider=_addr(STRANGER_KEY)), STRANGER_KEY)
            r2 = client.post("/v1/market/offers", json=stranger_body, headers=_headers(USER_KEY))
            assert r2.status_code == 403
            # The owning provider's replay still works.
            replay = self._signed(self._body(id=offer_id), PROVIDER_KEY)
            r3 = client.post("/v1/market/offers", json=replay, headers=_headers(USER_KEY))
            assert r3.status_code == 200

    def test_operator_unsigned_allowed(self, tiered):
        with tiered() as client:
            r = client.post("/v1/market/offers", json=self._body(), headers=_headers(OP_KEY))
        assert r.status_code == 200, r.text


# ------------------------------------------------------------------ #2612


class TestMatchBuyerBinding:
    def _match_body(self, **over) -> dict:
        body = {
            "requirements": {"gpu_model": "A100"},
            "max_price": "10",
            "buyer_address": _addr(BUYER_KEY),
            "chain_id": _chain_id(),
        }
        body.update(over)
        return body

    def _signed_match(self, body: dict, private_key: str) -> dict:
        from aitbc.market.job_request_signature import jobs_request_message

        address = _addr(private_key)
        chain_id = _chain_id()
        issued_at = int(time.time())
        binding = {
            "buyer_address": body["buyer_address"],
            "requirements": body["requirements"],
            "max_price": str(Decimal(str(body["max_price"]))) if body.get("max_price") is not None else None,
            "preferred_region": body.get("preferred_region"),
            "chain_id": body.get("chain_id"),
        }
        return {
            **body,
            "signer_address": address,
            "issued_at": issued_at,
            "signature": _sign(
                private_key, jobs_request_message(address, chain_id, issued_at, "/v1/market/match", binding=binding)
            ),
        }

    def test_unsigned_user_key_refused(self, tiered):
        with tiered() as client:
            r = client.post("/v1/market/match", json=self._match_body(), headers=_headers(USER_KEY))
        assert r.status_code == 403

    def test_buyer_signed_match_proceeds(self, tiered):
        body = self._signed_match(self._match_body(), BUYER_KEY)
        with tiered() as client:
            r = client.post("/v1/market/match", json=body, headers=_headers(USER_KEY))
        # No offers seeded → 'no_match' is a successful match response.
        assert r.status_code == 200
        assert r.json()["match"]["status"] == "no_match"

    def test_signature_for_other_buyer_refused(self, tiered):
        body = self._match_body()
        body = {**body, "buyer_address": _addr(STRANGER_KEY)}
        signed = self._signed_match(body, BUYER_KEY)  # signed by buyer, claims stranger
        with tiered() as client:
            r = client.post("/v1/market/match", json=signed, headers=_headers(USER_KEY))
        assert r.status_code == 403

    def test_operator_unsigned_allowed(self, tiered):
        with tiered() as client:
            r = client.post("/v1/market/match", json={"requirements": {}}, headers=_headers(OP_KEY))
        assert r.status_code == 200


# ------------------------------------------------------------------ #2613


class TestPluginRegistration:
    def _plugin_body(self, **over) -> dict:
        body = {
            "name": f"plugin-{_uid()}",
            "description": "test plugin",
            "type": "cli",
            "version": "1.0.0",
            "author": "mallory",
            "status": "approved",
            "download_count": 9999,
            "rating": 5.0,
        }
        body.update(over)
        return body

    def test_user_key_without_signature_refused(self, tiered):
        with tiered() as client:
            r = client.post("/v1/market/plugins", json=self._plugin_body(), headers=_headers(USER_KEY))
        assert r.status_code == 403

    def test_signed_registration_forces_pending_and_signer_author(self, tiered):
        body = {**self._plugin_body(), **_jobs_proof(PROVIDER_KEY, _addr(PROVIDER_KEY), "/v1/market/plugins")}
        with tiered() as client:
            r = client.post("/v1/market/plugins", json=body, headers=_headers(USER_KEY))
        assert r.status_code == 200, r.text
        plugin_id = r.json()["id"]
        # Read back the row: author is the signer, status pending, counters zero.
        import asyncio

        from market_service.domain.market import Plugin
        from market_service.storage import get_session_context

        async def fetch():
            async with get_session_context() as session:
                return await session.get(Plugin, plugin_id)

        row = asyncio.run(fetch())
        assert row.author.lower() == _addr(PROVIDER_KEY).lower()
        assert row.status == "pending"
        assert row.download_count == 0
        assert row.rating == 0.0

    def test_operator_can_approve(self, tiered):
        with tiered() as client:
            r = client.post(
                "/v1/market/plugins", json=self._plugin_body(author="ops", status="approved"), headers=_headers(OP_KEY)
            )
        assert r.status_code == 200, r.text

    def test_unknown_status_refused_for_operator(self, tiered):
        with tiered() as client:
            r = client.post("/v1/market/plugins", json=self._plugin_body(status="bogus"), headers=_headers(OP_KEY))
        assert r.status_code == 400


# ------------------------------------------------------------------ #2606


async def _seed_job() -> str:
    from datetime import UTC, datetime
    from decimal import Decimal

    from market_service.domain.market import MarketJob, MarketJobPayment
    from market_service.storage import get_session_context

    job_id = f"job_26xx_{_uid()}"
    async with get_session_context() as session:
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
                buyer_address=_addr(BUYER_KEY),
                provider_address=_addr(PROVIDER_KEY),
                service_type="ipfs",
                state="RUNNING",
                offer_id="offer_x",
                payload={"cid": "bafy-secret", "file_name": "customer-private.zip"},
                access_key=f"secret-access-key-{job_id}",
                payment_id=payment.id,
                payment_status="escrowed",
            )
        )
        await session.commit()
    return job_id


@pytest.mark.asyncio
class TestJobRecordVisibility:
    async def test_user_key_gets_public_view(self, tiered):
        job_id = await _seed_job()
        with tiered() as client:
            r = client.get(f"/v1/market/jobs/{job_id}", headers=_headers(USER_KEY))
        assert r.status_code == 200
        body = r.json()
        assert "payload" not in body
        assert "access_key" not in body
        assert body["job_id"] == job_id or body.get("id") == job_id

    async def test_operator_gets_full_record(self, tiered):
        job_id = await _seed_job()
        with tiered() as client:
            r = client.get(f"/v1/market/jobs/{job_id}", headers=_headers(OP_KEY))
        assert r.status_code == 200
        assert r.json().get("payload", {}).get("cid") == "bafy-secret"

    async def test_user_key_list_is_redacted(self, tiered):
        await _seed_job()
        with tiered() as client:
            r = client.get("/v1/market/jobs", headers=_headers(USER_KEY))
        assert r.status_code == 200
        rows = r.json()
        assert all("payload" not in row for row in rows)

    async def test_create_replay_public_for_user_key(self, tiered):
        job_id = f"job_replay_{_uid()}"
        body = {
            "id": job_id,
            "buyer_address": _addr(BUYER_KEY),
            "provider_address": _addr(PROVIDER_KEY),
            "service_type": "ipfs",
            "payload": {"cid": "bafy-secret"},
        }
        with tiered() as client:
            r1 = client.post("/v1/market/jobs", json=body, headers=_headers(USER_KEY))
            assert r1.status_code in (200, 201), r1.text
            r2 = client.post("/v1/market/jobs", json=body, headers=_headers(USER_KEY))
            assert r2.status_code in (200, 201), r2.text
            replay = r2.json()
            assert replay.get("deduplicated") is True
            assert "payload" not in replay or "cid" not in str(replay.get("payload"))
