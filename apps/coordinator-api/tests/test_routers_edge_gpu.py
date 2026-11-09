"""Tests for /v1/edge-gpu/* — nvidia-smi boundary, arg validation, response shapes (#1289 round 4).

The router shells out to ``nvidia-smi`` via ``asyncio.create_subprocess_exec``;
that boundary is faked here. Like ``knowledge``, the router has **no auth
dependency** — production gating is the matrix ``/v1/edge-gpu*`` → ANY floor
plus AuthMiddleware (disabled under TEST_MODE). ``run_nvidia_smi``'s
allowlist arg check is the security-relevant branch and is pinned directly.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from coordinator_api.contexts.edge_gpu.routers.edge_gpu import run_nvidia_smi

BASE = "/v1/edge-gpu"


class _FakeProc:
    def __init__(self, stdout: bytes = b"", returncode: int = 0) -> None:
        self._stdout = stdout
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, b""


def _patch_smi(monkeypatch: pytest.MonkeyPatch, output: str = "", returncode: int = 0) -> list[list[str]]:
    calls: list[list[str]] = []

    async def fake_exec(*cmd: str, **kwargs: Any) -> _FakeProc:
        calls.append(list(cmd))
        return _FakeProc(output.encode(), returncode)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return calls


class TestRunNvidiaSmi:
    async def test_rejects_unsafe_arg_without_exec(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = _patch_smi(monkeypatch, "0, 50, 60")
        out = await run_nvidia_smi(["--query-gpu=x", "--evil;rm -rf"])
        assert out == ""
        assert calls == []  # rejected before exec

    async def test_rejects_path_traversal_arg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = _patch_smi(monkeypatch)
        assert await run_nvidia_smi(["../../etc/passwd"]) == ""
        assert calls == []

    async def test_safe_args_return_stdout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_smi(monkeypatch, "0, RTX 4090, 24564\n")
        out = await run_nvidia_smi(["--query-gpu=index,name,memory.total", "--format=csv,noheader,nounits"])
        assert "RTX 4090" in out

    async def test_nonzero_returncode_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_smi(monkeypatch, "", returncode=9)
        assert await run_nvidia_smi(["--help"]) == ""

    async def test_missing_binary_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def boom(*a: Any, **k: Any) -> _FakeProc:
            raise FileNotFoundError("nvidia-smi")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", boom)
        assert await run_nvidia_smi(["--help"]) == ""


class TestProfiles:
    def test_no_gpus_empty(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_smi(monkeypatch, "")
        resp = client.get(f"{BASE}/profiles")
        assert resp.status_code == 200
        assert resp.json() == {"profiles": [], "total": 0}

    def test_parses_gpu_rows(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_smi(monkeypatch, "0, NVIDIA RTX 4090, 24564\n1, NVIDIA A100, 40960\n")
        resp = client.get(f"{BASE}/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["profiles"][0]["gpu_model"] == "NVIDIA RTX 4090"
        assert data["profiles"][0]["memory_gb"] == 24564 // 1024
        assert data["profiles"][0]["edge_optimized"] is True

    def test_malformed_rows_skipped(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_smi(monkeypatch, "garbage line\n0, Name Only\n")
        resp = client.get(f"{BASE}/profiles")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestMetrics:
    def test_single_gpu_metrics(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_smi(monkeypatch, "45.0, 1024.0, 55.0\n")
        resp = client.get(f"{BASE}/metrics/0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["gpu_id"] == "0"
        assert data["utilization"] == 45.0
        assert data["memory_used_mb"] == 1024.0
        assert data["temperature_c"] == 55.0

    def test_gpu_not_found(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_smi(monkeypatch, "")
        resp = client.get(f"{BASE}/metrics/9")
        assert resp.status_code == 200
        assert resp.json()["error"] == "GPU not found or nvidia-smi unavailable"

    def test_all_metrics_empty_when_no_gpus(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_smi(monkeypatch, "")
        resp = client.get(f"{BASE}/metrics")
        assert resp.status_code == 200
        assert resp.json() == {"metrics": [], "total": 0}


class TestWrites:
    def test_submit_metrics(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/metrics",
            json={
                "gpu_id": "0",
                "timestamp": "2026-11-09T00:00:00Z",
                "utilization": 10.0,
                "memory_used": 512.0,
                "temperature": 40.0,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["gpu_id"] == "0"

    def test_discover_counts_edge_optimized(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_smi(monkeypatch, "0, NVIDIA RTX 4090, 24564\n1, NVIDIA GTX 1660, 6144\n")
        resp = client.post(f"{BASE}/discover", params={"miner_id": "miner-1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["miner_id"] == "miner-1"
        assert data["registered"] == 2
        assert data["edge_optimized"] == 2

    def test_optimize_inference(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/optimize",
            params={"gpu_id": "0", "model_name": "llama"},
            json={"prompt": "hi"},
        )
        assert resp.status_code == 200
        assert resp.json()["optimized"] is True

    def test_no_dep_level_auth_documented(self, client: TestClient) -> None:
        """Same contract note as knowledge: no dep-level auth; prod floor is
        matrix ANY + middleware."""
        assert client.get(f"{BASE}/profiles").status_code == 200
