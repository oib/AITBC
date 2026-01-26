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


@pytest.mark.unit
class TestJobExecution:
    """Test job execution lifecycle"""
    
    def test_job_execution_flow(self, coordinator_client, sample_job_data, sample_tenant):
        """Test complete job execution flow"""
        # Create job
        response = coordinator_client.post(
            "/v1/jobs",
            json=sample_job_data,
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        assert response.status_code == 201
        job_id = response.json()["id"]
        
        # Accept job
        response = coordinator_client.patch(
            f"/v1/jobs/{job_id}/accept",
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "running"
        
        # Complete job
        response = coordinator_client.patch(
            f"/v1/jobs/{job_id}/complete",
            json={"result": "Task completed successfully"},
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "completed"
    
    def test_job_retry_mechanism(self, coordinator_client, sample_job_data, sample_tenant):
        """Test job retry mechanism"""
        # Create job
        response = coordinator_client.post(
            "/v1/jobs",
            json={**sample_job_data, "max_retries": 3},
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        job_id = response.json()["id"]
        
        # Fail job
        response = coordinator_client.patch(
            f"/v1/jobs/{job_id}/fail",
            json={"error": "Temporary failure"},
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["retry_count"] == 1
        
        # Retry job
        response = coordinator_client.post(
            f"/v1/jobs/{job_id}/retry",
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "pending"
    
    def test_job_timeout_handling(self, coordinator_client, sample_job_data, sample_tenant):
        """Test job timeout handling"""
        with patch('apps.coordinator_api.src.app.services.job_service.JobService.check_timeout') as mock_timeout:
            mock_timeout.return_value = True
            
            response = coordinator_client.post(
                "/v1/jobs/timeout-check",
                headers={"X-Tenant-ID": sample_tenant.id}
            )
        
        assert response.status_code == 200
        assert "timed_out" in response.json()


@pytest.mark.unit
class TestConfidentialTransactions:
    """Test confidential transaction features"""
    
    def test_create_confidential_job(self, coordinator_client, sample_tenant):
        """Test creating a confidential job"""
        confidential_job = {
            "job_type": "confidential_inference",
            "parameters": {
                "encrypted_data": "encrypted_payload",
                "verification_key": "zk_proof_key"
            },
            "confidential": True
        }
        
        with patch('apps.coordinator_api.src.app.services.zk_proofs.generate_proof') as mock_proof:
            mock_proof.return_value = "proof_hash"
            
            response = coordinator_client.post(
                "/v1/jobs",
                json=confidential_job,
                headers={"X-Tenant-ID": sample_tenant.id}
            )
        
        assert response.status_code == 201
        data = response.json()
        assert data["confidential"] is True
        assert "proof_hash" in data
    
    def test_verify_confidential_result(self, coordinator_client, sample_tenant):
        """Test verification of confidential job results"""
        verification_data = {
            "job_id": "confidential-job-123",
            "result_hash": "result_hash",
            "zk_proof": "zk_proof_data"
        }
        
        with patch('apps.coordinator_api.src.app.services.zk_proofs.verify_proof') as mock_verify:
            mock_verify.return_value = {"valid": True}
            
            response = coordinator_client.post(
                "/v1/jobs/verify-result",
                json=verification_data,
                headers={"X-Tenant-ID": sample_tenant.id}
            )
        
        assert response.status_code == 200
        assert response.json()["valid"] is True


@pytest.mark.unit
class TestBatchOperations:
    """Test batch operations"""
    
    def test_batch_job_creation(self, coordinator_client, sample_tenant):
        """Test creating multiple jobs in batch"""
        batch_data = {
            "jobs": [
                {"job_type": "inference", "parameters": {"model": "gpt-4"}},
                {"job_type": "inference", "parameters": {"model": "claude-3"}},
                {"job_type": "image_gen", "parameters": {"prompt": "test image"}}
            ]
        }
        
        response = coordinator_client.post(
            "/v1/jobs/batch",
            json=batch_data,
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "job_ids" in data
        assert len(data["job_ids"]) == 3
    
    def test_batch_job_cancellation(self, coordinator_client, sample_job_data, sample_tenant):
        """Test cancelling multiple jobs"""
        # Create multiple jobs
        job_ids = []
        for i in range(3):
            response = coordinator_client.post(
                "/v1/jobs",
                json=sample_job_data,
                headers={"X-Tenant-ID": sample_tenant.id}
            )
            job_ids.append(response.json()["id"])
        
        # Cancel all jobs
        response = coordinator_client.post(
            "/v1/jobs/batch-cancel",
            json={"job_ids": job_ids},
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["cancelled_count"] == 3


@pytest.mark.unit
class TestRealTimeFeatures:
    """Test real-time features"""
    
    def test_websocket_connection(self, coordinator_client):
        """Test WebSocket connection for job updates"""
        with patch('fastapi.WebSocket') as mock_websocket:
            mock_websocket.accept.return_value = None
            
            # Test WebSocket endpoint
            response = coordinator_client.get("/ws/jobs")
            # WebSocket connections use different protocol, so we test the endpoint exists
            assert response.status_code in [200, 401, 426]  # 426 for upgrade required
    
    def test_job_status_updates(self, coordinator_client, sample_job_data, sample_tenant):
        """Test real-time job status updates"""
        # Create job
        response = coordinator_client.post(
            "/v1/jobs",
            json=sample_job_data,
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        job_id = response.json()["id"]
        
        # Subscribe to updates
        with patch('apps.coordinator_api.src.app.services.notification_service.NotificationService.subscribe') as mock_sub:
            mock_sub.return_value = "subscription_id"
            
            response = coordinator_client.post(
                f"/v1/jobs/{job_id}/subscribe",
                headers={"X-Tenant-ID": sample_tenant.id}
            )
        
        assert response.status_code == 200
        assert "subscription_id" in response.json()


@pytest.mark.unit
class TestAdvancedScheduling:
    """Test advanced job scheduling features"""
    
    def test_scheduled_job_creation(self, coordinator_client, sample_tenant):
        """Test creating scheduled jobs"""
        scheduled_job = {
            "job_type": "inference",
            "parameters": {"model": "gpt-4"},
            "schedule": {
                "type": "cron",
                "expression": "0 2 * * *",  # Daily at 2 AM
                "timezone": "UTC"
            }
        }
        
        response = coordinator_client.post(
            "/v1/jobs/scheduled",
            json=scheduled_job,
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "schedule_id" in data
        assert data["next_run"] is not None
    
    def test_priority_queue_handling(self, coordinator_client, sample_job_data, sample_tenant):
        """Test priority queue job handling"""
        # Create high priority job
        high_priority_job = {**sample_job_data, "priority": "urgent"}
        response = coordinator_client.post(
            "/v1/jobs",
            json=high_priority_job,
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 201
        job_id = response.json()["id"]
        
        # Check priority queue
        with patch('apps.coordinator_api.src.app.services.queue_service.QueueService.get_priority_queue') as mock_queue:
            mock_queue.return_value = [job_id]
            
            response = coordinator_client.get(
                "/v1/jobs/queue/priority",
                headers={"X-Tenant-ID": sample_tenant.id}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert job_id in data["jobs"]


@pytest.mark.unit
class TestResourceManagement:
    """Test resource management and allocation"""
    
    def test_resource_allocation(self, coordinator_client, sample_tenant):
        """Test resource allocation for jobs"""
        resource_request = {
            "job_type": "gpu_inference",
            "requirements": {
                "gpu_memory": "16GB",
                "cpu_cores": 8,
                "ram": "32GB",
                "storage": "100GB"
            }
        }
        
        with patch('apps.coordinator_api.src.app.services.resource_service.ResourceService.check_availability') as mock_check:
            mock_check.return_value = {"available": True, "estimated_wait": 0}
            
            response = coordinator_client.post(
                "/v1/resources/check",
                json=resource_request,
                headers={"X-Tenant-ID": sample_tenant.id}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["available"] is True
    
    def test_resource_monitoring(self, coordinator_client, sample_tenant):
        """Test resource usage monitoring"""
        response = coordinator_client.get(
            "/v1/resources/usage",
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "gpu_usage" in data
        assert "cpu_usage" in data
        assert "memory_usage" in data


@pytest.mark.unit
class TestAPIVersioning:
    """Test API versioning"""
    
    def test_v1_api_compatibility(self, coordinator_client, sample_tenant):
        """Test v1 API endpoints"""
        response = coordinator_client.get("/v1/version")
        
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "v1"
    
    def test_deprecated_endpoint_warning(self, coordinator_client, sample_tenant):
        """Test deprecated endpoint returns warning"""
        response = coordinator_client.get(
            "/v1/legacy/jobs",
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 200
        assert "X-Deprecated" in response.headers
    
    def test_api_version_negotiation(self, coordinator_client, sample_tenant):
        """Test API version negotiation"""
        response = coordinator_client.get(
            "/version",
            headers={"Accept-Version": "v1"}
        )
        
        assert response.status_code == 200
        assert "API-Version" in response.headers


@pytest.mark.unit
class TestSecurityFeatures:
    """Test security features"""
    
    def test_cors_headers(self, coordinator_client):
        """Test CORS headers are set correctly"""
        response = coordinator_client.options("/v1/jobs")
        
        assert "Access-Control-Allow-Origin" in response.headers
        assert "Access-Control-Allow-Methods" in response.headers
    
    def test_request_size_limit(self, coordinator_client, sample_tenant):
        """Test request size limits"""
        large_data = {"data": "x" * 10_000_000}  # 10MB
        
        response = coordinator_client.post(
            "/v1/jobs",
            json=large_data,
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 413
    
    def test_sql_injection_protection(self, coordinator_client, sample_tenant):
        """Test SQL injection protection"""
        malicious_input = "'; DROP TABLE jobs; --"
        
        response = coordinator_client.get(
            f"/v1/jobs/{malicious_input}",
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 404
        assert response.status_code != 500


@pytest.mark.unit
class TestPerformanceOptimizations:
    """Test performance optimizations"""
    
    def test_response_compression(self, coordinator_client):
        """Test response compression for large payloads"""
        response = coordinator_client.get(
            "/v1/jobs",
            headers={"Accept-Encoding": "gzip"}
        )
        
        assert response.status_code == 200
        assert "Content-Encoding" in response.headers
    
    def test_caching_headers(self, coordinator_client):
        """Test caching headers are set"""
        response = coordinator_client.get("/v1/marketplace/offers")
        
        assert "Cache-Control" in response.headers
        assert "ETag" in response.headers
    
    def test_pagination_performance(self, coordinator_client, sample_tenant):
        """Test pagination with large datasets"""
        response = coordinator_client.get(
            "/v1/jobs?page=1&size=100",
            headers={"X-Tenant-ID": sample_tenant.id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 100
        assert "next_page" in data or len(data["items"]) == 0
