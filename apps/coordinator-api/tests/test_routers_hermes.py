"""
Tests for hermes router (agent messaging)
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestHermesRouter:
    """Test hermes router endpoints"""

    def test_register_agent(self, client: TestClient):
        """Test agent registration"""
        agent_data = {
            "agent_id": "agent-001",
            "public_key": "abc123def456",
            "capabilities": ["ai", "gpu", "messaging"]
        }

        response = client.post("/hermes/agents/register", json=agent_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["agent"]["id"] == "agent-001"
        assert "ai" in data["agent"]["capabilities"]

    def test_send_message(self, client: TestClient):
        """Test sending direct message"""
        # Register two agents first
        client.post("/hermes/agents/register", json={
            "agent_id": "sender-001",
            "public_key": "sender-key",
            "capabilities": ["messaging"]
        })
        client.post("/hermes/agents/register", json={
            "agent_id": "receiver-001",
            "public_key": "receiver-key",
            "capabilities": ["messaging"]
        })

        # Send message
        message_data = {
            "sender": "sender-001",
            "recipient": "receiver-001",
            "content": "Hello, this is a test message!",
            "message_type": "direct",
            "encrypted": False
        }

        response = client.post("/hermes/messages/send", json=message_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["message"]["sender"] == "sender-001"
        assert data["message"]["recipient"] == "receiver-001"

    def test_send_message_unregistered_sender(self, client: TestClient):
        """Test sending from unregistered agent fails"""
        message_data = {
            "sender": "unregistered-agent",
            "recipient": "receiver-001",
            "content": "Test message"
        }

        response = client.post("/hermes/messages/send", json=message_data)
        assert response.status_code == 400

    def test_broadcast_message(self, client: TestClient):
        """Test broadcasting to all agents"""
        # Register agents
        for i in range(3):
            client.post("/hermes/agents/register", json={
                "agent_id": f"agent-{i}",
                "public_key": f"key-{i}",
                "capabilities": ["messaging"]
            })

        # Broadcast
        broadcast_data = {
            "sender": "agent-0",
            "content": "Broadcast message to all agents!",
            "encrypted": False
        }

        response = client.post("/hermes/messages/broadcast", json=broadcast_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["sent_count"] == 2  # Excluding sender

    def test_get_messages(self, client: TestClient):
        """Test getting messages for agent"""
        # Setup
        client.post("/hermes/agents/register", json={
            "agent_id": "msg-receiver",
            "public_key": "receiver-key",
            "capabilities": ["messaging"]
        })
        client.post("/hermes/agents/register", json={
            "agent_id": "msg-sender",
            "public_key": "sender-key",
            "capabilities": ["messaging"]
        })

        # Send message
        client.post("/hermes/messages/send", json={
            "sender": "msg-sender",
            "recipient": "msg-receiver",
            "content": "Test message content"
        })

        # Get messages
        response = client.get("/hermes/messages/msg-receiver")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "msg-receiver"
        assert data["count"] >= 1
        assert any("Test message content" in str(m.get("content", "")) for m in data["messages"])

    def test_mark_message_read(self, client: TestClient):
        """Test marking message as read"""
        # Setup
        client.post("/hermes/agents/register", json={
            "agent_id": "read-test-receiver",
            "public_key": "key",
            "capabilities": ["messaging"]
        })
        client.post("/hermes/agents/register", json={
            "agent_id": "read-test-sender",
            "public_key": "key2",
            "capabilities": ["messaging"]
        })

        # Send message
        send_response = client.post("/hermes/messages/send", json={
            "sender": "read-test-sender",
            "recipient": "read-test-receiver",
            "content": "Message to mark as read"
        })
        message_id = send_response.json()["message"]["id"]

        # Mark as read
        read_data = {
            "agent_id": "read-test-receiver",
            "message_id": message_id
        }
        response = client.post("/hermes/messages/read", json=read_data)
        assert response.status_code == 200
        assert response.json()["status"] == "read"

    def test_list_agents(self, client: TestClient):
        """Test listing all agents"""
        response = client.get("/hermes/agents")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert "count" in data

    def test_get_agent_profile(self, client: TestClient):
        """Test getting agent profile"""
        # Register agent
        client.post("/hermes/agents/register", json={
            "agent_id": "profile-agent",
            "public_key": "profile-key",
            "capabilities": ["ai", "gpu"]
        })

        response = client.get("/hermes/agents/profile-agent/profile")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "profile-agent"
        assert "ai" in data["capabilities"]

    def test_heartbeat_updates_status(self, client: TestClient):
        """Test that heartbeat updates agent online status"""
        # Register agent
        client.post("/hermes/agents/register", json={
            "agent_id": "heartbeat-agent",
            "public_key": "hb-key",
            "capabilities": ["messaging"]
        })

        # Send heartbeat
        response = client.post("/hermes/agents/heartbeat-agent/heartbeat")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_hermes_stats(self, client: TestClient):
        """Test hermes statistics endpoint"""
        response = client.get("/hermes/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_messages" in data
        assert "registered_agents" in data
        assert "online_agents" in data

    def test_hermes_health(self, client: TestClient):
        """Test hermes health endpoint"""
        response = client.get("/hermes/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


@pytest.mark.integration
class TestHermesIntegration:
    """Integration tests for agent messaging"""

    def test_conversation_thread(self, client: TestClient):
        """Test conversation between two agents"""
        # Register agents
        client.post("/hermes/agents/register", json={
            "agent_id": "alice",
            "public_key": "alice-key",
            "capabilities": ["messaging"]
        })
        client.post("/hermes/agents/register", json={
            "agent_id": "bob",
            "public_key": "bob-key",
            "capabilities": ["messaging"]
        })

        # Alice sends message to Bob
        msg1 = client.post("/hermes/messages/send", json={
            "sender": "alice",
            "recipient": "bob",
            "content": "Hi Bob!",
            "message_type": "direct"
        }).json()["message"]

        # Bob replies
        msg2 = client.post("/hermes/messages/send", json={
            "sender": "bob",
            "recipient": "alice",
            "content": "Hi Alice!",
            "message_type": "direct",
            "reply_to": msg1["id"]
        }).json()["message"]

        # Verify both received messages
        alice_msgs = client.get("/hermes/messages/alice").json()
        bob_msgs = client.get("/hermes/messages/bob").json()

        assert any(m["sender"] == "bob" for m in alice_msgs["messages"])
        assert any(m["sender"] == "alice" for m in bob_msgs["messages"])
