"""#1676 sibling: agent-coordinator installs the JSON-safe 422 handler.

Literal ``NaN``/``Infinity`` JSON floats parse into Python floats that
pydantic rejects for typed fields; without
``register_request_validation_error_handler`` the default handler echoes
``input=nan`` into a body Starlette cannot serialize — a 500 on a money-path
endpoint (``POST /v1/tasks/submit`` payment amounts). These pins drive the
production ``register_exception_handlers`` wiring, not just the helper.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from agent_app import state  # noqa: E402
from agent_app.exceptions import register_exception_handlers  # noqa: E402
from agent_app.routers import tasks as tasks_router  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    fake_state = MagicMock()
    fake_state.task_distributor = MagicMock()
    fake_state.task_distributor.submit_task = AsyncMock(return_value=True)
    fake_state.payment_escrow = None
    fake_state.escrow_rpc = None
    # tasks.py reads the shared ``agent_app.state`` module object — patch its
    # attributes, not the module reference.
    monkeypatch.setattr(state, "task_distributor", fake_state.task_distributor)
    monkeypatch.setattr(state, "payment_escrow", None)
    monkeypatch.setattr(state, "escrow_rpc", None)

    app = FastAPI()
    app.include_router(tasks_router.router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


def _raw_body(amount_literal: bytes) -> bytes:
    return (
        b'{"task_data":{"task_id":"t-nan"},'
        b'"payment":{"requester":"0xBuyer","agent":"0xAgent","amount":' + amount_literal + b"}}"
    )


@pytest.mark.parametrize("literal", [b"NaN", b"Infinity", b"-Infinity", b"1e308"])
def test_task_submit_non_finite_amount_is_422_not_500(client, literal):
    resp = client.post(
        "/v1/tasks/submit",
        content=_raw_body(literal),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 422, f"amount={literal}: {resp.status_code} {resp.text[:200]}"
    # The 422 body must itself be valid JSON — the whole point of #1676.
    resp.json()


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_task_submit_non_finite_amount_string_is_422(client, literal):
    resp = client.post(
        "/v1/tasks/submit",
        json={
            "task_data": {"task_id": "t-nan"},
            "payment": {"requester": "0xBuyer", "agent": "0xAgent", "amount": literal},
        },
    )
    assert resp.status_code == 422, f"amount={literal!r}: {resp.status_code} {resp.text[:200]}"
    resp.json()
