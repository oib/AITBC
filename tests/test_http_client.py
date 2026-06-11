"""
HTTP Client Tests
Tests for AITBC HTTP client utilities
"""

import pytest

from aitbc.network.http_client import AITBCHTTPClient


class TestAITBCHTTPClient:
    """Test AITBCHTTPClient class"""

    def test_http_client_class_exists(self):
        """Test AITBCHTTPClient class exists"""
        assert AITBCHTTPClient is not None

    def test_http_client_can_be_instantiated(self):
        """Test AITBCHTTPClient can be instantiated"""
        client = AITBCHTTPClient(base_url="http://localhost:8000")
        assert client is not None
        assert client.base_url == "http://localhost:8000"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
