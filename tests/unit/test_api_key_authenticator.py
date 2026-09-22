"""Unit tests for aitbc.auth.dependencies.APIKeyAuthenticator.

Regression coverage for the websocket binding bug: a ``Request``-annotated
``__call__`` is never bound on websocket routes (FastAPI only fills it for
actual ``Request`` connections), so the dependency raised ``TypeError`` and
the handshake died with HTTP 500 — authenticated or not. The authenticator
now accepts ``HTTPConnection`` and rejects websocket handshakes with
``WebSocketException`` (1008 for auth failures, 1011 when unconfigured).

No live services required — routes run through ``fastapi.testclient``.
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from aitbc.auth.dependencies import APIKeyAuthenticator

KEY = "test-trading-key"
HEADER = "X-Trading-Api-Key"


def _make_app(auth: APIKeyAuthenticator) -> FastAPI:
    """Minimal app mirroring trading's router-level gating on both scopes."""
    app = FastAPI()

    @app.get("/ping", dependencies=[Depends(auth)])
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    @app.websocket("/ws", dependencies=[Depends(auth)])
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_json({"ok": True})

    return app


@pytest.fixture
def auth() -> APIKeyAuthenticator:
    return APIKeyAuthenticator(expected_key=KEY, auth_enabled=True, header_name=HEADER)


@pytest.fixture
def client(auth: APIKeyAuthenticator) -> TestClient:
    return TestClient(_make_app(auth))


# ---------------------------------------------------------------------------
# HTTP routes — behavior must be unchanged
# ---------------------------------------------------------------------------


def test_http_valid_key(client: TestClient) -> None:
    resp = client.get("/ping", headers={HEADER: KEY})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_http_missing_key(client: TestClient) -> None:
    resp = client.get("/ping")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Missing API key"


def test_http_wrong_key(client: TestClient) -> None:
    resp = client.get("/ping", headers={HEADER: "wrong"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid API key"


def test_http_unconfigured() -> None:
    auth = APIKeyAuthenticator(expected_key=None, auth_enabled=True, header_name=HEADER)
    resp = TestClient(_make_app(auth)).get("/ping", headers={HEADER: KEY})
    assert resp.status_code == 501
    assert resp.json()["detail"] == "API key not configured"


def test_http_auth_disabled() -> None:
    auth = APIKeyAuthenticator(expected_key=None, auth_enabled=False, header_name=HEADER)
    resp = TestClient(_make_app(auth)).get("/ping")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# WebSocket routes — the regression
# ---------------------------------------------------------------------------


def test_ws_valid_key_connects(client: TestClient) -> None:
    """With the correct key the dependency passes and the handler runs."""
    with client.websocket_connect("/ws", headers={HEADER: KEY}) as ws:
        assert ws.receive_json() == {"ok": True}


def test_ws_missing_key_denied(client: TestClient) -> None:
    # TestClient observes the ASGI-layer close code (1008). A real client sees
    # HTTP 403: uvicorn translates a pre-accept close into a handshake denial,
    # indistinguishable from an unmatched ws path.
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws"):
            pass
    assert exc.value.code == 1008


def test_ws_wrong_key_denied(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws", headers={HEADER: "wrong"}):
            pass
    assert exc.value.code == 1008


def test_ws_unconfigured_denied() -> None:
    auth = APIKeyAuthenticator(expected_key=None, auth_enabled=True, header_name=HEADER)
    with pytest.raises(WebSocketDisconnect) as exc:
        with TestClient(_make_app(auth)).websocket_connect("/ws", headers={HEADER: KEY}):
            pass
    assert exc.value.code == 1011


def test_ws_auth_disabled_connects() -> None:
    auth = APIKeyAuthenticator(expected_key=None, auth_enabled=False, header_name=HEADER)
    with TestClient(_make_app(auth)).websocket_connect("/ws") as ws:
        assert ws.receive_json() == {"ok": True}


# ---------------------------------------------------------------------------
# Direct invocation — the wallet deps.py path calls the authenticator directly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_direct_call_with_request(auth: APIKeyAuthenticator) -> None:
    from starlette.requests import Request

    scope = {
        "type": "http",
        "headers": [(HEADER.lower().encode(), KEY.encode())],
    }
    result = await auth(Request(scope))
    assert result["auth_type"] == "api_key"
    assert result["role"] == "admin"
