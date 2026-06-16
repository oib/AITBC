"""
Agent SDK CLI Tests
Tests for agent SDK and coordinator CLI commands
"""


import pytest
from aitbc_cli.commands.agent_sdk import agent
from click.testing import CliRunner


class TestAgentCLI:
    """Test agent SDK and coordinator CLI commands"""

    def test_agent_group(self):
        """Test agent command group exists"""
        runner = CliRunner()
        result = runner.invoke(agent, ["--help"])
        assert result.exit_code == 0
        assert "Agent SDK management commands" in result.output

    def test_agent_discover_command(self):
        """Test agent discover command"""
        runner = CliRunner()
        result = runner.invoke(agent, ["discover", "--help"])
        assert result.exit_code == 0
        assert "Discover agents by capability" in result.output

    def test_agent_inbox_command(self):
        """Test agent inbox command"""
        runner = CliRunner()
        result = runner.invoke(agent, ["inbox", "--help"])
        assert result.exit_code == 0
        assert "View agent inbox" in result.output

    def test_agent_subscribe_command(self):
        """Test agent subscribe command"""
        runner = CliRunner()
        result = runner.invoke(agent, ["subscribe", "--help"])
        assert result.exit_code == 0
        assert "Subscribe to topic" in result.output

    def test_agent_workflow_group(self):
        """Test agent workflow command group"""
        runner = CliRunner()
        result = runner.invoke(agent, ["workflow", "--help"])
        assert result.exit_code == 0
        assert "Workflow management" in result.output

    def test_agent_workflow_create_command(self):
        """Test agent workflow create command"""
        runner = CliRunner()
        result = runner.invoke(agent, ["workflow", "create", "--help"])
        assert result.exit_code == 0
        assert "Create workflow" in result.output

    def test_agent_workflow_execute_command(self):
        """Test agent workflow execute command"""
        runner = CliRunner()
        result = runner.invoke(agent, ["workflow", "execute", "--help"])
        assert result.exit_code == 0
        assert "Execute workflow" in result.output

    def test_agent_workflow_status_command(self):
        """Test agent workflow status command"""
        runner = CliRunner()
        result = runner.invoke(agent, ["workflow", "status", "--help"])
        assert result.exit_code == 0
        assert "Get workflow status" in result.output

    def test_agent_workflow_list_command(self):
        """Test agent workflow list command"""
        runner = CliRunner()
        result = runner.invoke(agent, ["workflow", "list", "--help"])
        assert result.exit_code == 0
        assert "List workflows" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
