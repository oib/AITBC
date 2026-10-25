"""PLAY2-ERRORS-1 item 3: `resource status` must accept the coordinator's
JSON-array response.

/v1/agent-performance/resources returns a bare array. The command used to
call client.get() which raises TypeError on arrays (expect_object) — the
isinstance fallback below it was dead code. Now it calls get_json().
"""

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.resource as res_mod


@pytest.fixture
def runner():
    return CliRunner()


class _ArrayClient:
    """Mimics the deployed coordinator response: a bare JSON array."""

    def get(self, endpoint, params=None):  # pragma: no cover - the old path must not be taken
        raise TypeError(f"{endpoint} returned a JSON array, not an object")

    def get_json(self, endpoint, params=None):
        assert endpoint == "/v1/agent-performance/resources"
        return [
            {
                "allocation_id": "alloc-1",
                "agent_id": "agent-7",
                "status": "active",
                "cpu_cores": 4,
                "memory_gb": 8.0,
                "gpu_count": 1,
                "allocated_at": "2026-10-25T18:00:00Z",
            }
        ]


def test_resource_status_accepts_array_response(runner, monkeypatch):
    monkeypatch.setattr(res_mod, "_client", lambda: _ArrayClient())
    result = runner.invoke(res_mod.resource, obj={"output_format": "table"}, args=["status"])
    assert result.exit_code == 0
    assert "alloc-1" in result.output
    assert "agent-7" in result.output


def test_resource_status_empty_array(runner, monkeypatch):
    class _Empty(_ArrayClient):
        def get_json(self, endpoint, params=None):
            return []

    monkeypatch.setattr(res_mod, "_client", lambda: _Empty())
    result = runner.invoke(res_mod.resource, obj={"output_format": "table"}, args=["status"])
    assert result.exit_code == 0


def test_resource_status_wrapped_object_shape(runner, monkeypatch):
    """Defensive: an object (single-allocation) response must not crash."""

    class _Obj(_ArrayClient):
        def get_json(self, endpoint, params=None):
            return {"allocation_id": "alloc-9", "agent_id": "a", "status": "pending"}

    monkeypatch.setattr(res_mod, "_client", lambda: _Obj())
    result = runner.invoke(res_mod.resource, obj={"output_format": "table"}, args=["status"])
    assert result.exit_code == 0
    assert "alloc-9" in result.output
