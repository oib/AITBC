"""
Unit tests for the `aitbc agent-msg` command group.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    """Create a Click CLI runner."""
    return CliRunner()


@pytest.fixture
def mock_client():
    """Mock AITBCHTTPClient returned by the agent-msg commands."""
    client = MagicMock()
    client.post.return_value = {
        "status": "success",
        "message_id": "msg-cli-1",
        "sender": "agent-a",
        "recipient": "agent-b",
        "message_status": "pending",
        "ws_delivered": False,
        "sent_at": "2026-08-21T12:00:00+00:00",
    }
    client.get.return_value = {
        "agent_id": "agent-b",
        "messages": [client.post.return_value],
        "count": 1,
    }
    with patch("aitbc_cli.commands.agent.AITBCHTTPClient", return_value=client):
        with patch(
            "aitbc_cli.commands.agent.get_config", return_value=MagicMock(agent_coordinator_url="http://localhost:8107")
        ):
            yield client


def test_agent_msg_group_help(runner):
    """The agent-msg group should list all subcommands."""
    from aitbc_cli.commands.agent import messaging

    result = runner.invoke(messaging, ["--help"], obj={"output_format": "table"})
    assert result.exit_code == 0
    for cmd in ["send", "receive", "ping", "peers", "request-coins"]:
        assert cmd in result.output, f"Missing {cmd} in help output"


def test_send_help(runner):
    """send --help should document the required options."""
    from aitbc_cli.commands.agent import messaging

    result = runner.invoke(messaging, ["send", "--help"], obj={"output_format": "table"})
    assert result.exit_code == 0
    assert "--from-agent" in result.output
    assert "--to-agent" in result.output
    assert "--priority" in result.output
    assert "--message-id" in result.output
    assert "--encrypt" in result.output


def test_send_success(runner, mock_client):
    """send should post to /api/v1/agent/messages/send with the correct payload."""
    from aitbc_cli.commands.agent import messaging

    result = runner.invoke(
        messaging,
        [
            "send",
            "hello",
            "--from-agent",
            "agent-a",
            "--to-agent",
            "agent-b",
            "--priority",
            "high",
        ],
        obj={"output_format": "table"},
    )

    assert result.exit_code == 0
    assert "Message sent via Agent Coordinator" in result.output
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "/api/v1/agent/messages/send"
    payload = call_args.kwargs["json"]
    assert payload["sender"] == "agent-a"
    assert payload["recipient"] == "agent-b"
    assert payload["content"] == {"message": "hello"}
    assert payload["priority"] == "high"
    assert payload["message_type"] == "direct"
    assert payload["encrypt"] is True


def test_send_idempotent(runner, mock_client):
    """send with --message-id should include the idempotency key."""
    from aitbc_cli.commands.agent import messaging

    result = runner.invoke(
        messaging,
        [
            "send",
            "hello",
            "--from-agent",
            "agent-a",
            "--to-agent",
            "agent-b",
            "--message-id",
            "msg-unique-1",
            "--no-encrypt",
        ],
        obj={"output_format": "table"},
    )

    assert result.exit_code == 0
    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["message_id"] == "msg-unique-1"
    assert payload["encrypt"] is False


def test_send_requires_to_agent(runner):
    """send without --to-agent should fail."""
    from aitbc_cli.commands.agent import messaging

    result = runner.invoke(
        messaging,
        ["send", "hello", "--from-agent", "agent-a"],
        obj={"output_format": "table"},
    )
    assert result.exit_code != 0


def test_receive_help(runner):
    """receive --help should document the inbox options."""
    from aitbc_cli.commands.agent import messaging

    result = runner.invoke(messaging, ["receive", "--help"], obj={"output_format": "table"})
    assert result.exit_code == 0
    assert "--from-agent" in result.output
    assert "--limit" in result.output
    assert "--unread-only" in result.output


def test_receive_success(runner, mock_client):
    """receive should fetch /api/v1/agent/messages/inbox for the given agent."""
    from aitbc_cli.commands.agent import messaging

    result = runner.invoke(
        messaging,
        ["receive", "--from-agent", "agent-b", "--limit", "10"],
        obj={"output_format": "table"},
    )

    assert result.exit_code == 0
    assert "Messages:" in result.output
    mock_client.get.assert_called_once()
    call_args = mock_client.get.call_args
    assert call_args[0][0] == "/api/v1/agent/messages/inbox"
    assert call_args.kwargs["params"]["agent_id"] == "agent-b"
    assert call_args.kwargs["params"]["limit"] == 10


def test_receive_unread_only(runner, mock_client):
    """receive --unread-only should pass the unread_only flag."""
    from aitbc_cli.commands.agent import messaging

    result = runner.invoke(
        messaging,
        ["receive", "--from-agent", "agent-b", "--unread-only"],
        obj={"output_format": "table"},
    )

    assert result.exit_code == 0
    assert mock_client.get.call_args.kwargs["params"]["unread_only"] == "true"


def test_peers_success(runner, mock_client):
    """peers should call /api/v1/agent/messages/discover."""
    from aitbc_cli.commands.agent import messaging

    mock_client.get.return_value = {"agents": [{"agent_id": "hub-coordinator"}]}
    result = runner.invoke(messaging, ["peers"], obj={"output_format": "table"})

    assert result.exit_code == 0
    assert "Agent Coordinator Peers:" in result.output
    mock_client.get.assert_called_once_with("/api/v1/agent/messages/discover")
