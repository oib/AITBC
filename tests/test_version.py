"""
Version Tests
Tests for AITBC version module
"""

import pytest

from aitbc._version import __version__


class TestVersion:
    """Test version module"""

    def test_version_exists(self):
        """Test __version__ exists"""
        assert __version__ is not None

    def test_version_is_string(self):
        """Test __version__ is a string"""
        assert isinstance(__version__, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
