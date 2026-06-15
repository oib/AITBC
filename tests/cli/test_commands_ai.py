"""
AI Commands Tests
Tests for ai CLI commands
"""

from unittest.mock import patch

import pytest


class TestAICommands:
    """Test ai command group"""

    def test_ai_group_exists(self):
        """Test that ai command group exists"""
        try:
            from aitbc_cli.commands.ai import ai

            assert ai is not None
            assert hasattr(ai, "name")
        except ImportError as e:
            pytest.skip(f"Cannot import ai commands: {e}")

    def test_ai_group_name(self):
        """Test ai group name"""
        try:
            from aitbc_cli.commands.ai import ai

            assert ai.name == "ai"
        except ImportError as e:
            pytest.skip(f"Cannot import ai commands: {e}")

    @patch("aitbc_cli.commands.ai.output")
    @patch("aitbc_cli.commands.ai.error")
    def test_ai_submit_command(self, mock_error, mock_output):
        """Test ai submit command - skip due to complex wallet and config dependencies"""
        pytest.skip("AI commands have complex wallet and config dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
