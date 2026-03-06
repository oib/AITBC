import pytest
import asyncio
from unittest.mock import patch, MagicMock
from app.services.edge_gpu_service import EdgeGPUService
from app.domain.gpu_marketplace import ConsumerGPUProfile

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
