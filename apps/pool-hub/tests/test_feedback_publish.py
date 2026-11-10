"""FeedbackRepository Redis publish tests.

#1394 (POOLHUB-SERIAL-1, silent variant): the feedback payload carries
``tokens_spent`` — a Decimal off Numeric(20,8) — into ``json.dumps``. The
TypeError is swallowed by the defensive ``except Exception`` that only logs a
warning, so the publish silently never happens whenever tokens_spent is set.
"""

from __future__ import annotations

import json
from decimal import Decimal
import pytest

from poolhub.repositories.feedback_repository import FeedbackRepository


class FakeRedis:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1


class FakeSession:
    """AsyncSession stand-in: add/flush/commit recorded, nothing persisted."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self.commits = 0
        self.flushed = 0

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushed += 1

    async def commit(self) -> None:
        self.commits += 1


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


class TestAddFeedback:
    async def test_feedback_row_is_added_and_committed(self, session, redis):
        repo = FeedbackRepository(session, redis)
        feedback = await repo.add_feedback(job_id="job-1", miner_id="m-1", outcome="success")

        assert feedback.job_id == "job-1"
        assert feedback.outcome == "success"
        assert len(session.added) == 1
        assert session.commits == 1

    async def test_publish_without_tokens_spent_succeeds(self, session, redis):
        repo = FeedbackRepository(session, redis)
        await repo.add_feedback(job_id="job-1", miner_id="m-1", outcome="success")

        assert len(redis.published) == 1
        channel, raw = redis.published[0]
        assert channel == "poolhub:events:feedback"
        payload = json.loads(raw)
        assert payload["job_id"] == "job-1"
        assert payload["tokens_spent"] is None

    async def test_publish_with_tokens_spent_reaches_redis(self, session, redis):
        repo = FeedbackRepository(session, redis)
        await repo.add_feedback(
            job_id="job-1",
            miner_id="m-1",
            outcome="success",
            tokens_spent=Decimal("1.50000000"),
        )

        assert len(redis.published) == 1, "feedback event with tokens_spent was silently dropped"
        payload = json.loads(redis.published[0][1])
        assert payload["tokens_spent"] is not None
