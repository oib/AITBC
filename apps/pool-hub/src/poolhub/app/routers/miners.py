"""Miner registration and heartbeat routes for pool hub."""

from __future__ import annotations

import hashlib
import math
import re
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Miner
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

    @field_validator("base_price")
    @classmethod
    def _valid_base_price(cls, v: str) -> str:
        # #1495: base_price reaches Decimal() and the Numeric(20,8) column
        # unvalidated — "abc" was a 500, NaN/negative/oversized values were
        # storable. Bound matches Numeric(20,8): 12 integer + 8 fraction digits.
        try:
            price = Decimal(v)
        except InvalidOperation as exc:
            raise ValueError("base_price must be a decimal number") from exc
        if not price.is_finite() or price < 0 or price > Decimal("999999999999.99999999"):
            raise ValueError("base_price must be a finite Decimal in [0, 999999999999.99999999]")
        return v

    @field_validator("gpu_vram_gb", "ram_gb")
    @classmethod
    def _valid_hardware_gb(cls, v: float) -> float:
        # #1398 residual: NaN is truthy so `float(nan or 0)` slips past every
        # positive minimum in /v1/match; negatives and Inf are storable too.
        if not math.isfinite(v) or v < 0:
            raise ValueError("hardware sizes must be finite and non-negative")
        return v

    @field_validator("wallet_address")
    @classmethod
    def _valid_wallet_address(cls, v: str | None) -> str | None:
        # #1570: wallet_address is stored verbatim and later used as the
        # payout transaction's `to`. A malformed value is only discovered
        # at chain-submit time, where the failed payout row then wedges
        # the epoch's UNIQUE(miner_id, chain_id, epoch) claim forever.
        # Blank means "no wallet" (same as None downstream).
        if v is None or not v.strip():
            return None
        v = v.strip()
        if not re.fullmatch(r"0x[0-9a-fA-F]{40}", v):
            raise ValueError("wallet_address must be '0x' followed by 40 hex characters")
        return v


MAX_HEARTBEAT_COUNT = 10_000_000  # jobs / MB: far above any real value, finite
MAX_HEARTBEAT_LATENCY_MS = 600_000.0  # 10 minutes


class MinerHeartbeatRequest(BaseModel):
    status: str = "active"
    # #1399: miner-reported numerics feed match scoring and SLA metrics, so a
    # negative or absurd value must be rejected at the edge (422).
    current_jobs: int = Field(default=0, ge=0, le=MAX_HEARTBEAT_COUNT)
    gpu_utilization: int = Field(default=0, ge=0, le=100)
    memory_used: int = Field(default=0, ge=0, le=MAX_HEARTBEAT_COUNT)
    memory_total: int = Field(default=0, ge=0, le=MAX_HEARTBEAT_COUNT)
    network_latency_ms: float = Field(default=0.0, ge=0.0, le=MAX_HEARTBEAT_LATENCY_MS, allow_inf_nan=False)


@router.post("/register")
async def register_miner(
    data: MinerRegisterRequest,
    session: Annotated[AsyncSession, Depends(db_session_dep)],
    redis: Annotated[Redis, Depends(redis_dep)],
) -> dict[str, Any]:
    """Register a miner with the pool hub.

    First registration is open (the submitted api key becomes the miner's
    credential). Re-registering an existing miner_id requires the same api
    key — otherwise anyone could overwrite another miner's address, price
    and payout wallet (#1083).
    """
    repo = MinerRepository(session, redis)
    api_key_hash = hashlib.sha256(data.api_key.encode()).hexdigest()

    existing = await session.get(Miner, data.miner_id)
    if existing is not None and existing.api_key_hash != api_key_hash:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="miner_id already registered")

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
        mem_free_gb=max(data.memory_total - data.memory_used, 0) / 1024 if data.memory_total else None,
    )
    return {"success": True, "miner_id": miner.miner_id}


@router.get("/status")
def miner_status(
    miner: Annotated[Any, Depends(get_miner_from_token)],
) -> dict[str, Any]:
    """Return the authenticated miner's status."""
    return {
        "miner_id": miner.miner_id,
        "last_seen_at": miner.last_seen_at.isoformat() if miner.last_seen_at else None,
        "addr": miner.addr,
        "capabilities": miner.capabilities,
    }
