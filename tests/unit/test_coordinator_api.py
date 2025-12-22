"""
Unit tests for AITBC Coordinator API
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient

from apps.coordinator_api.src.app.main import app
from apps.coordinator_api.src.app.models.job import Job, JobStatus
from apps.coordinator_api.src.app.models.receipt import JobReceipt
from apps.coordinator_api.src.app.services.job_service import JobService
from apps.coordinator_api.src.app.services.receipt_service import ReceiptService
from apps.coordinator_api.src.app.exceptions import JobError, ValidationError


@pytest.mark.unit
class TestJobEndpoints:
    """Test job-related endpoints"""
    
    def test_create_job_success(self, coordinator_client, sample_job_data, sample_tenant):
        """Test successful job creation"""
        response = coordinator_client.post(
            "/v1/jobs",
            json=sample_job_data,
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["id"] is not None
        assert data["status"] == "pending"
        assert data["job_type"] == sample_job_data["job_type"]
        assert data["tenant_id"] == sample_tenant.id
    
    def test_create_job_invalid_data(self, coordinator_client):
        """Test job creation with invalid data"""
        invalid_data = {
            "job_type": "invalid_type",
            "parameters": {},
        }
        
        response = coordinator_client.post("/v1/jobs", json=invalid_data)
        assert response.status_code == 422
        assert "detail" in response.json()
    
    def test_create_job_unauthorized(self, coordinator_client, sample_job_data):
        """Test job creation without tenant ID"""
        response = coordinator_client.post("/v1/jobs", json=sample_job_data)
        assert response.status_code == 401
    
    def test_get_job_success(self, coordinator_client, sample_job_data, sample_tenant):
        """Test successful job retrieval"""
        # Create a job first
        create_response = coordinator_client.post(
            "/v1/jobs",
            json=sample_job_data,
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        job_id = create_response.json()["id"]
        
        # Retrieve the job
        response = coordinator_client.get(
            f"/v1/jobs/{job_id}",
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == job_id
        assert data["job_type"] == sample_job_data["job_type"]
    
    def test_get_job_not_found(self, coordinator_client, sample_tenant):
        """Test retrieving non-existent job"""
        response = coordinator_client.get(
            "/v1/jobs/non-existent",
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        assert response.status_code == 404
    
    def test_list_jobs_success(self, coordinator_client, sample_job_data, sample_tenant):
        """Test successful job listing"""
        # Create multiple jobs
        for i in range(5):
            coordinator_client.post(
                "/v1/jobs",
                json=sample_job_data,
                headers={"X-Tenant-ID": sample_tenant.id}
            )
        
        # List jobs
        response = coordinator_client.get(
            "/v1/jobs",
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) >= 5
        assert "total" in data
        assert "page" in data
    
    def test_list_jobs_with_filters(self, coordinator_client, sample_job_data, sample_tenant):
        """Test job listing with filters"""
        # Create jobs with different statuses
        coordinator_client.post(
            "/v1/jobs",
            json={**sample_job_data, "priority": "high"},
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        # Filter by priority
        response = coordinator_client.get(
            "/v1/jobs?priority=high",
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert all(job["priority"] == "high" for job in data["items"])
    
    def test_cancel_job_success(self, coordinator_client, sample_job_data, sample_tenant):
        """Test successful job cancellation"""
        # Create a job
        create_response = coordinator_client.post(
            "/v1/jobs",
            json=sample_job_data,
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        job_id = create_response.json()["id"]
        
        # Cancel the job
        response = coordinator_client.patch(
            f"/v1/jobs/{job_id}/cancel",
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"
    
    def test_cancel_completed_job(self, coordinator_client, sample_job_data, sample_tenant):
        """Test cancelling a completed job"""
        # Create and complete a job
        create_response = coordinator_client.post(
            "/v1/jobs",
            json=sample_job_data,
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        job_id = create_response.json()["id"]
        
        # Mark as completed
        coordinator_client.patch(
            f"/v1/jobs/{job_id}",
            json={"status": "completed"},
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        # Try to cancel
        response = coordinator_client.patch(
            f"/v1/jobs/{job_id}/cancel",
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 400
        assert "cannot be cancelled" in response.json()["detail"].lower()


@pytest.mark.unit
class TestReceiptEndpoints:
    """Test receipt-related endpoints"""
    
    def test_get_receipts_success(self, coordinator_client, sample_job_data, sample_tenant, signed_receipt):
        """Test successful receipt retrieval"""
        # Create a job
        create_response = coordinator_client.post(
            "/v1/jobs",
            json=sample_job_data,
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        job_id = create_response.json()["id"]
        
        # Mock receipt storage
        with patch('apps.coordinator_api.src.app.services.receipt_service.ReceiptService.get_job_receipts') as mock_get:
            mock_get.return_value = [signed_receipt]
            
            response = coordinator_client.get(
                f"/v1/jobs/{job_id}/receipts",
                headers={"X-Tenant-ID": sample_tenant.id}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) > 0
        assert "signature" in data["items"][0]
    
    def test_verify_receipt_success(self, coordinator_client, signed_receipt):
        """Test successful receipt verification"""
        with patch('apps.coordinator_api.src.app.services.receipt_service.verify_receipt') as mock_verify:
            mock_verify.return_value = {"valid": True}
            
            response = coordinator_client.post(
                "/v1/receipts/verify",
                json={"receipt": signed_receipt}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
    
    def test_verify_receipt_invalid(self, coordinator_client):
        """Test verification of invalid receipt"""
        invalid_receipt = {
            "job_id": "test",
            "signature": "invalid"
        }
        
        with patch('apps.coordinator_api.src.app.services.receipt_service.verify_receipt') as mock_verify:
            mock_verify.return_value = {"valid": False, "error": "Invalid signature"}
            
            response = coordinator_client.post(
                "/v1/receipts/verify",
                json={"receipt": invalid_receipt}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "error" in data


@pytest.mark.unit
class TestMinerEndpoints:
    """Test miner-related endpoints"""
    
    def test_register_miner_success(self, coordinator_client, sample_tenant):
        """Test successful miner registration"""
        miner_data = {
            "miner_id": "test-miner-123",
            "endpoint": "http://localhost:9000",
            "capabilities": ["ai_inference", "image_generation"],
            "resources": {
                "gpu_memory": "16GB",
                "cpu_cores": 8,
            }
        }
        
        response = coordinator_client.post(
            "/v1/miners/register",
            json=miner_data,
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["miner_id"] == miner_data["miner_id"]
        assert data["status"] == "active"
    
    def test_miner_heartbeat_success(self, coordinator_client, sample_tenant):
        """Test successful miner heartbeat"""
        heartbeat_data = {
            "miner_id": "test-miner-123",
            "status": "active",
            "current_jobs": 2,
            "resources_used": {
                "gpu_memory": "8GB",
                "cpu_cores": 4,
            }
        }
        
        with patch('apps.coordinator_api.src.app.services.miner_service.MinerService.update_heartbeat') as mock_heartbeat:
            mock_heartbeat.return_value = {"updated": True}
            
            response = coordinator_client.post(
                "/v1/miners/heartbeat",
                json=heartbeat_data,
                headers={"X-Tenant-ID": sample_tenant.id}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["updated"] is True
    
    def test_fetch_jobs_success(self, coordinator_client, sample_tenant):
        """Test successful job fetching by miner"""
        with patch('apps.coordinator_api.src.app.services.job_service.JobService.get_available_jobs') as mock_fetch:
            mock_fetch.return_value = [
                {
                    "id": "job-123",
                    "job_type": "ai_inference",
                    "requirements": {"gpu_memory": "8GB"}
                }
            ]
            
            response = coordinator_client.get(
                "/v1/miners/jobs",
                headers={"X-Tenant-ID": sample_tenant.id}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0


@pytest.mark.unit
class TestMarketplaceEndpoints:
    """Test marketplace-related endpoints"""
    
    def test_create_offer_success(self, coordinator_client, sample_tenant):
        """Test successful offer creation"""
        offer_data = {
            "service_type": "ai_inference",
            "pricing": {
                "per_hour": 0.50,
                "per_token": 0.0001,
            },
            "capacity": 100,
            "requirements": {
                "gpu_memory": "16GB",
            }
        }
        
        response = coordinator_client.post(
            "/v1/marketplace/offers",
            json=offer_data,
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["id"] is not None
        assert data["service_type"] == offer_data["service_type"]
    
    def test_list_offers_success(self, coordinator_client, sample_tenant):
        """Test successful offer listing"""
        response = coordinator_client.get(
            "/v1/marketplace/offers",
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)
    
    def test_create_bid_success(self, coordinator_client, sample_tenant):
        """Test successful bid creation"""
        bid_data = {
            "offer_id": "offer-123",
            "quantity": 10,
            "max_price": 1.00,
        }
        
        response = coordinator_client.post(
            "/v1/marketplace/bids",
            json=bid_data,
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["id"] is not None
        assert data["offer_id"] == bid_data["offer_id"]


@pytest.mark.unit
class TestMultiTenancy:
    """Test multi-tenancy features"""
    
    def test_tenant_isolation(self, coordinator_client, sample_job_data, sample_tenant):
        """Test that tenants cannot access each other's data"""
        # Create job for tenant A
        response_a = coordinator_client.post(
            "/v1/jobs",
            json=sample_job_data,
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        job_id_a = response_a.json()["id"]
        
        # Try to access with different tenant ID
        response = coordinator_client.get(
            f"/v1/jobs/{job_id_a}",
            headers={"X-Tenant-ID": "different-tenant"}
        )
        
        assert response.status_code == 404
    
    def test_quota_enforcement(self, coordinator_client, sample_job_data, sample_tenant, sample_tenant_quota):
        """Test that quota limits are enforced"""
        # Mock quota service
        with patch('apps.coordinator_api.src.app.services.quota_service.QuotaService.check_quota') as mock_check:
            mock_check.return_value = False
            
            response = coordinator_client.post(
                "/v1/jobs",
                json=sample_job_data,
                headers={"X-Tenant-ID": sample_tenant.id}
            )
        
        assert response.status_code == 429
        assert "quota" in response.json()["detail"].lower()
    
    def test_tenant_metrics(self, coordinator_client, sample_tenant):
        """Test tenant-specific metrics"""
        response = coordinator_client.get(
            "/v1/metrics",
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "tenant_id" in data
        assert data["tenant_id"] == sample_tenant.id


@pytest.mark.unit
class TestErrorHandling:
    """Test error handling and edge cases"""
    
    def test_validation_errors(self, coordinator_client):
        """Test validation error responses"""
        # Send invalid JSON
        response = coordinator_client.post(
            "/v1/jobs",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 422
        assert "detail" in response.json()
    
    def test_rate_limiting(self, coordinator_client, sample_tenant):
        """Test rate limiting"""
        with patch('apps.coordinator_api.src.app.middleware.rate_limit.check_rate_limit') as mock_check:
            mock_check.return_value = False
            
            response = coordinator_client.get(
                "/v1/jobs",
                headers={"X-Tenant-ID": sample_tenant.id}
            )
        
        assert response.status_code == 429
        assert "rate limit" in response.json()["detail"].lower()
    
    def test_internal_server_error(self, coordinator_client, sample_tenant):
        """Test internal server error handling"""
        with patch('apps.coordinator_api.src.app.services.job_service.JobService.create_job') as mock_create:
            mock_create.side_effect = Exception("Database error")
            
            response = coordinator_client.post(
                "/v1/jobs",
                json={"job_type": "test"},
                headers={"X-Tenant-ID": sample_tenant.id}
            )
        
        assert response.status_code == 500
        assert "internal server error" in response.json()["detail"].lower()


@pytest.mark.unit
class TestWebhooks:
    """Test webhook functionality"""
    
    def test_webhook_signature_verification(self, coordinator_client):
        """Test webhook signature verification"""
        webhook_data = {
            "event": "job.completed",
            "job_id": "test-123",
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        # Mock signature verification
        with patch('apps.coordinator_api.src.app.webhooks.verify_webhook_signature') as mock_verify:
            mock_verify.return_value = True
            
            response = coordinator_client.post(
                "/v1/webhooks/job-status",
                json=webhook_data,
                headers={"X-Webhook-Signature": "test-signature"}
            )
        
        assert response.status_code == 200
    
    def test_webhook_invalid_signature(self, coordinator_client):
        """Test webhook with invalid signature"""
        webhook_data = {"event": "test"}
        
        with patch('apps.coordinator_api.src.app.webhooks.verify_webhook_signature') as mock_verify:
            mock_verify.return_value = False
            
            response = coordinator_client.post(
                "/v1/webhooks/job-status",
                json=webhook_data,
                headers={"X-Webhook-Signature": "invalid"}
            )
        
        assert response.status_code == 401


@pytest.mark.unit
class TestHealthAndMetrics:
    """Test health check and metrics endpoints"""
    
    def test_health_check(self, coordinator_client):
        """Test health check endpoint"""
        response = coordinator_client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
    
    def test_metrics_endpoint(self, coordinator_client):
        """Test Prometheus metrics endpoint"""
        response = coordinator_client.get("/metrics")
        
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
    
    def test_readiness_check(self, coordinator_client):
        """Test readiness check endpoint"""
        response = coordinator_client.get("/ready")
        
        assert response.status_code == 200
        data = response.json()
        assert "ready" in data
