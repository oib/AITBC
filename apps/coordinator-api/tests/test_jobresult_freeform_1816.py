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


@pytest.mark.unit
def test_decimal_fields_dump_to_json_safe_payload() -> None:
    """F1: unit_price/price/aitbc_earned/cost are Decimal — a python-mode
    model_dump would land Decimal objects in job.result and the signed
    receipt, dying with TypeError: not JSON serializable at commit/sign.
    The route dumps mode="json"; pin that the dumped payload round-trips
    through json.dumps and keeps settlement-readable values."""
    import json

    body = {
        "result": {"output": "x", "unit_price": "1.5", "price": "2.25", "aitbc_earned": "0.5", "cost": "0.1"},
        "metrics": {"duration_ms": 100, "unit_price": "1.5", "price": "2.25", "aitbc_earned": "0.5", "cost": "0.1"},
    }
    parsed = JobResultSubmit.model_validate(body)
    result_payload = parsed.result.model_dump(mode="json", exclude_none=True)
    metrics_payload = parsed.metrics.model_dump(mode="json", exclude_none=True)
    # What the route stores/signs must be JSON-serializable end to end.
    json.dumps({"result": result_payload, "metrics": metrics_payload})
    assert result_payload["unit_price"] == "1.5"
    assert metrics_payload["price"] == "2.25"
    # exclude_none keeps the stored payload free of ~30 null keys.
    assert "status" not in result_payload and result_payload["output"] == "x"
