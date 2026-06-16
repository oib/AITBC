"""
Training Setup Environment Tests
Tests for AITBC training setup environment utilities
"""

import pytest
from aitbc.training_setup.environment import TrainingEnvironment


class TestTrainingEnvironment:
    """Test TrainingEnvironment class"""

    def test_training_environment_class_exists(self):
        """Test TrainingEnvironment class exists"""
        assert TrainingEnvironment is not None

    def test_training_environment_can_be_instantiated(self):
        """Test TrainingEnvironment can be instantiated"""
        env = TrainingEnvironment(aitbc_dir="/opt/aitbc")
        assert env is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
