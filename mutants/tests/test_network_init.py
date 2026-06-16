"""
Network Init Tests
Tests for AITBC network package initialization
"""

import pytest

from aitbc.network import __all__


class TestNetworkInit:
    """Test network package initialization"""

    def test_network_package_has_all(self):
        """Test network package has __all__"""
        assert __all__ is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
