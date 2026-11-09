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
from aitbc_chain.metrics import metrics_registry


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
    monkeypatch.setattr(proposer, "_collect_proposal_txs", lambda *_, **__: ([], {}, {}, set()))
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
    monkeypatch.setattr(settings, "proposer_same_hash_retry_enabled", True)

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
    monkeypatch.setattr(settings, "proposer_same_hash_retry_enabled", True)

    assert await proposer._propose_block() is False
    # Force the candidate past its horizon.
    cand = proposer._same_hash_retry
    assert cand is not None
    proposer._same_hash_retry = (cand[0], cand[1], cand[2], cand[2].timestamp() - 1.0, cand[4])

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
    monkeypatch.setattr(settings, "proposer_same_hash_retry_enabled", True)

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


@pytest.mark.parametrize("timeout", [1.0, 5.0, 15.0, 25.0])
def test_horizon_positive_across_collect_timeout_matrix(monkeypatch, timeout):
    """#1298 respin: the horizon formula must stay positive at the production
    15 s collect timeout — the old ``4 × timeout + 8`` margin silently zeroed
    it fleet-wide (mesh-2 fh1298-leg FAIL). Config-matrix pin so a future
    margin change can't reintroduce the silent disable."""
    monkeypatch.setattr(settings, "multi_validator_attestation_timeout_seconds", timeout)
    proposer = _proposer()
    horizon = proposer._same_hash_retry_horizon_seconds()
    bound = min(
        float(settings.consensus_proposer_round_seconds),
        float(settings.attestation_header_max_age_seconds),
    )
    expected = bound - (timeout + float(settings.proposer_same_hash_retry_margin_seconds))
    assert horizon == pytest.approx(max(0.0, expected))
    if expected > 0:
        assert horizon > 0, f"horizon must stay positive at timeout={timeout}"


def test_margin_knob_controls_horizon(monkeypatch):
    """proposer_same_hash_retry_margin_seconds is the slack reserved on top of
    one collect window — tuning it must move the horizon 1:1."""
    monkeypatch.setattr(settings, "multi_validator_attestation_timeout_seconds", 15.0)
    monkeypatch.setattr(settings, "proposer_same_hash_retry_margin_seconds", 40.0)
    proposer = _proposer()
    bound = min(
        float(settings.consensus_proposer_round_seconds),
        float(settings.attestation_header_max_age_seconds),
    )
    assert proposer._same_hash_retry_horizon_seconds() == pytest.approx(bound - 55.0)


def test_zero_horizon_warns_once_and_disables(monkeypatch, caplog):
    """A horizon that computes to 0 must be loud, not silent: warn once per
    proposer and keep the candidate cleared (fresh-timestamp fallback)."""
    import logging

    monkeypatch.setattr(settings, "multi_validator_attestation_timeout_seconds", 120.0)
    monkeypatch.setattr(settings, "proposer_same_hash_retry_enabled", True)
    proposer = _proposer()
    with caplog.at_level(logging.WARNING):
        proposer._note_same_hash_retry(7, b"parent", datetime.now(UTC), ())
        proposer._note_same_hash_retry(7, b"parent", datetime.now(UTC), ())
    assert proposer._same_hash_retry is None
    hits = [r for r in caplog.records if "same-hash retry horizon is 0" in r.getMessage()]
    assert len(hits) == 1


def test_fleet_values_horizon_is_33s(monkeypatch):
    """Pin the exact production fleet tuple: round_seconds=60,
    header_max_age=60, attest_timeout=15, margin=12 -> horizon=33s.
    This is the configuration under which the pre-respin formula computed
    0 and the feature was inert fleet-wide."""
    monkeypatch.setattr(settings, "consensus_proposer_round_seconds", 60)
    monkeypatch.setattr(settings, "attestation_header_max_age_seconds", 60.0)
    monkeypatch.setattr(settings, "multi_validator_attestation_timeout_seconds", 15.0)
    monkeypatch.setattr(settings, "proposer_same_hash_retry_margin_seconds", 12.0)
    proposer = _proposer()
    assert proposer._same_hash_retry_horizon_seconds() == pytest.approx(33.0)


def test_default_is_disabled():
    """Operator ruling: same-hash retry ships default-OFF; deployments opt in
    via PROPOSER_SAME_HASH_RETRY_ENABLED until the AD design review clears
    default-on. Pin the default so it cannot silently flip back."""
    assert settings.proposer_same_hash_retry_enabled is False


