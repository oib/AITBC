"""
Config Commands Tests
Tests for config CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

import pytest


class TestConfigCommands:
    """Test config command group"""

    def test_config_group_exists(self):
        """Test that config command group exists"""
        from aitbc_cli.commands.config import config

        assert config is not None
        assert hasattr(config, "name")

    def test_config_group_name(self):
        """Test config group name"""
        from aitbc_cli.commands.config import config

        assert config.name == "config"

    def test_config_group_has_show_subcommand(self):
        """The ``show`` subcommand is registered on the config group."""
        from aitbc_cli.commands.config import config

        assert "show" in config.commands

    def test_config_group_has_set_subcommand(self):
        """The ``set`` subcommand is registered on the config group."""
        from aitbc_cli.commands.config import config

        assert "set" in config.commands

    def test_config_group_has_validate_subcommand(self):
        """The ``validate`` subcommand is registered on the config group."""
        from aitbc_cli.commands.config import config

        assert "validate" in config.commands

    def test_config_show_command(self, runner, mock_config):
        """``config show`` displays the current configuration."""
        from aitbc_cli.commands.config import config

        obj = {"output": "table", "output_format": "table", "config": mock_config}
        result = runner.invoke(config, ["show"], obj=obj)

        assert result.exit_code == 0, result.output
        assert "agent_coordinator_url" in result.output

    def test_config_validate_command(self, runner, mock_config):
        """``config validate`` validates the current configuration."""
        from aitbc_cli.commands.config import config

        obj = {"output": "table", "output_format": "table", "config": mock_config}
        result = runner.invoke(config, ["validate"], obj=obj)

        assert result.exit_code == 0, result.output

    def test_config_path_command(self, runner):
        """``config path`` shows the configuration file path."""
        from aitbc_cli.commands.config import config

        result = runner.invoke(config, ["path"])

        assert result.exit_code == 0, result.output
        assert "config_file" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
