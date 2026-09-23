"""Redis-backed Ollama task queue and worker.

Tasks are pushed to a Redis list and consumed by an async worker that calls the
local Ollama server. Results are written back to Redis with a TTL so clients can
poll them.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import ollama
from redis.asyncio import Redis

from coordinator_api.config import settings

QUEUE_KEY = "aitbc:ollama:queue"
RESULT_KEY_PREFIX = "aitbc:ollama:result:"
RESULT_TTL_SECONDS = 3600


def _redis() -> Redis:
    """Return an async Redis client using the coordinator API Redis config."""
    return Redis.from_url(settings.redis.url, decode_responses=True)


def _new_task_id() -> str:
    return uuid.uuid4().hex


def _result_key(task_id: str) -> str:
    return f"{RESULT_KEY_PREFIX}{task_id}"


async def get_queue() -> OllamaQueue:
    """Return a queue connected to the configured Redis URL."""
    return OllamaQueue(_redis())


class OllamaQueue:
    """Persistent task queue for Ollama inference jobs."""

    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def enqueue(
        self,
        gpu_id: str,
        model: str,
        prompt: str,
        parameters: dict[str, Any] | None = None,
    ) -> str:
        """Add a task to the queue and return its id."""
        task_id = _new_task_id()
        task = {
            "task_id": task_id,
            "gpu_id": gpu_id,
            "model": model,
            "prompt": prompt,
            "parameters": parameters or {},
            "queued_at": datetime.now(UTC).isoformat(),
        }
        await self.redis.lpush(QUEUE_KEY, json.dumps(task))
        return task_id

    async def dequeue(self, timeout: float = 5.0) -> dict[str, Any] | None:
        """Wait for and return the next task from the queue."""
        result = await self.redis.brpop(QUEUE_KEY, timeout=timeout)
        if result is None:
            return None
        return cast(dict[str, Any], json.loads(result[1]))

    async def set_result(self, task_id: str, result: dict[str, Any]) -> None:
        """Store a result for the given task id, expiring after RESULT_TTL_SECONDS."""
        await self.redis.setex(
            _result_key(task_id),
            RESULT_TTL_SECONDS,
            json.dumps(result),
        )

    async def get_result(self, task_id: str) -> dict[str, Any] | None:
        """Fetch a result by task id if it exists."""
        raw = await self.redis.get(_result_key(task_id))
        if raw is None:
            return None
        return cast(dict[str, Any], json.loads(raw))


async def _generate(task: dict[str, Any]) -> dict[str, Any]:
    """Run an Ollama generation and return a serialisable result."""
    client = ollama.AsyncClient()
    try:
        response = await client.generate(
            model=task["model"],
            prompt=task["prompt"],
            options=task.get("parameters") or {},
        )
        return {
            "done": response.done,
            "response": response.response,
            "model": response.model,
            "total_duration_ns": response.total_duration,
            "load_duration_ns": response.load_duration,
            "prompt_eval_count": response.prompt_eval_count,
            "eval_count": response.eval_count,
        }
    except ollama.ResponseError as e:
        return {"error": f"Ollama error: {e.status_code} {e.error}"}
    except Exception as e:  # noqa: BLE001 - worker must keep running on bad tasks
        return {"error": f"worker error: {e}"}


async def run_worker() -> None:
    """Blocking worker loop: dequeue tasks and run Ollama inference."""
    redis = _redis()
    queue = OllamaQueue(redis)
    while True:
        task = await queue.dequeue(timeout=1.0)
        if task is None:
            continue
        result = await _generate(task)
        result["task_id"] = task["task_id"]
        result["gpu_id"] = task["gpu_id"]
        result["completed_at"] = datetime.now(UTC).isoformat()
        await queue.set_result(task["task_id"], result)


if __name__ == "__main__":
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        pass
