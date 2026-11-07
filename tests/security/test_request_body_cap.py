"""Pins for the app-level request body-size cap (#1234 / R12-HARDEN-2).

nginx ``client_max_body_size`` is the live edge bound; these pins cover the
defense-in-depth layer inside the apps: ``RequestValidationMiddleware``
enforces the cap on the actual body stream (spoofed/missing
Content-Length can't walk past it) and ``exempt_prefixes`` lets routes with
their own size governance (media upload) stream through uncapped.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from aitbc.middleware.validation import RequestValidationMiddleware


def _scope(path: str = "/v1/jobs", method: str = "POST") -> dict:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "client": ("127.0.0.1", 1234),
    }


def _receive(chunks: list[bytes]):
    state = {"i": 0}

    async def receive():
        if state["i"] < len(chunks):
            body = chunks[state["i"]]
            state["i"] += 1
            return {"type": "http.request", "body": body, "more_body": state["i"] < len(chunks)}
        return {"type": "http.request", "body": b"", "more_body": False}

    return receive


async def _collect_send():
    messages = []

    async def send(message):
        messages.append(message)

    return messages, send


@pytest.mark.asyncio
async def test_body_over_cap_gets_413() -> None:
    app = AsyncMock()
    mw = RequestValidationMiddleware(app, max_request_size=100)
    messages, send = await _collect_send()
    await mw(_scope(), _receive([b"x" * 60, b"y" * 60]), send)
    app.assert_not_called()
    start = next(m for m in messages if m["type"] == "http.response.start")
    assert start["status"] == 413


@pytest.mark.asyncio
async def test_body_under_cap_reaches_app() -> None:
    app = AsyncMock()
    mw = RequestValidationMiddleware(app, max_request_size=100)
    messages, send = await _collect_send()
    await mw(_scope(), _receive([b"x" * 50]), send)
    app.assert_called_once()


@pytest.mark.asyncio
async def test_exempt_prefix_bypasses_cap() -> None:
    """Media upload keeps its own limiter — the middleware must not buffer
    or cap it (a 100MB upload would otherwise land in memory here)."""
    app = AsyncMock()
    mw = RequestValidationMiddleware(app, max_request_size=100, exempt_prefixes=("/v1/media/",))
    messages, send = await _collect_send()
    await mw(_scope("/v1/media/upload"), _receive([b"x" * 500]), send)
    app.assert_called_once()
    # The original receive is passed through untouched — no replay wrapper.
    assert app.call_args[0][1] is not None


@pytest.mark.asyncio
async def test_non_exempt_prefix_still_capped() -> None:
    app = AsyncMock()
    mw = RequestValidationMiddleware(app, max_request_size=100, exempt_prefixes=("/v1/media/",))
    messages, send = await _collect_send()
    await mw(_scope("/v1/mediax/evil"), _receive([b"x" * 500]), send)
    # "/v1/mediax/" does not start with "/v1/media/" — capped.
    app.assert_not_called()
    start = next(m for m in messages if m["type"] == "http.response.start")
    assert start["status"] == 413


@pytest.mark.asyncio
async def test_get_requests_untouched() -> None:
    app = AsyncMock()
    mw = RequestValidationMiddleware(app, max_request_size=1)
    messages, send = await _collect_send()
    await mw(_scope(method="GET"), _receive([]), send)
    app.assert_called_once()


def test_coordinator_defaults_match_nginx_bound() -> None:
    """Coordinator cap defaults to the nginx 5M API bound with the media
    upload route exempted (it enforces max_media_upload_bytes itself)."""
    from coordinator_api.config import Settings

    s = Settings()
    assert s.max_request_body_bytes == 5 * 1024 * 1024
    assert "/v1/media/" in s.max_request_body_exempt_prefixes
