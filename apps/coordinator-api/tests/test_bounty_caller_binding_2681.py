"""Caller binding on developer-platform bounty mutations (#2681).

POST /bounties, /bounties/{id}/submit and /bounties/{id}/review took no
user dependency: any client JWT could name any ``creator_address``, any
``developer_id`` and any ``reviewer_address``, and could reject any
submission. The routes now bind each actor id to the authenticated caller
(``require_identity_access``) and the review additionally requires the
bounty's creator.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from aitbc.auth import create_access_token

from coordinator_api.contexts.developer_platform.domain.developer_platform import (
    BountyStatus,
    BountySubmission,
    BountyTask,
    DeveloperProfile,
)
from coordinator_api.contexts.infrastructure.domain.user import User, Wallet

BASE = "/v1/developer-platform"

CREATOR_WALLET = "0x" + "aa" * 20
DEV_WALLET = "0x" + "bb" * 20
ATTACKER_WALLET = "0x" + "cc" * 20


def _actor(db_session: Session, sub: str, *addresses: str, role: str = "client") -> dict[str, str]:
    """Create/re-point the caller's wallet rows and return JWT headers."""
    if db_session.get(User, sub) is None:
        db_session.add(User(id=sub, email=f"{sub}@example.com", username=sub))
    for addr in addresses:
        existing = db_session.execute(select(Wallet).where(Wallet.address == addr.lower())).scalars().first()
        if existing is not None:
            existing.user_id = sub
        else:
            db_session.add(Wallet(user_id=sub, address=addr.lower()))
    db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _bounty(db_session: Session, bounty_id: str = "bty-1", creator: str = CREATOR_WALLET) -> BountyTask:
    row = BountyTask(
        id=bounty_id,
        title="fix the thing",
        description="desc",
        reward_amount=Decimal("1.0"),
        creator_address=creator,
        status=BountyStatus.OPEN,
    )
    db_session.add(row)
    db_session.commit()
    return row


def _developer(db_session: Session, dev_id: str = "dev-1", wallet: str = DEV_WALLET) -> DeveloperProfile:
    row = DeveloperProfile(id=dev_id, wallet_address=wallet, skills=["python"])
    db_session.add(row)
    db_session.commit()
    return row


def _submission(db_session: Session, bounty_id: str = "bty-1", dev_id: str = "dev-1") -> BountySubmission:
    row = BountySubmission(id="sub-1", bounty_id=bounty_id, developer_id=dev_id)
    db_session.add(row)
    db_session.commit()
    return row


def _create_body(creator: str) -> dict:
    return {
        "title": "t",
        "description": "d",
        "reward_amount": "1.0",
        "creator_address": creator,
    }


class TestCreateBountyBinding:
    def test_foreign_creator_address_rejected(self, client: TestClient, db_session):
        headers = _actor(db_session, "u-cr-1", ATTACKER_WALLET)
        resp = client.post(f"{BASE}/bounties", json=_create_body(CREATOR_WALLET), headers=headers)
        assert resp.status_code == 403

    def test_own_creator_address_accepted(self, client: TestClient, db_session):
        headers = _actor(db_session, "u-cr-2", CREATOR_WALLET)
        resp = client.post(f"{BASE}/bounties", json=_create_body(CREATOR_WALLET), headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True


class TestSubmitBinding:
    def test_foreign_developer_rejected(self, client: TestClient, db_session):
        _bounty(db_session)
        _developer(db_session)
        headers = _actor(db_session, "u-sub-1", ATTACKER_WALLET)
        resp = client.post(
            f"{BASE}/bounties/bty-1/submit",
            json={"developer_id": "dev-1", "github_pr_url": "https://example.com/pr/1"},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_own_developer_accepted(self, client: TestClient, db_session):
        _bounty(db_session)
        _developer(db_session)
        headers = _actor(db_session, "u-sub-2", DEV_WALLET)
        resp = client.post(
            f"{BASE}/bounties/bty-1/submit",
            json={"developer_id": "dev-1", "github_pr_url": "https://example.com/pr/1"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True


class TestReviewBinding:
    def _seed(self, db_session: Session) -> None:
        _developer(db_session)
        _bounty(db_session)
        _submission(db_session)

    def test_non_creator_cannot_reject(self, client: TestClient, db_session):
        self._seed(db_session)
        headers = _actor(db_session, "u-rev-1", ATTACKER_WALLET)
        resp = client.post(
            f"{BASE}/bounties/bty-1/review",
            params={
                "submission_id": "sub-1",
                "reviewer_address": ATTACKER_WALLET,
                "review_notes": "no",
            },
            headers=headers,
        )
        assert resp.status_code == 403
        db_session.expire_all()
        assert db_session.get(BountySubmission, "sub-1").reviewed_at is None

    def test_creator_can_reject(self, client: TestClient, db_session):
        self._seed(db_session)
        headers = _actor(db_session, "u-rev-2", CREATOR_WALLET)
        resp = client.post(
            f"{BASE}/bounties/bty-1/review",
            params={
                "submission_id": "sub-1",
                "reviewer_address": CREATOR_WALLET,
                "review_notes": "no",
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_approved"] is False

    def test_admin_can_review_any_bounty(self, client: TestClient, db_session):
        self._seed(db_session)
        headers = _actor(db_session, "u-rev-3", ATTACKER_WALLET, role="admin")
        resp = client.post(
            f"{BASE}/bounties/bty-1/review",
            params={
                "submission_id": "sub-1",
                "reviewer_address": ATTACKER_WALLET,
                "review_notes": "operator ruling",
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
