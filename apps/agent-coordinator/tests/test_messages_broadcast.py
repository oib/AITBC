"""
Tests for protocol-driven send/broadcast and the REST broadcast route.
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_app.protocols import communication as communication_module
from agent_app.routers import messages as messages_router


class FakeAgent:
    """Minimal discovery result for broadcast route tests."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id

    def to_dict(self) -> dict:
        return {"agent_id": self.agent_id, "agent_type": "worker", "capabilities": []}


@pytest.fixture
def messaging_app():
    """A FastAPI app with only the messaging router."""
    app = FastAPI()
    app.include_router(messages_router.router)
    return app


@pytest.fixture
def fake_connection_manager():
    """A ConnectionManager whose send/broadcast can be asserted."""
    cm = MagicMock()
    cm.send_personal_message = AsyncMock(return_value=True)
    cm.broadcast = AsyncMock(return_value=None)
    cm.active_connections = {}
    cm.agent_inboxes = {}
    return cm


@pytest.fixture
def client(monkeypatch, tmp_path, messaging_app, fake_connection_manager):
    """TestClient with broadcast dependencies patched."""
    os.environ["AITBC_ENABLE_RATE_LIMITING"] = "false"

    # Wire the protocol layer to our fake connection manager.
    monkeypatch.setattr(communication_module, "get_connection_manager", lambda: fake_connection_manager)

    # Build a real CommunicationManager with a broadcast protocol.
    from agent_app.protocols.communication import CommunicationManager, create_protocol

    comm_manager = CommunicationManager("agent-coordinator")
    comm_manager.add_protocol("broadcast", create_protocol("broadcast", "agent-coordinator"))

    # Fake agent registry and message storage.
    state = MagicMock()
    state.message_storage = MagicMock()
    state.message_storage.store_message = AsyncMock(return_value=True)
    state.agent_registry = MagicMock()
    state.agent_registry.discover_agents = AsyncMock(return_value=[FakeAgent("agent-1"), FakeAgent("agent-2")])
    state.communication_manager = comm_manager

    monkeypatch.setattr(messages_router, "state", state)
    return TestClient(messaging_app)


class TestCommunicationProtocol:
    """CommunicationProtocol wires _send_to_agent and _broadcast_message."""

    def test_send_to_agent_uses_connection_manager(self, fake_connection_manager, monkeypatch):
        """send_message with a receiver calls send_personal_message."""
        from agent_app.protocols.communication import (
            AgentMessage,
            CommunicationProtocol,
            MessageType,
            Priority,
        )

        monkeypatch.setattr(communication_module, "get_connection_manager", lambda: fake_connection_manager)

        protocol = CommunicationProtocol("agent-001")
        message = AgentMessage(
            sender_id="agent-001",
            receiver_id="agent-002",
            message_type=MessageType.DIRECT,
            priority=Priority.NORMAL,
            payload={"text": "hello"},
        )

        result = asyncio.run(protocol.send_message(message))

        assert result is True
        fake_connection_manager.send_personal_message.assert_called_once()
        call_args = fake_connection_manager.send_personal_message.call_args[0]
        assert call_args[1] == "agent-002"
        assert call_args[0]["message_type"] == "direct"

    def test_broadcast_uses_connection_manager(self, fake_connection_manager, monkeypatch):
        """send_message with BROADCAST and no receiver calls broadcast."""
        from agent_app.protocols.communication import (
            AgentMessage,
            CommunicationProtocol,
            MessageType,
            Priority,
        )

        monkeypatch.setattr(communication_module, "get_connection_manager", lambda: fake_connection_manager)

        protocol = CommunicationProtocol("agent-001")
        message = AgentMessage(
            sender_id="agent-001",
            message_type=MessageType.BROADCAST,
            priority=Priority.NORMAL,
            payload={"announcement": "hello all"},
        )

        result = asyncio.run(protocol.send_message(message))

        assert result is True
        fake_connection_manager.broadcast.assert_called_once()
        call_args = fake_connection_manager.broadcast.call_args[0]
        assert call_args[0]["message_type"] == "broadcast"

    def test_send_to_agent_queues_offline_recipient(self, fake_connection_manager, monkeypatch):
        """If send_personal_message returns False, the message is queued."""
        fake_connection_manager.send_personal_message = AsyncMock(return_value=False)

        monkeypatch.setattr(communication_module, "get_connection_manager", lambda: fake_connection_manager)

        from agent_app.protocols.communication import (
            AgentMessage,
            CommunicationProtocol,
            MessageType,
            Priority,
        )

        protocol = CommunicationProtocol("agent-001")
        message = AgentMessage(
            sender_id="agent-001",
            receiver_id="agent-002",
            message_type=MessageType.DIRECT,
            priority=Priority.NORMAL,
            payload={"text": "hello"},
        )

        result = asyncio.run(protocol.send_message(message))

        assert result is True
        assert "agent-002" in fake_connection_manager.agent_inboxes
        assert len(fake_connection_manager.agent_inboxes["agent-002"]) == 1


class TestBroadcastRoute:
    """REST POST /broadcast routes through the protocol layer."""

    def test_broadcast_route_sends_to_each_agent(self, client, fake_connection_manager):
        """The broadcast route uses the protocol to send to every matched agent."""
        response = client.post(
            "/api/v1/agent/messages/broadcast",
            json={
                "message_type": "status_update",
                "payload": {"status": "active"},
                "priority": "normal",
                "agent_type": "worker",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["count"] == 2
        assert set(data["recipients"]) == {"agent-1", "agent-2"}

        assert fake_connection_manager.send_personal_message.call_count == 2
        calls = [call[0][1] for call in fake_connection_manager.send_personal_message.call_args_list]
        assert set(calls) == {"agent-1", "agent-2"}
