"""#1310: the attest-listener v9 tx check is timed and, behind a flag, offloaded to a thread."""

from __future__ import annotations

import threading

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.metrics import metrics_registry


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    metrics_registry.reset()
    monkeypatch.setattr(ra_module, "DATA_DIR", tmp_path)
    yield
    metrics_registry.reset()


def _svc(monkeypatch, verdict=None, boom=False):
    svc = RemoteAttestationService("test-chain", {})
    seen: list[int] = []

    def fake(header, txs, _attempt=1):
        seen.append(threading.get_ident())
        if boom:
            raise RuntimeError("check blew up")
        return verdict

    monkeypatch.setattr(svc, "_v9_check_transactions", fake)
    return svc, seen


@pytest.mark.asyncio
async def test_flag_off_runs_inline_on_the_loop_thread(monkeypatch):
    monkeypatch.setattr(settings, "attest_v9_check_offload_enabled", False)
    svc, seen = _svc(monkeypatch, verdict="not_at_parent")
    assert await svc._run_v9_check({}, []) == "not_at_parent"
    assert seen == [threading.get_ident()]


@pytest.mark.asyncio
async def test_flag_on_runs_in_a_worker_thread_and_keeps_the_verdict(monkeypatch):
    monkeypatch.setattr(settings, "attest_v9_check_offload_enabled", True)
    svc, seen = _svc(monkeypatch, verdict="not_at_parent")
    assert await svc._run_v9_check({}, []) == "not_at_parent"
    assert seen and seen[0] != threading.get_ident()
    svc2, seen2 = _svc(monkeypatch, verdict=None)
    assert await svc2._run_v9_check({}, []) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", [False, True])
async def test_exception_propagates_and_is_still_timed(monkeypatch, flag):
    monkeypatch.setattr(settings, "attest_v9_check_offload_enabled", flag)
    observed: list[tuple[str, float]] = []
    monkeypatch.setattr(metrics_registry, "observe", lambda name, v: observed.append((name, v)))
    svc, _ = _svc(monkeypatch, boom=True)
    with pytest.raises(RuntimeError):
        await svc._run_v9_check({}, [])
    assert [n for n, _ in observed] == ["attest_v9_check_seconds"]


@pytest.mark.asyncio
async def test_loop_stays_responsive_while_the_check_blocks(monkeypatch):
    """With offload on, a blocking check does not freeze the event loop."""
    import asyncio
    import time

    monkeypatch.setattr(settings, "attest_v9_check_offload_enabled", True)
    svc = RemoteAttestationService("test-chain", {})
    monkeypatch.setattr(svc, "_v9_check_transactions", lambda *a, **k: time.sleep(0.3))
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    t = asyncio.create_task(ticker())
    await svc._run_v9_check({}, [])
    t.cancel()
    assert ticks >= 5
