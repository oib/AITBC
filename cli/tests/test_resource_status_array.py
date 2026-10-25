"""RESOURCE-STATUS-1: `resource status` renders array, dict and empty answers.

The endpoint returns a JSON array; a stubbed client proves the shapes
without a live host (every host 401s without a login).
"""

from click.testing import CliRunner

from aitbc_cli.commands import resource as resource_mod


class _Client:
    def __init__(self, payload):
        self._payload = payload

    def get_json(self, path, params=None):
        return self._payload


def _invoke(runner, monkeypatch, payload, args=None):
    monkeypatch.setattr(resource_mod, "_client", lambda: _Client(payload))
    return runner.invoke(resource_mod.resource, obj={"output_format": "table"}, args=["status"] + (args or []))


def test_status_renders_json_array(monkeypatch):
    runner = CliRunner()
    rows = [
        {
            "allocation_id": "a1",
            "agent_id": "ag-1",
            "status": "active",
            "cpu_cores": 4,
            "memory_gb": 8,
            "gpu_count": 1,
            "allocated_at": "2026-10-26T00:00:00",
        },
        {
            "allocation_id": "a2",
            "agent_id": "ag-2",
            "status": "pending",
            "cpu_cores": 2,
            "memory_gb": 4,
            "gpu_count": 0,
            "allocated_at": "2026-10-26T00:01:00",
        },
    ]
    result = _invoke(runner, monkeypatch, rows)
    assert result.exit_code == 0
    assert "a1" in result.output and "a2" in result.output


def test_status_wraps_single_dict(monkeypatch):
    runner = CliRunner()
    result = _invoke(runner, monkeypatch, {"allocation_id": "a1", "agent_id": "ag-1", "status": "active"})
    assert result.exit_code == 0
    assert "a1" in result.output


def test_status_empty_array_prints_explicit_line(monkeypatch):
    runner = CliRunner()
    result = _invoke(runner, monkeypatch, [])
    assert result.exit_code == 0
    assert "No resource allocations found" in result.output


def test_status_network_error_exits_nonzero(monkeypatch):
    runner = CliRunner()

    class _Boom:
        def get_json(self, path, params=None):
            raise resource_mod.NetworkError("refused")

    monkeypatch.setattr(resource_mod, "_client", lambda: _Boom())
    result = runner.invoke(resource_mod.resource, obj={"output_format": "table"}, args=["status"])
    assert result.exit_code != 0
