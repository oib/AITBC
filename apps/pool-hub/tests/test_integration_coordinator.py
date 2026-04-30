"""
Integration Tests for Pool-Hub with Coordinator-API
Tests the integration between pool-hub and coordinator-api's billing system.
"""
import sys

import pytest
from datetime import datetime, UTC, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session

from poolhub.models import Miner, MinerStatus, SLAMetric, CapacitySnapshot
from poolhub.services.sla_collector import SLACollector
from poolhub.services.billing_integration import BillingIntegration


@pytest.fixture
def sla_collector(db_session: Session) -> SLACollector:
    """Create SLA collector fixture"""
    return SLACollector(db_session)


@pytest.fixture
def billing_integration(db_session: Session) -> BillingIntegration:
    """Create billing integration fixture"""
    return BillingIntegration(db_session)


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


def test_end_to_end_sla_to_billing_workflow(
    sla_collector: SLACollector,
    billing_integration: BillingIntegration,
    sample_miner: Miner,
):
    """Test end-to-end workflow from SLA collection to billing"""
    # Step 1: Collect SLA metrics
    sla_collector.db.run_sync(
        lambda sess: sla_collector.record_sla_metric(
            miner_id=sample_miner.miner_id,
            metric_type="uptime_pct",
            metric_value=98.5,
        )
    )

    # Step 2: Verify metric was recorded
    metrics = sla_collector.db.run_sync(
        lambda sess: sla_collector.get_sla_metrics(
            miner_id=sample_miner.miner_id, hours=1
        )
    )
    assert len(metrics) > 0

    # Step 3: Collect usage data for billing
    end_date = datetime.now(datetime.UTC)
    start_date = end_date - timedelta(hours=1)
    usage_data = sla_collector.db.run_sync(
        lambda sess: billing_integration._collect_miner_usage(
            sample_miner.miner_id, start_date, end_date
        )
    )
    assert "gpu_hours" in usage_data
    assert "api_calls" in usage_data


def test_capacity_snapshot_creation(sla_collector: SLACollector, sample_miner: Miner):
    """Test capacity snapshot creation for capacity planning"""
    # Create capacity snapshot
    capacity = sla_collector.db.run_sync(
        lambda sess: sla_collector.collect_capacity_availability()
    )

    assert capacity["total_miners"] >= 1
    assert "active_miners" in capacity
    assert "capacity_availability_pct" in capacity

    # Verify snapshot was stored in database
    snapshots = sla_collector.db.run_sync(
        lambda sess: sla_collector.db.query(CapacitySnapshot)
        .order_by(CapacitySnapshot.timestamp.desc())
        .limit(1)
        .all()
    )
    assert len(snapshots) > 0


def test_sla_violation_billing_correlation(
    sla_collector: SLACollector,
    billing_integration: BillingIntegration,
    sample_miner: Miner,
):
    """Test correlation between SLA violations and billing"""
    # Record a violation
    sla_collector.db.run_sync(
        lambda sess: sla_collector.record_sla_metric(
            miner_id=sample_miner.miner_id,
            metric_type="uptime_pct",
            metric_value=80.0,  # Below threshold
        )
    )

    # Check violation was recorded
    violations = sla_collector.db.run_sync(
        lambda sess: sla_collector.get_sla_violations(
            miner_id=sample_miner.miner_id, resolved=False
        )
    )
    assert len(violations) > 0

    # Usage should still be recorded even with violations
    end_date = datetime.now(datetime.UTC)
    start_date = end_date - timedelta(hours=1)
    usage_data = sla_collector.db.run_sync(
        lambda sess: billing_integration._collect_miner_usage(
            sample_miner.miner_id, start_date, end_date
        )
    )
    assert usage_data is not None


def test_multi_miner_sla_collection(sla_collector: SLACollector, db_session: Session):
    """Test SLA collection across multiple miners"""
    # Create multiple miners
    miners = []
    for i in range(3):
        miner = Miner(
            miner_id=f"test_miner_{i:03d}",
            api_key_hash=f"hash{i}",
            addr=f"127.0.0.{i}:8080",
            proto="http",
            gpu_vram_gb=24.0,
            gpu_name="RTX 4090",
            cpu_cores=16,
            ram_gb=64.0,
            max_parallel=4,
            base_price=0.50,
        )
        db_session.add(miner)
        miners.append(miner)
    db_session.commit()

    # Collect metrics for all miners
    results = sla_collector.db.run_sync(
        lambda sess: sla_collector.collect_all_miner_metrics()
    )

    assert results["miners_processed"] >= 3


def test_billing_sync_with_coordinator_api(
    billing_integration: BillingIntegration,
    sample_miner: Miner,
):
    """Test billing sync with coordinator-api (mocked)"""
    from unittest.mock import AsyncMock, patch

    end_date = datetime.now(datetime.UTC)
    start_date = end_date - timedelta(hours=1)

    with patch("poolhub.services.billing_integration.httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.json.return_value = {"status": "success", "id": "usage_123"}
        mock_response.raise_for_status = AsyncMock()

        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

        result = billing_integration.db.run_sync(
            lambda sess: billing_integration.sync_miner_usage(
                miner_id=sample_miner.miner_id, start_date=start_date, end_date=end_date
            )
        )

        assert result["miner_id"] == sample_miner.miner_id
        assert result["usage_records"] >= 0


def test_sla_threshold_configuration(sla_collector: SLACollector):
    """Test SLA threshold configuration"""
    # Verify default thresholds
    assert sla_collector.sla_thresholds["uptime_pct"] == 95.0
    assert sla_collector.sla_thresholds["response_time_ms"] == 1000.0
    assert sla_collector.sla_thresholds["completion_rate_pct"] == 90.0
    assert sla_collector.sla_thresholds["capacity_availability_pct"] == 80.0


def test_capacity_utilization_calculation(sla_collector: SLACollector, sample_miner: Miner):
    """Test capacity utilization calculation"""
    capacity = sla_collector.db.run_sync(
        lambda sess: sla_collector.collect_capacity_availability()
    )

    # Verify utilization is between 0 and 100
    assert 0 <= capacity["capacity_availability_pct"] <= 100
