"""Miner registration and heartbeat routes for pool hub."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ...repositories.miner_repository import MinerRepository
from ..deps import db_session_dep, get_miner_from_token, redis_dep

router = APIRouter(prefix="/miners", tags=["miners"])


class MinerRegisterRequest(BaseModel):
    miner_id: str
    api_key: str
    addr: str = "localhost"
    proto: str = "http"
    gpu_vram_gb: float = 0.0
    gpu_name: str | None = None
    cpu_cores: int = 1
    ram_gb: float = 0.0
    max_parallel: int = 1
    base_price: str = "0.01"
    tags: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)
    region: str | None = "localhost"
    chain_id: str = "ait-hub"
    wallet_address: str | None = None


class MinerHeartbeatRequest(BaseModel):
    status: str = "active"
    current_jobs: int = 0
    gpu_utilization: int = 0
    memory_used: int = 0
    memory_total: int = 0
    network_latency_ms: float = 0.0


@router.post("/register")
async def register_miner(
    data: MinerRegisterRequest,
    session: Annotated[AsyncSession, Depends(db_session_dep)],
    redis: Annotated[Redis, Depends(redis_dep)],
) -> dict[str, Any]:
    """Register a miner with the pool hub."""
    repo = MinerRepository(session, redis)
    api_key_hash = hashlib.sha256(data.api_key.encode()).hexdigest()

    miner = await repo.register_miner(
        data.miner_id,
        api_key_hash,
        addr=data.addr,
        proto=data.proto,
        gpu_vram_gb=data.gpu_vram_gb,
        gpu_name=data.gpu_name,
        cpu_cores=data.cpu_cores,
        ram_gb=data.ram_gb,
        max_parallel=data.max_parallel,
        base_price=Decimal(data.base_price),
        tags=data.tags,
        capabilities=data.capabilities,
        region=data.region,
    )

    miner.chain_id = data.chain_id
    miner.wallet_address = data.wallet_address
    await session.commit()
    await session.refresh(miner)

    return {
        "success": True,
        "miner_id": miner.miner_id,
        "created": True,
    }


@router.post("/heartbeat")
async def miner_heartbeat(
    data: MinerHeartbeatRequest,
    miner: Annotated[Any, Depends(get_miner_from_token)],
    session: Annotated[AsyncSession, Depends(db_session_dep)],
    redis: Annotated[Redis, Depends(redis_dep)],
) -> dict[str, Any]:
    """Record a miner heartbeat."""
    repo = MinerRepository(session, redis)
    await repo.touch_heartbeat(miner.miner_id)
    await repo.update_status(
        miner.miner_id,
        queue_len=data.current_jobs,
        busy=data.status != "active" or data.current_jobs > 0,
        avg_latency_ms=int(data.network_latency_ms),
        mem_free_gb=(data.memory_total - data.memory_used) / 1024 if data.memory_total else None,
    )
    return {"success": True, "miner_id": miner.miner_id}


@router.get("/status")
async def miner_status(
    miner: Annotated[Any, Depends(get_miner_from_token)],
) -> dict[str, Any]:
    """Return the authenticated miner's status."""
    return {
        "miner_id": miner.miner_id,
        "last_seen_at": miner.last_seen_at.isoformat() if miner.last_seen_at else None,
        "addr": miner.addr,
        "capabilities": miner.capabilities,
    }
