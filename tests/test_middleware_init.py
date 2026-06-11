"""
Middleware Init Tests
Tests for AITBC middleware package initialization
"""

import pytest

from aitbc.middleware import __all__


class TestMiddlewareInit:
    """Test middleware package initialization"""

    def test_middleware_package_has_all(self):
        """Test middleware package has __all__"""
        assert __all__ is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
