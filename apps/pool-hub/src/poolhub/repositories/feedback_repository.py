from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Iterable, List, Optional
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Feedback
from ..storage.redis_keys import RedisKeys

logger = logging.getLogger(__name__)


class FeedbackRepository:
    """Persists coordinator feedback and emits Redis notifications."""

    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self._session = session
        self._redis = redis

    async def add_feedback(
        self,
        *,
        job_id: str,
        miner_id: str,
        outcome: str,
        latency_ms: Optional[int] = None,
        fail_code: Optional[str] = None,
        tokens_spent: Optional[float] = None,
    ) -> Feedback:
        feedback = Feedback(
            job_id=job_id,
            miner_id=miner_id,
            outcome=outcome,
            latency_ms=latency_ms,
            fail_code=fail_code,
            tokens_spent=tokens_spent,
            created_at=dt.datetime.utcnow(),
        )
        self._session.add(feedback)
        await self._session.flush()

        payload = {
            "job_id": job_id,
            "miner_id": miner_id,
            "outcome": outcome,
            "latency_ms": latency_ms,
            "fail_code": fail_code,
            "tokens_spent": tokens_spent,
            "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
        }
        try:
            await self._redis.publish(RedisKeys.feedback_channel(), json.dumps(payload))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to publish feedback event for job %s: %s", job_id, exc)
        return feedback

    async def list_feedback_for_miner(self, miner_id: str, limit: int = 50) -> List[Feedback]:
        stmt = (
            select(Feedback)
            .where(Feedback.miner_id == miner_id)
            .order_by(Feedback.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_feedback_for_job(self, job_id: str, limit: int = 50) -> List[Feedback]:
        stmt = (
            select(Feedback)
            .where(Feedback.job_id == job_id)
            .order_by(Feedback.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
