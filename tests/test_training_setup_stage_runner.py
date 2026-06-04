"""
Training Setup Stage Runner Tests
Tests for AITBC training setup stage runner
"""

import pytest
from aitbc.training_setup.stage_runner import StageRunner


class TestStageRunner:
    """Test StageRunner class"""

    def test_stage_runner_class_exists(self):
        """Test StageRunner class exists"""
        assert StageRunner is not None

    def test_stage_runner_can_be_instantiated(self):
        """Test StageRunner can be instantiated"""
        runner = StageRunner()
        assert runner is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
