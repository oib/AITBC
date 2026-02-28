"""
Test suite for AITBC Coordinator API core services
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, SQLModel
from sqlmodel.pool import StaticPool

from app.main import create_app
from app.config import Settings
from app.domain import Job, Miner, JobState
from app.schemas import JobCreate, MinerRegister
from app.services import JobService, MinerService


@pytest.fixture
def test_db():
    """Create a test database"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def test_session(test_db):
    """Create a test database session"""
    with Session(test_db) as session:
        yield session


@pytest.fixture
def test_app(test_session):
    """Create a test FastAPI app with test database"""
    app = create_app()
    
    # Override database session dependency
    def get_test_session():
        return test_session
    
    app.dependency_overrides[SessionDep] = get_test_session
    return app


@pytest.fixture
def client(test_app):
    """Create a test client"""
    return TestClient(test_app)


@pytest.fixture
def test_settings():
    """Create test settings"""
    return Settings(
        app_env="test",
        client_api_keys=["test-key"],
        miner_api_keys=["test-miner-key"],
        admin_api_keys=["test-admin-key"],
        hmac_secret="test-hmac-secret-32-chars-long",
        jwt_secret="test-jwt-secret-32-chars-long"
    )


class TestJobService:
    """Test suite for JobService"""
    
    def test_create_job(self, test_session):
        """Test job creation"""
        service = JobService(test_session)
        job = service.create_job(
            client_id="test-client",
            req=JobCreate(payload={"task": "test"})
        )
        
        assert job.id is not None
        assert job.client_id == "test-client"
        assert job.payload == {"task": "test"}
        assert job.state == JobState.queued
    
    def test_get_job(self, test_session):
        """Test job retrieval"""
        service = JobService(test_session)
        job = service.create_job(
            client_id="test-client",
            req=JobCreate(payload={"task": "test"})
        )
        
        fetched = service.get_job(job.id, client_id="test-client")
        assert fetched.id == job.id
        assert fetched.payload == {"task": "test"}
    
    def test_get_job_not_found(self, test_session):
        """Test job not found error"""
        service = JobService(test_session)
        
        with pytest.raises(KeyError, match="job not found"):
            service.get_job("nonexistent-id")
    
    def test_acquire_next_job(self, test_session):
        """Test job acquisition by miner"""
        service = JobService(test_session)
        
        # Create a job
        job = service.create_job(
            client_id="test-client",
            req=JobCreate(payload={"task": "test"})
        )
        
        # Create a miner
        miner = Miner(
            id="test-miner",
            capabilities={},
            concurrency=1,
            region="us-east-1"
        )
        test_session.add(miner)
        test_session.commit()
        
        # Acquire the job
        acquired_job = service.acquire_next_job(miner)
        
        assert acquired_job is not None
        assert acquired_job.id == job.id
        assert acquired_job.state == JobState.running
        assert acquired_job.assigned_miner_id == "test-miner"
    
    def test_acquire_next_job_empty(self, test_session):
        """Test job acquisition when no jobs available"""
        service = JobService(test_session)
        
        miner = Miner(
            id="test-miner",
            capabilities={},
            concurrency=1,
            region="us-east-1"
        )
        test_session.add(miner)
        test_session.commit()
        
        acquired_job = service.acquire_next_job(miner)
        assert acquired_job is None


class TestMinerService:
    """Test suite for MinerService"""
    
    def test_register_miner(self, test_session):
        """Test miner registration"""
        service = MinerService(test_session)
        
        miner = service.register(
            miner_id="test-miner",
            req=MinerRegister(
                capabilities={"gpu": "rtx3080"},
                concurrency=2,
                region="us-east-1"
            )
        )
        
        assert miner.id == "test-miner"
        assert miner.capabilities == {"gpu": "rtx3080"}
        assert miner.concurrency == 2
        assert miner.region == "us-east-1"
        assert miner.session_token is not None
    
    def test_heartbeat(self, test_session):
        """Test miner heartbeat"""
        service = MinerService(test_session)
        
        # Register miner first
        miner = service.register(
            miner_id="test-miner",
            req=MinerRegister(
                capabilities={"gpu": "rtx3080"},
                concurrency=2,
                region="us-east-1"
            )
        )
        
        # Send heartbeat
        service.heartbeat("test-miner", Mock())
        
        # Verify miner is still accessible
        retrieved = service.get_record("test-miner")
        assert retrieved.id == "test-miner"


