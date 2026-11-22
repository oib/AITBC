"""#2607–#2626 market state/audit pins (second 26xx batch).

Service- and route-level regressions for the follow-up audit cluster:

- #2607 access_key uniqueness (409 on create, robust duplicate lookup)
- #2608 payment/escrow bound to the offer's listed minimum
- #2609 cancel/refund refused after provider delivery attestation
- #2615 DSN logging redacted
- #2618 book escrow terms from offer/bid, not the request body
- #2619 malformed requirements rejected before any reservation
- #2620 coordinator failure reports no_match, never "matched"
- #2621 edge advertisement bound to a signed node identity + endpoint check
- #2622 knowledge-graph owner/existence binding + field allowlists
- #2623 rental tokens job-bound, immutable, URL-validated, expiring
- #2624 history/performance computed from bids/offers
- #2625/#2626 dead SQL script and systemd wrapper removed
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aitbc_shared import MarketOffer  # noqa: E402
from market_service.domain.market import (  # noqa: E402
    Bid,
    IpfsRentalToken,
    MarketJob,
    MarketJobPayment,
    SoftwareService,
)
from market_service.services.market_service import AccessKeyConflict, MarketService  # noqa: E402
from market_service.services.matching_service import MatchingService  # noqa: E402
from market_service.storage import get_session_context  # noqa: E402

pytestmark = pytest.mark.asyncio

USER_KEY = "user-tier-key-26b"
OP_KEY = "operator-tier-key-26b"

BUYER_KEY = "0x" + "33" * 32
PROVIDER_KEY = "0x" + "44" * 32
STRANGER_KEY = "0x" + "55" * 32


def _uid() -> str:
    return uuid4().hex[:8]


@pytest.fixture
async def session():
    async with get_session_context() as s:
        yield s


@pytest.fixture
async def service(session) -> MarketService:
    return MarketService(session)


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


def _proof(private_key: str, route: str, binding: dict | None = None) -> dict:
    from aitbc.market.job_request_signature import jobs_request_message

    address = _addr(private_key)
    chain_id = _chain_id()
    issued_at = int(time.time())
    return {
        "signer_address": address,
        "chain_id": chain_id,
        "issued_at": issued_at,
        "signature": _sign(private_key, jobs_request_message(address, chain_id, issued_at, route, binding=binding)),
    }


async def _priced_offer(service: MarketService, offer_id: str, price: str = "10") -> None:
    service.session.add(
        SoftwareService(
            service_type="ipfs",
            offer_id=offer_id,
            price=Decimal(price),
            price_unit="per_day",
            provider_address=_addr(PROVIDER_KEY),
        )
    )
    await service.session.commit()


async def _job_fields(offer_id: str | None = None, **over) -> dict:
    data = {
        "service_type": "ipfs",
        "buyer_address": _addr(BUYER_KEY),
        "provider_address": _addr(PROVIDER_KEY),
        "payload": {"cid": f"Qm{_uid()}", "size": 10},
        "payment": {"amount": "1.0"},
    }
    if offer_id:
        data["offer_id"] = offer_id
    data.update(over)
    return data


# ------------------------------------------------------------------ #2607


class TestAccessKeyUnique:
    async def test_duplicate_access_key_rejected(self, service):
        key = f"ak-{_uid()}"
        await service.create_market_job(await _job_fields(payload={"access_key": key}))
        with pytest.raises(AccessKeyConflict):
            await service.create_market_job(await _job_fields(payload={"access_key": key}))

    async def test_same_key_on_same_job_id_replays(self, service):
        """A retried create with the caller's job id replays, not conflicts."""
        job_id = f"job-{_uid()}"
        fields = await _job_fields()
        fields["id"] = job_id
        fields["payload"] = {"access_key": f"ak-{_uid()}"}
        first = await service.create_market_job(fields)
        second = await service.create_market_job(fields)
        assert second["job_id"] == first["job_id"]

    async def test_access_key_column_is_unique(self, session):
        """The schema itself refuses duplicate access keys — legacy DBs that
        predates the constraint are covered by the create-path 409 and the
        secret-match lookup."""
        from sqlalchemy.exc import IntegrityError

        key = f"ak-uniq-{_uid()}"
        now = datetime.now(UTC).replace(tzinfo=None)
        session.add(
            MarketJob(
                service_type="ipfs",
                state="RUNNING",
                access_key=key,
                payload={"access_secret": "s1"},
                expires_at=now + timedelta(hours=1),
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
        session.add(
            MarketJob(
                service_type="ipfs",
                state="RUNNING",
                access_key=key,
                payload={"access_secret": "s2"},
                expires_at=now + timedelta(hours=1),
                created_at=now,
                updated_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async def test_access_lookup_resolves_matching_secret(self, service):
        created = await service.create_market_job(
            await _job_fields(payload={"access_key": f"ak-{_uid()}", "access_secret": "sekret"})
        )
        job = await service.session.get(MarketJob, created["job_id"])
        assert job is not None and job.access_key
        assert await service.get_market_job_access_token(job.access_key, "wrong") is None

    async def test_create_route_duplicate_returns_409(self, tiered):
        key = f"ak-route-{_uid()}"
        offer_id = f"offer-{_uid()}"
        async with get_session_context() as s:
            s.add(SoftwareService(service_type="ipfs", offer_id=offer_id))
            await s.commit()
        body = {
            "service_type": "ipfs",
            "offer_id": offer_id,
            "buyer_address": _addr(BUYER_KEY),
            "provider_address": _addr(PROVIDER_KEY),
            "payload": {"access_key": key},
            "payment": {"amount": "1.0"},
        }
        with tiered() as client:
            r1 = client.post("/v1/market/jobs", json=body, headers=_headers(USER_KEY))
            r2 = client.post("/v1/market/jobs", json={**body, "id": f"job2-{_uid()}"}, headers=_headers(USER_KEY))
        assert r1.status_code == 200, r1.text
        assert r2.status_code == 409, r2.text


# ------------------------------------------------------------------ #2608


class TestPaymentBoundToOfferPrice:
    async def test_underpayment_rejected_at_creation(self, service):
        offer_id = f"offer-{_uid()}"
        await _priced_offer(service, offer_id, "10")
        with pytest.raises(ValueError, match="listed minimum"):
            await service.create_market_job(await _job_fields(offer_id, payment={"amount": "0.5"}))

    async def test_payment_at_floor_accepted(self, service):
        offer_id = f"offer-{_uid()}"
        await _priced_offer(service, offer_id, "10")
        result = await service.create_market_job(await _job_fields(offer_id, payment={"amount": "10"}))
        assert result["job_id"]

    async def test_unpriced_offer_unaffected(self, service):
        offer_id = f"offer-{_uid()}"
        service.session.add(SoftwareService(service_type="ipfs", offer_id=offer_id))
        await service.session.commit()
        result = await service.create_market_job(await _job_fields(offer_id, payment={"amount": "0.001"}))
        assert result["job_id"]

    async def test_escrow_verify_rechecks_floor(self, service, session):
        """A tampered payment row below the listed minimum cannot flip to
        escrowed — the check runs again at escrow verification."""
        offer_id = f"offer-{_uid()}"
        await _priced_offer(service, offer_id, "10")
        created = await service.create_market_job(await _job_fields(offer_id, payment={"amount": "10"}))
        created["job_id"]
        job = await session.get(MarketJob, created["job_id"])
        payment = await session.get(MarketJobPayment, job.payment_id)
        payment.amount = Decimal("0.5")  # simulate a tampered/legacy row
        session.add(payment)
        await session.commit()

        class StubRPC:
            async def verify_escrow(self, job_id):
                return {"state": "locked", "amount": "0.5", "buyer": job.buyer_address, "provider": job.provider_address}

        service._rpc_client = StubRPC()  # type: ignore[assignment]
        with pytest.raises(ValueError, match="listed minimum"):
            await service._require_locked_escrow(job, payment)

    async def test_access_token_denies_underpaid_lock(self, service, session):
        offer_id = f"offer-{_uid()}"
        await _priced_offer(service, offer_id, "10")
        created = await service.create_market_job(await _job_fields(offer_id, payment={"amount": "10"}))
        job = await session.get(MarketJob, created["job_id"])
        payment = await session.get(MarketJobPayment, job.payment_id)
        payment.amount = Decimal("0.5")
        session.add(payment)
        await session.commit()
        assert await service._job_token_escrow_verified(job, payment) is False


# ------------------------------------------------------------------ #2609


class TestCancelRefundAfterDelivery:
    async def _confirmed_job(self, service, session):
        created = await service.create_market_job(await _job_fields())
        job = await session.get(MarketJob, created["job_id"])
        payload = dict(job.payload or {})
        payload["provider_confirmed"] = True
        payload["provider_confirmed_at"] = datetime.now(UTC).replace(tzinfo=None).isoformat()
        job.payload = payload
        job.state = "RUNNING"
        payment = await session.get(MarketJobPayment, job.payment_id)
        payment.status = "escrowed"
        job.payment_status = "escrowed"
        session.add_all([job, payment])
        await session.commit()
        return created["job_id"]

    async def test_cancel_refused_after_provider_confirmed(self, service, session):
        job_id = await self._confirmed_job(service, session)
        with pytest.raises(ValueError, match="provider confirmed delivery"):
            await service.cancel_market_job(job_id)
        job = await session.get(MarketJob, job_id)
        assert job.state == "RUNNING"

    async def test_refund_refused_after_provider_confirmed(self, service, session):
        job_id = await self._confirmed_job(service, session)
        with pytest.raises(ValueError, match="provider confirmed delivery"):
            await service.refund_market_job_payment(job_id)

    async def test_unconfirmed_cancel_still_works(self, service):
        created = await service.create_market_job(await _job_fields())
        result = await service.cancel_market_job(created["job_id"])
        assert result["state"] == "CANCELED"

    async def test_expired_confirmed_job_still_refundable(self, service, session):
        """Expiry remains a valid resolution path after attestation."""
        job_id = await self._confirmed_job(service, session)
        job = await session.get(MarketJob, job_id)
        job.state = "EXPIRED"
        session.add(job)
        await session.commit()

        class StubRPC:
            async def refund_escrow(self, job_id):
                return {"success": True, "tx_hash": "0xrefund", "refunded_amount": "1.0"}

        service._rpc_client = StubRPC()  # type: ignore[assignment]
        result = await service.refund_market_job_payment(job_id)
        assert result["state"] == "REFUNDED"


# ------------------------------------------------------------------ #2615


async def test_dsn_log_summary_hides_credentials():
    from market_service.storage import _dsn_log_summary

    out = _dsn_log_summary("postgresql://aitbc_market:s3cr3t-pw@db.internal:5432/aitbc_market")
    assert "s3cr3t-pw" not in out
    assert "db.internal" in out
    assert "aitbc_market" in out
    assert _dsn_log_summary("not a url") == "unparseable"


# ------------------------------------------------------------------ #2618


class TestBookEscrowTerms:
    async def test_escrow_uses_offer_provider_and_bid_price(self, tiered, session, monkeypatch):
        """Body provider/amount must not steer the on-chain escrow — the
        offer row's provider and the accepted bid's price do."""
        offer_id = f"offer-{_uid()}"
        offer = MarketOffer(
            id=offer_id,
            provider=_addr(PROVIDER_KEY),
            status="available",
            capacity=1,
            price=Decimal("5"),
            price_per_hour=Decimal("5"),
            region=f"r{_uid()}",
            chain_id=_chain_id(),
        )
        session.add(offer)
        await session.commit()

        captured = []

        async def fake_escrow(job_id, buyer, provider, amount):
            captured.append((job_id, buyer, provider, amount))

        monkeypatch.setattr("market_service.routers.offers._create_escrow_bg", fake_escrow)

        body = {
            "wallet": _addr(BUYER_KEY),
            "provider": _addr(STRANGER_KEY),
            "amount": "0.00000001",
            "price": "5",
            **_proof("0x" + "33" * 32, f"/v1/market/offers/{offer_id}/book"),
        }
        with tiered() as client:
            r = client.post(f"/v1/market/offers/{offer_id}/book", json=body, headers=_headers(USER_KEY))
        assert r.status_code == 200, r.text
        result = r.json()
        assert result["provider"] == _addr(PROVIDER_KEY)
        assert captured, "escrow background task was not scheduled"
        _job_id, _buyer, provider, amount = captured[0]
        assert provider == _addr(PROVIDER_KEY)
        assert Decimal(str(amount)) == Decimal("5")


# ------------------------------------------------------------------ #2619/#2620


class TestMatchRequirements:
    async def _seed_match_offer(self, session) -> str:
        offer_id = f"offer-{_uid()}"
        session.add(
            MarketOffer(
                id=offer_id,
                provider=_addr(PROVIDER_KEY),
                status="available",
                capacity=1,
                price=Decimal("5"),
                price_per_hour=Decimal("1.5"),
                region=f"r{_uid()}",
                chain_id=_chain_id(),
            )
        )
        await session.commit()
        return offer_id

    async def test_garbage_max_price_rejected_before_reservation(self, session):
        offer_id = await self._seed_match_offer(session)
        matcher = MatchingService(session)
        with pytest.raises(ValueError, match="max_price"):
            await matcher.match_and_assign({"max_price": "not-a-number"})
        offer = await session.get(MarketOffer, offer_id)
        assert offer.status == "available"

    async def test_match_route_bad_requirements_4xx(self, tiered, session):
        offer_id = await self._seed_match_offer(session)
        body = {
            "requirements": {"max_price": "abc"},
            "chain_id": _chain_id(),
            **_proof(
                "0x" + "33" * 32,
                "/v1/market/match",
                binding={
                    "buyer_address": _addr("0x" + "33" * 32),
                    "requirements": {"max_price": "abc"},
                    "max_price": None,
                    "preferred_region": None,
                    "chain_id": _chain_id(),
                },
            ),
            "buyer_address": _addr("0x" + "33" * 32),
        }
        with tiered() as client:
            r = client.post("/v1/market/match", json=body, headers=_headers(USER_KEY))
        assert r.status_code in (400, 422), r.text
        offer = await session.get(MarketOffer, offer_id)
        assert offer.status == "available"

    async def test_coordinator_failure_reports_no_match(self, service, session, monkeypatch):
        await self._seed_match_offer(session)

        class FailingClient:
            async def post(self, *a, **k):
                raise httpx.ConnectError("refused")

        monkeypatch.setattr(MatchingService, "_ensure_client", lambda self: FailingClient())
        matcher = MatchingService(session)
        result = await matcher.match_and_assign({"capacity": 1})
        assert result["status"] == "no_match"
        assert "coordinator" in result["error"]

    async def test_failed_match_releases_reservation(self, service, session, monkeypatch):
        offer_id = await self._seed_match_offer(session)

        class FailingClient:
            async def post(self, *a, **k):
                raise httpx.ConnectError("refused")

        monkeypatch.setattr(MatchingService, "_ensure_client", lambda self: FailingClient())
        matcher = MatchingService(session)
        result = await matcher.match_and_assign({"capacity": 1})
        assert result["status"] == "no_match"
        offer = await session.get(MarketOffer, offer_id)
        assert offer.status == "available"


# ------------------------------------------------------------------ #2621


class TestEdgeAdvertise:
    def _node_id(self) -> str:
        return f"edge-{_uid()}"

    async def test_unsigned_user_key_refused(self, tiered):
        with tiered() as client:
            r = client.post(
                "/v1/market/edge-advertise",
                json={"node_id": self._node_id(), "gpu_count": 1},
                headers=_headers(USER_KEY),
            )
        assert r.status_code == 403, r.text

    async def test_signed_create_binds_owner_and_blocks_foreign_update(self, tiered):
        node_id = self._node_id()
        # IP literal — private-LAN space is allowed and needs no DNS.
        endpoint = "http://10.9.9.9:8111"
        binding = {"node_id": node_id, "endpoint": endpoint}
        with tiered() as client:
            r1 = client.post(
                "/v1/market/edge-advertise",
                json={
                    "node_id": node_id,
                    "endpoint": endpoint,
                    "gpu_count": 1,
                    **_proof("0x" + "33" * 32, "/v1/market/edge-advertise", binding=binding),
                },
                headers=_headers(USER_KEY),
            )
            assert r1.status_code == 200, r1.text
            # A different signer cannot overwrite the advertisement.
            r2 = client.post(
                "/v1/market/edge-advertise",
                json={
                    "node_id": node_id,
                    "endpoint": endpoint,
                    "gpu_count": 2,
                    **_proof("0x" + "55" * 32, "/v1/market/edge-advertise", binding=binding),
                },
                headers=_headers(USER_KEY),
            )
            assert r2.status_code == 403, r2.text
            # The owner can update it.
            r3 = client.post(
                "/v1/market/edge-advertise",
                json={
                    "node_id": node_id,
                    "endpoint": endpoint,
                    "gpu_count": 2,
                    **_proof("0x" + "33" * 32, "/v1/market/edge-advertise", binding=binding),
                },
                headers=_headers(USER_KEY),
            )
            assert r3.status_code == 200, r3.text

    async def test_unsafe_endpoint_refused(self, tiered):
        node_id = self._node_id()
        endpoint = "http://169.254.169.254/latest"
        binding = {"node_id": node_id, "endpoint": endpoint}
        with tiered() as client:
            r = client.post(
                "/v1/market/edge-advertise",
                json={
                    "node_id": node_id,
                    "endpoint": endpoint,
                    **_proof("0x" + "33" * 32, "/v1/market/edge-advertise", binding=binding),
                },
                headers=_headers(USER_KEY),
            )
        assert r.status_code == 400, r.text

    async def test_operator_bypass(self, tiered):
        with tiered() as client:
            r = client.post(
                "/v1/market/edge-advertise",
                json={"node_id": self._node_id(), "endpoint": "", "gpu_count": 0},
                headers=_headers(OP_KEY),
            )
        assert r.status_code == 200, r.text


# ------------------------------------------------------------------ #2622


class TestKnowledgeGraph:
    def _make_graph(self, client, private_key: str = "0x" + "33" * 32) -> str:
        r = client.post(
            "/v1/knowledge-graph",
            json={"name": f"g-{_uid()}", "owner": "spoofed", **_proof(private_key, "/v1/knowledge-graph")},
            headers=_headers(USER_KEY),
        )
        assert r.status_code == 200, r.text
        return r.json()["id"]

    async def test_graph_owner_is_the_signer(self, tiered):
        """The stored owner is the recovered signer — a spoofed body owner
        never reaches the row."""
        from market_service.domain.market import KnowledgeGraph

        with tiered() as client:
            graph_id = self._make_graph(client)
        async with get_session_context() as s:
            graph = await s.get(KnowledgeGraph, graph_id)
            assert graph is not None
            assert graph.owner == _addr("0x" + "33" * 32)

    async def test_create_requires_signature(self, tiered):
        with tiered() as client:
            r = client.post("/v1/knowledge-graph", json={"name": "x"}, headers=_headers(USER_KEY))
        assert r.status_code == 403, r.text

    async def test_create_binds_signer_owner_ignores_body(self, tiered):
        with tiered() as client:
            r = client.post(
                "/v1/knowledge-graph",
                json={"name": f"g-{_uid()}", "owner": "spoofed", **_proof("0x" + "33" * 32, "/v1/knowledge-graph")},
                headers=_headers(USER_KEY),
            )
        assert r.status_code == 200, r.text
        assert r.json()["id"]

    async def test_node_write_requires_graph_and_owner(self, tiered):
        with tiered() as client:
            graph_id = self._make_graph(client)
            # Missing graph -> 404.
            r404 = client.post(
                "/v1/knowledge-graph/no-such-graph/nodes",
                json={
                    "node_type": "entity",
                    "label": "x",
                    **_proof("0x" + "33" * 32, "/v1/knowledge-graph/no-such-graph/nodes"),
                },
                headers=_headers(USER_KEY),
            )
            assert r404.status_code == 404, r404.text
            # Owner writes a node.
            r1 = client.post(
                f"/v1/knowledge-graph/{graph_id}/nodes",
                json={
                    "node_type": "entity",
                    "label": "n1",
                    **_proof("0x" + "33" * 32, f"/v1/knowledge-graph/{graph_id}/nodes"),
                },
                headers=_headers(USER_KEY),
            )
            assert r1.status_code == 200, r1.text
            node_id = r1.json()["id"]
            # A different signer is refused.
            r2 = client.post(
                f"/v1/knowledge-graph/{graph_id}/nodes",
                json={
                    "node_type": "entity",
                    "label": "n2",
                    **_proof("0x" + "55" * 32, f"/v1/knowledge-graph/{graph_id}/nodes"),
                },
                headers=_headers(USER_KEY),
            )
            assert r2.status_code == 403, r2.text
            # Edge to a node in another graph is refused.
            other = self._make_graph(client, "0x" + "55" * 32)
            r3 = client.post(
                f"/v1/knowledge-graph/{other}/edges",
                json={
                    "source_node_id": node_id,
                    "target_node_id": node_id,
                    "edge_type": "relates_to",
                    **_proof("0x" + "55" * 32, f"/v1/knowledge-graph/{other}/edges"),
                },
                headers=_headers(USER_KEY),
            )
            assert r3.status_code == 400, r3.text


# ------------------------------------------------------------------ #2623


class TestRentalTokenBinding:
    async def test_standalone_token_refused(self, service):
        with pytest.raises(ValueError, match="rental_id"):
            await service.register_ipfs_rental_token({"access_key": f"ak-{_uid()}", "access_secret": "s3cr3t", "cid": "QmX"})

    async def test_unresolvable_rental_id_refused(self, service):
        with pytest.raises(ValueError, match="does not resolve"):
            await service.register_ipfs_rental_token(
                {"access_key": f"ak-{_uid()}", "access_secret": "s3cr3t", "cid": "QmX", "rental_id": "no-such-job"}
            )

    async def test_job_bound_token_requires_provider_signature(self, service):
        cid = f"Qm{_uid()}"
        created = await service.create_market_job(await _job_fields(payload={"cid": cid}))
        with pytest.raises(ValueError):
            await service.register_ipfs_rental_token(
                {"access_key": f"ak-{_uid()}", "access_secret": "s3cr3t", "cid": cid, "rental_id": created["job_id"]}
            )

    async def test_job_bound_token_signed_gets_expiry_and_binding(self, service):
        cid = f"Qm{_uid()}"
        created = await service.create_market_job(await _job_fields(payload={"cid": cid}))
        job_id = created["job_id"]
        job = await service.session.get(MarketJob, job_id)
        binding = {
            "rental_id": job_id,
            "cid": cid,
            "buyer_address": str(job.buyer_address or ""),
            "provider_address": str(job.provider_address or ""),
        }
        result = await service.register_ipfs_rental_token(
            {
                "access_key": f"ak-{_uid()}",
                "access_secret": "s3cr3t",
                "cid": cid,
                "rental_id": job_id,
                **_proof(PROVIDER_KEY, "/v1/market/ipfs/rental-token", binding=binding),
            }
        )
        assert result["expires_at"] is not None
        assert result["buyer_address"] == _addr(BUYER_KEY)
        assert result["provider_address"] == _addr(PROVIDER_KEY)

    async def test_unsafe_ipfs_api_refused(self, service):
        with pytest.raises(ValueError, match="ipfs_api"):
            await service.register_ipfs_rental_token(
                {
                    "access_key": f"ak-{_uid()}",
                    "access_secret": "s3cr3t",
                    "cid": "QmX",
                    "rental_id": "job-x",
                    "ipfs_api": "http://169.254.169.254/latest",
                }
            )

    async def test_non_job_token_is_immutable(self, service, session):
        key = f"ak-{_uid()}"
        now = datetime.now(UTC).replace(tzinfo=None)
        session.add(
            IpfsRentalToken(
                access_key=key,
                access_secret="hash:x",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
        with pytest.raises(ValueError, match="cannot be updated"):
            await service.register_ipfs_rental_token({"access_key": key, "cid": "QmNew"})


# ------------------------------------------------------------------ #2624


class TestHistoryPerformance:
    async def test_offer_history_from_completed_bids(self, service, session):
        offer_id = f"offer-{_uid()}"
        offer = MarketOffer(
            id=offer_id,
            provider=_addr(PROVIDER_KEY),
            status="delisted",
            capacity=1,
            price=Decimal("5"),
            price_per_hour=Decimal("5"),
            chain_id=_chain_id(),
        )
        session.add(offer)
        now = datetime.now(UTC).replace(tzinfo=None)
        for i in range(3):
            session.add(
                Bid(
                    offer_id=offer_id,
                    provider=_addr(PROVIDER_KEY),
                    buyer=_addr(BUYER_KEY),
                    capacity=1,
                    price=Decimal("5"),
                    status="completed",
                    created_at=now - timedelta(minutes=i),
                )
            )
        await session.commit()
        history = await service.get_offer_history(offer)
        assert history["booking_count"] == 3
        assert Decimal(history["total_revenue"]) == Decimal("15")
        assert history["last_booked"] is not None

    async def test_market_performance_from_bids(self, service, session):
        offer_id = f"offer-{_uid()}"
        session.add(
            MarketOffer(
                id=offer_id,
                provider=_addr(PROVIDER_KEY),
                status="in_use",
                capacity=1,
                price=Decimal("5"),
                price_per_hour=Decimal("5"),
                chain_id=_chain_id(),
            )
        )
        now = datetime.now(UTC).replace(tzinfo=None)
        for price in ("4", "5", "6"):
            session.add(
                Bid(
                    offer_id=offer_id,
                    provider=_addr(PROVIDER_KEY),
                    buyer=_addr(BUYER_KEY),
                    capacity=1,
                    price=Decimal(price),
                    status="completed",
                    created_at=now,
                )
            )
        session.add(
            Bid(
                offer_id=offer_id,
                provider=_addr(PROVIDER_KEY),
                buyer=_addr(BUYER_KEY),
                capacity=1,
                price=Decimal("5"),
                status="pending",
                created_at=now,
            )
        )
        await session.commit()
        perf = await service.get_market_performance("daily")
        assert perf["total_trades"] >= 3
        assert Decimal(perf["total_volume"]) >= Decimal("15")
        assert Decimal(perf["fill_rate"]) > 0
        assert perf["active_providers"] >= 1


# ------------------------------------------------------------------ #2625/#2626


class TestDeploymentFiles:
    async def test_setup_database_sql_removed(self):
        repo_root = Path(__file__).resolve().parents[3]
        assert not (repo_root / "apps/market/scripts/setup-database.sql").exists()

    async def test_systemd_unit_has_no_literal_pythonpath(self):
        repo_root = Path(__file__).resolve().parents[3]
        unit = (repo_root / "apps/market/aitbc-market.service").read_text()
        assert "$PYTHONPATH" not in unit

    async def test_wrapper_removed(self):
        repo_root = Path(__file__).resolve().parents[3]
        assert not (repo_root / "apps/market/aitbc-market-wrapper.py").exists()
