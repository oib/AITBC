from __future__ import annotations

import math
import time
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from poolhub.repositories.match_repository import MatchRepository
from poolhub.repositories.miner_repository import MinerRepository

from ..deps import db_session_dep, redis_dep
from ..prometheus import (
    match_candidates_returned,
    match_failures_total,
    match_latency_seconds,
    match_requests_total,
)
from ..schemas import MatchCandidate, MatchRequestPayload, MatchResponse

router = APIRouter(tags=["match"])


def _normalize_requirements(requirements: dict[str, Any]) -> dict[str, Any]:
    return requirements or {}


def _candidate_from_payload(payload: dict[str, Any]) -> MatchCandidate:
    return MatchCandidate(**payload)


def _minimum_hardware(requirements: dict[str, Any], key: str) -> float:
    """Validate a caller-supplied hardware minimum (#1494).

    ``requirements`` is arbitrary JSON; a malformed value must be a 400, not a
    float()/set() crash surfaced as 500 — and NaN must never reach the
    comparison, where every ``vram < NaN`` is False and the filter is bypassed.
    """
    raw = requirements.get(key, 0)
    if isinstance(raw, bool):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"requirements.{key} must be a number, got bool")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"requirements.{key} must be a number") from exc
    if not math.isfinite(value) or value < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"requirements.{key} must be a finite number >= 0",
        )
    return value


@router.post("/match", response_model=MatchResponse, summary="Find top miners for a job")
async def match_endpoint(
    payload: MatchRequestPayload,
    session: Annotated[AsyncSession, Depends(db_session_dep)],
    redis: Annotated[Redis, Depends(redis_dep)],
) -> MatchResponse:
    start = time.perf_counter()
    match_requests_total.inc()

    miner_repo = MinerRepository(session, redis)
    match_repo = MatchRepository(session, redis)

    requirements = _normalize_requirements(payload.requirements)
    top_k = payload.top_k

    try:
        request = await match_repo.create_request(
            job_id=payload.job_id,
            requirements=requirements,
            hints=payload.hints,
            top_k=top_k,
        )

        active_miners = await miner_repo.list_active_miners()
        candidates = _select_candidates(requirements, payload.hints, active_miners, top_k)

        await match_repo.add_results(
            request_id=uuid.UUID(str(request.id)),
            candidates=candidates,
        )

        match_candidates_returned.inc(len(candidates))
        duration = time.perf_counter() - start
        match_latency_seconds.observe(duration)

        return MatchResponse(
            job_id=payload.job_id,
            candidates=[_candidate_from_payload(candidate) for candidate in candidates],
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - safeguards unexpected failures
        match_failures_total.inc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="match_failed") from exc


def _select_candidates(
    requirements: dict[str, Any],
    hints: dict[str, Any],
    active_miners: list[tuple[Any, ...]],
    top_k: int,
) -> list[dict[str, Any]]:
    min_vram = _minimum_hardware(requirements, "min_vram_gb")
    min_ram = _minimum_hardware(requirements, "min_ram_gb")
    capabilities_raw = requirements.get("capabilities_any", [])
    if not isinstance(capabilities_raw, (list, tuple)) or not all(isinstance(c, str) for c in capabilities_raw):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="requirements.capabilities_any must be a list of strings",
        )
    capabilities_required = set(capabilities_raw)
    region_hint = hints.get("region")

    ranked: list[dict[str, Any]] = []
    for miner, miner_status, score in active_miners:
        # `or 0` is deliberate (#1398): gpu_vram_gb/ram_gb are Float columns
        # whose registration default is 0.0, and a bare truthiness check let a
        # GPU-less miner satisfy any min_vram_gb requirement. None and 0.0
        # both mean "no usable hardware" and must fail a positive minimum;
        # they still pass when no minimum is requested (min == 0).
        if float(miner.gpu_vram_gb or 0) < min_vram:
            continue
        if float(miner.ram_gb or 0) < min_ram:
            continue
        if capabilities_required and not capabilities_required.issubset(set(miner.capabilities or [])):
            continue
        if region_hint and miner.region and miner.region != region_hint:
            continue

        candidate = {
            "miner_id": miner.miner_id,
            "addr": miner.addr,
            "proto": miner.proto,
            "score": float(score),
            "explain": _compose_explain(score, miner, miner_status),
            "eta_ms": miner_status.avg_latency_ms if miner_status else None,
            "price": miner.base_price,
        }
        ranked.append(candidate)

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:top_k]


def _compose_explain(score: float, miner: Any, miner_status: Any) -> str:
    """Human-readable explanation of a candidate's score.

    Reads `miner_status`, the parameter. This previously read `status`, which resolves to
    the module-level `fastapi.status` import -- always truthy, so it took the non-None
    branch and raised AttributeError ('module has no attribute queue_len') on every
    /v1/match call that reached candidate building. The surrounding broad except turned
    that into a generic 500, which is why it read as a server fault rather than a typo.
    """
    load = miner_status.queue_len if miner_status else 0
    latency = miner_status.avg_latency_ms if miner_status else "n/a"
    return f"score={score:.3f} load={load} latency={latency}"