class TestAPIEndpoints:
    """Test suite for API endpoints"""
    
    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    
    def test_liveness_probe(self, client):
        """Test liveness probe endpoint"""
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"
    
    def test_readiness_probe(self, client):
        """Test readiness probe endpoint"""
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"
    
    def test_submit_job(self, client):
        """Test job submission endpoint"""
        response = client.post(
            "/v1/jobs",
            json={"payload": {"task": "test"}},
            headers={"X-API-Key": "test-key"}
        )
        assert response.status_code == 201
        assert "job_id" in response.json()
    
    def test_submit_job_invalid_api_key(self, client):
        """Test job submission with invalid API key"""
        response = client.post(
            "/v1/jobs",
            json={"payload": {"task": "test"}},
            headers={"X-API-Key": "invalid-key"}
        )
        assert response.status_code == 401
    
    def test_get_job(self, client):
        """Test job retrieval endpoint"""
        # First submit a job
        submit_response = client.post(
            "/v1/jobs",
            json={"payload": {"task": "test"}},
            headers={"X-API-Key": "test-key"}
        )
        job_id = submit_response.json()["job_id"]
        
        # Then retrieve it
        response = client.get(
            f"/v1/jobs/{job_id}",
            headers={"X-API-Key": "test-key"}
        )
        assert response.status_code == 200
        assert response.json()["payload"] == {"task": "test"}


class TestErrorHandling:
    """Test suite for error handling"""
    
    def test_validation_error_handling(self, client):
        """Test validation error handling"""
        response = client.post(
            "/v1/jobs",
            json={"invalid_field": "test"},
            headers={"X-API-Key": "test-key"}
        )
        assert response.status_code == 422
        assert "VALIDATION_ERROR" in response.json()["error"]["code"]
    
    def test_not_found_error_handling(self, client):
        """Test 404 error handling"""
        response = client.get(
            "/v1/jobs/nonexistent",
            headers={"X-API-Key": "test-key"}
        )
        assert response.status_code == 404
    
    def test_rate_limiting(self, client):
        """Test rate limiting (basic test)"""
        # This test would need to be enhanced to actually test rate limiting
        # For now, just verify the endpoint exists
        for i in range(5):
            response = client.post(
                "/v1/jobs",
                json={"payload": {"task": f"test-{i}"}},
                headers={"X-API-Key": "test-key"}
            )
            assert response.status_code in [201, 429]  # 429 if rate limited


class TestConfiguration:
    """Test suite for configuration validation"""
    
    def test_production_config_validation(self):
        """Test production configuration validation"""
        with pytest.raises(ValueError, match="API keys cannot be empty"):
            Settings(
                app_env="production",
                client_api_keys=[],
                hmac_secret="test-secret-32-chars-long",
                jwt_secret="test-secret-32-chars-long"
            )
    
    def test_short_secret_validation(self):
        """Test secret length validation"""
        with pytest.raises(ValueError, match="must be at least 32 characters"):
            Settings(
                app_env="production",
                client_api_keys=["test-key-long-enough"],
                hmac_secret="short",
                jwt_secret="test-secret-32-chars-long"
            )
    
    def test_placeholder_secret_validation(self):
        """Test placeholder secret validation"""
        with pytest.raises(ValueError, match="must be set to a secure value"):
            Settings(
                app_env="production",
                client_api_keys=["test-key-long-enough"],
                hmac_secret="${HMAC_SECRET}",
                jwt_secret="test-secret-32-chars-long"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
