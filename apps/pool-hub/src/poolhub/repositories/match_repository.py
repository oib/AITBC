from __future__ import annotations

import datetime as dt
import json
from typing import Iterable, List, Optional, Sequence
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import MatchRequest, MatchResult
from ..storage.redis_keys import RedisKeys


class MatchRepository:
    """Handles match request logging, result persistence, and Redis fan-out."""

    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self._session = session
        self._redis = redis

    async def create_request(
        self,
        *,
        job_id: str,
        requirements: dict[str, object],
        hints: Optional[dict[str, object]] = None,
        top_k: int = 1,
        enqueue: bool = True,
    ) -> MatchRequest:
        request = MatchRequest(
            job_id=job_id,
            requirements=requirements,
            hints=hints or {},
            top_k=top_k,
            created_at=dt.datetime.utcnow(),
        )
        self._session.add(request)
        await self._session.flush()

        if enqueue:
            payload = {
                "request_id": str(request.id),
                "job_id": request.job_id,
                "requirements": request.requirements,
                "hints": request.hints,
                "top_k": request.top_k,
            }
            await self._redis.rpush(RedisKeys.match_requests(), json.dumps(payload))
        return request

    async def add_results(
        self,
        *,
        request_id: UUID,
        candidates: Sequence[dict[str, object]],
        publish: bool = True,
    ) -> List[MatchResult]:
        results: List[MatchResult] = []
        created_at = dt.datetime.utcnow()
        for candidate in candidates:
            result = MatchResult(
                request_id=request_id,
                miner_id=str(candidate.get("miner_id")),
                score=float(candidate.get("score", 0.0)),
                explain=candidate.get("explain"),
                eta_ms=candidate.get("eta_ms"),
                price=candidate.get("price"),
                created_at=created_at,
            )
            self._session.add(result)
            results.append(result)
        await self._session.flush()

        if publish:
            request = await self._session.get(MatchRequest, request_id)
            if request:
                redis_key = RedisKeys.match_results(request.job_id)
                await self._redis.delete(redis_key)
                if results:
                    payloads = [json.dumps(self._result_payload(result)) for result in results]
                    await self._redis.rpush(redis_key, *payloads)
                    await self._redis.expire(redis_key, 300)
                    channel = RedisKeys.match_results_channel(request.job_id)
                    for payload in payloads:
                        await self._redis.publish(channel, payload)
        return results

    async def get_request(self, request_id: UUID) -> Optional[MatchRequest]:
        return await self._session.get(MatchRequest, request_id)

    async def list_recent_requests(self, limit: int = 20) -> List[MatchRequest]:
        stmt: Select[MatchRequest] = (
            select(MatchRequest)
            .order_by(MatchRequest.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_results_for_job(self, job_id: str, limit: int = 10) -> List[MatchResult]:
        stmt: Select[MatchResult] = (
            select(MatchResult)
            .join(MatchRequest)
            .where(MatchRequest.job_id == job_id)
            .order_by(MatchResult.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    def _result_payload(self, result: MatchResult) -> dict[str, object]:
        return {
            "request_id": str(result.request_id),
            "miner_id": result.miner_id,
            "score": result.score,
            "explain": result.explain,
            "eta_ms": result.eta_ms,
            "price": result.price,
            "created_at": result.created_at.isoformat() if result.created_at else None,
        }
