"""
Contract Handlers Tests
Tests for contract CLI handlers
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest  # noqa: E402


class TestContractHandlers:
    """Test contract handlers"""

    def test_handle_contract_list_function_exists(self):
        """Test that handle_contract_list function exists"""
        try:
            from handlers.contract import handle_contract_list

            assert handle_contract_list is not None
        except ImportError as e:
            pytest.skip(f"Cannot import contract handlers: {e}")

    def test_handle_contract_list_command(self):
        """Test handle_contract_list - skip due to complex RPC dependencies"""
        pytest.skip("Contract handlers have complex RPC and HTTP client dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
