"""
Training Setup CLI Tests
Tests for AITBC training setup CLI utilities
"""

import pytest

from aitbc.training_setup.cli import cli


class TestTrainingSetupCLI:
    """Test training setup CLI"""

    def test_cli_group_exists(self):
        """Test CLI group exists"""
        assert cli is not None

    def test_cli_is_click_group(self):
        """Test CLI is a click group"""
        assert hasattr(cli, "commands")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
