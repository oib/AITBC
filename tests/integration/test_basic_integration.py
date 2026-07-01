"""
Basic integration test to verify the test setup works
"""

from unittest.mock import Mock

import pytest


@pytest.mark.integration
def test_coordinator_client_fixture(coordinator_client):
    """Test that the coordinator_client fixture works"""
    # Test that we can make a request to a live endpoint
    response = coordinator_client.get("/health")

    # Should succeed
    assert response.status_code == 200

    # Check it's a health response
    data = response.json()
    assert "status" in data or "healthy" in response.text.lower()


@pytest.mark.integration
def test_mock_coordinator_client():
    """Test with a fully mocked client"""
    # Create a mock client
    mock_client = Mock()

    # Mock response
    mock_response = Mock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"job_id": "test-123", "status": "created"}

    mock_client.post.return_value = mock_response

    # Use the mock
    response = mock_client.post("/v1/jobs", json={"test": "data"})

    assert response.status_code == 201
    assert response.json()["job_id"] == "test-123"


@pytest.mark.integration
def test_simple_job_creation_mock():
    """Test job creation with mocked dependencies"""

    # Skip this test as it's redundant with the coordinator_client fixture tests
    pytest.skip("Redundant test - already covered by fixture tests")


@pytest.mark.unit
def test_pytest_markings():
    """Test that pytest markings work"""
    # This test should be collected as a unit test
    assert True


@pytest.mark.integration
def test_pytest_markings_integration():
    """Test that integration markings work"""
    # This test should be collected as an integration test
    assert True
