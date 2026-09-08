"""R7: watchdog phase-level diagnosis.

The 1804 freeze left no log indicating which proposal phase stalled. The
watchdog now logs the active phase in its ERROR and increments a per-phase
metric, so a stalled proposer is identifiable at LOG_LEVEL=INFO.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace


import pytest

from aitbc_chain.config import ProposerConfig
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.metrics import metrics_registry


@contextmanager
def _null_session():
    yield None


@pytest.fixture
def proposer(caplog):
    """A minimal PoAProposer with a no-op session factory and short interval."""
    caplog.set_level(logging.INFO, logger="aitbc_chain.consensus.poa")
    config = ProposerConfig(
        chain_id="test-chain",
        proposer_id="test-node",
        interval_seconds=1,
        max_block_size_bytes=1000,
        max_txs_per_block=100,
    )
    proposer = PoAProposer(config=config, session_factory=_null_session)
    return proposer


def _head():
    """Return a fake head with a timestamp."""
    head = SimpleNamespace()
    head.timestamp = datetime.now(UTC)
    return head


def _block():
    """Return a fake block and block hash."""
    block = SimpleNamespace()
    block.block_metadata = ""
    return block, b"fake-block-hash"


def _patch_pipeline(proposer, monkeypatch):
    """Patch every proposal phase with fast, valid defaults."""

    async def _passes_early_gates(*_args, **_kwargs):
        return SimpleNamespace()

    async def _run_consensus_gates(*_args, **_kwargs):
        return True

    async def _broadcast_block(*_args, **_kwargs):
        return True

    monkeypatch.setattr(proposer, "_passes_early_gates", _passes_early_gates)
    monkeypatch.setattr(proposer, "_resolve_proposal_head", lambda *_: (_head(), 1, b"parent", 1))
    monkeypatch.setattr(proposer, "_select_round_proposer", lambda *_: ("0x" + "0" * 40, 0))
    monkeypatch.setattr(proposer, "_collect_proposal_txs", lambda *_: ([], {}, {}))
    monkeypatch.setattr(proposer, "_process_proposal_txs", lambda *_: ([], set(), True))
    monkeypatch.setattr(proposer, "_reject_if_all_invalid", lambda *_: False)
    monkeypatch.setattr(proposer, "_assemble_proposal_block", lambda *_: _block())
    monkeypatch.setattr(proposer, "_run_consensus_gates", _run_consensus_gates)
    monkeypatch.setattr(proposer, "_sign_block_hash_for", lambda *_: b"sig")
    monkeypatch.setattr(proposer, "_commit_and_record_block", lambda *_: None)
    monkeypatch.setattr(proposer, "_broadcast_block", _broadcast_block)


class TestProposerWatchdogPhase:
    """Verify the watchdog reports the active phase when an await-bearing phase stalls."""

    @pytest.mark.parametrize(
        ("phase_name", "stall_in", "return_value"),
        [
            ("early_gates", "_passes_early_gates", SimpleNamespace()),
            ("consensus_gates", "_run_consensus_gates", True),
            ("broadcast", "_broadcast_block", True),
        ],
    )
    async def test_watchdog_logs_phase_at_info(self, proposer, phase_name, stall_in, return_value, monkeypatch, caplog):
        """When a phase stalls, the watchdog ERROR names the active phase."""
        _patch_pipeline(proposer, monkeypatch)

        async def _hanging(*_args, **_kwargs):
            await asyncio.sleep(0.1)
            return return_value

        monkeypatch.setattr(proposer, stall_in, _hanging)

        result = await proposer._propose_block_with_watchdog(watchdog_after=0.05)

        assert result is True
        assert any(
            "proposal iteration still running" in record.message and f"(phase={phase_name})" in record.message
            for record in caplog.records
        )

    async def test_watchdog_increments_total_metric(self, proposer, monkeypatch):
        """A stalled iteration increments the stalled-iterations counter."""
        _patch_pipeline(proposer, monkeypatch)

        async def _hanging(*_args, **_kwargs):
            await asyncio.sleep(0.1)
            return SimpleNamespace()

        monkeypatch.setattr(proposer, "_passes_early_gates", _hanging)

        before = metrics_registry._counters.get("poa_proposer_stalled_iterations_total", 0)
        await proposer._propose_block_with_watchdog(watchdog_after=0.05)
        after = metrics_registry._counters.get("poa_proposer_stalled_iterations_total", 0)

        assert after == before + 1

    async def test_phase_metric_tracks_active_phase(self, proposer, monkeypatch):
        """The per-phase stalled-iterations counter is keyed to the active phase."""
        _patch_pipeline(proposer, monkeypatch)

        async def _hanging(*_args, **_kwargs):
            await asyncio.sleep(0.1)
            return SimpleNamespace()

        monkeypatch.setattr(proposer, "_passes_early_gates", _hanging)

        metric_name = "poa_proposer_stalled_iterations_total_phase_early_gates"
        before = metrics_registry._counters.get(metric_name, 0)
        await proposer._propose_block_with_watchdog(watchdog_after=0.05)
        after = metrics_registry._counters.get(metric_name, 0)

        assert after == before + 1

    async def test_propose_phase_is_set_before_awaits(self, proposer, monkeypatch):
        """The active phase attribute is updated before each await-bearing call."""
        _patch_pipeline(proposer, monkeypatch)

        called = []

        async def _early_gates(*_args, **_kwargs):
            called.append(proposer._propose_phase)
            return SimpleNamespace()

        monkeypatch.setattr(proposer, "_passes_early_gates", _early_gates)

        await proposer._propose_block_with_watchdog(watchdog_after=0.01)

        assert called == ["early_gates"]
