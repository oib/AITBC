"""Integration tests for plugin analytics service"""

import pytest
import sys
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from datetime import datetime


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


@pytest.mark.integration
def test_root_endpoint():
    """Test root endpoint"""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "AITBC Plugin Analytics Service"
    assert data["status"] == "running"


@pytest.mark.integration
def test_health_check_endpoint():
    """Test health check endpoint"""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "total_usage_records" in data
    assert "total_performance_records" in data


@pytest.mark.integration
def test_record_plugin_usage():
    """Test recording plugin usage"""
    client = TestClient(app)
    usage = PluginUsage(
        plugin_id="plugin_123",
        user_id="user_123",
        action="install",
        timestamp=datetime.utcnow()
    )
    response = client.post("/api/v1/analytics/usage", json=usage.model_dump(mode='json'))
    assert response.status_code == 200
    data = response.json()
    assert data["usage_id"]
    assert data["status"] == "recorded"


@pytest.mark.integration
def test_record_plugin_performance():
    """Test recording plugin performance"""
    client = TestClient(app)
    perf = PluginPerformance(
        plugin_id="plugin_123",
        version="1.0.0",
        cpu_usage=50.5,
        memory_usage=30.2,
        response_time=0.123,
        error_rate=0.001,
        uptime=99.9,
        timestamp=datetime.utcnow()
    )
    response = client.post("/api/v1/analytics/performance", json=perf.model_dump(mode='json'))
    assert response.status_code == 200
    data = response.json()
    assert data["performance_id"]
    assert data["status"] == "recorded"


@pytest.mark.integration
def test_record_plugin_rating():
    """Test recording plugin rating"""
    client = TestClient(app)
    rating = PluginRating(
        plugin_id="plugin_123",
        user_id="user_123",
        rating=5,
        review="Great plugin!",
        timestamp=datetime.utcnow()
    )
    response = client.post("/api/v1/analytics/rating", json=rating.model_dump(mode='json'))
    assert response.status_code == 200
    data = response.json()
    assert data["rating_id"]
    assert data["status"] == "recorded"


@pytest.mark.integration
def test_record_plugin_event():
    """Test recording plugin event"""
    client = TestClient(app)
    event = PluginEvent(
        event_type="error",
        plugin_id="plugin_123",
        user_id="user_123",
        data={"error": "timeout"},
        timestamp=datetime.utcnow()
    )
    response = client.post("/api/v1/analytics/event", json=event.model_dump(mode='json'))
    assert response.status_code == 200
    data = response.json()
    assert data["event_id"]
    assert data["status"] == "recorded"


@pytest.mark.integration
def test_get_plugin_usage():
    """Test getting plugin usage analytics"""
    client = TestClient(app)
    # Record usage first
    usage = PluginUsage(
        plugin_id="plugin_123",
        user_id="user_123",
        action="install",
        timestamp=datetime.utcnow()
    )
    client.post("/api/v1/analytics/usage", json=usage.model_dump(mode='json'))
    
    response = client.get("/api/v1/analytics/usage/plugin_123")
    assert response.status_code == 200
    data = response.json()
    assert data["plugin_id"] == "plugin_123"
    assert "usage_statistics" in data


@pytest.mark.integration
def test_get_plugin_performance():
    """Test getting plugin performance analytics"""
    client = TestClient(app)
    # Record performance first
    perf = PluginPerformance(
        plugin_id="plugin_123",
        version="1.0.0",
        cpu_usage=50.5,
        memory_usage=30.2,
        response_time=0.123,
        error_rate=0.001,
        uptime=99.9,
        timestamp=datetime.utcnow()
    )
    client.post("/api/v1/analytics/performance", json=perf.model_dump(mode='json'))
    
    response = client.get("/api/v1/analytics/performance/plugin_123")
    assert response.status_code == 200
    data = response.json()
    assert data["plugin_id"] == "plugin_123"
    assert "performance_statistics" in data


@pytest.mark.integration
def test_get_plugin_ratings():
    """Test getting plugin ratings"""
    client = TestClient(app)
    # Record rating first
    rating = PluginRating(
        plugin_id="plugin_123",
        user_id="user_123",
        rating=5,
        timestamp=datetime.utcnow()
    )
    client.post("/api/v1/analytics/rating", json=rating.model_dump(mode='json'))
    
    response = client.get("/api/v1/analytics/ratings/plugin_123")
    assert response.status_code == 200
    data = response.json()
    assert data["plugin_id"] == "plugin_123"
    assert "rating_statistics" in data


@pytest.mark.integration
def test_get_analytics_dashboard():
    """Test getting analytics dashboard"""
    client = TestClient(app)
    response = client.get("/api/v1/analytics/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert "dashboard" in data
    assert "overview" in data["dashboard"]
    assert "trending_plugins" in data["dashboard"]


@pytest.mark.integration
def test_get_usage_trends():
    """Test getting usage trends"""
    client = TestClient(app)
    response = client.get("/api/v1/analytics/trends")
    assert response.status_code == 200
    data = response.json()
    assert "trends" in data


@pytest.mark.integration
def test_get_usage_trends_plugin_specific():
    """Test getting usage trends for specific plugin"""
    client = TestClient(app)
    response = client.get("/api/v1/analytics/trends?plugin_id=plugin_123")
    assert response.status_code == 200
    data = response.json()
    assert "plugin_id" in data


@pytest.mark.integration
def test_generate_analytics_report_usage():
    """Test generating usage report"""
    client = TestClient(app)
    response = client.get("/api/v1/analytics/reports?report_type=usage")
    assert response.status_code == 200
    data = response.json()


@pytest.mark.integration
def test_generate_analytics_report_performance():
    """Test generating performance report"""
    client = TestClient(app)
    response = client.get("/api/v1/analytics/reports?report_type=performance")
    assert response.status_code == 200
    data = response.json()


@pytest.mark.integration
def test_generate_analytics_report_ratings():
    """Test generating ratings report"""
    client = TestClient(app)
    response = client.get("/api/v1/analytics/reports?report_type=ratings")
    assert response.status_code == 200
    data = response.json()


@pytest.mark.integration
def test_generate_analytics_report_invalid():
    """Test generating analytics report with invalid type"""
    client = TestClient(app)
    response = client.get("/api/v1/analytics/reports?report_type=invalid")
    assert response.status_code == 400
