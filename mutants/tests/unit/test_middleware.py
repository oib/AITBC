"""Unit tests for middleware module."""

import pytest
from app.middleware import register_middleware
from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestMiddleware:
    """Tests for middleware registration."""

    def test_register_middleware_adds_middleware(self):
        """Test that register_middleware registers middleware on app."""
        app = FastAPI()
        register_middleware(app)

        # Check that middleware was added
        assert len(app.user_middleware) == 2

    def test_security_headers_middleware(self):
        """Test security headers middleware adds headers."""
        app = FastAPI()
        register_middleware(app)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "hello"}

        with TestClient(app) as client:
            response = client.get("/test")
            assert response.status_code == 200
            # Check security headers are present
            assert "x-content-type-options" in response.headers
            assert "x-frame-options" in response.headers

    def test_metrics_middleware(self):
        """Test metrics middleware records request."""
        app = FastAPI()
        register_middleware(app)

        @app.get("/metrics-test")
        async def metrics_test():
            return {"data": "test"}

        with TestClient(app) as client:
            response = client.get("/metrics-test")
            assert response.status_code == 200
            assert response.json() == {"data": "test"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