@pytest.mark.asyncio
async def test_parent_change_at_same_height_drops_pin(monkeypatch):
    """E c20975 probe: a same-height reorg (different parent_hash) must not
    reuse the pinned timestamp — the assembled block would differ anyway,
    and a pinned timestamp against a new parent is meaningless."""
    proposer = _proposer()
    timestamps: list[datetime] = []
    _arm(monkeypatch, proposer, timestamps)
    monkeypatch.setattr(settings, "proposer_same_hash_retry_enabled", True)

    assert await proposer._propose_block() is False
    head = SimpleNamespace()
    head.timestamp = datetime.now(UTC)
    monkeypatch.setattr(proposer, "_resolve_proposal_head", lambda *_: (head, 7, b"other-parent", 1))

    assert await proposer._propose_block() is False
    assert timestamps[1] > timestamps[0], "pinned timestamp leaked across a parent change"


@pytest.mark.asyncio
async def test_tx_set_drift_stamps_fresh_timestamp(monkeypatch):
    """E c20975 probe: if the drained tx set differs from the pinned
    snapshot, the retry must stamp a FRESH timestamp — same timestamp with
    a different tx set is a rival hash inside attesters' lock window."""
    proposer = _proposer()
    timestamps: list[datetime] = []
    seen_txs: list[object] = []
    _arm(monkeypatch, proposer, timestamps)
    monkeypatch.setattr(settings, "proposer_same_hash_retry_enabled", True)

    def _assemble(_s, _h, _p, timestamp, txs, _pr):
        timestamps.append(timestamp)
        seen_txs.append(tuple(getattr(t, "tx_hash", t) for t in txs))
        return SimpleNamespace(block_metadata=""), b"fake-block-hash"

    monkeypatch.setattr(proposer, "_assemble_proposal_block", _assemble)
    batches = iter(
        [
            [SimpleNamespace(tx_hash="a", content={})],
            [SimpleNamespace(tx_hash="a", content={}), SimpleNamespace(tx_hash="b", content={})],
        ]
    )
    monkeypatch.setattr(proposer, "_collect_proposal_txs", lambda *_, **__: (next(batches), {}, {}, set()))
    monkeypatch.setattr(proposer, "_process_proposal_txs", lambda _s, txs, *_a: (list(txs), set(), True))

    drift_before = metrics_registry._counters.get("proposer_same_hash_retry_tx_drift_total", 0.0)
    assert await proposer._propose_block() is False
    assert await proposer._propose_block() is False
    assert not (timestamps[0] == timestamps[1] and seen_txs[0] != seen_txs[1]), "same timestamp with a different tx set"
    assert metrics_registry._counters.get("proposer_same_hash_retry_tx_drift_total", 0.0) == drift_before + 1.0


@pytest.mark.asyncio
async def test_same_parent_and_tx_set_still_reuses(monkeypatch):
    """Guard against an over-fix: identical parent + tx set + horizon must
    still reuse the pinned timestamp across three failed proposals."""
    proposer = _proposer()
    timestamps: list[datetime] = []
    _arm(monkeypatch, proposer, timestamps)
    monkeypatch.setattr(settings, "proposer_same_hash_retry_enabled", True)

    for _ in range(3):
        assert await proposer._propose_block() is False
    assert timestamps[0] == timestamps[1] == timestamps[2]


@pytest.mark.asyncio
async def test_tx_drift_reselection_abort_is_safe(monkeypatch):
    """E c20986: the least-tested path — tx drift forces a fresh timestamp
    whose round may belong to another proposer. When re-selection finds no
    local turn (or the journal holds), the attempt must abort cleanly."""
    proposer = _proposer()
    timestamps: list[datetime] = []
    _arm(monkeypatch, proposer, timestamps)
    monkeypatch.setattr(settings, "proposer_same_hash_retry_enabled", True)

    selections = iter([("0x" + "0" * 40, 0), ("0x" + "0" * 40, 0), None])
    monkeypatch.setattr(proposer, "_select_round_proposer", lambda *_: next(selections))
    batches = iter(
        [
            [SimpleNamespace(tx_hash="a", content={})],
            [SimpleNamespace(tx_hash="a", content={}), SimpleNamespace(tx_hash="b", content={})],
        ]
    )
    monkeypatch.setattr(proposer, "_collect_proposal_txs", lambda *_, **__: (next(batches), {}, {}, set()))
    monkeypatch.setattr(proposer, "_process_proposal_txs", lambda _s, txs, *_a: (list(txs), set(), True))

    assert await proposer._propose_block() is False
    # attempt 2: pinned-ts selection succeeds, tx drift forces fresh ts,
    # re-selection finds no local turn -> clean abort before assemble.
    assert await proposer._propose_block() is False
    assert len(timestamps) == 1, "drift abort must happen before block assembly"
    assert proposer._same_hash_retry is None, "drift must drop the pin"
