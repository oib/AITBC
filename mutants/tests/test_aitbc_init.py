"""
AITBC Init Tests
Tests for AITBC package initialization
"""

import aitbc
import pytest


class TestAitbcInit:
    """Test AITBC package initialization"""

    def test_aitbc_package_exists(self):
        """Test aitbc package exists"""
        assert aitbc is not None

    def test_aitbc_has_version(self):
        """Test aitbc has __version__"""
        assert hasattr(aitbc, "__version__")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
