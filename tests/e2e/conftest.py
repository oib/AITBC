"""
Configuration for end-to-end tests
"""

import pytest
import asyncio
import os
from typing import AsyncGenerator

# Enhanced services configuration
ENHANCED_SERVICES = {
    "multimodal": {"port": 8002, "url": "http://localhost:8002"},
    "gpu_multimodal": {"port": 8003, "url": "http://localhost:8003"},
    "modality_optimization": {"port": 8004, "url": "http://localhost:8004"},
    "adaptive_learning": {"port": 8005, "url": "http://localhost:8005"},
    "marketplace_enhanced": {"port": 8006, "url": "http://localhost:8006"},
    "openclaw_enhanced": {"port": 8007, "url": "http://localhost:8007"}
}

# Test configuration
TEST_CONFIG = {
    "timeout": 30.0,
    "retry_attempts": 3,
    "retry_delay": 1.0,
    "parallel_workers": 4,
    "performance_samples": 10,
    "concurrent_levels": [1, 5, 10, 20]
}


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def enhanced_services_health():
    """Check health of all enhanced services before running tests"""
    import httpx
    
    print("🔍 Checking enhanced services health...")
    
    healthy_services = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for service_name, service_config in ENHANCED_SERVICES.items():
            try:
                response = await client.get(f"{service_config['url']}/health")
                if response.status_code == 200:
                    healthy_services[service_name] = True
                    print(f"✅ {service_name} healthy")
                else:
                    healthy_services[service_name] = False
                    print(f"❌ {service_name} unhealthy: {response.status_code}")
            except Exception as e:
                healthy_services[service_name] = False
                print(f"❌ {service_name} unavailable: {e}")
    
    return healthy_services


@pytest.fixture(scope="session")
def skip_if_services_unavailable(enhanced_services_health):
    """Skip tests if required services are unavailable"""
    def _skip_if_services_unavailable(required_services: list):
        unavailable = [s for s in required_services if not enhanced_services_health.get(s, False)]
        if unavailable:
            pytest.skip(f"Required services unavailable: {', '.join(unavailable)}")
    
    return _skip_if_services_unavailable


@pytest.fixture(scope="session")
def test_data():
    """Provide test data for end-to-end tests"""
    return {
        "text_samples": [
            "This is a positive review with great features.",
            "The product failed to meet expectations.",
            "Average quality, nothing special.",
            "Excellent performance and reliability."
        ],
        "image_urls": [
            "https://example.com/test-image-1.jpg",
            "https://example.com/test-image-2.jpg",
            "https://example.com/test-image-3.jpg"
        ],
        "agent_configs": {
            "text_analysis": {
                "agent_id": "test-text-agent",
                "algorithm": "transformer",
                "model_size": "small"
            },
            "multimodal": {
                "agent_id": "test-multimodal-agent",
                "algorithm": "cross_modal_attention",
                "model_size": "medium"
            },
            "adaptive": {
                "agent_id": "test-adaptive-agent",
                "algorithm": "deep_q_network",
                "learning_rate": 0.001
            }
        },
        "marketplace_data": {
            "model_listings": [
                {
                    "title": "Text Analysis Agent",
                    "description": "Advanced text analysis with sentiment detection",
                    "price": 0.01,
                    "capabilities": ["sentiment_analysis", "entity_extraction"]
                },
                {
                    "title": "Multi-Modal Processor",
                    "description": "Process text, images, and audio together",
                    "price": 0.05,
                    "capabilities": ["text_analysis", "image_processing", "audio_processing"]
                }
            ]
        }
    }


@pytest.fixture
def performance_targets():
    """Provide performance targets for benchmarking"""
    return {
        "multimodal": {
            "text_processing_max_time": 0.02,
            "image_processing_max_time": 0.15,
            "min_accuracy": 0.90
        },
        "gpu_multimodal": {
            "min_speedup": 10.0,
            "max_memory_gb": 3.0
        },
        "marketplace": {
            "transaction_max_time": 0.03,
            "royalty_calculation_max_time": 0.01
        },
        "concurrent": {
            "min_success_rate": 0.9,
            "max_response_time": 1.0
        }
    }


# Pytest markers
def pytest_configure(config):
    """Configure pytest markers"""
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test"
    )
    config.addinivalue_line(
        "markers", "performance: mark test as performance benchmark"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


# Custom pytest collection hook
def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers and skip conditions"""
    
    # Add e2e marker to all tests in this directory
    for item in items:
        if "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
            item.add_marker(pytest.mark.slow)  # E2E tests are typically slow
        
        # Add performance marker to performance tests
        if "performance" in item.name or "benchmark" in item.name:
            item.add_marker(pytest.mark.performance)
        
        # Add integration marker to workflow tests
        if "workflow" in item.name or "integration" in item.name:
            item.add_marker(pytest.mark.integration)


# Test discovery and execution configuration
pytest_plugins = []

# Environment-specific configuration
def pytest_sessionstart(session):
    """Called after the Session object has been created and before performing collection and entering the run test loop."""
    print("\n🚀 Starting AITBC Enhanced Services E2E Test Suite")
    print("="*60)
    
    # Check environment
    required_env_vars = ["PYTHONPATH"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        print(f"⚠️  Missing environment variables: {', '.join(missing_vars)}")
    
    # Check test dependencies
    try:
        import httpx
        print("✅ httpx available")
    except ImportError:
        print("❌ httpx not available - some tests may fail")
    
    try:
        import psutil
        print("✅ psutil available")
    except ImportError:
        print("⚠️  psutil not available - system metrics limited")


def pytest_sessionfinish(session, exitstatus):
    """Called after whole test run finished, right before returning the exit status to the system."""
    print("\n" + "="*60)
    print("🏁 AITBC Enhanced Services E2E Test Suite Complete")
    print(f"Exit Status: {exitstatus}")
    
    if exitstatus == 0:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed - check logs for details")


# Test result reporting
def pytest_report_teststatus(report, config):
    """Add custom test status reporting"""
    if report.when == "call":
        if report.passed:
            return "passed", "✅", "PASSED"
        elif report.failed:
            return "failed", "❌", "FAILED"
        elif report.skipped:
            return "skipped", "⏭️ ", "SKIPPED"
