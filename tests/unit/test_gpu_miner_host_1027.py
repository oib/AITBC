"""#1027 pin: gpu_miner_host retry/credentials and exchange-status honesty.

Before the fix: `except httpx.RequestException` named a class httpx does
not have, so a down coordinator crashed with AttributeError instead of
retrying; placeholder "${...}" credentials ran happily; capabilities
were hard-coded; a failed result submit vanished; and the status script
printed a hard-coded "everything works" block.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

GPU_DIR = Path(__file__).resolve().parents[2] / "scripts/services/gpu"


@pytest.fixture()
def miner(monkeypatch, tmp_path):
    monkeypatch.setenv("LOG_PATH", str(tmp_path / "miner.log"))
    sys.path.insert(0, str(GPU_DIR))
    try:
        import gpu_miner_host

        yield gpu_miner_host
    finally:
        sys.path.remove(str(GPU_DIR))
        sys.modules.pop("gpu_miner_host", None)


def test_coordinator_down_is_retried_not_attributeerror(miner, monkeypatch):
    calls = []

    class FakeHttp:
        class RequestError(Exception):
            pass

        @staticmethod
        def get(url, timeout):
            calls.append(url)
            raise FakeHttp.RequestError("connection refused")

    import httpx

    monkeypatch.setattr(miner.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("refused")))
    monkeypatch.setattr(miner, "MAX_RETRIES", 3)
    monkeypatch.setattr(miner.time, "sleep", lambda s: None)
    assert miner.wait_for_coordinator() is False


def test_placeholder_credentials_refuse_to_start(miner, monkeypatch):
    assert miner.credentials_ok() is False  # test env has no real key
    monkeypatch.setattr(miner, "AUTH_TOKEN", "${MINER_API_KEY}")
    monkeypatch.setattr(miner, "MINER_ID", "miner-1")
    assert miner.credentials_ok() is False
    monkeypatch.setattr(miner, "AUTH_TOKEN", "real-key-123")
    assert miner.credentials_ok() is True  # a real key must pass the gate


def test_capabilities_come_from_probe(miner):
    caps = miner.build_gpu_capabilities(
        {"name": "NVIDIA GeForce RTX 5090", "memory_total": 32768, "memory_used": 0, "utilization": 0}
    )
    assert caps["gpu"]["model"] == "NVIDIA GeForce RTX 5090"
    assert caps["gpu"]["memory_gb"] == 32


def test_failed_submit_retries_then_reports_lost(miner, monkeypatch):
    import httpx

    calls = []
    monkeypatch.setattr(
        miner.httpx, "post", lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(httpx.ConnectError("refused"))
    )
    # miner.time IS the stdlib time module — patching sleep here is
    # process-global, so it must go through monkeypatch's auto-undo or
    # every later time.sleep() in the suite becomes a no-op (#1219).
    monkeypatch.setattr(miner.time, "sleep", lambda s: None)
    assert miner.submit_result("job-1", {"result": {}}, retries=3, delay=0) is False
    assert len(calls) == 3


def test_status_script_reports_real_probes(capsys):
    runpy.run_path(str(GPU_DIR / "gpu_exchange_status.py"))
    captured = capsys.readouterr().out
    # nothing is listening in the test env: the summary must show failures,
    # never a hard-coded "everything works" status
    assert "GPU Miner: Running (systemd)" not in captured
    assert "❌" in captured
