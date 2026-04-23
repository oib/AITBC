"""
Tests for SLA Collector Service
"""

import sys
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session

from poolhub.models import Miner, MinerStatus, SLAMetric, SLAViolation, Feedback, MatchResult
from poolhub.services.sla_collector import SLACollector


@pytest.fixture
def sla_collector(db_session: Session) -> SLACollector:
    """Create SLA collector fixture"""
    return SLACollector(db_session)


@pytest.fixture
def sample_miner(db_session: Session) -> Miner:
    """Create sample miner fixture"""
    miner = Miner(
        miner_id="test_miner_001",
        api_key_hash="hash123",
        addr="127.0.0.1:8080",
        proto="http",
        gpu_vram_gb=24.0,
        gpu_name="RTX 4090",
        cpu_cores=16,
        ram_gb=64.0,
        max_parallel=4,
        base_price=0.50,
    )
    db_session.add(miner)
    db_session.commit()
    return miner


@pytest.fixture
def sample_miner_status(db_session: Session, sample_miner: Miner) -> MinerStatus:
    """Create sample miner status fixture"""
    status = MinerStatus(
        miner_id=sample_miner.miner_id,
        queue_len=2,
        busy=False,
        avg_latency_ms=150,
        temp_c=65,
        mem_free_gb=32.0,
        last_heartbeat_at=datetime.utcnow(),
    )
    db_session.add(status)
    db_session.commit()
    return status


@pytest.mark.asyncio
async def test_record_sla_metric(sla_collector: SLACollector, sample_miner: Miner):
    """Test recording an SLA metric"""
    metric = await sla_collector.record_sla_metric(
        miner_id=sample_miner.miner_id,
        metric_type="uptime_pct",
        metric_value=98.5,
        metadata={"test": "true"},
    )

    assert metric.miner_id == sample_miner.miner_id
    assert metric.metric_type == "uptime_pct"
    assert metric.metric_value == 98.5
    assert metric.is_violation == False


@pytest.mark.asyncio
async def test_record_sla_metric_violation(sla_collector: SLACollector, sample_miner: Miner):
    """Test recording an SLA metric that violates threshold"""
    metric = await sla_collector.record_sla_metric(
        miner_id=sample_miner.miner_id,
        metric_type="uptime_pct",
        metric_value=80.0,  # Below threshold of 95%
        metadata={"test": "true"},
    )

    assert metric.is_violation == True

    # Check violation was recorded
    violations = await sla_collector.get_sla_violations(
        miner_id=sample_miner.miner_id, resolved=False
    )
    assert len(violations) > 0
    assert violations[0].violation_type == "uptime_pct"


@pytest.mark.asyncio
async def test_collect_miner_uptime(sla_collector: SLACollector, sample_miner_status: MinerStatus):
    """Test collecting miner uptime"""
    uptime = await sla_collector.collect_miner_uptime(sample_miner_status.miner_id)

    assert uptime is not None
    assert 0 <= uptime <= 100


@pytest.mark.asyncio
async def test_collect_response_time_no_results(sla_collector: SLACollector, sample_miner: Miner):
    """Test collecting response time when no match results exist"""
    response_time = await sla_collector.collect_response_time(sample_miner.miner_id)

    assert response_time is None


@pytest.mark.asyncio
async def test_collect_completion_rate_no_feedback(sla_collector: SLACollector, sample_miner: Miner):
    """Test collecting completion rate when no feedback exists"""
    completion_rate = await sla_collector.collect_completion_rate(sample_miner.miner_id)

    assert completion_rate is None


@pytest.mark.asyncio
async def test_collect_capacity_availability(sla_collector: SLACollector):
    """Test collecting capacity availability"""
    capacity = await sla_collector.collect_capacity_availability()

    assert "total_miners" in capacity
    assert "active_miners" in capacity
    assert "capacity_availability_pct" in capacity


@pytest.mark.asyncio
async def test_get_sla_metrics(sla_collector: SLACollector, sample_miner: Miner):
    """Test getting SLA metrics"""
    # Record a metric first
    await sla_collector.record_sla_metric(
        miner_id=sample_miner.miner_id,
        metric_type="uptime_pct",
        metric_value=98.5,
    )

    metrics = await sla_collector.get_sla_metrics(
        miner_id=sample_miner.miner_id, hours=24
    )

    assert len(metrics) > 0
    assert metrics[0].miner_id == sample_miner.miner_id


@pytest.mark.asyncio
async def test_get_sla_violations(sla_collector: SLACollector, sample_miner: Miner):
    """Test getting SLA violations"""
    # Record a violation
    await sla_collector.record_sla_metric(
        miner_id=sample_miner.miner_id,
        metric_type="uptime_pct",
        metric_value=80.0,  # Below threshold
    )

    violations = await sla_collector.get_sla_violations(
        miner_id=sample_miner.miner_id, resolved=False
    )

    assert len(violations) > 0


def test_check_violation_uptime_below_threshold(sla_collector: SLACollector):
    """Test violation check for uptime below threshold"""
    is_violation = sla_collector._check_violation("uptime_pct", 90.0, 95.0)
    assert is_violation == True


def test_check_violation_uptime_above_threshold(sla_collector: SLACollector):
    """Test violation check for uptime above threshold"""
    is_violation = sla_collector._check_violation("uptime_pct", 98.0, 95.0)
    assert is_violation == False


@pytest.mark.asyncio
async def test_check_violation_response_time_above_threshold(sla_collector: SLACollector):
    """Test violation check for response time above threshold"""
    is_violation = sla_collector._check_violation("response_time_ms", 2000.0, 1000.0)
    assert is_violation == True


@pytest.mark.asyncio
async def test_check_violation_response_time_below_threshold(sla_collector: SLACollector):
    """Test violation check for response time below threshold"""
    is_violation = sla_collector._check_violation("response_time_ms", 500.0, 1000.0)
    assert is_violation == False
