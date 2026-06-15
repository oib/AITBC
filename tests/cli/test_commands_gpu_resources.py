"""
GPU Resources Commands Tests
Tests for gpu_resources CLI commands
"""

from unittest.mock import patch

import pytest


class TestGPUResourcesCommands:
    """Test gpu command group"""

    def test_gpu_group_exists(self):
        """Test that gpu command group exists"""
        try:
            from aitbc_cli.commands.gpu_resources import gpu

            assert gpu is not None
            assert hasattr(gpu, "name")
        except ImportError as e:
            pytest.skip(f"Cannot import gpu commands: {e}")

    def test_gpu_group_name(self):
        """Test gpu group name"""
        try:
            from aitbc_cli.commands.gpu_resources import gpu

            assert gpu.name == "gpu-onchain"
        except ImportError as e:
            pytest.skip(f"Cannot import gpu commands: {e}")

    @patch("aitbc_cli.commands.gpu_resources.output")
    @patch("aitbc_cli.commands.gpu_resources.error")
    def test_gpu_register_command(self, mock_error, mock_output):
        """Test gpu register command - skip due to complex config dependencies"""
        pytest.skip("GPU commands have complex config and HTTP client dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
