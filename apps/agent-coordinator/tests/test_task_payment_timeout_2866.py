"""#2866: TaskPayment.timeout_seconds must be finite and bounded.

A NaN/negative/huge timeout lands directly in the escrow's expires_at — a
locked escrow either refunds instantly or is never swept. The bound lives
at the Pydantic layer (422 on submit) and again in
payment_escrow.create_escrow (ValueError).
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

os.environ.setdefault("SECRET_KEY", "test-secret-key")

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from agent_app import state  # noqa: E402
from agent_app.models import TaskPayment  # noqa: E402
from agent_app.routers import tasks as tasks_router  # noqa: E402


class TestTaskPaymentTimeoutBounds:
    @pytest.mark.parametrize("bad", [-1.0, 0.0, float("nan"), float("inf"), float("-inf"), 3_000_000.0])
    def test_model_rejects_invalid_timeout(self, bad):
        with pytest.raises(ValidationError):
            TaskPayment(amount=100, requester="0xB", agent="0xA", timeout_seconds=bad)

    @pytest.mark.parametrize("good", [1.0, 60.0, 3600.0, 2_592_000.0])
    def test_model_accepts_valid_timeout(self, good):
        payment = TaskPayment(amount=100, requester="0xB", agent="0xA", timeout_seconds=good)
        assert payment.timeout_seconds == good


@pytest.fixture
def client(monkeypatch):
    fake_state = MagicMock()
    fake_state.task_distributor = MagicMock()
    fake_state.task_distributor.submit_task = AsyncMock(return_value=True)
    fake_state.payment_escrow = None
    fake_state.escrow_rpc = None
    monkeypatch.setattr(state, "task_distributor", fake_state.task_distributor)
    monkeypatch.setattr(state, "payment_escrow", None)
    monkeypatch.setattr(state, "escrow_rpc", None)

    app = FastAPI()
    app.include_router(tasks_router.router, prefix="/v1")
    return TestClient(app), fake_state


class TestSubmitTimeoutValidation:
    @pytest.mark.parametrize("bad", [-1.0, 0.0, 3_000_000.0])
    def test_submit_rejects_out_of_range_timeout(self, client, bad):
        test_client, fake_state = client
        resp = test_client.post(
            "/v1/tasks/submit",
            json={
                "task_data": {"task_id": f"t-bad-timeout-{bad}"},
                "payment": {
                    "requester": "0xBuyer",
                    "agent": "0xAgent",
                    "amount": 100,
                    "timeout_seconds": bad,
                },
            },
        )
        assert resp.status_code == 422, f"timeout={bad}: {resp.status_code} {resp.text[:200]}"
        fake_state.task_distributor.submit_task.assert_not_called()
