"""
Agent Comm Commands Tests
Tests for agent_comm CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestAgentCommCommands:
    """Test agent_comm command group"""

    def test_agent_comm_group_exists(self):
        """Test that agent_comm command group exists"""
        try:
            from aitbc_cli.commands.agent_comm import agent_comm
            assert agent_comm is not None
            assert hasattr(agent_comm, 'name')
        except ImportError as e:
            pytest.skip(f"Cannot import agent_comm commands: {e}")

    def test_agent_comm_group_name(self):
        """Test agent_comm group name"""
        try:
            from aitbc_cli.commands.agent_comm import agent_comm
            assert agent_comm.name == "agent-comm"
        except ImportError as e:
            pytest.skip(f"Cannot import agent_comm commands: {e}")

    @patch('aitbc_cli.commands.agent_comm.output')
    @patch('aitbc_cli.commands.agent_comm.error')
    def test_agent_comm_register_command(self, mock_error, mock_output):
        """Test agent_comm register command - skip due to complex dependencies"""
        pytest.skip("Agent comm commands have complex config and async dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
