"""
Middleware Performance Tests
Tests for AITBC middleware performance
"""

import pytest

from aitbc.middleware.performance import PerformanceLoggingMiddleware


class TestPerformanceLoggingMiddleware:
    """Test PerformanceLoggingMiddleware class"""

    def test_performance_logging_middleware_class_exists(self):
        """Test PerformanceLoggingMiddleware class exists"""
        assert PerformanceLoggingMiddleware is not None

    def test_performance_logging_middleware_can_be_instantiated(self):
        """Test PerformanceLoggingMiddleware can be instantiated"""
        middleware = PerformanceLoggingMiddleware(app=None)
        assert middleware is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
