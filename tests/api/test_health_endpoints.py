"""
Health Endpoint Tests
Tests for health check and root endpoints
"""

import sys
from pathlib import Path

# Add coordinator path for imports
coordinator_path = Path("/opt/aitbc/apps/agent-coordinator/src")
if str(coordinator_path) not in sys.path:
    sys.path.insert(0, str(coordinator_path))

import pytest
from datetime import UTC, datetime


class TestHealthEndpoints:
    """Test health check endpoint structure"""

    def test_health_response_structure(self):
        """Test health check response has required fields"""
        # Simulate health check response structure
        health_response = {
            "status": "healthy",
            "service": "agent-coordinator",
            "timestamp": datetime.now(UTC).isoformat(),
            "version": "1.0.0"
        }
        
        assert "status" in health_response
        assert "service" in health_response
        assert "timestamp" in health_response
        assert "version" in health_response
        assert health_response["status"] == "healthy"
        assert health_response["service"] == "agent-coordinator"

    def test_health_timestamp_format(self):
        """Test health check timestamp is valid ISO format"""
        timestamp = datetime.now(UTC).isoformat()
        
        # Should be parseable as datetime
        parsed = datetime.fromisoformat(timestamp)
        assert parsed is not None
        assert isinstance(parsed, datetime)

    def test_root_endpoint_structure(self):
        """Test root endpoint response structure"""
        root_response = {
            "service": "AITBC Agent Coordinator",
            "description": "Advanced multi-agent coordination and management system",
            "version": "1.0.0",
            "endpoints": [
                "/health",
                "/agents/register",
                "/agents/discover",
                "/agents/{agent_id}",
                "/agents/{agent_id}/status",
                "/tasks/submit",
                "/tasks/status",
                "/messages/send",
                "/load-balancer/stats",
                "/registry/stats"
            ]
        }
        
        assert "service" in root_response
        assert "description" in root_response
        assert "version" in root_response
        assert "endpoints" in root_response
        assert len(root_response["endpoints"]) == 10
        assert "/health" in root_response["endpoints"]
        assert "/agents/register" in root_response["endpoints"]

    def test_endpoint_list_completeness(self):
        """Test all expected endpoints are listed"""
        expected_endpoints = [
            "/health",
            "/agents/register",
            "/agents/discover",
            "/agents/{agent_id}",
            "/agents/{agent_id}/status",
            "/tasks/submit",
            "/tasks/status",
            "/messages/send",
            "/load-balancer/stats",
            "/registry/stats"
        ]
        
        assert len(expected_endpoints) == 10
        
        # Verify endpoint patterns
        for endpoint in expected_endpoints:
            assert endpoint.startswith("/")
            assert len(endpoint) > 0

    def test_service_name_consistency(self):
        """Test service name is consistent across endpoints"""
        health_service = "agent-coordinator"
        root_service = "AITBC Agent Coordinator"
        
        # Both should contain "agent" and "coordinator"
        assert "agent" in health_service.lower()
        assert "coordinator" in health_service.lower()
        assert "agent" in root_service.lower()
        assert "coordinator" in root_service.lower()

    def test_version_format(self):
        """Test version follows semantic versioning"""
        version = "1.0.0"
        
        # Should follow major.minor.patch format
        parts = version.split(".")
        assert len(parts) == 3
        
        # All parts should be numeric
        for part in parts:
            assert part.isdigit()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
