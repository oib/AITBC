"""JOBRESULT-FREEFORM-1 (#1816): JobResultSubmit rejects unknown/malformed payload keys."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from aitbc.auth import create_access_token

from coordinator_api.schemas import JobResultSubmit


def _miner_headers(sub: str = "miner-1") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, 'miner')}"}


_PRODUCTION_MINER_SHAPE = {
    "result": {
        "status": "completed",
        "output": "hello",
        "execution_time": 1.25,
        "gpu_used": True,
        "model": "llama3.2:latest",
        "tokens_processed": 42,
    },
    "metrics": {
        "gpu_utilization": 80,
        "memory_used": 1024,
        "memory_peak": 2048,
        "duration_ms": 1250,
    },
}


@pytest.mark.unit
class TestJobResultSubmitSchema:
    def test_accepts_production_miner_shape(self) -> None:
        parsed = JobResultSubmit.model_validate(_PRODUCTION_MINER_SHAPE)
        assert parsed.result.output == "hello"
        assert parsed.metrics.duration_ms == 1250

    def test_rejects_unknown_result_field(self) -> None:
        body = {"result": {"output": "x", "injected_settlement_hook": True}, "metrics": {}}
        with pytest.raises(ValidationError):
            JobResultSubmit.model_validate(body)

    def test_rejects_unknown_metrics_field(self) -> None:
        body = {"result": {"output": "x"}, "metrics": {"duration_ms": 1, "extra_billing": 999}}
        with pytest.raises(ValidationError):
            JobResultSubmit.model_validate(body)

    def test_rejects_unknown_top_level_field(self) -> None:
        body = {"result": {"output": "x"}, "metrics": {}, "admin_override": True}
        with pytest.raises(ValidationError):
            JobResultSubmit.model_validate(body)

    def test_rejects_negative_duration_ms(self) -> None:
        body = {"result": {"output": "x"}, "metrics": {"duration_ms": -1}}
        with pytest.raises(ValidationError):
            JobResultSubmit.model_validate(body)


@pytest.mark.unit
class TestJobResultSubmitRouteValidation:
    def test_unknown_result_key_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/miners/any-job/result",
            json={"result": {"output": "ok", "evil": True}, "metrics": {}},
            headers=_miner_headers(),
        )
        assert resp.status_code == 422

    def test_unknown_metrics_key_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/miners/any-job/result",
            json={"result": {"output": "ok"}, "metrics": {"duration_ms": 10, "bogus": 1}},
            headers=_miner_headers(),
        )
        assert resp.status_code == 422
