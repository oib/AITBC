"""
Middleware Request ID Tests
Tests for AITBC middleware request ID
"""

import pytest

from aitbc.middleware.request_id import RequestIDMiddleware


class TestRequestIDMiddleware:
    """Test RequestIDMiddleware class"""

    def test_request_id_middleware_class_exists(self):
        """Test RequestIDMiddleware class exists"""
        assert RequestIDMiddleware is not None

    def test_request_id_middleware_can_be_instantiated(self):
        """Test RequestIDMiddleware can be instantiated"""
        middleware = RequestIDMiddleware(app=None)
        assert middleware is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
