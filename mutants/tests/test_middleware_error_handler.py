"""
Middleware Error Handler Tests
Tests for AITBC middleware error handler
"""

import pytest
from aitbc.middleware.error_handler import ErrorHandlerMiddleware


class TestErrorHandlerMiddleware:
    """Test ErrorHandlerMiddleware class"""

    def test_error_handler_middleware_class_exists(self):
        """Test ErrorHandlerMiddleware class exists"""
        assert ErrorHandlerMiddleware is not None

    def test_error_handler_middleware_can_be_instantiated(self):
        """Test ErrorHandlerMiddleware can be instantiated"""
        middleware = ErrorHandlerMiddleware(app=None)
        assert middleware is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
