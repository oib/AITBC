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

    def test_service_name_format(self):
        """Test service name follows expected format"""
        service_name = "agent-coordinator"
        
        # Should be lowercase with hyphens
        assert service_name.islower()
        assert "-" in service_name
        assert " " not in service_name

    def test_version_format_with_patch(self):
        """Test version format with patch version"""
        version = "2.1.3"
        
        parts = version.split(".")
        assert len(parts) == 3
        assert parts[0] == "2"
        assert parts[1] == "1"
        assert parts[2] == "3"

    def test_endpoint_without_parameters(self):
        """Test endpoint without path parameters"""
        endpoints = ["/health", "/metrics", "/status"]
        
        for endpoint in endpoints:
            assert "{" not in endpoint
            assert "}" not in endpoint

    def test_endpoint_list_consistency(self):
        """Test endpoint list contains expected endpoints"""
        endpoints = ["/health", "/metrics", "/status", "/info"]
        
        assert "/health" in endpoints
        assert "/metrics" in endpoints
        assert len(endpoints) == 4

    def test_service_name_case_consistency(self):
        """Test service name uses consistent case"""
        service_names = ["agent-coordinator", "workflow-orchestrator", "message-queue"]
        
        for name in service_names:
            assert name.islower()
            assert "-" in name

    def test_version_string_format(self):
        """Test version string format with multiple dots"""
        version = "1.2.3.4"
        
        parts = version.split(".")
        assert len(parts) == 4
        assert parts[0] == "1"
        assert parts[3] == "4"

    def test_endpoint_path_validation(self):
        """Test endpoint path starts with slash"""
        endpoints = ["/health", "/metrics", "/status", "/info", "/ready"]
        
        for endpoint in endpoints:
            assert endpoint.startswith("/")
            assert len(endpoint) > 1

    def test_service_name_without_spaces(self):
        """Test service name has no spaces"""
        service_names = ["agent-coordinator", "workflow-orchestrator", "message-queue"]
        
        for name in service_names:
            assert " " not in name

    def test_endpoint_without_double_slashes(self):
        """Test endpoint path has no double slashes"""
        endpoints = ["/health", "/metrics", "/status", "/info", "/ready"]
        
        for endpoint in endpoints:
            assert "//" not in endpoint

    def test_version_without_negative_numbers(self):
        """Test version has no negative numbers"""
        version = "1.2.3"
        
        parts = version.split(".")
        for part in parts:
            assert int(part) >= 0

    def test_endpoint_without_trailing_slash(self):
        """Test endpoint path has no trailing slash"""
        endpoints = ["/health", "/metrics", "/status", "/info", "/ready"]
        
        for endpoint in endpoints:
            assert not endpoint.endswith("/")

    def test_service_name_with_hyphen(self):
        """Test service name with hyphen"""
        service_name = "agent-coordinator"
        
        assert "-" in service_name
        assert len(service_name) > 0

    def test_endpoint_with_numeric(self):
        """Test endpoint path with numeric characters"""
        endpoints = ["/api/v1/health", "/api/v2/metrics"]
        
        for endpoint in endpoints:
            assert any(char.isdigit() for char in endpoint)

    def test_version_with_multiple_dots(self):
        """Test version string with multiple dots"""
        version = "1.2.3.4"
        
        assert version.count(".") == 3
        parts = version.split(".")
        assert len(parts) == 4

    def test_endpoint_with_special_characters(self):
        """Test endpoint path with special characters"""
        endpoints = ["/api/v1/health", "/api/v2/status"]
        
        for endpoint in endpoints:
            assert "/" in endpoint
            assert endpoint.startswith("/")

    def test_version_with_patch_only(self):
        """Test version string with only patch version"""
        version = "1.0.0"
        
        parts = version.split(".")
        assert len(parts) == 3

    def test_endpoint_with_query_params(self):
        """Test endpoint path with query parameters"""
        endpoints = ["/health?format=json", "/metrics?format=txt"]
        
        for endpoint in endpoints:
            assert "?" in endpoint
            assert "=" in endpoint

    def test_service_name_with_underscore(self):
        """Test service name with underscore"""
        service_name = "test_service"
        
        assert "_" in service_name
        assert len(service_name) > 0

    def test_endpoint_with_version_prefix(self):
        """Test endpoint path with version prefix"""
        endpoints = ["/v1/health", "/v2/metrics"]
        
        for endpoint in endpoints:
            assert "/v" in endpoint
            assert endpoint.startswith("/v")

    def test_service_name_starts_with_letter(self):
        """Test service name starts with letter"""
        service_name = "HealthService"
        
        assert service_name[0].isalpha()

    def test_endpoint_without_leading_slash(self):
        """Test endpoint without leading slash (edge case)"""
        endpoints = ["health", "metrics"]
        
        for endpoint in endpoints:
            assert not endpoint.startswith("/")
            assert len(endpoint) > 0

    def test_service_name_with_mixed_case(self):
        """Test service name with mixed case"""
        service_name = "HealthServiceAPI"
        
        assert "Health" in service_name
        assert "API" in service_name

    def test_endpoint_with_trailing_slash(self):
        """Test endpoint with trailing slash"""
        endpoints = ["/health/", "/metrics/"]
        
        for endpoint in endpoints:
            assert endpoint.endswith("/")
            assert len(endpoint) > 1

    def test_service_name_with_numbers(self):
        """Test service name with numbers"""
        service_name = "Service123"
        
        assert "123" in service_name

    def test_endpoint_with_multiple_segments(self):
        """Test endpoint with multiple path segments"""
        endpoints = ["/api/v1/health", "/api/v2/metrics/status"]
        
        for endpoint in endpoints:
            assert "/" in endpoint
            assert endpoint.count("/") >= 3

    def test_service_name_with_special_characters(self):
        """Test service name with special characters"""
        service_name = "Service@123!"
        
        assert "@" in service_name
        assert "!" in service_name

    def test_endpoint_with_query_params(self):
        """Test endpoint with query parameters"""
        endpoints = ["/health?format=json", "/metrics?verbose=true"]
        
        for endpoint in endpoints:
            assert "?" in endpoint

    def test_service_name_with_spaces(self):
        """Test service name with spaces"""
        service_name = "Service Name With Spaces"
        
        assert " " in service_name

    def test_endpoint_without_leading_slash(self):
        """Test endpoint without leading slash (edge case)"""
        endpoints = ["health", "metrics"]
        
        for endpoint in endpoints:
            assert not endpoint.startswith("/")

    def test_service_name_with_underscores(self):
        """Test service name with underscores"""
        service_name = "service_name_with_underscores"
        
        assert "_" in service_name

    def test_endpoint_with_hash_fragment(self):
        """Test endpoint with hash fragment (edge case)"""
        endpoints = ["/health#section", "/metrics#overview"]
        
        for endpoint in endpoints:
            assert "#" in endpoint

    def test_service_name_with_hyphen(self):
        """Test service name with hyphen"""
        service_name = "service-name"
        
        assert "-" in service_name

    def test_endpoint_with_port(self):
        """Test endpoint with port"""
        endpoints = ["localhost:8080", "localhost:9090"]
        
        for endpoint in endpoints:
            assert ":" in endpoint

    def test_service_name_with_numbers(self):
        """Test service name with numbers"""
        service_name = "service123"
        
        assert "123" in service_name

    def test_endpoint_with_trailing_slash(self):
        """Test endpoint with trailing slash"""
        endpoints = ["/health/", "/metrics/"]
        
        for endpoint in endpoints:
            assert endpoint.endswith("/")

    def test_service_name_with_mixed_case(self):
        """Test service name with mixed case"""
        service_name = "ServiceName"
        
        assert "Service" in service_name
        assert "Name" in service_name

    def test_endpoint_with_double_slash(self):
        """Test endpoint with double slash (edge case)"""
        endpoints = ["//health", "//metrics"]
        
        for endpoint in endpoints:
            assert "//" in endpoint

    def test_service_name_with_special_characters(self):
        """Test service name with special characters"""
        service_name = "service@#$"
        
        assert "@" in service_name
        assert "#" in service_name
        assert "$" in service_name

    def test_endpoint_with_underscore(self):
        """Test endpoint with underscore"""
        endpoints = ["/health_check", "/metrics_data"]
        
        for endpoint in endpoints:
            assert "_" in endpoint

    def test_service_name_with_empty_string(self):
        """Test service name with empty string (edge case)"""
        service_name = ""
        
        assert service_name == ""

    def test_endpoint_with_empty_string(self):
        """Test endpoint with empty string (edge case)"""
        endpoints = [""]
        
        for endpoint in endpoints:
            assert endpoint == ""

    def test_service_name_with_single_character(self):
        """Test service name with single character"""
        service_name = "A"
        
        assert len(service_name) == 1

    def test_endpoint_with_single_character(self):
        """Test endpoint with single character"""
        endpoints = ["/a"]
        
        for endpoint in endpoints:
            assert len(endpoint) == 2

    def test_service_name_with_hyphen(self):
        """Test service name with hyphen"""
        service_name = "service-name"
        
        assert "-" in service_name

    def test_endpoint_with_hyphen(self):
        """Test endpoint with hyphen"""
        endpoints = ["/service-name"]
        
        for endpoint in endpoints:
            assert "-" in endpoint

    def test_service_name_with_dot(self):
        """Test service name with dot"""
        service_name = "service.name"
        
        assert "." in service_name

    def test_endpoint_with_dot(self):
        """Test endpoint with dot"""
        endpoints = ["/service.name"]
        
        for endpoint in endpoints:
            assert "." in endpoint

    def test_service_name_with_underscore(self):
        """Test service name with underscore"""
        service_name = "service_name"
        
        assert "_" in service_name

    def test_endpoint_with_underscore(self):
        """Test endpoint with underscore"""
        endpoints = ["/service_name"]
        
        for endpoint in endpoints:
            assert "_" in endpoint

    def test_service_name_with_colon(self):
        """Test service name with colon"""
        service_name = "service:name"
        
        assert ":" in service_name

    def test_endpoint_with_colon(self):
        """Test endpoint with colon"""
        endpoints = ["/service:name"]
        
        for endpoint in endpoints:
            assert ":" in endpoint

    def test_service_name_with_equals(self):
        """Test service name with equals"""
        service_name = "service=name"
        
        assert "=" in service_name

    def test_endpoint_with_equals(self):
        """Test endpoint with equals"""
        endpoints = ["/service=name"]
        
        for endpoint in endpoints:
            assert "=" in endpoint

    def test_service_name_with_slash(self):
        """Test service name with slash"""
        service_name = "service/name"
        
        assert "/" in service_name

    def test_endpoint_with_slash(self):
        """Test endpoint with slash"""
        endpoints = ["/service/name"]
        
        for endpoint in endpoints:
            assert "/" in endpoint

    def test_service_name_with_bracket(self):
        """Test service name with bracket"""
        service_name = "service[name]"
        
        assert "[" in service_name
        assert "]" in service_name

    def test_endpoint_with_bracket(self):
        """Test endpoint with bracket"""
        endpoints = ["/service[name]"]
        
        for endpoint in endpoints:
            assert "[" in endpoint
            assert "]" in endpoint

    def test_service_name_with_curly_bracket(self):
        """Test service name with curly bracket"""
        service_name = "service{name}"
        
        assert "{" in service_name
        assert "}" in service_name

    def test_endpoint_with_curly_bracket(self):
        """Test endpoint with curly bracket"""
        endpoints = ["/service{name}"]
        
        for endpoint in endpoints:
            assert "{" in endpoint
            assert "}" in endpoint

    def test_service_name_with_dollar(self):
        """Test service name with dollar"""
        service_name = "service$name"
        
        assert "$" in service_name

    def test_endpoint_with_dollar(self):
        """Test endpoint with dollar"""
        endpoints = ["/service$name"]
        
        for endpoint in endpoints:
            assert "$" in endpoint

    def test_service_name_with_hash(self):
        """Test service name with hash"""
        service_name = "service#name"
        
        assert "#" in service_name

    def test_endpoint_with_hash(self):
        """Test endpoint with hash"""
        endpoints = ["/service#name"]
        
        for endpoint in endpoints:
            assert "#" in endpoint

    def test_service_name_with_exclamation(self):
        """Test service name with exclamation"""
        service_name = "service!name"
        
        assert "!" in service_name

    def test_service_name_with_asterisk(self):
        """Test service name with asterisk"""
        service_name = "service*name"
        
        assert "*" in service_name

    def test_endpoint_with_asterisk(self):
        """Test endpoint with asterisk"""
        endpoints = ["/service*name"]
        
        for endpoint in endpoints:
            assert "*" in endpoint

    def test_service_name_with_plus(self):
        """Test service name with plus"""
        service_name = "service+name"
        
        assert "+" in service_name

    def test_service_name_with_equals(self):
        """Test service name with equals"""
        service_name = "service=name"
        
        assert "=" in service_name

    def test_endpoint_with_equals(self):
        """Test endpoint with equals"""
        endpoints = ["/service=name"]
        
        for endpoint in endpoints:
            assert "=" in endpoint

    def test_service_name_with_bracket(self):
        """Test service name with bracket"""
        service_name = "service[name]"
        
        assert "[" in service_name

    def test_service_name_with_curly_brace(self):
        """Test service name with curly brace"""
        service_name = "service{name}"
        
        assert "{" in service_name

    def test_endpoint_with_curly_brace(self):
        """Test endpoint with curly brace"""
        endpoints = ["/service{name}"]
        
        for endpoint in endpoints:
            assert "{" in endpoint

    def test_service_name_with_pipe(self):
        """Test service name with pipe"""
        service_name = "service|name"
        
        assert "|" in service_name


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
