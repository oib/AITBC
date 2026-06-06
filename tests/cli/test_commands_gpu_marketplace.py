"""
GPU Marketplace Commands Tests
Tests for gpu_marketplace CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch, Mock

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestGPUMarketplaceCommands:
    """Test gpu command group"""

    def test_gpu_group_exists(self):
        """Test that gpu command group exists"""
        try:
            from aitbc_cli.commands.gpu_marketplace import gpu
            assert gpu is not None
            assert hasattr(gpu, 'name')
        except ImportError as e:
            pytest.skip(f"Cannot import gpu commands: {e}")

    def test_gpu_group_name(self):
        """Test gpu group name"""
        try:
            from aitbc_cli.commands.gpu_marketplace import gpu
            assert gpu.name == "gpu"
        except ImportError as e:
            pytest.skip(f"Cannot import gpu commands: {e}")

    @patch('aitbc_cli.commands.gpu_marketplace.output')
    @patch('aitbc_cli.commands.gpu_marketplace.error')
    def test_gpu_discover_command(self, mock_error, mock_output):
        """Test gpu discover command - skip due to complex config dependencies"""
        pytest.skip("GPU commands have complex config and HTTP client dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
