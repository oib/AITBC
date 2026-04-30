"""Edge case and error handling tests for plugin analytics service"""

import pytest
import sys
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from datetime import datetime, UTC


from main import app, PluginUsage, PluginPerformance, PluginRating, PluginEvent, plugin_usage_data, plugin_performance_data, plugin_ratings, plugin_events


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test"""
    plugin_usage_data.clear()
    plugin_performance_data.clear()
    plugin_ratings.clear()
    plugin_events.clear()
    yield
    plugin_usage_data.clear()
    plugin_performance_data.clear()
    plugin_ratings.clear()
    plugin_events.clear()


@pytest.mark.unit
def test_plugin_usage_empty_plugin_id():
    """Test PluginUsage with empty plugin_id"""
    usage = PluginUsage(
        plugin_id="",
        user_id="user_123",
        action="install",
        timestamp=datetime.now(datetime.UTC)
    )
    assert usage.plugin_id == ""


@pytest.mark.unit
def test_plugin_performance_negative_values():
    """Test PluginPerformance with negative values"""
    perf = PluginPerformance(
        plugin_id="plugin_123",
        version="1.0.0",
        cpu_usage=-10.0,
        memory_usage=-5.0,
        response_time=-0.1,
        error_rate=-0.01,
        uptime=-50.0,
        timestamp=datetime.now(datetime.UTC)
    )
    assert perf.cpu_usage == -10.0
    assert perf.memory_usage == -5.0


@pytest.mark.unit
def test_plugin_rating_out_of_range():
    """Test PluginRating with out of range rating"""
    rating = PluginRating(
        plugin_id="plugin_123",
        user_id="user_123",
        rating=10,
        timestamp=datetime.now(datetime.UTC)
    )
    assert rating.rating == 10


@pytest.mark.unit
def test_plugin_rating_zero():
    """Test PluginRating with zero rating"""
    rating = PluginRating(
        plugin_id="plugin_123",
        user_id="user_123",
        rating=0,
        timestamp=datetime.now(datetime.UTC)
    )
    assert rating.rating == 0


@pytest.mark.integration
def test_get_plugin_usage_no_data():
    """Test getting plugin usage when no data exists"""
    client = TestClient(app)
    response = client.get("/api/v1/analytics/usage/nonexistent")
    assert response.status_code == 200
    data = response.json()
    assert data["total_records"] == 0


@pytest.mark.integration
def test_get_plugin_performance_no_data():
    """Test getting plugin performance when no data exists"""
    client = TestClient(app)
    response = client.get("/api/v1/analytics/performance/nonexistent")
    assert response.status_code == 200
    data = response.json()
    assert data["total_records"] == 0


@pytest.mark.integration
def test_get_plugin_ratings_no_data():
    """Test getting plugin ratings when no data exists"""
    client = TestClient(app)
    response = client.get("/api/v1/analytics/ratings/nonexistent")
    assert response.status_code == 200
    data = response.json()
    assert data["total_ratings"] == 0


@pytest.mark.integration
def test_dashboard_with_no_data():
    """Test dashboard with no data"""
    client = TestClient(app)
    response = client.get("/api/v1/analytics/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["dashboard"]["overview"]["total_plugins"] == 0


@pytest.mark.integration
def test_record_multiple_usage_events():
    """Test recording multiple usage events for same plugin"""
    client = TestClient(app)
    
    for i in range(5):
        usage = PluginUsage(
            plugin_id="plugin_123",
            user_id=f"user_{i}",
            action="use",
            timestamp=datetime.now(datetime.UTC)
        )
        client.post("/api/v1/analytics/usage", json=usage.model_dump(mode='json'))
    
    response = client.get("/api/v1/analytics/usage/plugin_123")
    assert response.status_code == 200
    data = response.json()
    assert data["total_records"] == 5


@pytest.mark.integration
def test_usage_trends_days_parameter():
    """Test usage trends with custom days parameter"""
    client = TestClient(app)
    response = client.get("/api/v1/analytics/trends?days=7")
    assert response.status_code == 200
    data = response.json()
    assert "trends" in data


@pytest.mark.integration
def test_get_plugin_usage_days_parameter():
    """Test getting plugin usage with custom days parameter"""
    client = TestClient(app)
    response = client.get("/api/v1/analytics/usage/plugin_123?days=7")
    assert response.status_code == 200
    data = response.json()
    assert data["period_days"] == 7


@pytest.mark.integration
def test_get_plugin_performance_hours_parameter():
    """Test getting plugin performance with custom hours parameter"""
    client = TestClient(app)
    response = client.get("/api/v1/analytics/performance/plugin_123?hours=12")
    assert response.status_code == 200
    data = response.json()
    assert data["period_hours"] == 12
