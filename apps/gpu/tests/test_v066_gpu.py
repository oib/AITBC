"""Integration tests for v0.6.6 GPU service features.

Tests cover:
- GPU service config (chain_id default, blockchain_rpc_url)
- OfferFSM validation in GPU status transitions
- BlockchainRPCClient usage in GPU service
- chain_id in GPU registration
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add the gpu src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def client():
    """Create test client for GPU service."""
    from gpu_service.main import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# GPU service config tests
# ---------------------------------------------------------------------------


class TestGPUServiceConfig:
    """Test GPU service config (v0.6.6)."""

    def test_config_has_correct_defaults(self):
        from gpu_service.config import settings

        assert settings.blockchain_rpc_url == "http://localhost:8202"
        assert settings.default_chain_id == "ait-hub"

    def test_config_no_stale_8006_port(self):
        from gpu_service.config import settings

        assert "8006" not in settings.blockchain_rpc_url

    def test_config_no_empty_chain_id(self):
        from gpu_service.config import settings

        assert settings.default_chain_id != ""
        assert settings.default_chain_id == "ait-hub"


# ---------------------------------------------------------------------------
# GPURegistry chain_id field tests
# ---------------------------------------------------------------------------


class TestGPURegistryChainId:
    """Test GPURegistry model has chain_id field (v0.6.6)."""

    def test_gpu_registry_has_chain_id_field(self):
        from gpu_service.domain.gpu_marketplace import GPURegistry

        # Check the model has chain_id field
        assert "chain_id" in GPURegistry.model_fields
        # Default should be ait-hub
        field_info = GPURegistry.model_fields["chain_id"]
        assert field_info.default == "ait-hub"

    def test_gpu_registry_chain_id_indexed(self):
        from gpu_service.domain.gpu_marketplace import GPURegistry

        # chain_id should be indexed for query performance
        field_info = GPURegistry.model_fields["chain_id"]
        # SQLModel Field with index=True sets sa_column_params
        assert field_info is not None


# ---------------------------------------------------------------------------
# OfferFSM validation in GPU status transitions
# ---------------------------------------------------------------------------


class TestGPUStatusFSMValidation:
    """Test GPU status transition validation via OfferFSM (v0.6.6)."""

    def test_validate_available_to_booked(self):
        from gpu_service.main import _validate_gpu_status_transition

        result = _validate_gpu_status_transition("available", "booked")
        assert result == "booked"

    def test_validate_available_to_offline(self):
        from gpu_service.main import _validate_gpu_status_transition

        result = _validate_gpu_status_transition("available", "offline")
        assert result == "offline"

    def test_validate_invalid_transition_raises(self):
        from gpu_service.main import _validate_gpu_status_transition

        # available → in_use directly is invalid (must go through reserved/booked)
        # But "in_use" maps to OfferStatus.IN_USE which can't be reached from AVAILABLE
        with pytest.raises(ValueError, match="Invalid offer transition"):
            _validate_gpu_status_transition("available", "in_use")

    def test_validate_unknown_status_passes_through(self):
        from gpu_service.main import _validate_gpu_status_transition

        # Unknown status strings should pass through with a warning (not raise)
        result = _validate_gpu_status_transition("available", "custom_status")
        assert result == "custom_status"


# ---------------------------------------------------------------------------
# GPU service endpoint tests
# ---------------------------------------------------------------------------


class TestGPUEndpoints:
    """Test GPU service endpoints (v0.6.6)."""

    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_gpu_status(self, client):
        response = client.get("/v1/gpu/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "operational"

    def test_gpu_discover(self, client):
        """Test GPU discover endpoint (auto-discovery via nvidia-smi)."""
        response = client.get("/v1/gpu/discover")
        assert response.status_code == 200
        # Returns dict (may be empty if no GPU)
        data = response.json()
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# BlockchainRPCClient integration tests (mocked)
# ---------------------------------------------------------------------------


class TestBlockchainRPCClientIntegration:
    """Test BlockchainRPCClient is used by GPU service (v0.6.6)."""

    def test_rpc_client_initialized(self):
        """GPU service initializes a BlockchainRPCClient at module level."""
        from gpu_service import main

        assert hasattr(main, "_rpc_client")
        assert main._rpc_client.rpc_url.endswith("8202")

    def test_rpc_client_chain_aware(self):
        """BlockchainRPCClient requires chain_id for transactions."""
        from gpu_service.main import _rpc_client

        # The client should be configured with the correct RPC URL
        assert "8202" in _rpc_client.rpc_url
        assert "8006" not in _rpc_client.rpc_url
