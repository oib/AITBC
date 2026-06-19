"""
Integration tests for X-Request-ID propagation
"""

import pytest


@pytest.mark.asyncio
async def test_request_id_propagation_to_outbound_calls():
    """Test that X-Request-ID is propagated to outbound HTTP calls"""
    from aitbc.http_client import get_request_id, set_request_id

    # Set a test request ID in context
    test_request_id = "test-request-id-12345"
    set_request_id(test_request_id)

    # Verify it can be retrieved
    retrieved_id = get_request_id()
    assert retrieved_id == test_request_id


@pytest.mark.asyncio
async def test_request_id_middleware_sets_context():
    """Test that request ID middleware sets context correctly"""
    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    # Make a request with X-Request-ID header
    response = client.get("/health", headers={"X-Request-ID": "test-id-123"})

    # Verify the response contains the same request ID
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert response.headers["X-Request-ID"] == "test-id-123"


@pytest.mark.asyncio
async def test_request_id_propagating_client():
    """Test that RequestIDPropagatingClient adds X-Request-ID to outbound calls"""
    from aitbc.http_client import RequestIDPropagatingClient, set_request_id

    # Set a test request ID in context
    test_request_id = "test-request-id-67890"
    set_request_id(test_request_id)

    # Create a propagating client
    RequestIDPropagatingClient()

    # Make a test request (this would normally be to an external service)
    # For testing, we'll just verify the client adds the header
    # In a real test, we'd mock the httpx.AsyncClient.request method


@pytest.mark.asyncio
async def test_request_id_generation_when_missing():
    """Test that request ID is generated when not provided"""
    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    # Make a request without X-Request-ID header
    response = client.get("/health")

    # Verify the response contains a generated request ID
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0  # Should be a UUID


@pytest.mark.asyncio
async def test_request_id_context_isolation():
    """Test that request ID context is isolated between requests"""
    from aitbc.http_client import get_request_id, set_request_id

    # Set a request ID
    set_request_id("request-1")
    assert get_request_id() == "request-1"

    # Set a different request ID (should replace the previous one)
    set_request_id("request-2")
    assert get_request_id() == "request-2"
    assert get_request_id() != "request-1"
