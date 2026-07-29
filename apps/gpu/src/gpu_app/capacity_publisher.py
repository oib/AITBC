"""Publish updated GPU/storage capacity to the coordinator marketplace."""

from __future__ import annotations

import os
import urllib.error
import urllib.request
import json
from decimal import Decimal
from typing import Any


DEFAULT_COORDINATOR_URL = "http://localhost:8203"


def publish_capacity(
    provider_id: str,
    capacity: int,
    *,
    coordinator_url: str | None = None,
    token: str = "AITBC",
    price_per_hour: Decimal | str | float | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Publish or update a provider's compute capacity.

    ponytail: This is a skeleton publisher. It posts to the coordinator API
    marketplace capacity endpoint; production deployments should use the
    shared HTTP client with retries and authentication.
    """
    base = (coordinator_url or os.getenv("COORDINATOR_URL", DEFAULT_COORDINATOR_URL)).rstrip("/")
    url = f"{base}/v1/marketplace/providers/{provider_id}/capacity"
    payload: dict[str, Any] = {
        "provider_id": provider_id,
        "capacity": capacity,
        "token": token,
    }
    if price_per_hour is not None:
        payload["price_per_hour"] = str(price_per_hour)

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-Api-Key"] = api_key

    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")  # type: ignore[arg-type]
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310 - coordinator_url comes from a caller-supplied param or trusted COORDINATOR_URL env var, not runtime user input
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return {"error": exc.read().decode(), "status": exc.code}
    except urllib.error.URLError as exc:
        return {"error": str(exc.reason), "status": 503}
