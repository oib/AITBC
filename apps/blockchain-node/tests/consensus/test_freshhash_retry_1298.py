"""#1298 FRESHHASH-RETRY-1 pins: a gate-failed proposal retries with the SAME
block timestamp (hence the same hash) while inside the attestation-lock /
header-age horizon, and falls back to a fresh timestamp once it lapses.

Before the fix every retry re-assembled with ``datetime.now(UTC)`` — a fresh
hash per round that attesters locked to the first hash could never accept,
which is what kept wedged heights from converging (B's 8-leg matrix residual;
E's E1/E2/E3: fresh 287 s vs same-hash 15 s).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from aitbc_chain.config import ProposerConfig, settings
from aitbc_chain.consensus.poa import PoAProposer


@contextmanager
def _null_session():
    yield None


def _proposer() -> PoAProposer:
    config = ProposerConfig(
        chain_id="test-chain",
        proposer_id="test-node",
        interval_seconds=1,
        max_block_size_bytes=1000,
        max_txs_per_block=100,
    )
    return PoAProposer(config=config, session_factory=_null_session)


def _arm(monkeypatch, proposer, timestamps: list[datetime]) -> None:
    """Stub the whole proposal pipeline; record the timestamp each attempt
    would stamp into the block."""
    head = SimpleNamespace()
    head.timestamp = datetime.now(UTC)

    block = SimpleNamespace()
    block.block_metadata = ""

    def _assemble(_session, _h, _parent, timestamp, _txs, _proposer):
        timestamps.append(timestamp)
        return block, b"fake-block-hash"

    async def _gates_failed(*_args, **_kwargs):
        return False

    monkeypatch.setattr(proposer, "_passes_early_gates", AsyncMock(return_value=SimpleNamespace()))
    monkeypatch.setattr(proposer, "_resolve_proposal_head", lambda *_: (head, 7, b"parent", 1))
    monkeypatch.setattr(proposer, "_select_round_proposer", lambda *_: ("0x" + "0" * 40, 0))
    monkeypatch.setattr(proposer, "_collect_proposal_txs", lambda *_: ([], {}, {}))
    monkeypatch.setattr(proposer, "_process_proposal_txs", lambda *_: ([], set(), True))
    monkeypatch.setattr(proposer, "_reject_if_all_invalid", lambda *_: False)
    monkeypatch.setattr(proposer, "_assemble_proposal_block", _assemble)
    monkeypatch.setattr(proposer, "_sign_block_hash_for", lambda *_: "sig")
    monkeypatch.setattr(proposer, "_run_journaled_gates", _gates_failed)


@pytest.mark.asyncio
async def test_gate_failure_retries_same_timestamp_within_horizon(monkeypatch):
    """Two consecutive failed proposals at the same height reuse the first
    timestamp — the assembled block (and hash) is identical, so attesters
    inside the lock window see an idempotent re-publish, not a rival."""
    proposer = _proposer()
    timestamps: list[datetime] = []
    _arm(monkeypatch, proposer, timestamps)

    assert await proposer._propose_block() is False
    assert await proposer._propose_block() is False

    assert len(timestamps) == 2
    assert timestamps[0] == timestamps[1], "retry must reuse the failed block's timestamp"


@pytest.mark.asyncio
async def test_horizon_expiry_falls_back_to_fresh_timestamp(monkeypatch):
    """Once the attestation-lock/header-age horizon lapses the retry stamps
    a fresh timestamp — the lapsed-lock path can never be a timer-only
    re-sign (#1245 semantics preserved)."""
    proposer = _proposer()
    timestamps: list[datetime] = []
    _arm(monkeypatch, proposer, timestamps)

    assert await proposer._propose_block() is False
    # Force the candidate past its horizon.
    height, ts, _not_after = proposer._same_hash_retry
    proposer._same_hash_retry = (height, ts, ts.timestamp() - 1.0)

    assert await proposer._propose_block() is False
    assert timestamps[1] > timestamps[0], "expired horizon must produce a fresh timestamp"


@pytest.mark.asyncio
async def test_flag_off_always_fresh_timestamp(monkeypatch):
    proposer = _proposer()
    timestamps: list[datetime] = []
    _arm(monkeypatch, proposer, timestamps)
    monkeypatch.setattr(settings, "proposer_same_hash_retry_enabled", False)

    assert await proposer._propose_block() is False
    assert await proposer._propose_block() is False
    assert timestamps[0] != timestamps[1]
    assert proposer._same_hash_retry is None


@pytest.mark.asyncio
async def test_height_change_drops_candidate(monkeypatch):
    """A candidate recorded for height 7 must not leak into height 8."""
    proposer = _proposer()
    timestamps: list[datetime] = []
    _arm(monkeypatch, proposer, timestamps)

    assert await proposer._propose_block() is False
    head = SimpleNamespace()
    head.timestamp = datetime.now(UTC)
    monkeypatch.setattr(proposer, "_resolve_proposal_head", lambda *_: (head, 8, b"parent", 1))

    assert await proposer._propose_block() is False
    assert timestamps[1] > timestamps[0]


def test_horizon_is_bounded_by_lock_and_header_age():
    """The reuse horizon can never exceed the tighter of the attestation
    lock window and the signed-header max age (minus margin) — a reused
    block must still be acceptable to attesters."""
    proposer = _proposer()
    horizon = proposer._same_hash_retry_horizon_seconds()
    lock = float(settings.consensus_proposer_round_seconds)
    header = float(settings.attestation_header_max_age_seconds)
    assert 0 < horizon < min(lock, header)
