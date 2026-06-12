# mypy: ignore-errors
from __future__ import annotations

import datetime as dt

from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Miner, MinerStatus
from ..settings import settings
from ..storage.redis_keys import RedisKeys


class MinerRepository:
    """Coordinates miner registry persistence across PostgreSQL and Redis."""

    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self._session = session
        self._redis = redis

    async def register_miner(
        self,
        miner_id: str,
        api_key_hash: str,
        *,
        addr: str,
        proto: str,
        gpu_vram_gb: float,
        gpu_name: str | None,
        cpu_cores: int,
        ram_gb: float,
        max_parallel: int,
        base_price: float,
        tags: dict[str, str],
        capabilities: list[str],
        region: str | None,
    ) -> Miner:
        miner = await self._session.get(Miner, miner_id)
        if miner is None:
            miner = Miner(
                miner_id=miner_id,
                api_key_hash=api_key_hash,
                addr=addr,
                proto=proto,
                gpu_vram_gb=gpu_vram_gb,
                gpu_name=gpu_name,
                cpu_cores=cpu_cores,
                ram_gb=ram_gb,
                max_parallel=max_parallel,
                base_price=base_price,
                tags=tags,
                capabilities=capabilities,
                region=region,
            )
            self._session.add(miner)
            status = MinerStatus(miner_id=miner_id)
            self._session.add(status)
        else:
            miner.addr = addr
            miner.proto = proto
            miner.gpu_vram_gb = gpu_vram_gb
            miner.gpu_name = gpu_name
            miner.cpu_cores = cpu_cores
            miner.ram_gb = ram_gb
            miner.max_parallel = max_parallel
            miner.base_price = base_price
            miner.tags = tags
            miner.capabilities = capabilities
            miner.region = region

        miner.last_seen_at = dt.datetime.now(dt.UTC)

        await self._session.flush()
        await self._sync_miner_to_redis(miner_id)
        return miner

    async def update_status(
        self,
        miner_id: str,
        *,
        queue_len: int | None = None,
        busy: bool | None = None,
        avg_latency_ms: int | None = None,
        temp_c: int | None = None,
        mem_free_gb: float | None = None,
    ) -> None:
        stmt = (
            update(MinerStatus)
            .where(MinerStatus.miner_id == miner_id)
            .values(
                {
                    k: v
                    for k, v in {
                        "queue_len": queue_len,
                        "busy": busy,
                        "avg_latency_ms": avg_latency_ms,
                        "temp_c": temp_c,
                        "mem_free_gb": mem_free_gb,
                        "updated_at": dt.datetime.now(dt.UTC),
                    }.items()
                    if v is not None
                }
            )
        )
        await self._session.execute(stmt)

        miner = await self._session.get(Miner, miner_id)
        if miner:
            miner.last_seen_at = dt.datetime.now(dt.UTC)
        await self._session.flush()
        await self._sync_miner_to_redis(miner_id)

    async def touch_heartbeat(self, miner_id: str) -> None:
        miner = await self._session.get(Miner, miner_id)
        if miner is None:
            return
        miner.last_seen_at = dt.datetime.now(dt.UTC)
        await self._session.flush()
        await self._sync_miner_to_redis(miner_id)

    async def get_miner(self, miner_id: str) -> Miner | None:
        return await self._session.get(Miner, miner_id)

    async def iter_miners(self) -> list[Miner]:
        result = await self._session.execute(select(Miner))
        return list(result.scalars().all())

    async def get_status(self, miner_id: str) -> MinerStatus | None:
        return await self._session.get(MinerStatus, miner_id)

    async def list_active_miners(self) -> list[tuple[Miner, MinerStatus | None, float]]:
        stmt = select(Miner, MinerStatus).join(MinerStatus, MinerStatus.miner_id == Miner.miner_id, isouter=True)
        result = await self._session.execute(stmt)
        records: list[tuple[Miner, MinerStatus | None, float]] = []
        for miner, status in result.all():
            score = self._compute_score(miner, status)
            records.append((miner, status, score))
        return records

    async def _sync_miner_to_redis(self, miner_id: str) -> None:
        miner = await self._session.get(Miner, miner_id)
        if miner is None:
            return
        status = await self._session.get(MinerStatus, miner_id)

        payload = {
            "miner_id": miner.miner_id,
            "addr": miner.addr,
            "proto": miner.proto,
            "region": miner.region or "",
            "gpu_vram_gb": str(miner.gpu_vram_gb),
            "ram_gb": str(miner.ram_gb),
            "max_parallel": str(miner.max_parallel),
            "base_price": str(miner.base_price),
            "trust_score": str(miner.trust_score),
            "queue_len": str(status.queue_len if status else 0),
            "busy": str(status.busy if status else False),
        }

        redis_key = RedisKeys.miner_hash(miner_id)
        await self._redis.hset(redis_key, mapping=payload)
        await self._redis.expire(redis_key, settings.session_ttl_seconds + settings.heartbeat_grace_seconds)

        score = self._compute_score(miner, status)
        ranking_key = RedisKeys.miner_rankings(miner.region)
        await self._redis.zadd(ranking_key, {miner_id: score})
        await self._redis.expire(ranking_key, settings.session_ttl_seconds + settings.heartbeat_grace_seconds)

    def _compute_score(self, miner: Miner, status: MinerStatus | None) -> float:
        load_factor = 1.0
        if status and miner.max_parallel:
            utilization = min(status.queue_len / max(miner.max_parallel, 1), 1.0)
            load_factor = 1.0 - utilization
        price_factor = 1.0 if miner.base_price <= 0 else min(1.0, 1.0 / miner.base_price)
        trust_factor = max(miner.trust_score, 0.0)
        return (settings.default_score_weights.capability * 1.0) + (
            settings.default_score_weights.price * price_factor
        ) + (settings.default_score_weights.load * load_factor) + (
            settings.default_score_weights.trust * trust_factor
        )
