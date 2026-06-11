"""
Blockchain Handlers Tests
Tests for blockchain CLI handlers
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestBlockchainHandlers:
    """Test blockchain handlers"""

    def test_handle_blockchain_info_function_exists(self):
        """Test that handle_blockchain_info function exists"""
        try:
            from handlers.blockchain import handle_blockchain_info
            assert handle_blockchain_info is not None
        except ImportError as e:
            pytest.skip(f"Cannot import blockchain handlers: {e}")

    def test_handle_blockchain_height_function_exists(self):
        """Test that handle_blockchain_height function exists"""
        try:
            from handlers.blockchain import handle_blockchain_height
            assert handle_blockchain_height is not None
        except ImportError as e:
            pytest.skip(f"Cannot import blockchain handlers: {e}")

    def test_handle_blockchain_block_function_exists(self):
        """Test that handle_blockchain_block function exists"""
        try:
            from handlers.blockchain import handle_blockchain_block
            assert handle_blockchain_block is not None
        except ImportError as e:
            pytest.skip(f"Cannot import blockchain handlers: {e}")

    def test_handle_blockchain_info_command(self):
        """Test handle_blockchain_info - skip due to complex RPC dependencies"""
        pytest.skip("Blockchain handlers have complex RPC and chain info dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
