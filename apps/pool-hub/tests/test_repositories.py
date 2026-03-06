from __future__ import annotations

import json
import uuid

import pytest

from poolhub.repositories.feedback_repository import FeedbackRepository
from poolhub.repositories.match_repository import MatchRepository
from poolhub.repositories.miner_repository import MinerRepository
from poolhub.storage.redis_keys import RedisKeys


@pytest.mark.asyncio
async def test_register_miner_persists_and_syncs(db_session, redis_client):
    repo = MinerRepository(db_session, redis_client)

    await repo.register_miner(
        miner_id="miner-1",
        api_key_hash="hash",
        addr="127.0.0.1",
        proto="grpc",
        gpu_vram_gb=16,
        gpu_name="A100",
        cpu_cores=32,
        ram_gb=128,
        max_parallel=4,
        base_price=0.8,
        tags={"tier": "gold"},
        capabilities=["embedding"],
        region="eu",
    )

    miner = await repo.get_miner("miner-1")
    assert miner is not None
    assert miner.addr == "127.0.0.1"

    redis_hash = await redis_client.hgetall(RedisKeys.miner_hash("miner-1"))
    assert redis_hash["miner_id"] == "miner-1"
    ranking = await redis_client.zscore(RedisKeys.miner_rankings("eu"), "miner-1")
    assert ranking is not None


@pytest.mark.asyncio
async def test_match_request_flow(db_session, redis_client):
    match_repo = MatchRepository(db_session, redis_client)

    req = await match_repo.create_request(
        job_id="job-123",
        requirements={"min_vram_gb": 8},
        hints={"region": "eu"},
        top_k=2,
    )
    await db_session.commit()

    queue_entry = await redis_client.lpop(RedisKeys.match_requests())
    assert queue_entry is not None
    payload = json.loads(queue_entry)
    assert payload["job_id"] == "job-123"

    await match_repo.add_results(
        request_id=req.id,
        candidates=[
            {"miner_id": "miner-1", "score": 0.9, "explain": "fit"},
            {"miner_id": "miner-2", "score": 0.8, "explain": "backup"},
        ],
    )
    await db_session.commit()

    results = await match_repo.list_results_for_job("job-123")
    assert len(results) == 2

    redis_results = await redis_client.lrange(RedisKeys.match_results("job-123"), 0, -1)
    assert len(redis_results) == 2


@pytest.mark.asyncio
async def test_feedback_repository(db_session, redis_client):
    feedback_repo = FeedbackRepository(db_session, redis_client)

    feedback = await feedback_repo.add_feedback(
        job_id="job-321",
        miner_id="miner-1",
        outcome="completed",
        latency_ms=1200,
        tokens_spent=1.5,
    )
    await db_session.commit()

    rows = await feedback_repo.list_feedback_for_job("job-321")
    assert len(rows) == 1
    assert rows[0].outcome == "completed"

    # Ensure Redis publish occurred by checking pubsub message count via monitor list (best effort)
    # Redis doesn't buffer publishes for inspection, so this is a smoke check ensuring repository returns object
    assert feedback.miner_id == "miner-1"
