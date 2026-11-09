"""Service tests for BountyService lifecycle (#1347).

Bounties are live on creation: there is no draft/publish surface, so
``create_bounty`` must persist ``ACTIVE`` — previously the model default
``CREATED`` was a dead state and ``create_submission`` (which requires
ACTIVE) could never succeed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlmodel import Session

from coordinator_api.contexts.bounty.domain.bounty import BountyStatus, SubmissionStatus
from coordinator_api.contexts.bounty.services.bounty_service import BountyService


def _create_kwargs() -> dict:
    return {
        "creator_id": "creator-agent-1",
        "title": "fix the bug",
        "description": "a sufficiently long description",
        "reward_amount": Decimal("100.0"),
        "tier": "bronze",
        "performance_criteria": {},
        "min_accuracy": 90.0,
        "max_response_time": None,
        "deadline": datetime.now(UTC) + timedelta(days=7),
        "max_submissions": 10,
        "requires_zk_proof": False,
        "auto_verify_threshold": 95.0,
        "tags": ["python"],
        "category": None,
        "difficulty": None,
    }


async def test_created_bounty_is_active(db_session: Session) -> None:
    bounty = await BountyService(db_session).create_bounty(**_create_kwargs())
    assert bounty.status == BountyStatus.ACTIVE


async def test_submission_reachable_after_create(db_session: Session) -> None:
    service = BountyService(db_session)
    bounty = await service.create_bounty(**_create_kwargs())
    submission = await service.create_submission(
        bounty_id=bounty.bounty_id,
        submitter_address="0x" + "11" * 20,
        accuracy=92.0,
        performance_hash="deadbeef",
        submission_data={"solution_url": "https://example.com/fix"},
    )
    assert submission.bounty_id == bounty.bounty_id
    assert submission.status.value == "pending"


async def test_dispute_after_verify_survives_naive_roundtrip(db_session: Session) -> None:
    """#1353: verification_time round-trips naive through sqlite; the dispute
    window check must normalize before subtracting (same class as #1347)."""
    service = BountyService(db_session)
    bounty = await service.create_bounty(**_create_kwargs())
    submission = await service.create_submission(
        bounty_id=bounty.bounty_id,
        submitter_address="0x" + "11" * 20,
        accuracy=92.0,
        performance_hash="deadbeef",
        submission_data={"solution_url": "https://example.com/fix"},
    )
    await service.verify_submission(bounty.bounty_id, submission.submission_id, True, "verifier-1")
    disputed = await service.create_dispute(bounty.bounty_id, submission.submission_id, "0x" + "22" * 20, "result is wrong")
    assert disputed.status == SubmissionStatus.DISPUTED
