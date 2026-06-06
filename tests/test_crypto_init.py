"""
Crypto Init Tests
Tests for AITBC crypto package initialization
"""

import pytest
from aitbc.crypto import __all__


class TestCryptoInit:
    """Test crypto package initialization"""

    def test_crypto_package_has_all(self):
        """Test crypto package has __all__"""
        assert __all__ is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
