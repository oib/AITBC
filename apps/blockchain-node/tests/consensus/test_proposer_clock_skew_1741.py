"""#1741 pins: wall-clock-behind detection for proposer scheduling.

A validator whose wall clock sits more than
``attestation_header_future_skew_seconds`` behind the chain head's
timestamps derives every proposer round as future-dated — its scheduled
turns never come due and it silently exits BOTH consensus roles while peers
see only round-robin fallthrough (attestation refusal is the separate
#1709 surface). The proposer now publishes ``proposer_clock_behind_seconds``,
counts ``proposer_clock_skew_detected_total``, logs a throttled CRITICAL,
and refuses to stamp a header attesters would reject as ``stale_header``
anyway. Scheduling itself is untouched — re-deriving rounds from monotonic
time or clamping the stamped timestamp is consensus-semantics work flagged
for E/Validator review.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, create_engine

from aitbc_chain.base_models import Block
from aitbc_chain.consensus.poa import PoAProposer, ProposerConfig
from aitbc_chain.database import clear_chain_db_quarantine
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.metadata import chain_metadata

CHAIN = "skew-1741"
ADDR = "0x" + "22" * 20


@pytest.fixture(autouse=True)
def _clean_state():
    clear_chain_db_quarantine()
    metrics_registry._gauges.pop("proposer_clock_behind_seconds", None)
    metrics_registry._counters.pop("proposer_clock_skew_detected_total", None)
    yield
    clear_chain_db_quarantine()
    metrics_registry._gauges.pop("proposer_clock_behind_seconds", None)
    metrics_registry._counters.pop("proposer_clock_skew_detected_total", None)


def _session_factory(engine):
    @contextmanager
    def factory():
        with Session(engine) as session:
            yield session

    return factory


def _proposer(chain_id: str = CHAIN, engine=None) -> PoAProposer:
    config = ProposerConfig(
        chain_id=chain_id,
        proposer_id=ADDR,
        interval_seconds=1,
        max_block_size_bytes=1_000_000,
        max_txs_per_block=100,
    )
    if engine is None:
        engine = create_engine("sqlite:///:memory:")
    return PoAProposer(config=config, session_factory=_session_factory(engine))


def _engine(tmp_path, name: str = "skew.db"):
    engine = create_engine(f"sqlite:///{tmp_path / name}")
    chain_metadata.create_all(engine)
    return engine


def _seed_head(engine, chain_id: str, timestamp: datetime, height: int = 5) -> None:
    with Session(engine) as session:
        session.add(
            Block(
                chain_id=chain_id,
                height=height,
                hash="0x" + "33" * 32,
                parent_hash="0x" + "11" * 32,
                proposer=ADDR,
                timestamp=timestamp,
                tx_count=0,
            )
        )
        session.commit()


# ── detector unit behaviour ───────────────────────────────────────


def test_clock_behind_head_is_detected():
    p = _proposer()
    head_ts = datetime.now(UTC) + timedelta(seconds=120)
    behind = p._note_wall_clock_skew(head_ts)
    assert behind == pytest.approx(120, abs=5)
    assert metrics_registry._gauges["proposer_clock_behind_seconds"] > 100
    assert metrics_registry._counters["proposer_clock_skew_detected_total"] == 1.0


def test_within_future_skew_bound_is_not_skew():
    p = _proposer()
    head_ts = datetime.now(UTC) + timedelta(seconds=5)  # inside the 10s bound
    assert p._note_wall_clock_skew(head_ts) == 0.0
    # The gauge still reports the small estimate — only the alarm bound gates
    # the counter/log/refusal.
    assert 0 < metrics_registry._gauges["proposer_clock_behind_seconds"] < 10
    assert "proposer_clock_skew_detected_total" not in metrics_registry._counters


def test_healthy_and_idle_heads_report_zero():
    p = _proposer()
    assert p._note_wall_clock_skew(None) == 0.0
    assert p._note_wall_clock_skew(datetime.now(UTC) - timedelta(hours=1)) == 0.0
    assert metrics_registry._gauges["proposer_clock_behind_seconds"] == 0.0


def test_error_log_is_throttled_but_detection_is_not():
    p = _proposer()
    head_ts = datetime.now(UTC) + timedelta(seconds=90)
    p._monotonic = lambda: 1000.0
    p._note_wall_clock_skew(head_ts)
    first_warn = p._clock_skew_warned_at
    assert first_warn == 1000.0
    # Inside the throttle window the warned_at latch must not move.
    p._monotonic = lambda: 1010.0
    p._note_wall_clock_skew(head_ts)
    assert p._clock_skew_warned_at == first_warn
    # Counter still counts every detection — only the log line is throttled.
    assert metrics_registry._counters["proposer_clock_skew_detected_total"] == 2.0
    # Past the window it warns again.
    p._monotonic = lambda: 1070.0
    p._note_wall_clock_skew(head_ts)
    assert p._clock_skew_warned_at == 1070.0


# ── proposal-path wiring ──────────────────────────────────────────


def test_resolve_proposal_head_refuses_on_behind_clock(tmp_path):
    """The drill's shape: head timestamp ~2 min in our future → the proposal
    head resolution refuses instead of stamping a stale_header-bound block."""
    engine = _engine(tmp_path)
    chain = CHAIN + "-resolve"
    try:
        proposer = _proposer(chain_id=chain, engine=engine)
        _seed_head(engine, chain, datetime.now(UTC) + timedelta(seconds=120))
        with Session(engine) as session:
            assert proposer._resolve_proposal_head(session) is None
        assert metrics_registry._gauges["proposer_clock_behind_seconds"] > 100
    finally:
        engine.dispose()


def test_resolve_proposal_head_passes_with_sane_clock(tmp_path):
    """Control: a head older than the block interval resolves normally."""
    engine = _engine(tmp_path)
    chain = CHAIN + "-ok"
    try:
        proposer = _proposer(chain_id=chain, engine=engine)
        _seed_head(engine, chain, datetime.now(UTC) - timedelta(seconds=30))
        with Session(engine) as session:
            resolved = proposer._resolve_proposal_head(session)
        assert resolved is not None
        head, next_height, _parent_hash, _interval = resolved
        assert head is not None and head.height == 5 and next_height == 6
    finally:
        engine.dispose()


def test_selected_proposer_gate_still_runs_but_reports_skew(tmp_path):
    """_selected_proposer_is_local is where the skewed node exits silently —
    the gate outcome is unchanged (still returns its normal verdict) but the
    skew is now detected, gauged and logged on every pass."""
    engine = _engine(tmp_path)
    try:
        proposer = _proposer(engine=engine)
        _seed_head(engine, CHAIN, datetime.now(UTC) + timedelta(seconds=90))
        head = proposer._fetch_chain_head()
        assert head is not None
        # Single-proposer fallback: gate verdict unchanged (True)…
        assert proposer._selected_proposer_is_local(head) is True
        # …but the skew was detected and published.
        assert metrics_registry._gauges["proposer_clock_behind_seconds"] > 80
        assert metrics_registry._counters["proposer_clock_skew_detected_total"] >= 1.0
    finally:
        engine.dispose()
