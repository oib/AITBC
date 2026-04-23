"""Unit tests for plugin analytics service"""

import pytest
import sys
import sys
from pathlib import Path
from datetime import datetime


from main import app, PluginUsage, PluginPerformance, PluginRating, PluginEvent


@pytest.mark.unit
def test_app_initialization():
    """Test that the FastAPI app initializes correctly"""
    assert app is not None
    assert app.title == "AITBC Plugin Analytics Service"
    assert app.version == "1.0.0"


@pytest.mark.unit
def test_plugin_usage_model():
    """Test PluginUsage model"""
    usage = PluginUsage(
        plugin_id="plugin_123",
        user_id="user_123",
        action="install",
        timestamp=datetime.utcnow(),
        metadata={"source": "marketplace"}
    )
    assert usage.plugin_id == "plugin_123"
    assert usage.user_id == "user_123"
    assert usage.action == "install"
    assert usage.metadata == {"source": "marketplace"}


@pytest.mark.unit
def test_plugin_usage_defaults():
    """Test PluginUsage with default metadata"""
    usage = PluginUsage(
        plugin_id="plugin_123",
        user_id="user_123",
        action="use",
        timestamp=datetime.utcnow()
    )
    assert usage.metadata == {}


@pytest.mark.unit
def test_plugin_performance_model():
    """Test PluginPerformance model"""
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
    assert perf.plugin_id == "plugin_123"
    assert perf.version == "1.0.0"
    assert perf.cpu_usage == 50.5
    assert perf.memory_usage == 30.2
    assert perf.response_time == 0.123
    assert perf.error_rate == 0.001
    assert perf.uptime == 99.9


@pytest.mark.unit
def test_plugin_rating_model():
    """Test PluginRating model"""
    rating = PluginRating(
        plugin_id="plugin_123",
        user_id="user_123",
        rating=5,
        review="Great plugin!",
        timestamp=datetime.utcnow()
    )
    assert rating.plugin_id == "plugin_123"
    assert rating.rating == 5
    assert rating.review == "Great plugin!"


@pytest.mark.unit
def test_plugin_rating_defaults():
    """Test PluginRating with default review"""
    rating = PluginRating(
        plugin_id="plugin_123",
        user_id="user_123",
        rating=4,
        timestamp=datetime.utcnow()
    )
    assert rating.review is None


@pytest.mark.unit
def test_plugin_event_model():
    """Test PluginEvent model"""
    event = PluginEvent(
        event_type="error",
        plugin_id="plugin_123",
        user_id="user_123",
        data={"error": "timeout"},
        timestamp=datetime.utcnow()
    )
    assert event.event_type == "error"
    assert event.plugin_id == "plugin_123"
    assert event.user_id == "user_123"
    assert event.data == {"error": "timeout"}


@pytest.mark.unit
def test_plugin_event_defaults():
    """Test PluginEvent with default values"""
    event = PluginEvent(
        event_type="info",
        plugin_id="plugin_123",
        timestamp=datetime.utcnow()
    )
    assert event.user_id is None
    assert event.data == {}
