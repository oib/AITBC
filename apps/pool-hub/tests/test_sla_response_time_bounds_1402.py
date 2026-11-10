"""#1402 (POOLHUB-SLA-1) Option B — server-side sanity bounds on the
miner-self-reported response-time SLA leg.

MatchResult.eta_ms is copied from the miner's own heartbeat latency
(routers/match.py), so the measured entity supplies the measurement. The
operator ruling keeps self-report but adds defense-in-depth: every sample is
clamped to [0, ceiling] at SLA-metric ingestion, out-of-range samples are
counted and flagged via ``outliers_clamped`` in the metric metadata, and the
``source: miner_self_reported`` provenance label lets consumers discount the
leg. SLAMetricResponse already serializes ``meta_data`` as ``metadata``, so
the label reaches API responses unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from poolhub.app.routers.sla import SLAMetricResponse
from poolhub.models import Base, MatchRequest, MatchResult, Miner, MinerStatus, SLAMetric, SLAViolation
from poolhub.services.sla_collector import SLACollector, _RESPONSE_TIME_SAMPLE_MAX_MS, _bounded_response_times


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _miner(miner_id: str = "miner-1") -> Miner:
    return Miner(
        miner_id=miner_id,
        api_key_hash="x" * 64,
        addr="/ip4/127.0.0.1/tcp/9000",
        proto="tcp",
        gpu_vram_gb=24.0,
        gpu_name="RTX 4090",
        cpu_cores=16,
        ram_gb=64.0,
        max_parallel=4,
        base_price=Decimal("0.01"),
        wallet_address="0x" + "ab" * 20,
    )


def _status(miner_id: str) -> MinerStatus:
    return MinerStatus(miner_id=miner_id, last_heartbeat_at=datetime.now(UTC) - timedelta(seconds=30))


async def _seed_match_results(session_factory, eta_values: list[int]) -> None:
    async with session_factory() as s:
        s.add(_miner())
        s.add(_status("miner-1"))
        req = MatchRequest(job_id="job-1", requirements={})
        s.add(req)
        await s.flush()
        for eta in eta_values:
            s.add(MatchResult(request_id=req.id, miner_id="miner-1", score=0.9, eta_ms=eta))
        await s.commit()


class TestBoundedResponseTimes:
    def test_sane_values_pass_through(self):
        bounded, outliers = _bounded_response_times([0, 500, 1000])
        assert bounded == [0.0, 500.0, 1000.0]
        assert outliers == 0

    def test_negative_is_clamped_and_flagged(self):
        bounded, outliers = _bounded_response_times([-1, 500])
        assert bounded == [0.0, 500.0]
        assert outliers == 1

    def test_over_ceiling_is_clamped_and_flagged(self):
        bounded, outliers = _bounded_response_times([10**9, 500])
        assert bounded == [_RESPONSE_TIME_SAMPLE_MAX_MS, 500.0]
        assert outliers == 1

    def test_non_finite_is_clamped_to_ceiling_and_flagged(self):
        # NaN/Inf are garbage self-reports — they clamp to the ceiling (a
        # violation), never to 0 (a perfect score).
        bounded, outliers = _bounded_response_times([float("nan"), float("inf"), -float("inf"), 100.0])
        assert bounded == [_RESPONSE_TIME_SAMPLE_MAX_MS] * 3 + [100.0]
        assert outliers == 3


@pytest.mark.asyncio
async def test_collect_response_time_clamps_and_labels(session_factory):
    """Single-miner path: out-of-range eta_ms samples are bounded, counted,
    and the metric carries the self-reported provenance label."""
    await _seed_match_results(session_factory, [500, -50, 10**9])
    async with session_factory() as s:
        avg = await SLACollector(s).collect_response_time("miner-1")

    expected = (500.0 + 0.0 + _RESPONSE_TIME_SAMPLE_MAX_MS) / 3
    assert avg == pytest.approx(expected)
    async with session_factory() as s:
        metric = (
            await s.execute(
                select(SLAMetric).where(SLAMetric.miner_id == "miner-1", SLAMetric.metric_type == "response_time_ms")
            )
        ).scalar_one()
    assert metric.meta_data["source"] == "miner_self_reported"
    assert metric.meta_data["outliers_clamped"] == "2"
    # The provenance label is what API consumers see under ``metadata``.
    response = SLAMetricResponse.model_validate(metric)
    assert response.metadata["source"] == "miner_self_reported"
    assert response.metadata["outliers_clamped"] == "2"


@pytest.mark.asyncio
async def test_collect_all_bounds_batched_path(session_factory):
    """Batched path: same bounds, and a clamped-out violation row keeps the
    provenance + outlier labels in its metadata."""
    await _seed_match_results(session_factory, [-1, 10**9])
    async with session_factory() as s:
        await SLACollector(s).collect_all_miner_metrics()

    async with session_factory() as s:
        metric = (
            await s.execute(
                select(SLAMetric).where(SLAMetric.miner_id == "miner-1", SLAMetric.metric_type == "response_time_ms")
            )
        ).scalar_one()
    # (-1 -> 0, 1e9 -> 600000) averages far above the 1000ms threshold.
    assert metric.metric_value == pytest.approx(_RESPONSE_TIME_SAMPLE_MAX_MS / 2)
    assert metric.is_violation is True
    assert metric.meta_data["method"] == "collect_all"
    assert metric.meta_data["source"] == "miner_self_reported"
    assert metric.meta_data["outliers_clamped"] == "2"

    async with session_factory() as s2:
        v = (
            await s2.execute(
                select(SLAViolation).where(
                    SLAViolation.miner_id == "miner-1", SLAViolation.violation_type == "response_time_ms"
                )
            )
        ).scalar_one()
    assert v.meta_data["source"] == "miner_self_reported"
    assert v.meta_data["outliers_clamped"] == "2"


@pytest.mark.asyncio
async def test_collect_response_time_clean_samples_have_no_outlier_flag(session_factory):
    await _seed_match_results(session_factory, [400, 600])
    async with session_factory() as s:
        avg = await SLACollector(s).collect_response_time("miner-1")
    assert avg == pytest.approx(500.0)
    async with session_factory() as s:
        metric = (
            await s.execute(
                select(SLAMetric).where(SLAMetric.miner_id == "miner-1", SLAMetric.metric_type == "response_time_ms")
            )
        ).scalar_one()
    assert metric.meta_data["source"] == "miner_self_reported"
    assert "outliers_clamped" not in metric.meta_data
