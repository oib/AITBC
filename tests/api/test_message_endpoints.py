"""
API Endpoint Tests
Tests for agent messaging API endpoints
"""

import sys
from pathlib import Path

# Add coordinator path for imports
coordinator_path = Path("/opt/aitbc/apps/agent-coordinator/src")
if str(coordinator_path) not in sys.path:
    sys.path.insert(0, str(coordinator_path))

import pytest
from datetime import UTC, datetime

from app.routers.messages import SendMessageRequest, SubscribeRequest


class TestSendMessageRequest:
    """Test send message request model"""

    def test_send_message_request_creation(self):
        """Test creating a send message request"""
        request = SendMessageRequest(
            sender="agent_001",
            recipient="agent_002",
            content={"message": "Hello"},
            message_type="direct",
            encrypt=True,
            priority="normal",
            ttl=300
        )
        
        assert request.sender == "agent_001"
        assert request.recipient == "agent_002"
        assert request.content == {"message": "Hello"}
        assert request.encrypt is True
        assert request.priority == "normal"
        assert request.ttl == 300

    def test_send_message_request_defaults(self):
        """Test send message request with defaults"""
        request = SendMessageRequest(
            sender="agent_001",
            recipient="agent_002",
            content={"message": "Hello"}
        )
        
        assert request.message_type == "direct"
        assert request.encrypt is True
        assert request.priority == "normal"
        assert request.ttl == 300

    def test_send_message_request_unencrypted(self):
        """Test send message request without encryption"""
        request = SendMessageRequest(
            sender="agent_001",
            recipient="agent_002",
            content={"message": "Hello"},
            encrypt=False
        )
        
        assert request.encrypt is False


class TestSubscribeRequest:
    """Test subscribe request model"""

    def test_subscribe_request_creation(self):
        """Test creating a subscribe request"""
        request = SubscribeRequest(
            agent_id="agent_001",
            topic="notifications",
            filter={"type": "alert"}
        )
        
        assert request.agent_id == "agent_001"
        assert request.topic == "notifications"
        assert request.filter == {"type": "alert"}

    def test_subscribe_request_defaults(self):
        """Test subscribe request with defaults"""
        request = SubscribeRequest(
            agent_id="agent_001",
            topic="notifications"
        )
        
        assert request.filter == {}

    def test_subscribe_request_complex_filter(self):
        """Test subscribe request with complex filter"""
        request = SubscribeRequest(
            agent_id="agent_002",
            topic="market_updates",
            filter={
                "priority": "high",
                "sender": "marketplace",
                "types": ["offer", "bid", "ask"]
            }
        )
        
        assert len(request.filter) == 3
        assert "priority" in request.filter
        assert "types" in request.filter
        assert len(request.filter["types"]) == 3

    def test_send_message_request_with_all_fields(self):
        """Test send message request with all fields"""
        request = SendMessageRequest(
            sender="sender_all",
            recipient="recipient_all",
            content={"task": "training", "model": "gpt-4"},
            message_type="task_assignment",
            priority="high",
            ttl=3600
        )
        
        assert request.sender == "sender_all"
        assert request.recipient == "recipient_all"
        assert request.message_type == "task_assignment"
        assert request.priority == "high"
        assert request.ttl == 3600

    def test_subscribe_request_empty_filters(self):
        """Test subscribe request with empty filter criteria"""
        request = SubscribeRequest(
            agent_id="agent_empty",
            topic="notifications",
            filter={}
        )
        
        assert request.filter == {}
        assert request.topic == "notifications"

    def test_send_message_request_minimal(self):
        """Test send message request with minimal fields"""
        request = SendMessageRequest(
            sender="sender_minimal",
            recipient="recipient_minimal",
            content={"data": "test"}
        )
        
        assert request.sender == "sender_minimal"
        assert request.recipient == "recipient_minimal"
        assert request.content == {"data": "test"}
        assert request.message_type == "direct"  # default

    def test_subscribe_request_with_topic(self):
        """Test subscribe request with single topic"""
        request = SubscribeRequest(
            agent_id="agent_topic",
            topic="alerts"
        )
        
        assert request.agent_id == "agent_topic"
        assert request.topic == "alerts"
        assert request.filter == {}  # default


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
