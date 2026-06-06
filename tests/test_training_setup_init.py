"""
Training Setup Init Tests
Tests for AITBC training_setup package initialization
"""

import pytest
from aitbc.training_setup import __all__


class TestTrainingSetupInit:
    """Test training_setup package initialization"""

    def test_training_setup_package_has_all(self):
        """Test training_setup package has __all__"""
        assert __all__ is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
