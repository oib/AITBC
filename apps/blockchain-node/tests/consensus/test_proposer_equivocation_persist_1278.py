"""#1278 follow-up: proposer-side evidence persistence must never block the event loop.

The clean D9b-patched drill (#1268 mesh, 8 Nov) showed the proposer-side
recorder's synchronous ``save_state()`` — a separate sqlite connection — blocks
for the busy timeout (~60 s) while the proposal's own session holds the write
lock: "database is locked", a stalled proposer, gossip keepalive timeouts, gates
failing. The fix records in memory at once (evidence exists before the
proposal signature leaves the node) and persists off the event loop, retrying
until the lock clears.
"""

from __future__ import annotations

import asyncio
import threading

import pytest
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA
from aitbc_chain.consensus.slashing import SlashingManager

from .test_proposer_equivocation_1278 import HA, HB, _proposal, _seed_prior_attestation, _setup
from .test_vote_journal_1268 import _counter, _env  # noqa: F401


class _ConsensusRecorder(SlashingManager):
    """Mimics MultiValidatorPoA: records in memory, persists via save_state()."""

    def __init__(self, save_results=None, block: threading.Event | None = None):
        super().__init__()
        self.save_calls: list[int] = []  # thread ids
        self.save_results = list(save_results or [])
        self.block = block
        self.saved_event_counts: list[int] = []

    def record_attestation_equivocation(self, *args, persist: bool = True, **kwargs):
        event = super().record_attestation_equivocation(*args, **kwargs)
        if persist:
            self.save_state()
        return event

    def save_state(self) -> bool:
        self.save_calls.append(threading.get_ident())
        if self.block is not None:
            self.block.wait(timeout=10)
        self.saved_event_counts.append(len(self.slashing_events))
        return self.save_results.pop(0) if self.save_results else True


def _arm(monkeypatch, recorder):
    svc, _mgr, our_addr, our_key, _, _ = _setup(monkeypatch)
    monkeypatch.setattr(svc, "_equivocation_recorder", lambda: recorder)
    _seed_prior_attestation(svc, our_addr, our_key, HA, round_bound_round=None)
    message, signature = _proposal(our_addr, our_key)
    return svc, message, signature


async def _drain(svc):
    for task in list(svc._deferred_state_saves):
        await task


class TestSaveNeverBlocksTheLoop:
    @pytest.mark.asyncio
    async def test_evidence_is_in_memory_immediately_and_save_runs_off_loop(self, monkeypatch):
        gate = threading.Event()
        rec = _ConsensusRecorder(block=gate)
        svc, message, signature = _arm(monkeypatch, rec)
        loop_thread = threading.get_ident()

        svc.record_proposal_equivocation(message, signature, 0)

        # the recording call returned without waiting for the (blocked) save
        assert len(rec.slashing_events) == 1
        # the loop stays responsive while the save thread is stuck on the db lock
        ticks = 0
        for _ in range(20):
            await asyncio.sleep(0.01)
            ticks += 1
        assert ticks == 20
        assert rec.save_calls, "deferred save should have started in a worker thread"
        assert all(t != loop_thread for t in rec.save_calls)
        assert not rec.saved_event_counts  # still blocked

        gate.set()
        await _drain(svc)
        assert rec.saved_event_counts == [1]  # persisted with the evidence present

    @pytest.mark.asyncio
    async def test_save_is_not_called_inline_by_the_recording_call(self, monkeypatch):
        rec = _ConsensusRecorder()
        svc, message, signature = _arm(monkeypatch, rec)

        svc.record_proposal_equivocation(message, signature, 0)

        assert rec.save_calls == []  # nothing ran synchronously on this thread
        await _drain(svc)
        assert len(rec.save_calls) == 1
        assert rec.save_calls[0] != threading.get_ident()


