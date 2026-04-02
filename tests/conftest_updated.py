"""
Updated pytest configuration for AITBC Agent Systems
"""

import pytest
import asyncio
import sys
import os
from pathlib import Path

# Add src directories to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "apps/agent-coordinator/src"))

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def sample_agent_data():
    """Sample agent data for testing"""
    return {
        "agent_id": "test_agent_001",
        "agent_type": "worker",
        "capabilities": ["data_processing", "analysis"],
        "services": ["process_data", "analyze_results"],
        "endpoints": {
            "http": "http://localhost:8001",
            "ws": "ws://localhost:8002"
        },
        "metadata": {
            "version": "1.0.0",
            "region": "test"
        }
    }

@pytest.fixture
def sample_task_data():
    """Sample task data for testing"""
    return {
        "task_data": {
            "task_id": "test_task_001",
            "task_type": "data_processing",
            "data": {
                "input": "test_data",
                "operation": "process"
            },
            "required_capabilities": ["data_processing"]
        },
        "priority": "normal",
        "requirements": {
            "agent_type": "worker",
            "min_health_score": 0.8
        }
    }

@pytest.fixture
def api_base_url():
    """Base URL for API tests"""
    return "http://localhost:9001"

@pytest.fixture
def mock_redis():
    """Mock Redis connection for testing"""
    import redis
    from unittest.mock import Mock
    
    mock_redis = Mock()
    mock_redis.ping.return_value = True
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.delete.return_value = True
    mock_redis.hgetall.return_value = {}
    mock_redis.hset.return_value = True
    mock_redis.hdel.return_value = True
    mock_redis.keys.return_value = []
    mock_redis.exists.return_value = False
    
    return mock_redis

# pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "unit: Mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: Mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "performance: Mark test as a performance test"
    )
    config.addinivalue_line(
        "markers", "phase1: Mark test as Phase 1 test"
    )
    config.addinivalue_line(
        "markers", "phase2: Mark test as Phase 2 test"
    )
    config.addinivalue_line(
        "markers", "phase3: Mark test as Phase 3 test"
    )
    config.addinivalue_line(
        "markers", "phase4: Mark test as Phase 4 test"
    )
    config.addinivalue_line(
        "markers", "phase5: Mark test as Phase 5 test"
    )

# Custom markers for test selection
def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on file location"""
    for item in items:
        # Add phase markers based on file path
        if "phase1" in str(item.fspath):
            item.add_marker(pytest.mark.phase1)
        elif "phase2" in str(item.fspath):
            item.add_marker(pytest.mark.phase2)
        elif "phase3" in str(item.fspath):
            item.add_marker(pytest.mark.phase3)
        elif "phase4" in str(item.fspath):
            item.add_marker(pytest.mark.phase4)
        elif "phase5" in str(item.fspath):
            item.add_marker(pytest.mark.phase5)
        
        # Add type markers based on file content
        if "api" in str(item.fspath).lower():
            item.add_marker(pytest.mark.integration)
        elif "performance" in str(item.fspath).lower():
            item.add_marker(pytest.mark.performance)
        elif "test_communication" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
