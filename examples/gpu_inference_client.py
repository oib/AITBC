#!/usr/bin/env python3
"""
AITBC GPU Inference Client Example

Submits an inference job to the coordinator, polls for completion, and prints
the result. The example generates a short-lived JWT from JWT_SECRET so it can
be run without a pre-existing user session.

Usage:
    export JWT_SECRET="test-secret-32-characters-for-tests"
    python examples/gpu_inference_client.py --prompt "What is PoA consensus?"

Production note: use a login/session token instead of generating a JWT locally.
"""

import argparse
import json
import logging
import os
import time
from typing import Any, cast

import httpx

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("gpu_client")


def _create_jwt(user_id: str, role: str, jwt_secret: str) -> str:
    """Create a minimal JWT with the configured secret.

    In production you should obtain a session token from /v1/login or /v1/register.
    """
    import jwt
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    return jwt.encode(payload, jwt_secret, algorithm="HS256")


def submit_job(
    client: httpx.Client,
    coordinator: str,
    token: str,
    prompt: str,
    model: str,
    min_vram_gb: int,
) -> dict[str, Any]:
    """Submit an inference job to the coordinator."""
    payload = {
        "payload": {"type": "inference", "model": model, "prompt": prompt},
        "constraints": {
            "gpu": "NVIDIA",
            "min_vram_gb": min_vram_gb,
            "models": [model],
        },
        "ttl_seconds": 900,
    }
    response = client.post(
        f"{coordinator}/v1/jobs",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
    )
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


def get_job(client: httpx.Client, coordinator: str, token: str, job_id: str) -> dict[str, Any]:
    """Fetch the current job state."""
    response = client.get(
        f"{coordinator}/v1/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


def get_result(client: httpx.Client, coordinator: str, token: str, job_id: str) -> dict[str, Any]:
    """Fetch the job result."""
    response = client.get(
        f"{coordinator}/v1/jobs/{job_id}/result",
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


def wait_for_completion(
    client: httpx.Client,
    coordinator: str,
    token: str,
    job_id: str,
    timeout: int,
    poll_interval: int,
) -> dict[str, Any]:
    """Poll until the job reaches a terminal state."""
    terminal = {"COMPLETED", "FAILED", "CANCELED", "EXPIRED"}
    start = time.time()
    while time.time() - start < timeout:
        job = get_job(client, coordinator, token, job_id)
        state = job.get("state", "UNKNOWN")
        logger.info("Job %s state: %s", job_id, state)
        if state in terminal:
            return job
        time.sleep(poll_interval)
    raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")


def main() -> None:
    parser = argparse.ArgumentParser(description="AITBC GPU inference client example")
    parser.add_argument("--coordinator", default="http://localhost:8203", help="Coordinator base URL")
    parser.add_argument("--jwt-secret", default=os.getenv("JWT_SECRET", ""), help="JWT signing secret")
    parser.add_argument("--user-id", default="demo-client", help="Client user ID")
    parser.add_argument("--model", default="llama2", help="Requested model")
    parser.add_argument("--prompt", default="Explain zero-knowledge proofs in one paragraph.", help="Inference prompt")
    parser.add_argument("--min-vram-gb", type=int, default=8, help="Minimum GPU VRAM")
    parser.add_argument("--timeout", type=int, default=120, help="Max seconds to wait for result")
    parser.add_argument("--poll-interval", type=int, default=2, help="Seconds between status polls")
    args = parser.parse_args()

    if not args.jwt_secret:
        raise SystemExit("--jwt-secret or JWT_SECRET env var is required")

    token = _create_jwt(args.user_id, "client", args.jwt_secret)
    client = httpx.Client(timeout=15)
    try:
        logger.info("Submitting inference job...")
        job = submit_job(client, args.coordinator, token, args.prompt, args.model, args.min_vram_gb)
        job_id = job["job_id"]
        logger.info("Job created: %s", job_id)

        final_job = wait_for_completion(client, args.coordinator, token, job_id, args.timeout, args.poll_interval)

        if final_job.get("state") == "COMPLETED":
            result = get_result(client, args.coordinator, token, job_id)
            logger.info("Result:\n%s", json.dumps(result.get("result", {}), indent=2))
        else:
            logger.error("Job did not complete successfully: %s", final_job)
    finally:
        client.close()


if __name__ == "__main__":
    main()
