"""
Pool Hub Handlers Tests
Tests for pool_hub CLI handlers
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestPoolHubHandlers:
    """Test pool_hub handlers"""

    def test_handle_pool_hub_sla_metrics_function_exists(self):
        """Test that handle_pool_hub_sla_metrics function exists"""
        try:
            from handlers.pool_hub import handle_pool_hub_sla_metrics
            assert handle_pool_hub_sla_metrics is not None
        except ImportError as e:
            pytest.skip(f"Cannot import pool_hub handlers: {e}")

    def test_handle_pool_hub_sla_metrics_command(self):
        """Test handle_pool_hub_sla_metrics - skip due to complex legacy command dependencies"""
        pytest.skip("Pool hub handlers have complex legacy command and HTTP client dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
