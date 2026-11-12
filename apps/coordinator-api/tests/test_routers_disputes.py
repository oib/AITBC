"""Router tests for /v1/disputes/* (#1289 round 9 batch 4; #1333/#1334/#1335 fixes;
#1854 authz hardening).

Real DisputeResolutionService (in-memory). Caller identity is bound to the
JWT subject on every endpoint:
- file: job must exist; caller must be a job party (client_id /
  provider_address / assigned_miner_id); parties+amount come from the Job
  row, not the request body
- evidence: submitted_by = user["sub"], party membership checked against
  the caller's full identity set (sub + wallet addresses)
- vote: arbitrator = user["sub"]; registration requires ACTIVE AgentStake
  >= MIN_STAKE_AMOUNT; stake_amount may not exceed active stake
- read: GET / and GET /{id} require auth; non-admins only see disputes they
  are a party to
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

import coordinator_api.contexts.governance.services.dispute_resolution as dr_mod
from coordinator_api.contexts.governance.services.dispute_resolution import init_dispute_service
from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.infrastructure.domain.user import User, Wallet
from coordinator_api.contexts.staking.domain.staking import AgentStake
from aitbc.auth import create_access_token

BASE = "/v1/disputes"
CLIENT_SUB = "client-sub-1"
PROVIDER_SUB = "provider-user-1"
PROVIDER_ADDR = "0x" + "22" * 20
JOB_ID = "job-1"
ARB1 = "0x" + "a1" * 20
ARB2 = "0x" + "a2" * 20
ARB3 = "0x" + "a3" * 20
STAKE_AMOUNT = Decimal("100000")


def _headers(sub: str, role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


@pytest.fixture
def dispute_service():
    # app startup already ran _init_dispute_service(get_session); swap in a
    # fresh in-memory service per test and restore the app-level one after
    original = dr_mod._dispute_service
    svc = init_dispute_service(None)
    yield svc
    dr_mod._dispute_service = original


def _ensure_user(db_session: Session, sub: str) -> None:
    if db_session.get(User, sub) is None:
        db_session.add(User(id=sub, email=f"{sub}@example.com", username=sub))
        db_session.commit()


def _make_job(
    db_session: Session,
    job_id: str = JOB_ID,
    client_id: str = CLIENT_SUB,
    provider_address: str | None = PROVIDER_ADDR,
    amount: Decimal | None = Decimal("5000"),
) -> Job:
    _ensure_user(db_session, client_id)
    job = db_session.get(Job, job_id)
    if job is None:
        job = Job(
            id=job_id,
            client_id=client_id,
            state="COMPLETED",
            payload={},
            provider_address=provider_address,
            payment_amount=amount,
        )
        db_session.add(job)
        db_session.commit()
    return job


def _link_wallet(db_session: Session, sub: str, address: str) -> None:
    _ensure_user(db_session, sub)
    if db_session.exec(select(Wallet).where(Wallet.user_id == sub)).first() is None:
        db_session.add(Wallet(user_id=sub, address=address))
        db_session.commit()


def _stake(db_session: Session, address: str, amount: Decimal = STAKE_AMOUNT) -> None:
    db_session.add(
        AgentStake(
            staker_address=address,
            agent_wallet=address,
            amount=amount,
            end_time=datetime.now(UTC) + timedelta(days=30),
        )
    )
    db_session.commit()


def _file(client: TestClient, db_session: Session, sub: str = CLIENT_SUB, job_id: str = JOB_ID, **over) -> dict:
    _make_job(db_session, job_id=job_id)
    body = {
        "job_id": job_id,
        "client": "attacker-supplied",
        "provider": "attacker-supplied",
        "amount": 1,
        "reason": "no delivery",
    }
    body.update(over)
    resp = client.post(f"{BASE}/file", json=body, headers=_headers(sub))
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestDisputeLifecycle:
    def test_health(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/health").json()["service"] == "disputes"

    def test_list_empty_service(self, client: TestClient, db_session: Session, dispute_service) -> None:
        resp = client.get(f"{BASE}/", headers=_headers(CLIENT_SUB))
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_file_and_get(self, client: TestClient, db_session: Session, dispute_service) -> None:
        dispute = _file(client, db_session)
        did = dispute["dispute_id"]
        # parties/amount come from the job row, not the request body
        assert dispute["client"] == CLIENT_SUB
        assert dispute["provider"] == PROVIDER_ADDR
        assert dispute["amount"] == 5000
        got = client.get(f"{BASE}/{did}", headers=_headers(CLIENT_SUB))
        assert got.status_code == 200
        assert got.json()["job_id"] == JOB_ID

    def test_list_filters(self, client: TestClient, db_session: Session, dispute_service) -> None:
        _file(client, db_session)
        resp = client.get(f"{BASE}/", params={"party": CLIENT_SUB}, headers=_headers(CLIENT_SUB))
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

    def test_get_missing_404(self, client: TestClient, db_session: Session, dispute_service) -> None:
        assert client.get(f"{BASE}/0xghost", headers=_headers(CLIENT_SUB)).status_code == 404

    def test_validation(self, client: TestClient, db_session: Session, dispute_service) -> None:
        assert client.post(f"{BASE}/file", json={}, headers=_headers(CLIENT_SUB)).status_code == 422

    def test_file_requires_auth(self, client: TestClient, db_session: Session, dispute_service) -> None:
        body = {"job_id": "j", "client": CLIENT_SUB, "provider": PROVIDER_ADDR, "amount": 1, "reason": "r"}
        assert client.post(f"{BASE}/file", json=body).status_code == 401

    def test_file_requires_existing_job(self, client: TestClient, db_session: Session, dispute_service) -> None:
        body = {"job_id": "no-such-job", "client": CLIENT_SUB, "provider": PROVIDER_ADDR, "amount": 1, "reason": "r"}
        resp = client.post(f"{BASE}/file", json=body, headers=_headers(CLIENT_SUB))
        assert resp.status_code == 404

    def test_file_null_provider_is_409_not_body_fallback(
        self, client: TestClient, db_session: Session, dispute_service
    ) -> None:
        # #1879: NULL provider_address/assigned_miner_id must not fall back
        # to the request body's provider — that re-trusts caller input.
        _make_job(db_session, job_id="job-noprovider", provider_address=None)
        body = {"job_id": "job-noprovider", "client": CLIENT_SUB, "provider": "0x" + "ab" * 20, "amount": 1, "reason": "r"}
        resp = client.post(f"{BASE}/file", json=body, headers=_headers(CLIENT_SUB))
        assert resp.status_code == 409

    def test_file_null_amount_is_409_not_body_fallback(self, client: TestClient, db_session: Session, dispute_service) -> None:
        _make_job(db_session, job_id="job-noamount", amount=None)
        body = {"job_id": "job-noamount", "client": CLIENT_SUB, "provider": PROVIDER_ADDR, "amount": 999, "reason": "r"}
        resp = client.post(f"{BASE}/file", json=body, headers=_headers(CLIENT_SUB))
        assert resp.status_code == 409

    def test_file_non_party_rejected(self, client: TestClient, db_session: Session, dispute_service) -> None:
        _make_job(db_session)
        body = {"job_id": JOB_ID, "client": "random-sub", "provider": PROVIDER_ADDR, "amount": 1, "reason": "r"}
        resp = client.post(f"{BASE}/file", json=body, headers=_headers("random-sub"))
        assert resp.status_code == 403

    def test_file_provider_via_wallet_identity(self, client: TestClient, db_session: Session, dispute_service) -> None:
        _make_job(db_session)
        _link_wallet(db_session, PROVIDER_SUB, PROVIDER_ADDR)
        body = {"job_id": JOB_ID, "client": CLIENT_SUB, "provider": PROVIDER_ADDR, "amount": 1, "reason": "r"}
        resp = client.post(f"{BASE}/file", json=body, headers=_headers(PROVIDER_SUB))
        assert resp.status_code == 200
        assert resp.json()["filed_by"] == PROVIDER_SUB

    def test_admin_can_file_and_read_any(self, client: TestClient, db_session: Session, dispute_service) -> None:
        _make_job(db_session)
        body = {"job_id": JOB_ID, "client": CLIENT_SUB, "provider": PROVIDER_ADDR, "amount": 1, "reason": "r"}
        resp = client.post(f"{BASE}/file", json=body, headers=_headers("admin-1", role="admin"))
        assert resp.status_code == 200
        did = resp.json()["dispute_id"]
        # admin sees disputes they are not a party to
        got = client.get(f"{BASE}/{did}", headers=_headers("admin-1", role="admin"))
        assert got.status_code == 200
        listing = client.get(f"{BASE}/", headers=_headers("admin-1", role="admin"))
        assert listing.json()["count"] >= 1


class TestReadPartyScoping:
    def test_get_non_party_rejected(self, client: TestClient, db_session: Session, dispute_service) -> None:
        dispute = _file(client, db_session)
        resp = client.get(f"{BASE}/{dispute['dispute_id']}", headers=_headers("random-sub"))
        assert resp.status_code == 403

    def test_get_requires_auth(self, client: TestClient, db_session: Session, dispute_service) -> None:
        dispute = _file(client, db_session)
        assert client.get(f"{BASE}/{dispute['dispute_id']}").status_code == 401

    def test_list_hides_non_party_disputes(self, client: TestClient, db_session: Session, dispute_service) -> None:
        _file(client, db_session)
        resp = client.get(f"{BASE}/", headers=_headers("random-sub"))
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_list_party_filter_cannot_widen_scope(self, client: TestClient, db_session: Session, dispute_service) -> None:
        _file(client, db_session)
        # random-sub asks for CLIENT_SUB's disputes — still sees nothing
        resp = client.get(f"{BASE}/", params={"party": CLIENT_SUB}, headers=_headers("random-sub"))
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


class TestEvidenceBinding:
    def test_submit_evidence_as_client_party(self, client: TestClient, db_session: Session, dispute_service) -> None:
        dispute = _file(client, db_session)
        resp = client.post(
            f"{BASE}/evidence",
            json={
                "dispute_id": dispute["dispute_id"],
                "evidence_type": "log",
                "description": "proof",
                "ipfs_hash": "Qm...",
            },
            headers=_headers(CLIENT_SUB),
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_submit_evidence_as_provider_wallet_identity(
        self, client: TestClient, db_session: Session, dispute_service
    ) -> None:
        dispute = _file(client, db_session)
        _link_wallet(db_session, PROVIDER_SUB, PROVIDER_ADDR)
        resp = client.post(
            f"{BASE}/evidence",
            json={"dispute_id": dispute["dispute_id"], "evidence_type": "log", "description": "provider proof"},
            headers=_headers(PROVIDER_SUB),
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_submit_evidence_non_party_rejected(self, client: TestClient, db_session: Session, dispute_service) -> None:
        dispute = _file(client, db_session)
        resp = client.post(
            f"{BASE}/evidence",
            json={"dispute_id": dispute["dispute_id"], "evidence_type": "log", "description": "x"},
            headers=_headers("random-sub"),
        )
        assert resp.status_code == 400

    def test_evidence_requires_auth(self, client: TestClient, db_session: Session, dispute_service) -> None:
        resp = client.post(
            f"{BASE}/evidence",
            json={"dispute_id": "d", "evidence_type": "log", "description": "x"},
        )
        assert resp.status_code == 401


class TestArbitration:
    def _open_dispute(self, client: TestClient, db_session: Session) -> str:
        return _file(client, db_session)["dispute_id"]

    def _register(self, client: TestClient, sub: str, address: str | None = None) -> int:
        return client.post(
            f"{BASE}/arbitrators/register", params={"address": address or sub}, headers=_headers(sub)
        ).status_code

    def _vote(self, client: TestClient, sub: str, did: str, outcome: str = "client_wins", stake: int = 5000) -> int:
        return client.post(
            f"{BASE}/vote",
            json={"dispute_id": did, "outcome": outcome, "reasoning": "r", "stake_amount": stake},
            headers=_headers(sub),
        ).status_code

    def _stake_all_arbitrators(self, db_session: Session) -> None:
        for arb in (ARB1, ARB2, ARB3):
            _stake(db_session, arb)

    def test_distinct_arbitrators_reach_quorum(self, client: TestClient, db_session: Session, dispute_service) -> None:
        did = self._open_dispute(client, db_session)
        self._stake_all_arbitrators(db_session)
        for arb in (ARB1, ARB2, ARB3):
            assert self._register(client, arb) == 200
        assert self._vote(client, ARB1, did) == 200
        assert self._vote(client, ARB2, did, "provider_wins") == 200
        assert self._vote(client, ARB3, did, "split") == 200
        # 3 votes = MIN_ARBITRATORS -> dispute resolves
        got = client.get(f"{BASE}/{did}", headers=_headers(CLIENT_SUB)).json()
        assert got["status"] == "resolved"

    def test_same_arbitrator_cannot_vote_twice(self, client: TestClient, db_session: Session, dispute_service) -> None:
        did = self._open_dispute(client, db_session)
        _stake(db_session, ARB1)
        assert self._register(client, ARB1) == 200
        assert self._vote(client, ARB1, did) == 200
        assert self._vote(client, ARB1, did, "provider_wins") == 400

    def test_arbitrator_registration_requires_auth(self, client: TestClient, db_session: Session, dispute_service) -> None:
        resp = client.post(f"{BASE}/arbitrators/register", params={"address": "attacker"})
        assert resp.status_code == 401

    def test_arbitrator_cannot_register_other_identity(self, client: TestClient, db_session: Session, dispute_service) -> None:
        resp = client.post(f"{BASE}/arbitrators/register", params={"address": "victim"}, headers=_headers("attacker"))
        assert resp.status_code == 403

    def test_arbitrator_registration_requires_stake(self, client: TestClient, db_session: Session, dispute_service) -> None:
        # no AgentStake rows -> fresh account cannot self-register
        assert self._register(client, ARB1) == 403

    def test_arbitrator_registration_below_min_stake(self, client: TestClient, db_session: Session, dispute_service) -> None:
        _stake(db_session, ARB1, amount=Decimal("500"))
        assert self._register(client, ARB1) == 403

    def test_inactive_stake_does_not_count(self, client: TestClient, db_session: Session, dispute_service) -> None:
        from coordinator_api.contexts.staking.domain.staking import StakeStatus

        db_session.add(
            AgentStake(
                staker_address=ARB1,
                agent_wallet=ARB1,
                amount=STAKE_AMOUNT,
                status=StakeStatus.COMPLETED,
                end_time=datetime.now(UTC) + timedelta(days=30),
            )
        )
        db_session.commit()
        assert self._register(client, ARB1) == 403

    def test_vote_requires_registered_arbitrator(self, client: TestClient, db_session: Session, dispute_service) -> None:
        did = self._open_dispute(client, db_session)
        assert self._vote(client, "0x" + "99" * 20, did) in (400, 403)

    def test_min_stake_enforced(self, client: TestClient, db_session: Session, dispute_service) -> None:
        did = self._open_dispute(client, db_session)
        _stake(db_session, ARB1)
        assert self._register(client, ARB1) == 200
        resp = client.post(
            f"{BASE}/vote",
            json={"dispute_id": did, "outcome": "split", "reasoning": "r", "stake_amount": 1},
            headers=_headers(ARB1),
        )
        assert resp.status_code == 400

    def test_vote_stake_cannot_exceed_active_stake(self, client: TestClient, db_session: Session, dispute_service) -> None:
        did = self._open_dispute(client, db_session)
        _stake(db_session, ARB1, amount=Decimal("10000"))
        assert self._register(client, ARB1) == 200
        # 20000 > 10000 active stake -> rejected before the service sees it
        assert self._vote(client, ARB1, did, stake=20000) == 403

    def test_vote_requires_auth(self, client: TestClient, db_session: Session, dispute_service) -> None:
        did = self._open_dispute(client, db_session)
        resp = client.post(
            f"{BASE}/vote",
            json={"dispute_id": did, "outcome": "client_wins", "reasoning": "r", "stake_amount": 5000},
        )
        assert resp.status_code == 401
