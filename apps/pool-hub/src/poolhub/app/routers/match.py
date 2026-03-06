from __future__ import annotations

import time
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import db_session_dep, redis_dep
from ..prometheus import (
    match_candidates_returned,
    match_failures_total,
    match_latency_seconds,
    match_requests_total,
)
from poolhub.repositories.match_repository import MatchRepository
from poolhub.repositories.miner_repository import MinerRepository
from ..schemas import MatchCandidate, MatchRequestPayload, MatchResponse

router = APIRouter(tags=["match"])


def _normalize_requirements(requirements: Dict[str, Any]) -> Dict[str, Any]:
    return requirements or {}


def _candidate_from_payload(payload: Dict[str, Any]) -> MatchCandidate:
    return MatchCandidate(**payload)


@router.post("/match", response_model=MatchResponse, summary="Find top miners for a job")
async def match_endpoint(
    payload: MatchRequestPayload,
    session: AsyncSession = Depends(db_session_dep),
    redis: Redis = Depends(redis_dep),
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
            request_id=request.id,
            candidates=candidates,
        )

        match_candidates_returned.inc(len(candidates))
        duration = time.perf_counter() - start
        match_latency_seconds.observe(duration)

        return MatchResponse(
            job_id=payload.job_id,
            candidates=[_candidate_from_payload(candidate) for candidate in candidates],
        )
    except Exception as exc:  # pragma: no cover - safeguards unexpected failures
        match_failures_total.inc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="match_failed") from exc


def _select_candidates(
    requirements: Dict[str, Any],
    hints: Dict[str, Any],
    active_miners: List[tuple],
    top_k: int,
) -> List[Dict[str, Any]]:
    min_vram = float(requirements.get("min_vram_gb", 0))
    min_ram = float(requirements.get("min_ram_gb", 0))
    capabilities_required = set(requirements.get("capabilities_any", []))
    region_hint = hints.get("region")

    ranked: List[Dict[str, Any]] = []
    for miner, status, score in active_miners:
        if miner.gpu_vram_gb and miner.gpu_vram_gb < min_vram:
            continue
        if miner.ram_gb and miner.ram_gb < min_ram:
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
            "explain": _compose_explain(score, miner, status),
            "eta_ms": status.avg_latency_ms if status else None,
            "price": miner.base_price,
        }
        ranked.append(candidate)

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:top_k]


def _compose_explain(score: float, miner, status) -> str:
    load = status.queue_len if status else 0
    latency = status.avg_latency_ms if status else "n/a"
    return f"score={score:.3f} load={load} latency={latency}"
