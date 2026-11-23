"""Bounty approval must not fake a payout (#2683).

``_submit_reward_payout`` POSTed ``/rpc/sendTransaction`` — a route no
node serves — so every approval failed 502 while the response read as a
live payout. There is no funded on-chain leg to pay from either:
dev-platform bounties never deploy a ``/rpc/bounty/deploy`` lock or record
a ``/rpc/bounty/{id}/submit`` submission. The payout now answers 501
honestly and approval is refused (nothing commits).
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlmodel import Session

from aitbc.auth import create_access_token

from coordinator_api.contexts.developer_platform.domain.developer_platform import (
    BountyStatus,
    BountySubmission,
    BountyTask,
    DeveloperProfile,
)
from coordinator_api.contexts.infrastructure.domain.user import User

BASE = "/v1/developer-platform"
CREATOR_WALLET = "0x" + "ee" * 20
DEV_WALLET = "0x" + "ff" * 20


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('admin-2683', 'admin')}"}


def _seed(db_session: Session) -> None:
    db_session.add(User(id="admin-2683", email="a@x.com", username="admin-2683"))
    db_session.add(DeveloperProfile(id="dev-2683", wallet_address=DEV_WALLET))
    db_session.add(
        BountyTask(
            id="bty-2683",
            title="t",
            description="d",
            reward_amount=Decimal("5.0"),
            creator_address=CREATOR_WALLET,
            status=BountyStatus.IN_REVIEW,
        )
    )
    db_session.add(BountySubmission(id="sub-2683", bounty_id="bty-2683", developer_id="dev-2683"))
    db_session.commit()


def test_approve_answers_501_and_records_nothing(client: TestClient, db_session):
    _seed(db_session)
    resp = client.post(
        f"{BASE}/bounties/bty-2683/review",
        params={
            "submission_id": "sub-2683",
            "reviewer_address": CREATOR_WALLET,
            "review_notes": "looks good",
            "approved": "true",
        },
        headers=_headers(),
    )
    assert resp.status_code == 501, resp.text
    db_session.expire_all()
    submission = db_session.get(BountySubmission, "sub-2683")
    assert submission is not None and submission.is_approved is False
    bounty = db_session.get(BountyTask, "bty-2683")
    assert bounty is not None and bounty.status == BountyStatus.IN_REVIEW


def test_reject_still_works_without_payout(client: TestClient, db_session):
    """Reject never touched the payout path — unchanged."""
    _seed(db_session)
    resp = client.post(
        f"{BASE}/bounties/bty-2683/review",
        params={
            "submission_id": "sub-2683",
            "reviewer_address": CREATOR_WALLET,
            "review_notes": "not good enough",
        },
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_approved"] is False
