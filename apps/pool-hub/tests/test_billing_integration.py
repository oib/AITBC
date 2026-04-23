"""
Tests for Billing Integration Service
"""

import sys
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from sqlalchemy.orm import Session

from poolhub.models import Miner, MatchRequest, MatchResult
from poolhub.services.billing_integration import BillingIntegration


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


@pytest.mark.asyncio
async def test_record_usage(billing_integration: BillingIntegration):
    """Test recording usage data"""
    # Mock the HTTP client
    with patch("poolhub.services.billing_integration.httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.json.return_value = {"status": "success", "id": "usage_123"}
        mock_response.raise_for_status = AsyncMock()
        
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        
        result = await billing_integration.record_usage(
            tenant_id="tenant_001",
            resource_type="gpu_hours",
            quantity=Decimal("10.5"),
            unit_price=Decimal("0.50"),
            job_id="job_123",
        )
        
        assert result["status"] == "success"


@pytest.mark.asyncio
async def test_record_usage_with_fallback_pricing(billing_integration: BillingIntegration):
    """Test recording usage with fallback pricing when unit_price not provided"""
    with patch("poolhub.services.billing_integration.httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.json.return_value = {"status": "success", "id": "usage_123"}
        mock_response.raise_for_status = AsyncMock()
        
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        
        result = await billing_integration.record_usage(
            tenant_id="tenant_001",
            resource_type="gpu_hours",
            quantity=Decimal("10.5"),
            # unit_price not provided
        )
        
        assert result["status"] == "success"


@pytest.mark.asyncio
async def test_sync_miner_usage(billing_integration: BillingIntegration, sample_miner: Miner):
    """Test syncing usage for a specific miner"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(hours=24)
    
    with patch("poolhub.services.billing_integration.httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.json.return_value = {"status": "success", "id": "usage_123"}
        mock_response.raise_for_status = AsyncMock()
        
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        
        result = await billing_integration.sync_miner_usage(
            miner_id=sample_miner.miner_id,
            start_date=start_date,
            end_date=end_date,
        )
        
        assert result["miner_id"] == sample_miner.miner_id
        assert result["tenant_id"] == sample_miner.miner_id
        assert "usage_records" in result


@pytest.mark.asyncio
async def test_sync_all_miners_usage(billing_integration: BillingIntegration, sample_miner: Miner):
    """Test syncing usage for all miners"""
    with patch("poolhub.services.billing_integration.httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.json.return_value = {"status": "success", "id": "usage_123"}
        mock_response.raise_for_status = AsyncMock()
        
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        
        result = await billing_integration.sync_all_miners_usage(hours_back=24)
        
        assert result["miners_processed"] >= 1
        assert "total_usage_records" in result


def test_collect_miner_usage(billing_integration: BillingIntegration, sample_miner: Miner):
    """Test collecting usage data for a miner"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(hours=24)
    
    usage_data = billing_integration.db.run_sync(
        lambda sess: billing_integration._collect_miner_usage(
            sample_miner.miner_id, start_date, end_date
        )
    )
    
    assert "gpu_hours" in usage_data
    assert "api_calls" in usage_data
    assert "compute_hours" in usage_data


@pytest.mark.asyncio
async def test_get_billing_metrics(billing_integration: BillingIntegration):
    """Test getting billing metrics from coordinator-api"""
    with patch("poolhub.services.billing_integration.httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "totals": {"cost": 100.0, "records": 50},
            "by_resource": {"gpu_hours": {"cost": 50.0}},
        }
        mock_response.raise_for_status = AsyncMock()
        
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        
        metrics = await billing_integration.get_billing_metrics(hours=24)
        
        assert "totals" in metrics


@pytest.mark.asyncio
async def test_trigger_invoice_generation(billing_integration: BillingIntegration):
    """Test triggering invoice generation"""
    with patch("poolhub.services.billing_integration.httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "invoice_number": "INV-001",
            "status": "draft",
            "total_amount": 100.0,
        }
        mock_response.raise_for_status = AsyncMock()
        
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)
        
        result = await billing_integration.trigger_invoice_generation(
            tenant_id="tenant_001",
            period_start=start_date,
            period_end=end_date,
        )
        
        assert result["invoice_number"] == "INV-001"


def test_resource_type_mapping(billing_integration: BillingIntegration):
    """Test resource type mapping"""
    assert "gpu_hours" in billing_integration.resource_type_mapping
    assert "storage_gb" in billing_integration.resource_type_mapping


def test_fallback_pricing(billing_integration: BillingIntegration):
    """Test fallback pricing configuration"""
    assert "gpu_hours" in billing_integration.fallback_pricing
    assert billing_integration.fallback_pricing["gpu_hours"]["unit_price"] == Decimal("0.50")
