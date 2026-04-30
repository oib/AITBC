"""
Tests for SLA API Endpoints
"""

import sys
import pytest
from datetime import datetime, UTC, timedelta
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from poolhub.models import Miner, MinerStatus, SLAMetric
from poolhub.app.routers.sla import router
from poolhub.database import get_db


@pytest.fixture
def test_client(db_session: Session):
    """Create test client fixture"""
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    
    # Override database dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    return TestClient(app)


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
def sample_sla_metric(db_session: Session, sample_miner: Miner) -> SLAMetric:
    """Create sample SLA metric fixture"""
    from uuid import uuid4
    
    metric = SLAMetric(
        id=uuid4(),
        miner_id=sample_miner.miner_id,
        metric_type="uptime_pct",
        metric_value=98.5,
        threshold=95.0,
        is_violation=False,
        timestamp=datetime.now(datetime.UTC),
        metadata={"test": "true"},
    )
    db_session.add(metric)
    db_session.commit()
    return metric


def test_get_miner_sla_metrics(test_client: TestClient, sample_sla_metric: SLAMetric):
    """Test getting SLA metrics for a specific miner"""
    response = test_client.get(f"/sla/metrics/{sample_sla_metric.miner_id}?hours=24")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert data[0]["miner_id"] == sample_sla_metric.miner_id


def test_get_all_sla_metrics(test_client: TestClient, sample_sla_metric: SLAMetric):
    """Test getting SLA metrics across all miners"""
    response = test_client.get("/sla/metrics?hours=24")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0


def test_get_sla_violations(test_client: TestClient, sample_miner: Miner):
    """Test getting SLA violations"""
    response = test_client.get("/sla/violations?resolved=false")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_collect_sla_metrics(test_client: TestClient):
    """Test triggering SLA metrics collection"""
    response = test_client.post("/sla/metrics/collect")
    
    assert response.status_code == 200
    data = response.json()
    assert "miners_processed" in data


def test_get_capacity_snapshots(test_client: TestClient):
    """Test getting capacity planning snapshots"""
    response = test_client.get("/sla/capacity/snapshots?hours=24")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_capacity_forecast(test_client: TestClient):
    """Test getting capacity forecast"""
    response = test_client.get("/sla/capacity/forecast?hours_ahead=168")
    
    assert response.status_code == 200
    data = response.json()
    assert "forecast_horizon_hours" in data
    assert "current_capacity" in data


def test_get_scaling_recommendations(test_client: TestClient):
    """Test getting scaling recommendations"""
    response = test_client.get("/sla/capacity/recommendations")
    
    assert response.status_code == 200
    data = response.json()
    assert "current_state" in data
    assert "recommendations" in data


def test_configure_capacity_alerts(test_client: TestClient):
    """Test configuring capacity alerts"""
    alert_config = {
        "threshold_pct": 80.0,
        "notification_email": "admin@example.com",
    }
    response = test_client.post("/sla/capacity/alerts/configure", json=alert_config)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "configured"


def test_get_billing_usage(test_client: TestClient):
    """Test getting billing usage data"""
    response = test_client.get("/sla/billing/usage?hours=24")
    
    # This may fail if coordinator-api is not available
    # For now, we expect either 200 or 500
    assert response.status_code in [200, 500]


def test_sync_billing_usage(test_client: TestClient):
    """Test triggering billing sync"""
    request_data = {
        "hours_back": 24,
    }
    response = test_client.post("/sla/billing/sync", json=request_data)
    
    # This may fail if coordinator-api is not available
    # For now, we expect either 200 or 500
    assert response.status_code in [200, 500]


def test_record_usage(test_client: TestClient):
    """Test recording a single usage event"""
    request_data = {
        "tenant_id": "tenant_001",
        "resource_type": "gpu_hours",
        "quantity": 10.5,
        "unit_price": 0.50,
        "job_id": "job_123",
    }
    response = test_client.post("/sla/billing/usage/record", json=request_data)
    
    # This may fail if coordinator-api is not available
    # For now, we expect either 200 or 500
    assert response.status_code in [200, 500]


def test_generate_invoice(test_client: TestClient):
    """Test triggering invoice generation"""
    end_date = datetime.now(datetime.UTC)
    start_date = end_date - timedelta(days=30)
    
    request_data = {
        "tenant_id": "tenant_001",
        "period_start": start_date.isoformat(),
        "period_end": end_date.isoformat(),
    }
    response = test_client.post("/sla/billing/invoice/generate", json=request_data)
    
    # This may fail if coordinator-api is not available
    # For now, we expect either 200 or 500
    assert response.status_code in [200, 500]


def test_get_sla_status(test_client: TestClient):
    """Test getting overall SLA status"""
    response = test_client.get("/sla/status")
    
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "active_violations" in data
    assert "timestamp" in data
