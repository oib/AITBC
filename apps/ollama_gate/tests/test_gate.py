"""Tests for the ollama shop gate (OLLAMA-PROXY-GATE-1, #841)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

# Load under a unique module name — sibling root-layout apps ship their own
# main.py and a bare ``import main`` collides in sys.modules across suites
# (whoever imports first wins; the loser's tests get the wrong FastAPI app).
# Same convention as apps/ffmpeg/tests/test_smoke.py.
_spec = importlib.util.spec_from_file_location("aitbc_ollama_gate_main", Path(__file__).resolve().parents[1] / "main.py")
gate = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["aitbc_ollama_gate_main"] = gate
_spec.loader.exec_module(gate)


@pytest.fixture()
def client():
    with TestClient(gate.app, raise_server_exceptions=False) as c:
        yield c


def _backend_response(status: int = 200, body: bytes = b'{"response":"ok"}') -> httpx.Response:
    return httpx.Response(status, content=body, headers={"content-type": "application/json"})


def test_gated_route_rejects_anonymous(client):
    assert client.post("/api/generate", json={}).status_code in (401, 403)
    assert client.post("/api/chat", json={}).status_code in (401, 403)
    assert client.post("/api/embed", json={}).status_code in (401, 403)


def test_wrong_job_token_is_403(client):
    with patch("aitbc.shop_gate._verify", return_value={"job_id": "job-A"}):
        resp = client.post(
            "/api/generate",
            json={},
            headers={"X-Access-Key": "access-key-1", "X-Access-Secret": "s", "X-Job-Id": "job-B"},
        )
    assert resp.status_code == 403


def test_valid_token_reaches_backend(client):
    gate.app.dependency_overrides[gate.require_job_access] = lambda: {"job_id": "job-A"}
    try:
        mock_send = AsyncMock(return_value=_backend_response())
        with patch.object(gate._client, "send", mock_send):
            resp = client.post(
                "/api/generate",
                json={"model": "m", "prompt": "p"},
                headers={"X-Access-Key": "k", "X-Access-Secret": "s", "X-Job-Id": "job-A"},
            )
        assert resp.status_code == 200
        assert resp.json() == {"response": "ok"}
        assert mock_send.call_args.args[0].url.path == "/api/generate"
    finally:
        gate.app.dependency_overrides.pop(gate.require_job_access, None)


def test_metadata_routes_require_job_access(client):
    """OLLAMA-GATE-EDGE-TRUST-1 (#1937): /api/tags + /api/version are no longer
    public — the edge IP allowlist cannot tell public buyers from attackers,
    so model metadata needs the same per-job token as inference."""
    for path in ("/api/tags", "/api/version"):
        assert client.get(path).status_code == 401


def test_metadata_routes_ignore_spoofed_forwarding_headers(client):
    """A client-asserted edge/trusted IP in XFF or X-Real-IP must not buy
    trust: the gate authorizes on the job token only, never on client IP."""
    spoofed = {
        "X-Forwarded-For": "10.1.223.1, 192.168.0.1",
        "X-Real-IP": "95.216.198.140",
        "X-Access-Key": "access-key-1",
        "X-Access-Secret": "s",
        "X-Job-Id": "job-A",
    }
    with patch("aitbc.shop_gate._verify", return_value=None):
        for path in ("/api/tags", "/api/version"):
            assert client.get(path, headers=spoofed).status_code == 401


def test_metadata_routes_pass_with_valid_token(client):
    gate.app.dependency_overrides[gate.require_job_access] = lambda: {"job_id": "job-A"}
    try:
        mock_send = AsyncMock(return_value=_backend_response(body=b'{"models":[]}'))
        with patch.object(gate._client, "send", mock_send):
            assert client.get("/api/tags").status_code == 200
            assert client.get("/api/version").status_code == 200
        assert mock_send.call_count == 2
    finally:
        gate.app.dependency_overrides.pop(gate.require_job_access, None)


def test_model_management_routes_are_not_proxied(client):
    # A paid token must not buy model management: these paths don't exist here.
    for path in ("/api/pull", "/api/create", "/api/delete", "/api/copy", "/api/push", "/api/blobs/sha256:x"):
        assert client.post(path, json={}).status_code in (401, 404, 405)


# ── APIGW-OLLAMA-DEPTH2-1 (#1613): paid-body policy + concurrency bounds ────


def _authed(client, job=None):
    """Install a job-access override; returns a cleanup callable."""
    gate.app.dependency_overrides[gate.require_job_access] = lambda: job or {"job_id": "job-A"}
    return lambda: gate.app.dependency_overrides.pop(gate.require_job_access, None)


def _headers():
    return {"X-Access-Key": "k", "X-Access-Secret": "s", "X-Job-Id": "job-A"}


def test_non_json_body_rejected_before_upstream(client):
    cleanup = _authed(client)
    try:
        with patch.object(gate._client, "send", AsyncMock()) as mock_send:
            resp = client.post("/api/generate", content=b"not json{", headers=_headers())
        assert resp.status_code == 400
        mock_send.assert_not_called()
    finally:
        cleanup()


def test_missing_model_rejected(client):
    cleanup = _authed(client)
    try:
        with patch.object(gate._client, "send", AsyncMock()) as mock_send:
            resp = client.post("/api/generate", json={"prompt": "hi"}, headers=_headers())
        assert resp.status_code == 400
        mock_send.assert_not_called()
    finally:
        cleanup()


def test_model_must_match_paid_job(client):
    cleanup = _authed(client, {"job_id": "job-A", "model": "llama3.2:3b"})
    try:
        with patch.object(gate._client, "send", AsyncMock()) as mock_send:
            resp = client.post(
                "/api/generate",
                json={"model": "llama3.2:70b", "prompt": "hi"},
                headers=_headers(),
            )
        assert resp.status_code == 403
        mock_send.assert_not_called()

        with patch.object(gate._client, "send", AsyncMock(return_value=_backend_response())) as mock_send:
            resp = client.post(
                "/api/generate",
                json={"model": "llama3.2:3b", "prompt": "hi"},
                headers=_headers(),
            )
        assert resp.status_code == 200
        mock_send.assert_called_once()
    finally:
        cleanup()


def test_options_resource_bounds_enforced(client):
    cleanup = _authed(client)
    try:
        for options in (
            {"num_ctx": 10**9},
            {"num_predict": -5},
            {"num_gpu": "all"},
            {"num_ctx": "lots"},
        ):
            with patch.object(gate._client, "send", AsyncMock()) as mock_send:
                resp = client.post(
                    "/api/generate",
                    json={"model": "m", "prompt": "hi", "options": options},
                    headers=_headers(),
                )
            assert resp.status_code == 400, options
            mock_send.assert_not_called()

        with patch.object(gate._client, "send", AsyncMock(return_value=_backend_response())) as mock_send:
            resp = client.post(
                "/api/generate",
                json={"model": "m", "prompt": "hi", "options": {"num_ctx": 8192, "temperature": 0.5}},
                headers=_headers(),
            )
        assert resp.status_code == 200
        mock_send.assert_called_once()
    finally:
        cleanup()


def test_keep_alive_is_bounded(client):
    cleanup = _authed(client)
    try:
        for keep_alive in (-1, "100h", "soon"):
            with patch.object(gate._client, "send", AsyncMock()) as mock_send:
                resp = client.post(
                    "/api/generate",
                    json={"model": "m", "prompt": "hi", "keep_alive": keep_alive},
                    headers=_headers(),
                )
            assert resp.status_code == 400, keep_alive
            mock_send.assert_not_called()

        with patch.object(gate._client, "send", AsyncMock(return_value=_backend_response())):
            resp = client.post(
                "/api/generate",
                json={"model": "m", "prompt": "hi", "keep_alive": "30m"},
                headers=_headers(),
            )
        assert resp.status_code == 200
    finally:
        cleanup()


def test_second_call_for_same_job_is_429(client):
    cleanup = _authed(client)
    try:
        gate._inflight_jobs.add("job-A")
        try:
            with patch.object(gate._client, "send", AsyncMock()) as mock_send:
                resp = client.post(
                    "/api/generate",
                    json={"model": "m", "prompt": "hi"},
                    headers=_headers(),
                )
            assert resp.status_code == 429
            mock_send.assert_not_called()
        finally:
            gate._inflight_jobs.discard("job-A")
    finally:
        cleanup()


def test_global_concurrency_bound_yields_429(client, monkeypatch):
    cleanup = _authed(client)
    monkeypatch.setattr(gate, "_QUEUE_TIMEOUT", 0.01)
    try:
        # Exhaust every permit; the next gated call must time out into a 429.
        for _ in range(gate._MAX_CONCURRENT):
            assert gate._inflight.acquire(blocking=False)
        try:
            with patch.object(gate._client, "send", AsyncMock()) as mock_send:
                resp = client.post(
                    "/api/generate",
                    json={"model": "m", "prompt": "hi"},
                    headers={"X-Access-Key": "k", "X-Access-Secret": "s", "X-Job-Id": "job-B"},
                )
            assert resp.status_code == 429
            mock_send.assert_not_called()
        finally:
            for _ in range(gate._MAX_CONCURRENT):
                gate._inflight.release()
    finally:
        cleanup()


def test_model_allowlist_env(monkeypatch):
    # The allowlist is read at import; exercise the predicate directly.
    monkeypatch.setattr(gate, "_ALLOWED_MODELS", frozenset({"llama3.2:3b"}))
    assert gate._validate_paid_body({"model": "llama3.2:3b"}, {"job_id": "j"}) is None
    assert gate._validate_paid_body({"model": "other"}, {"job_id": "j"}) == (403, "model is not available on this shop")


# --- OLLAMA-GATE-BODY-1 (#1480): bounded request body ---


def _override_access():
    gate.app.dependency_overrides[gate.require_job_access] = lambda: {"job_id": "job-A"}


def test_oversized_content_length_is_413(client, monkeypatch):
    monkeypatch.setattr(gate, "MAX_BODY_BYTES", 16)
    _override_access()
    try:
        resp = client.post("/api/generate", content=b"x" * 64)
        assert resp.status_code == 413
    finally:
        gate.app.dependency_overrides.pop(gate.require_job_access, None)


def test_streamed_body_over_cap_is_413_without_content_length(monkeypatch):
    """The stream cap catches a body whose Content-Length lied or is absent."""
    from starlette.requests import Request

    monkeypatch.setattr(gate, "MAX_BODY_BYTES", 10)

    async def receive():
        return {"type": "http.request", "body": b"x" * 32, "more_body": False}

    scope = {"type": "http", "method": "POST", "path": "/api/generate", "headers": [], "query_string": b""}
    req = Request(scope, receive)
    import asyncio

    with pytest.raises(Exception) as ei:
        asyncio.run(gate._read_bounded_body(req))
    assert getattr(ei.value, "status_code", None) == 413


def test_body_under_cap_passes(monkeypatch):
    from starlette.requests import Request

    monkeypatch.setattr(gate, "MAX_BODY_BYTES", 1024)

    async def receive():
        return {"type": "http.request", "body": b'{"model":"m"}', "more_body": False}

    scope = {"type": "http", "method": "POST", "path": "/api/generate", "headers": [], "query_string": b""}
    req = Request(scope, receive)
    import asyncio

    assert asyncio.run(gate._read_bounded_body(req)) == b'{"model":"m"}'


def test_bounds_held_until_stream_end():
    """#1613: the semaphore slot + per-job marker release when the response
    stream finishes, not when the handler returns the StreamingResponse."""
    import asyncio

    from starlette.requests import Request
    from starlette.responses import StreamingResponse

    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": b'{"model":"m","prompt":"p"}', "more_body": False}
        return {"type": "http.disconnect"}

    scope = {"type": "http", "method": "POST", "path": "/api/generate", "headers": [], "query_string": b""}
    req = Request(scope, receive)

    class _Upstream:
        status_code = 200
        headers = {"content-type": "application/json"}

        async def aiter_bytes(self):
            yield b'{"a":'
            yield b"1}"

        async def aclose(self):
            pass

    async def fake_send(request, stream=False):
        return _Upstream()

    async def _run():
        gate._inflight_jobs.discard("job-S")
        with patch.object(gate._client, "send", AsyncMock(side_effect=fake_send)):
            resp = await gate._dispatch_gated(req, "/api/generate", {"job_id": "job-S"})
            assert isinstance(resp, StreamingResponse)
            # Handler returned, stream not yet consumed: bounds must still hold.
            assert "job-S" in gate._inflight_jobs
            resp2 = await gate._dispatch_gated(req, "/api/generate", {"job_id": "job-S"})
            assert resp2.status_code == 429
            body = b"".join([c async for c in resp.body_iterator])
            assert body == b'{"a":1}'
            assert "job-S" not in gate._inflight_jobs

    try:
        asyncio.run(_run())
    finally:
        gate._inflight_jobs.discard("job-S")


def test_gated_get_response_is_bounded(client, monkeypatch):
    """#1613: /api/tags + /api/version stream under a byte cap, not resp.content."""
    monkeypatch.setattr(gate, "_PROXY_GET_MAX_BYTES", 4)
    cleanup = _authed(client)

    class _Big:
        status_code = 200
        headers = {"content-type": "application/json"}

        async def aiter_bytes(self):
            yield b"12345"

        async def aclose(self):
            pass

    with patch.object(gate._client, "send", AsyncMock(return_value=_Big())):
        assert client.get("/api/tags").status_code == 502
    cleanup()