class TestDeferredSaveRetries:
    @pytest.mark.asyncio
    async def test_retries_until_the_lock_clears(self, monkeypatch):
        monkeypatch.setattr(ra_module, "DEFERRED_SAVE_RETRY_DELAY", 0.001)
        rec = _ConsensusRecorder(save_results=[False, False, True])
        svc, message, signature = _arm(monkeypatch, rec)

        svc.record_proposal_equivocation(message, signature, 0)
        await _drain(svc)

        assert len(rec.save_calls) == 3
        assert _counter("proposal_equivocation_persist_failed_total") == 0

    @pytest.mark.asyncio
    async def test_gives_up_loudly_after_the_attempt_budget(self, monkeypatch):
        monkeypatch.setattr(ra_module, "DEFERRED_SAVE_RETRY_DELAY", 0.001)
        monkeypatch.setattr(ra_module, "DEFERRED_SAVE_ATTEMPTS", 3)
        rec = _ConsensusRecorder(save_results=[False] * 10)
        svc, message, signature = _arm(monkeypatch, rec)

        svc.record_proposal_equivocation(message, signature, 0)
        await _drain(svc)

        assert len(rec.save_calls) == 3
        assert _counter("proposal_equivocation_persist_failed_total") == 1
        assert len(rec.slashing_events) == 1  # the in-memory evidence is untouched

    @pytest.mark.asyncio
    async def test_a_raising_save_is_retried_not_lost(self, monkeypatch):
        monkeypatch.setattr(ra_module, "DEFERRED_SAVE_RETRY_DELAY", 0.001)
        rec = _ConsensusRecorder()
        calls = {"n": 0}
        real = rec.save_state

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")
            return real()

        rec.save_state = flaky  # type: ignore[method-assign]
        svc, message, signature = _arm(monkeypatch, rec)

        svc.record_proposal_equivocation(message, signature, 0)
        await _drain(svc)

        assert calls["n"] == 2
        assert _counter("proposal_equivocation_persist_failed_total") == 0


class TestOtherPaths:
    def test_without_a_running_loop_the_save_runs_inline(self, monkeypatch):
        rec = _ConsensusRecorder()
        svc, message, signature = _arm(monkeypatch, rec)

        svc.record_proposal_equivocation(message, signature, 0)

        assert rec.save_calls == [threading.get_ident()]

    def test_inline_save_failure_without_a_loop_is_counted(self, monkeypatch):
        rec = _ConsensusRecorder(save_results=[False])
        svc, message, signature = _arm(monkeypatch, rec)

        svc.record_proposal_equivocation(message, signature, 0)

        assert _counter("proposal_equivocation_persist_failed_total") == 1

    @pytest.mark.asyncio
    async def test_attester_path_still_persists_inline(self, monkeypatch):
        rec = _ConsensusRecorder()
        svc, message, signature = _arm(monkeypatch, rec)
        svc._record_signed_attestation(
            message["height"], message["hash"], message["proposer"], message, None, False, signature
        )

        svc._record_attestation_equivocation_evidence(
            message["height"], message["hash"], message["proposer"], message["proposer"], None
        )

        # default persist=True: saved synchronously, nothing deferred
        assert rec.save_calls == [threading.get_ident()]
        assert not svc._deferred_state_saves

    @pytest.mark.asyncio
    async def test_nothing_recorded_means_nothing_scheduled(self, monkeypatch):
        rec = _ConsensusRecorder()
        svc, _mgr, our_addr, our_key, _, _ = _setup(monkeypatch)
        monkeypatch.setattr(svc, "_equivocation_recorder", lambda: rec)
        message, signature = _proposal(our_addr, our_key, HB)  # first vote at the height: no prior

        svc.record_proposal_equivocation(message, signature, 0)

        assert rec.slashing_events == []
        assert not svc._deferred_state_saves
        assert rec.save_calls == []

    @pytest.mark.asyncio
    async def test_plain_slashing_manager_recorder_needs_no_deferral(self, monkeypatch):
        svc, mgr, our_addr, our_key, _, _ = _setup(monkeypatch)  # recorder is a bare SlashingManager
        _seed_prior_attestation(svc, our_addr, our_key, HA, round_bound_round=None)
        message, signature = _proposal(our_addr, our_key)

        svc.record_proposal_equivocation(message, signature, 0)

        assert len(mgr.slashing_events) == 1
        assert not svc._deferred_state_saves


class TestConsensusRecorderPersistFlag:
    def _consensus(self, monkeypatch):
        consensus = MultiValidatorPoA.__new__(MultiValidatorPoA)
        consensus._slashing_manager = SlashingManager()
        saves: list[int] = []
        monkeypatch.setattr(consensus, "save_state", lambda: saves.append(1) or True, raising=False)
        return consensus, saves

    def _record(self, consensus, **kw):
        return consensus.record_attestation_equivocation(
            validator_address="0x" + "11" * 20,
            height=5,
            round_number=None,
            block_hash_a=HA,
            block_hash_b=HB,
            proposer="p",
            **kw,
        )

    def test_default_persists_synchronously(self, monkeypatch):
        consensus, saves = self._consensus(monkeypatch)
        self._record(consensus)
        assert saves == [1]

    def test_persist_false_records_in_memory_only(self, monkeypatch):
        consensus, saves = self._consensus(monkeypatch)
        event = self._record(consensus, persist=False)
        assert saves == []
        assert event in consensus._slashing_manager.slashing_events


def test_module_constants_are_sane():
    assert ra_module.DEFERRED_SAVE_ATTEMPTS >= 3
    assert 0 < ra_module.DEFERRED_SAVE_RETRY_DELAY <= ra_module.DEFERRED_SAVE_RETRY_MAX_DELAY
