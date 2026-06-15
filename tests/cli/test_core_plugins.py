"""
Core Plugins Tests
Tests for plugin system (non-Click functions only)
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest  # noqa: E402


class TestGetPluginDir:
    """Test get_plugin_dir function"""

    @patch("aitbc_cli.core.plugins.PLUGIN_DIR")
    def test_get_plugin_dir(self, mock_plugin_dir):
        """Test getting plugin directory"""
        from aitbc_cli.core.plugins import get_plugin_dir

        mock_plugin_dir.mkdir = Mock()
        mock_plugin_dir.exists.return_value = False

        result = get_plugin_dir()

        mock_plugin_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        assert result == mock_plugin_dir


class TestLoadPlugins:
    """Test load_plugins function"""

    @patch("aitbc_cli.core.plugins.get_plugin_dir")
    def test_load_plugins_no_manifest(self, mock_get_plugin_dir):
        """Test loading plugins when no manifest exists"""
        from aitbc_cli.core.plugins import load_plugins

        mock_plugin_dir = Path("/tmp/test_plugins")
        mock_get_plugin_dir.return_value = mock_plugin_dir

        cli_group = Mock()

        load_plugins(cli_group)

        # Should return early without adding commands
        cli_group.add_command.assert_not_called()

    @patch("aitbc_cli.core.plugins.get_plugin_dir")
    def test_load_plugins_with_manifest(self, mock_get_plugin_dir):
        """Test loading plugins with manifest"""
        from aitbc_cli.core.plugins import load_plugins

        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            manifest_file = plugin_dir / "plugins.json"

            # Create manifest
            manifest_data = {"plugins": [{"name": "test_plugin", "file": "test.py", "enabled": False}]}
            with open(manifest_file, "w") as f:
                json.dump(manifest_data, f)

            mock_get_plugin_dir.return_value = plugin_dir

            cli_group = Mock()

            load_plugins(cli_group)

            # Plugin is disabled, so should not be loaded
            cli_group.add_command.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
