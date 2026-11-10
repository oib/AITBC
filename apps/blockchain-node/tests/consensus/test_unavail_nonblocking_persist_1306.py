"""#1306 nonblocking persist — the attest listener must not park on leg 1.

``unfetchable_persists`` polled the shared sampler for the whole
``unavail_evidence_seconds`` window; run inside the serial attest-request
listener (driver11: 40 s stalls, frozen height) it answered no attest
requests meanwhile. With ``unavail_nonblocking_persist_enabled`` armed the
listener path reads the sampler's current verdict instead.

Pins:

* ``unfetchable_persists(block=False)`` returns at once — False while the
  streak is immature, True only once it has matured, False on a fetch hit —
  and never releases early (safety: only the waiting moves);
* the default (blocking) behavior is unchanged, and the proposer path keeps
  it;
* the listener passes ``nonblocking_persist`` only when the flag AND the UC
  barrier are armed, so OFF is byte-identical to before.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest
from aitbc.crypto.signature_recovery import canonical_address
from aitbc_chain.config import settings
from aitbc_chain.consensus import unavail
from aitbc_chain.consensus.unavail import unfetchable_persists, unlock_justification

from . import test_unavail_justification_1281 as base

# Re-exported autouse fixture + helpers (assignment, not import: avoids F811).
_env = base._env
CHAIN, H, RIVAL = base.CHAIN, base.H, base.RIVAL
ADDR1, ADDR2, ADDR3, KEY2, KEY3 = base.ADDR1, base.ADDR2, base.ADDR3, base.KEY2, base.KEY3
PROPOSER = base.PROPOSER


async def _fresh(monkeypatch, locate):
    monkeypatch.setattr(unavail, "locate_voted_block", locate)
    await unavail.reset_observation_indices()


class TestPersistNonBlocking:
    @pytest.mark.asyncio
    async def test_immature_streak_returns_false_immediately(self, monkeypatch):
        await _fresh(monkeypatch, AsyncMock(return_value=None))
        monkeypatch.setattr(settings, "unavail_evidence_seconds", 30.0)
        t0 = time.monotonic()
        ok = await unfetchable_persists(CHAIN, 100, [H], block=False)
        assert ok is False
        assert time.monotonic() - t0 < 0.3, "block=False must not poll/sleep"
        # The sampler was started and keeps running in the background.
        sampler = unavail._FETCH_SAMPLERS.get((CHAIN, 100, H))
        assert sampler is not None and sampler.task is not None and not sampler.task.done()

    @pytest.mark.asyncio
    async def test_matured_streak_returns_true_without_waiting(self, monkeypatch):
        await _fresh(monkeypatch, AsyncMock(return_value=None))
        # Evidence 0.25 s (fixture): start the sampler, let it mature.
        assert await unfetchable_persists(CHAIN, 100, [H], block=False) is False
        await asyncio.sleep(0.6)
        t0 = time.monotonic()
        assert await unfetchable_persists(CHAIN, 100, [H], block=False) is True
        assert time.monotonic() - t0 < 0.3

    @pytest.mark.asyncio
    async def test_fetch_hit_never_proves(self, monkeypatch):
        await _fresh(monkeypatch, AsyncMock(return_value="https://peer"))
        assert await unfetchable_persists(CHAIN, 100, [H], block=False) is False
        await asyncio.sleep(0.4)
        assert await unfetchable_persists(CHAIN, 100, [H], block=False) is False

    @pytest.mark.asyncio
    async def test_default_still_blocks_until_matured(self, monkeypatch):
        """Unchanged contract: the default call waits out the evidence window."""
        await _fresh(monkeypatch, AsyncMock(return_value=None))
        t0 = time.monotonic()
        assert await unfetchable_persists(CHAIN, 100, [H], timeout=5.0) is True
        assert time.monotonic() - t0 >= 0.2, "default must still wait for T_evidence"

    @pytest.mark.asyncio
    async def test_no_hashes_is_false(self, monkeypatch):
        await _fresh(monkeypatch, AsyncMock(return_value=None))
        assert await unfetchable_persists(CHAIN, 100, [], block=False) is False


class TestUnlockJustificationNonBlocking:
    @pytest.mark.asyncio
    async def test_listener_returns_fast_then_releases_after_maturity(self, monkeypatch):
        """Immature streak: None within <1 s (refuse now). The sampler keeps
        running, so the retry after T_evidence releases — latency moves from
        'listener parked' to 'next retry', safety unchanged."""
        await _fresh(monkeypatch, AsyncMock(return_value=None))
        monkeypatch.setattr(settings, "unavail_evidence_seconds", 1.0)
        broker = base._Broker(responders=[(ADDR2, KEY2), (ADDR3, KEY3)])
        ignore = {canonical_address(ADDR1)}

        t0 = time.monotonic()
        early = await unlock_justification(
            CHAIN, 100, [H], ignore=ignore, broker=broker, wait_for_probe=False, nonblocking_persist=True
        )
        assert early is None
        assert time.monotonic() - t0 < 0.5, "listener path parked on leg 1"
        # No release before T_evidence: nothing was published (no probe ran).
        assert [m for t, m in broker.published if "unavail_query" in t] == []

        await asyncio.sleep(1.5)  # streak matures in the background
        late = await unlock_justification(
            CHAIN, 100, [H], ignore=ignore, broker=broker, wait_for_probe=True, nonblocking_persist=True
        )
        assert late is not None and late["kind"] == "unavailability_cert"

    @pytest.mark.asyncio
    async def test_default_blocking_leg1_unchanged(self, monkeypatch):
        """nonblocking_persist defaults False: leg 1 waits (proposer path)."""
        seen: list[bool] = []

        async def persists(chain_id, height, hashes, *, timeout=None, block=True):
            seen.append(block)
            return False

        monkeypatch.setattr(unavail, "unfetchable_persists", persists)
        await unlock_justification(CHAIN, 100, [H], broker=base._Broker())
        await unlock_justification(CHAIN, 100, [H], broker=base._Broker(), nonblocking_persist=True)
        assert seen == [True, False]


class TestListenerWiring:
    def test_flag_gate_requires_flag_and_barrier(self, monkeypatch):
        monkeypatch.setattr(settings, "vote_journal_enabled", True)
        monkeypatch.setattr(settings, "vote_journal_justification_enabled", True)
        monkeypatch.setattr(settings, "unavail_nonblocking_persist_enabled", False)
        assert unavail.nonblocking_persist_enabled() is False
        monkeypatch.setattr(settings, "unavail_nonblocking_persist_enabled", True)
        assert unavail.nonblocking_persist_enabled() is True
        monkeypatch.setattr(settings, "vote_journal_justification_enabled", False)
        assert unavail.nonblocking_persist_enabled() is False
        monkeypatch.setattr(settings, "vote_journal_justification_enabled", True)
        monkeypatch.setattr(settings, "vote_journal_enabled", False)
        assert unavail.nonblocking_persist_enabled() is False

    def test_default_is_off(self):
        from aitbc_chain.config import ChainSettings

        assert ChainSettings.model_fields["unavail_nonblocking_persist_enabled"].default is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("flag", [False, True])
    async def test_listener_passes_flag_state(self, monkeypatch, flag):
        """The attest-request listener passes nonblocking_persist=<flag>;
        OFF → False (byte-identical blocking behavior)."""
        monkeypatch.setattr(settings, "vote_journal_justification_enabled", True)
        monkeypatch.setattr(settings, "unavail_nonblocking_persist_enabled", flag)
        captured: dict = {}

        async def spy(*_a, **kw):
            captured.update(kw)
            return None

        monkeypatch.setattr(unavail, "unlock_justification", spy)
        svc, _broker, clock, _ = base.TestAttesterGateArmed()._service(monkeypatch)
        await svc._handle_request(base._request(100, H, PROPOSER, clock.now))
        clock.advance(10_000)
        await svc._handle_request(base._request(100, RIVAL, PROPOSER, clock.now))
        assert captured.get("nonblocking_persist") is flag
        assert captured.get("wait_for_probe") is False

    @pytest.mark.asyncio
    async def test_proposer_path_never_passes_nonblocking(self, monkeypatch):
        """poa.py keeps the blocking default even with the flag armed."""
        import inspect

        from aitbc_chain.consensus import poa as poa_module

        src = inspect.getsource(poa_module)
        call = src[src.index("unavail.unlock_justification(") :][:600]
        assert "wait_for_probe=True" in call
        assert "nonblocking_persist" not in call
