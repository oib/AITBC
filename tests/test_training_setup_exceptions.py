"""
Training Setup Exceptions Tests
Tests for AITBC training setup exceptions
"""

import pytest

from aitbc.training_setup.exceptions import TrainingSetupError


class TestTrainingSetupError:
    """Test TrainingSetupError exception"""

    def test_training_setup_error_exists(self):
        """Test TrainingSetupError exists"""
        assert TrainingSetupError is not None

    def test_training_setup_error_can_be_raised(self):
        """Test TrainingSetupError can be raised"""
        with pytest.raises(TrainingSetupError):
            raise TrainingSetupError("Test error")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
