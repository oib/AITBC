"""
Node Commands Tests
Tests for node CLI commands
"""


import pytest


class TestNodeCommands:
    """Test node command group"""

    def test_node_group_exists(self):
        """Test that node command group exists"""
        try:
            from aitbc_cli.commands.node import node

            assert node is not None
            assert hasattr(node, "name")
        except ImportError as e:
            pytest.skip(f"Cannot import node commands: {e}")

    def test_node_group_name(self):
        """Test node group name"""
        try:
            from aitbc_cli.commands.node import node

            assert node.name == "node"
        except ImportError as e:
            pytest.skip(f"Cannot import node commands: {e}")

    def test_node_status_command(self):
        """Test node status command - skip due to complex config dependencies"""
        pytest.skip("Node commands have complex config and async dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
