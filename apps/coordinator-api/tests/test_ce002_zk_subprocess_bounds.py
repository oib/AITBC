"""CE-002 (#1171): Node subprocesses for Groth16 work are bounded.

Every /zk/generate, /ml-zk/prove/* and verify call started its own ``node`` with no timeout
and no limit on how many ran at once. These tests drive ``_run_node`` with stand-in process
objects (no node, no snarkjs) and pin the three bounds: concurrency, queue wait, run time --
plus that a killed or cancelled run leaves no child behind and frees its slot.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from coordinator_api.contexts.zk_applications.routers import ml_zk_proofs
from coordinator_api.contexts.zk_applications.routers import zk_proofs as zk_router
from coordinator_api.contexts.zk_applications.services import zk_proofs as zk_module
from coordinator_api.contexts.zk_applications.services.zk_proofs import (
    ZKBusyError,
    ZKProofService,
    ZKTimeoutError,
    _run_node,
)


class _Proc:
    """A process whose communicate() blocks until released, and which records kill/wait."""

    def __init__(self, tracker: _Tracker, *, hang: bool, returncode: int = 0, out: bytes = b"true\n") -> None:
        self.t = tracker
        self.hang = hang
        self.returncode: int | None = None if hang else returncode
        self._final = returncode
        self.out = out
        self.killed = False
        self.reaped = False
        self._exited = asyncio.Event()

    async def communicate(self) -> tuple[bytes, bytes]:
        self.t.running += 1
        self.t.peak = max(self.t.peak, self.t.running)
        try:
            if self.hang:
                await self.t.release.wait()
            else:
                await asyncio.sleep(0)
            self.returncode = self._final
            return self.out, b""
        finally:
            self.t.running -= 1

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self._exited.set()

    async def wait(self) -> int:
        self.reaped = True
        return -9


class _Tracker:
    def __init__(self) -> None:
        self.running = 0
        self.peak = 0
        self.release = asyncio.Event()
        self.procs: list[_Proc] = []


@pytest.fixture
def fake_node(monkeypatch):
    """Patch process creation; ``hang`` in the returned dict decides whether children block."""
    cfg: dict[str, Any] = {"hang": True, "returncode": 0, "out": b"true\n"}
    made: list[_Proc] = []
    tracker_holder: dict[str, _Tracker] = {}

    async def fake_exec(*args, **kwargs):
        tracker = tracker_holder["t"]
        proc = _Proc(tracker, hang=cfg["hang"], returncode=cfg["returncode"], out=cfg["out"])
        made.append(proc)
        return proc

    monkeypatch.setattr(zk_module.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(zk_module, "ZK_MAX_CONCURRENT", 2)
    monkeypatch.setattr(zk_module, "ZK_QUEUE_TIMEOUT_SECONDS", 0.2)
    cfg["made"] = made
    cfg["holder"] = tracker_holder
    return cfg


def _run(coro):
    return asyncio.run(coro)


def test_concurrency_never_exceeds_the_limit_and_the_rest_are_refused(fake_node):
    async def scenario():
        t = _Tracker()
        fake_node["holder"]["t"] = t
        calls = [asyncio.create_task(_run_node("x.js", timeout=5)) for _ in range(6)]
        await asyncio.sleep(0.5)  # queue timeout (0.2 s) has passed for the four waiting calls
        results = []
        t.release.set()
        for c in calls:
            try:
                results.append(await c)
            except ZKBusyError:
                results.append("busy")
        return t, results

    t, results = _run(scenario())
    assert t.peak == 2, f"{t.peak} node subprocesses ran at once; the limit is 2"
    assert results.count("busy") == 4, results
    assert len(fake_node["made"]) == 2, "a refused caller must not have spawned a process"


def test_a_run_past_its_timeout_is_killed_reaped_and_reported(fake_node):
    async def scenario():
        t = _Tracker()
        fake_node["holder"]["t"] = t
        with pytest.raises(ZKTimeoutError):
            await _run_node("x.js", timeout=0.05)
        return t

    _run(scenario())
    (proc,) = fake_node["made"]
    assert proc.killed and proc.reaped, "the timed-out child was left running"


def test_the_slot_is_freed_after_a_timeout(fake_node, monkeypatch):
    async def scenario():
        t = _Tracker()
        fake_node["holder"]["t"] = t
        for _ in range(5):  # more timeouts than slots: a leaked slot would turn these into busy errors
            with pytest.raises(ZKTimeoutError):
                await _run_node("x.js", timeout=0.02)
        fake_node["hang"] = False
        return await _run_node("x.js", timeout=1)

    rc, out, _err = _run(scenario())
    assert rc == 0 and out == b"true\n"


def test_a_cancelled_caller_kills_its_child_and_frees_the_slot(fake_node):
    async def scenario():
        t = _Tracker()
        fake_node["holder"]["t"] = t
        task = asyncio.create_task(_run_node("x.js", timeout=30))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        fake_node["hang"] = False
        return await _run_node("x.js", timeout=1)

    _run(scenario())
    first = fake_node["made"][0]
    assert first.killed and first.reaped, "a client disconnect left its node subprocess running"


def test_nonzero_exit_is_returned_not_raised(fake_node):
    fake_node["hang"] = False
    fake_node["returncode"] = 1

    async def scenario():
        fake_node["holder"]["t"] = _Tracker()
        return await _run_node("x.js", timeout=1)

    rc, _out, _err = _run(scenario())
    assert rc == 1


def test_every_node_site_goes_through_the_bounded_runner():
    """No call site may spawn ``node`` itself again; the one spawn lives in _run_node."""
    source = zk_module.Path(zk_module.__file__).read_text()
    assert source.count("create_subprocess_exec") == 1, "a node subprocess is being spawned outside _run_node"
    assert source.count("_run_node(") >= 5  # definition + verify, poseidon, receipt prove, generic prove


def test_verify_reports_busy_and_timeout_as_unverified_with_a_reason(monkeypatch, tmp_path):
    service = ZKProofService()

    async def busy(*a, **k):
        raise ZKBusyError("slots")

    async def slow(*a, **k):
        raise ZKTimeoutError("slow")

    monkeypatch.setattr(zk_module, "_run_node", busy)
    verified, error = _run(service._snarkjs_groth16_verify({}, {}, []))
    assert verified is False and "busy" in (error or "")

    monkeypatch.setattr(zk_module, "_run_node", slow)
    verified, error = _run(service._snarkjs_groth16_verify({}, {}, []))
    assert verified is False and "timed out" in (error or "")


def test_generate_proof_lets_capacity_errors_through_but_folds_other_failures(monkeypatch):
    service = ZKProofService()
    service.enabled = True
    service.available_circuits = {"c": {"wasm_path": "w", "zkey_path": "z", "vkey_path": "v"}}

    async def boom(kind):
        raise kind("x")

    async def busy(*a, **k):
        await boom(ZKBusyError)

    async def slow(*a, **k):
        await boom(ZKTimeoutError)

    async def other(*a, **k):
        await boom(RuntimeError)

    monkeypatch.setattr(service, "_generate_proof_generic", busy)
    with pytest.raises(ZKBusyError):
        _run(service.generate_proof("c", {}))
    monkeypatch.setattr(service, "_generate_proof_generic", slow)
    with pytest.raises(ZKTimeoutError):
        _run(service.generate_proof("c", {}))
    monkeypatch.setattr(service, "_generate_proof_generic", other)
    assert _run(service.generate_proof("c", {})) is None


class TestRoutersAnswerCapacityHonestly:
    @pytest.mark.parametrize(
        ("exc", "status"),
        [(ZKBusyError, 503), (ZKTimeoutError, 504)],
    )
    def test_zk_generate(self, client, monkeypatch, exc, status):
        async def raises(*a, **k):
            raise exc("detail with numbers 120s")

        monkeypatch.setattr(zk_router.zk_proof_service, "generate_proof", raises)
        r = client.post("/v1/zk/generate", json={"circuit_name": "c", "inputs": {}})
        assert r.status_code == status, r.text
        assert "120s" not in r.text, "the numbers belong in the log, not in a 5xx body"
        if status == 503:
            assert r.headers.get("retry-after")

    @pytest.mark.parametrize(
        ("exc", "status"),
        [(ZKBusyError, 503), (ZKTimeoutError, 504)],
    )
    def test_ml_prove(self, client, monkeypatch, exc, status):
        async def raises(*a, **k):
            raise exc("detail with numbers 120s")

        monkeypatch.setattr(ml_zk_proofs.zk_service, "available_circuits", {"ml_training_verification": {}})
        monkeypatch.setattr(ml_zk_proofs.zk_service, "generate_proof", raises)
        r = client.post("/v1/ml-zk/prove/training", json={"inputs": {}})
        assert r.status_code == status, r.text
        assert "120s" not in r.text
