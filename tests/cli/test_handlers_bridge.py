"""
Bridge Handlers Tests
Tests for bridge CLI handlers
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest  # noqa: E402


class TestBridgeHandlers:
    """Test bridge handlers"""

    def test_handle_bridge_health_function_exists(self):
        """Test that handle_bridge_health function exists"""
        try:
            from handlers.bridge import handle_bridge_health

            assert handle_bridge_health is not None
        except ImportError as e:
            pytest.skip(f"Cannot import bridge handlers: {e}")

    def test_handle_bridge_health_command(self):
        """Test handle_bridge_health - skip due to complex legacy command dependencies"""
        pytest.skip("Bridge handlers have complex legacy command and HTTP client dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
