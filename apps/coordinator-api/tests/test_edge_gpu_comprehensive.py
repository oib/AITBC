import os
from typing import Generator
import pytest
import asyncio
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

os.environ["DATABASE_URL"] = "sqlite:///./data/test_edge_gpu.db"
os.makedirs("data", exist_ok=True)

from app.main import app  # noqa: E402
from app.storage import db  # noqa: E402
from app.storage.db import get_session  # noqa: E402
from app.services.edge_gpu_service import EdgeGPUService
from app.domain.gpu_marketplace import (
    GPURegistry,
    GPUArchitecture,
    ConsumerGPUProfile,
    EdgeGPUMetrics,
)  # noqa: E402


TEST_DB_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/test_edge_gpu.db")
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
SQLModel.metadata.create_all(engine)


def override_get_session() -> Generator[Session, None, None]:
    db._engine = engine  # ensure storage uses this engine
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_session] = override_get_session
# Create client after overrides and table creation
client = TestClient(app)


class TestEdgeGPUAPI:
    """Test edge GPU API endpoints"""

    def test_profiles_seed_and_filter(self):
        """Test GPU profile seeding and filtering"""
        resp = client.get("/v1/marketplace/edge-gpu/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 3

        resp_filter = client.get(
            "/v1/marketplace/edge-gpu/profiles",
            params={"architecture": GPUArchitecture.ADA_LOVELACE.value},
        )
        assert resp_filter.status_code == 200
        filtered = resp_filter.json()
        assert all(item["architecture"] == GPUArchitecture.ADA_LOVELACE.value for item in filtered)

    def test_metrics_ingest_and_list(self):
        """Test GPU metrics ingestion and listing"""
        # create gpu registry entry
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            existing = session.get(GPURegistry, "gpu_test")
            if existing:
                session.delete(existing)
                session.commit()

            gpu = GPURegistry(
                id="gpu_test",
                miner_id="miner-1",
                model="RTX 4090",
                memory_gb=24,
                cuda_version="12.0",
                region="us-east",
                price_per_hour=1.5,
                capabilities=["tensor", "cuda"],
            )
            session.add(gpu)
            session.commit()

        payload = {
            "gpu_id": "gpu_test",
            "network_latency_ms": 10.5,
            "compute_latency_ms": 20.1,
            "total_latency_ms": 30.6,
            "gpu_utilization_percent": 75.0,
            "memory_utilization_percent": 65.0,
            "power_draw_w": 200.0,
            "temperature_celsius": 68.0,
            "thermal_throttling_active": False,
            "power_limit_active": False,
            "clock_throttling_active": False,
            "region": "us-east",
            "city": "nyc",
            "isp": "test-isp",
            "connection_type": "ethernet",
        }

        resp = client.post("/v1/marketplace/edge-gpu/metrics", json=payload)
        assert resp.status_code == 200, resp.text
        created = resp.json()
        assert created["gpu_id"] == "gpu_test"

        list_resp = client.get(f"/v1/marketplace/edge-gpu/metrics/{payload['gpu_id']}")
        assert list_resp.status_code == 200
        metrics = list_resp.json()
        assert len(metrics) >= 1
        assert metrics[0]["gpu_id"] == "gpu_test"


class TestEdgeGPUIntegration:
    """Integration tests for edge GPU features"""

    @pytest.fixture
    def edge_service(self, db_session):
        return EdgeGPUService(db_session)

    @pytest.mark.asyncio
    async def test_consumer_gpu_discovery(self, edge_service):
        """Test consumer GPU discovery and classification"""
        # Test listing profiles (simulates discovery)
        profiles = edge_service.list_profiles()
        
        assert len(profiles) > 0
        assert all(hasattr(p, 'gpu_model') for p in profiles)
        assert all(hasattr(p, 'architecture') for p in profiles)

    @pytest.mark.asyncio
    async def test_edge_latency_measurement(self, edge_service):
        """Test edge latency measurement for geographic optimization"""
        # Test creating metrics (simulates latency measurement)
        metric_payload = {
            "gpu_id": "test_gpu_123",
            "network_latency_ms": 50.0,
            "compute_latency_ms": 10.0,
            "total_latency_ms": 60.0,
            "gpu_utilization_percent": 80.0,
            "memory_utilization_percent": 60.0,
            "power_draw_w": 200.0,
            "temperature_celsius": 65.0,
            "region": "us-east"
        }
        
        metric = edge_service.create_metric(metric_payload)
        
        assert metric.gpu_id == "test_gpu_123"
        assert metric.network_latency_ms == 50.0
        assert metric.region == "us-east"

    @pytest.mark.asyncio
    async def test_ollama_edge_optimization(self, edge_service):
        """Test Ollama model optimization for edge GPUs"""
        # Test filtering edge-optimized profiles
        edge_profiles = edge_service.list_profiles(edge_optimized=True)
        
        assert len(edge_profiles) > 0
        for profile in edge_profiles:
            assert profile.edge_optimized == True

    def test_consumer_gpu_profile_filtering(self, edge_service, db_session):
        """Test consumer GPU profile database filtering"""
        # Seed test data
        profiles = [
            ConsumerGPUProfile(
                gpu_model="RTX 3060",
                architecture="AMPERE",
                consumer_grade=True,
                edge_optimized=True,
                cuda_cores=3584,
                memory_gb=12
            ),
            ConsumerGPUProfile(
                gpu_model="RTX 4090",
                architecture="ADA_LOVELACE",
                consumer_grade=True,
                edge_optimized=False,
                cuda_cores=16384,
                memory_gb=24
            )
        ]

        db_session.add_all(profiles)
        db_session.commit()

        # Test filtering
        edge_profiles = edge_service.list_profiles(edge_optimized=True)
        assert len(edge_profiles) >= 1  # At least our test data
        assert any(p.gpu_model == "RTX 3060" for p in edge_profiles)

        ampere_profiles = edge_service.list_profiles(architecture="AMPERE")
        assert len(ampere_profiles) >= 1  # At least our test data
        assert any(p.gpu_model == "RTX 3060" for p in ampere_profiles)
