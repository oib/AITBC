"""Tests for WebSocket agent streaming module"""

import sys
from pathlib import Path

# Add coordinator path for imports
coordinator_path = Path("/opt/aitbc/apps/agent-coordinator/src")
if str(coordinator_path) not in sys.path:
    sys.path.insert(0, str(coordinator_path))


from app.websocket.agent_stream import ConnectionManager  # noqa: E402


class TestConnectionManager:
    """Test ConnectionManager class"""

    def test_connection_manager_initialization(self):
        """Test ConnectionManager initialization"""
        manager = ConnectionManager()
        assert manager.active_connections == {}
        assert manager.topic_subscriptions == {}
        assert manager.agent_topics == {}
        assert manager.message_handlers == {}
        assert manager.agent_inboxes == {}

    def test_disconnect_nonexistent_agent(self):
        """Test disconnecting a non-existent agent"""
        manager = ConnectionManager()
        # Should not raise an error
        manager.disconnect("non-existent-agent")
        assert manager.active_connections == {}

    def test_get_agent_inbox(self):
        """Test getting agent inbox"""
        manager = ConnectionManager()
        manager.agent_inboxes["agent-123"] = [{"message": "test"}]
        inbox = manager.agent_inboxes.get("agent-123", [])
        assert inbox == [{"message": "test"}]

    def test_get_agent_inbox_empty(self):
        """Test getting inbox for agent with no messages"""
        manager = ConnectionManager()
        manager.agent_inboxes["agent-123"] = []
        inbox = manager.agent_inboxes.get("agent-123", [])
        assert inbox == []

    def test_topic_subscriptions_initialization(self):
        """Test topic subscriptions are initialized as empty dict"""
        manager = ConnectionManager()
        assert manager.topic_subscriptions == {}

    def test_message_handlers_initialization(self):
        """Test message handlers are initialized as empty dict"""
        manager = ConnectionManager()
        assert manager.message_handlers == {}

    def test_agent_topics_initialization(self):
        """Test agent topics are initialized as empty dict"""
        manager = ConnectionManager()
        assert manager.agent_topics == {}
