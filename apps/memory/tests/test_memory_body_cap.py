"""Request-envelope cap tests for the memory service (#1652).

The per-blob caps bound ``data`` but not the JSON body around it — the route's
encoded-length check runs only after FastAPI has parsed the whole request.
``RequestValidationMiddleware`` refuses oversized bodies before that parse.
"""

from __future__ import annotations

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aitbc.middleware import RequestValidationMiddleware
from memory_app.api import router
from memory_app.config import settings
from memory_app.main import app as service_app


def _app_with_cap(cap: int) -> FastAPI:
    """A fresh app carrying only the size middleware + the real router."""
    test_app = FastAPI()
    test_app.add_middleware(RequestValidationMiddleware, max_request_size=cap)
    test_app.include_router(router, prefix=settings.api_prefix)
    return test_app


@pytest.mark.unit
def test_store_rejects_oversized_request_body() -> None:
    """A body over the middleware cap is a 413 before any blob logic runs."""
    client = TestClient(_app_with_cap(4096))
    payload = {
        "owner": "cap-user",
        "data": base64.b64encode(b"x" * 8000).decode("ascii"),
        "tags": {"pad": "y" * 8000},
    }
    resp = client.post("/v1/store", json=payload)
    assert resp.status_code == 413


@pytest.mark.unit
def test_store_accepts_body_within_cap() -> None:
    """A normal store request passes the middleware and reaches the route."""
    client = TestClient(_app_with_cap(1 << 20))
    resp = client.post(
        "/v1/store",
        json={
            "owner": "cap-user",
            "data": base64.b64encode(b"small blob").decode("ascii"),
            "tags": {},
        },
    )
    assert resp.status_code == 201


@pytest.mark.unit
def test_service_app_carries_body_cap() -> None:
    """The deployed app has the middleware sized to the blob cap + envelope slack."""
    from memory_app import main as main_module

    expected = (settings.memory_max_blob_bytes * 4) // 3 + 1024 * 1024
    assert main_module._MAX_REQUEST_BYTES == expected
    caps = [m.kwargs.get("max_request_size") for m in service_app.user_middleware if m.cls is RequestValidationMiddleware]
    assert caps == [expected]
