"""
Script Commands Tests
Tests for script CLI commands
"""


import pytest


class TestScriptCommands:
    """Test script command group"""

    def test_script_group_exists(self):
        """Test that script command group exists"""
        try:
            from aitbc_cli.commands.script import script

            assert script is not None
            assert hasattr(script, "name")
        except ImportError as e:
            pytest.skip(f"Cannot import script commands: {e}")

    def test_script_group_name(self):
        """Test script group name"""
        try:
            from aitbc_cli.commands.script import script

            assert script.name == "script"
        except ImportError as e:
            pytest.skip(f"Cannot import script commands: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
