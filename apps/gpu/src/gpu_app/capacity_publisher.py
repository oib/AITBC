"""Publish updated GPU/storage capacity to the coordinator market."""

from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request
import json
from decimal import Decimal
from typing import Any, cast


DEFAULT_COORDINATOR_URL = "http://localhost:8203"

# #2914: the coordinator response is parsed as JSON — bound the read so a
# hostile or broken endpoint cannot stream an unbounded body into memory.
_MAX_RESPONSE_BYTES = 1_048_576


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse redirects (#2914).

    urllib's default opener re-sends the request — headers included — to a
    30x target. A redirected capacity POST would carry X-Api-Key to an
    arbitrary host, so redirects surface as ordinary HTTP errors instead.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirectHandler())


def _open(req: urllib.request.Request, timeout: float):
    return _OPENER.open(req, timeout=timeout)


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

    This is a skeleton publisher. It posts to the coordinator API market
    capacity endpoint; production deployments should use the shared HTTP client
    with retries and authentication.
    """
    base = (coordinator_url or os.getenv("COORDINATOR_URL", DEFAULT_COORDINATOR_URL) or "").rstrip("/")
    # #2914: provider_id is interpolated into the URL path — encode it so it
    # cannot rewrite the path while X-Api-Key still attaches.
    url = f"{base}/v1/market/providers/{urllib.parse.quote(str(provider_id), safe='')}/capacity"
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
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        # coordinator_url comes from a caller-supplied param or trusted COORDINATOR_URL env var, not runtime user input
        with _open(req, timeout=10) as resp:
            raw = resp.read(_MAX_RESPONSE_BYTES + 1)
        if len(raw) > _MAX_RESPONSE_BYTES:
            return {"error": "coordinator response too large", "status": 502}
        return cast(dict[str, Any], json.loads(raw.decode()))
    except urllib.error.HTTPError as exc:
        return {"error": exc.read(_MAX_RESPONSE_BYTES + 1).decode(), "status": exc.code}
    except urllib.error.URLError as exc:
        return {"error": str(exc.reason), "status": 503}
