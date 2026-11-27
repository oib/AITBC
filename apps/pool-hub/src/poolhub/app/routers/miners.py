"""Miner registration and heartbeat routes for pool hub."""

from __future__ import annotations

import hashlib
import hmac
import math
import re
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from aitbc.auth import APIKeyAuthenticator
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Miner
from ...repositories.miner_repository import MinerRepository
from ...settings import settings
from ...storage.redis_keys import RedisKeys
from ..deps import db_session_dep, get_miner_from_token, redis_dep

router = APIRouter(prefix="/miners", tags=["miners"])

# Operator credential for the miner recovery path (DELETE /v1/miners/{id},
# #3059). Same secret class and header as /v1/parameters/apply — the
# pool-hub operator key (POOLHUB_COORDINATOR_SHARED_SECRET). Bound at import
# like _governance_auth in routers/parameters.py; an unconfigured secret
# fails closed (501) inside APIKeyAuthenticator.
_operator_auth = APIKeyAuthenticator(
    expected_key=settings.coordinator_shared_secret,
    auth_enabled=True,
    header_name="X-PoolHub-Key",
    success_role="operator",
    key_name="POOLHUB_COORDINATOR_SHARED_SECRET",
)


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
    # #3059: operator-issued shared secret (POOLHUB_MINER_REGISTRATION_KEY),
    # required only when no miner row exists yet for miner_id. Ignored on
    # re-registration — the stored api_key_hash remains the credential.
    registration_key: str | None = None

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


def _require_first_registration_key(registration_key: str | None) -> None:
    """Gate first-time miner registration behind the operator-issued key (#3059).

    Fails closed when ``POOLHUB_MINER_REGISTRATION_KEY`` is unconfigured —
    an open first-registration path is the squatting defect itself, so an
    unprovisioned deployment refuses new miner_ids rather than silently
    re-opening it. Already-registered miners are unaffected: they take the
    re-registration branch, which never consults this key.
    """
    configured = settings.miner_registration_key
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="first-time miner registration is not configured on this pool hub",
        )
    if not registration_key or not hmac.compare_digest(registration_key, configured):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="first-time miner registration requires a valid registration_key",
        )


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

    First registration of a miner_id is gated by the operator-issued
    ``registration_key`` (#3059): the submitted api key becomes the miner's
    credential, and without a gate anyone could claim a predictable id
    (node2-gpu-01) first and own it forever — the #1083 re-registration
    check then 403s the real operator with no recovery path. Re-registering
    an existing miner_id requires the same api key — otherwise anyone could
    overwrite another miner's address, price and payout wallet (#1083).
    """
    repo = MinerRepository(session, redis)
    api_key_hash = hashlib.sha256(data.api_key.encode()).hexdigest()

    existing = await session.get(Miner, data.miner_id)
    if existing is not None:
        if existing.api_key_hash != api_key_hash:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="miner_id already registered")
    else:
        _require_first_registration_key(data.registration_key)

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
    # #3058: wallet_address is Optional and absent on re-registration payloads
    # that don't carry it — overwriting with None permanently stripped
    # production miners' payout wallet ("no_wallet_address" forever). None
    # now means "not provided, keep the stored value"; a new wallet is only
    # written when the caller actually sends one.
    if data.wallet_address is not None:
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


@router.delete("/{miner_id}")
async def deregister_miner(
    miner_id: str,
    session: Annotated[AsyncSession, Depends(db_session_dep)],
    redis: Annotated[Redis, Depends(redis_dep)],
    _: Annotated[dict[str, Any], Depends(_operator_auth)],
) -> dict[str, Any]:
    """Operator recovery path for a squatted or stale miner_id (#3059).

    Deletes the miner row so the legitimate operator can re-register the id
    as a first-time registration (which requires ``registration_key``).
    Child rows cascade (miner_status, service_configs, feedback, SLA
    metrics/violations); RewardPayout and MatchResult carry no FK and are
    retained as history. Gated by the pool-hub operator key
    (``X-PoolHub-Key`` = POOLHUB_COORDINATOR_SHARED_SECRET), the same
    credential class as ``/v1/parameters/apply``.
    """
    miner = await session.get(Miner, miner_id)
    if miner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="miner not found")
    region = miner.region
    await session.delete(miner)
    await session.commit()
    # Drop the Redis ranking/hash copies immediately instead of waiting out
    # the session TTL — a deleted miner must not stay matchable.
    await redis.delete(RedisKeys.miner_hash(miner_id))
    await redis.zrem(RedisKeys.miner_rankings(region), miner_id)
    if region:
        await redis.zrem(RedisKeys.miner_rankings(), miner_id)
    return {"success": True, "miner_id": miner_id, "deleted": True}


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
