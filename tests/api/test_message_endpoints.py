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


import pytest  # noqa: E402
from app.routers.messages import SendMessageRequest, SubscribeRequest  # noqa: E402


class TestSendMessageRequest:
    """Test send message request model"""

    def test_send_message_request_creation(self):  # noqa: F811
        """Test creating a send message request"""
        request = SendMessageRequest(
            sender="agent_001",
            recipient="agent_002",
            content={"message": "Hello"},
            message_type="direct",
            encrypt=True,
            priority="normal",
            ttl=300,
        )

        assert request.sender == "agent_001"
        assert request.recipient == "agent_002"
        assert request.content == {"message": "Hello"}
        assert request.encrypt is True
        assert request.priority == "normal"
        assert request.ttl == 300

    def test_send_message_request_defaults(self):  # noqa: F811
        """Test send message request with defaults"""
        request = SendMessageRequest(sender="agent_001", recipient="agent_002", content={"message": "Hello"})

        assert request.message_type == "direct"
        assert request.encrypt is True
        assert request.priority == "normal"
        assert request.ttl == 300

    def test_send_message_request_unencrypted(self):  # noqa: F811
        """Test send message request without encryption"""
        request = SendMessageRequest(sender="agent_001", recipient="agent_002", content={"message": "Hello"}, encrypt=False)

        assert request.encrypt is False


class TestSubscribeRequest:
    """Test subscribe request model"""

    def test_subscribe_request_creation(self):  # noqa: F811
        """Test creating a subscribe request"""
        request = SubscribeRequest(agent_id="agent_001", topic="notifications", filter={"type": "alert"})

        assert request.agent_id == "agent_001"
        assert request.topic == "notifications"
        assert request.filter == {"type": "alert"}

    def test_subscribe_request_defaults(self):  # noqa: F811
        """Test subscribe request with defaults"""
        request = SubscribeRequest(agent_id="agent_001", topic="notifications")

        assert request.filter == {}

    def test_subscribe_request_complex_filter(self):  # noqa: F811
        """Test subscribe request with complex filter"""
        request = SubscribeRequest(
            agent_id="agent_002",
            topic="market_updates",
            filter={"priority": "high", "sender": "marketplace", "types": ["offer", "bid", "ask"]},
        )

        assert len(request.filter) == 3
        assert "priority" in request.filter
        assert "types" in request.filter
        assert len(request.filter["types"]) == 3

    def test_send_message_request_with_all_fields(self):  # noqa: F811
        """Test send message request with all fields"""
        request = SendMessageRequest(
            sender="sender_all",
            recipient="recipient_all",
            content={"task": "training", "model": "gpt-4"},
            message_type="task_assignment",
            priority="high",
            ttl=3600,
        )

        assert request.sender == "sender_all"
        assert request.recipient == "recipient_all"
        assert request.message_type == "task_assignment"
        assert request.priority == "high"
        assert request.ttl == 3600

    def test_subscribe_request_empty_filters(self):  # noqa: F811
        """Test subscribe request with empty filter criteria"""
        request = SubscribeRequest(agent_id="agent_empty", topic="notifications", filter={})

        assert request.filter == {}
        assert request.topic == "notifications"

    def test_send_message_request_minimal(self):  # noqa: F811
        """Test send message request with minimal fields"""
        request = SendMessageRequest(sender="sender_minimal", recipient="recipient_minimal", content={"data": "test"})

        assert request.sender == "sender_minimal"
        assert request.recipient == "recipient_minimal"
        assert request.content == {"data": "test"}
        assert request.message_type == "direct"  # default

    def test_subscribe_request_with_topic(self):  # noqa: F811
        """Test subscribe request with single topic"""
        request = SubscribeRequest(agent_id="agent_topic", topic="alerts")

        assert request.agent_id == "agent_topic"
        assert request.topic == "alerts"
        assert request.filter == {}  # default

    def test_send_message_request_with_broadcast_type(self):  # noqa: F811
        """Test send message request with broadcast message type"""
        request = SendMessageRequest(
            sender="sender_broadcast", recipient="*", content={"data": "broadcast message"}, message_type="broadcast"
        )

        assert request.message_type == "broadcast"
        assert request.recipient == "*"

    def test_subscribe_request_with_multiple_topics(self):  # noqa: F811
        """Test subscribe request with multiple filter topics"""
        request = SubscribeRequest(
            agent_id="agent_multi_topic",
            topic="tasks",
            filter={"topics": ["training", "inference", "storage"], "priority": "high"},
        )

        assert len(request.filter["topics"]) == 3
        assert "training" in request.filter["topics"]

    def test_send_message_request_with_zero_ttl(self):  # noqa: F811
        """Test send message request with zero TTL"""
        request = SendMessageRequest(
            sender="sender_zero_ttl", recipient="recipient_zero_ttl", content={"data": "immediate message"}, ttl=0
        )

        assert request.ttl == 0

    def test_subscribe_request_with_numeric_filter(self):  # noqa: F811
        """Test subscribe request with numeric filter values"""
        request = SubscribeRequest(
            agent_id="agent_numeric", topic="tasks", filter={"min_priority": 1, "max_priority": 10, "timeout": 300}
        )

        assert request.filter["min_priority"] == 1
        assert request.filter["timeout"] == 300

    def test_send_message_request_with_long_content(self):  # noqa: F811
        """Test send message request with long content"""
        long_content = "x" * 10000
        request = SendMessageRequest(
            sender="sender_long", recipient="recipient_long", content={"data": long_content}, ttl=3600
        )

        assert len(request.content["data"]) == 10000

    def test_subscribe_request_with_boolean_filter(self):  # noqa: F811
        """Test subscribe request with boolean filter values"""
        request = SubscribeRequest(agent_id="agent_bool", topic="alerts", filter={"enabled": True, "urgent": False})

        assert request.filter["enabled"] is True
        assert request.filter["urgent"] is False

    def test_send_message_request_with_high_ttl(self):  # noqa: F811
        """Test send message request with high TTL"""
        request = SendMessageRequest(
            sender="sender_high_ttl",
            recipient="recipient_high_ttl",
            content={"data": "persistent message"},
            ttl=86400,  # 24 hours
        )

        assert request.ttl == 86400

    def test_subscribe_request_with_nested_filter(self):  # noqa: F811
        """Test subscribe request with nested filter structure"""
        request = SubscribeRequest(
            agent_id="agent_nested", topic="tasks", filter={"priority": {"min": 1, "max": 10}, "type": "urgent"}
        )

        assert "priority" in request.filter
        assert request.filter["type"] == "urgent"

    def test_send_message_request_with_special_characters_in_content(self):  # noqa: F811
        """Test send message request with special characters in content"""
        request = SendMessageRequest(
            sender="sender_special_chars",
            recipient="recipient_special",
            content={"data": "Hello! @#$%^&*()_+-=[]{}|;':\",./<>?"},
            ttl=3600,
        )

        assert "@" in request.content["data"]

    def test_subscribe_request_with_array_filter(self):  # noqa: F811
        """Test subscribe request with array filter values"""
        request = SubscribeRequest(
            agent_id="agent_array",
            topic="tasks",
            filter={"allowed_priorities": ["low", "normal", "high"], "blocked_agents": ["agent_1", "agent_2"]},
        )

        assert isinstance(request.filter["allowed_priorities"], list)
        assert len(request.filter["blocked_agents"]) == 2

    def test_send_message_request_with_unicode_content(self):  # noqa: F811
        """Test send message request with unicode content"""
        request = SendMessageRequest(
            sender="sender_unicode", recipient="recipient_unicode", content={"data": "Hello 世界 🌍"}, ttl=3600
        )

        assert "世界" in request.content["data"]

    def test_subscribe_request_with_empty_filter(self):  # noqa: F811
        """Test subscribe request with empty filter"""
        request = SubscribeRequest(agent_id="agent_empty_filter", topic="general", filter={})

        assert len(request.filter) == 0

    def test_send_message_request_with_numeric_content(self):  # noqa: F811
        """Test send message request with numeric content"""
        request = SendMessageRequest(
            sender="sender_numeric", recipient="recipient_numeric", content={"value": 12345, "count": 42}, ttl=3600
        )

        assert request.content["value"] == 12345
        assert request.content["count"] == 42

    def test_subscribe_request_with_topic_validation(self):  # noqa: F811
        """Test subscribe request with topic field"""
        request = SubscribeRequest(agent_id="agent_topic", topic="alerts", filter={"level": "high"})

        assert request.topic == "alerts"
        assert len(request.topic) > 0

    def test_send_message_request_with_zero_ttl(self):  # noqa: F811
        """Test send message request with zero TTL (edge case)"""
        request = SendMessageRequest(sender="sender_zero_ttl", recipient="recipient_zero", content={"data": "test"}, ttl=0)

        assert request.ttl == 0

    def test_subscribe_request_with_numeric_agent_id(self):  # noqa: F811
        """Test subscribe request with numeric characters in agent_id"""
        request = SubscribeRequest(agent_id="agent_12345", topic="notifications", filter={"type": "info"})

        assert "12345" in request.agent_id

    def test_send_message_request_with_empty_content(self):  # noqa: F811
        """Test send message request with empty content (edge case)"""
        request = SendMessageRequest(sender="sender_empty", recipient="recipient_empty", content={}, ttl=3600)

        assert len(request.content) == 0

    def test_subscribe_request_with_special_topic(self):  # noqa: F811
        """Test subscribe request with special characters in topic"""
        request = SubscribeRequest(agent_id="agent_special_topic", topic="special-topic_@123", filter={"type": "alert"})

        assert "-" in request.topic
        assert "_" in request.topic
        assert "@" in request.topic

    def test_send_message_request_with_nested_content(self):  # noqa: F811
        """Test send message request with nested content structure"""
        request = SendMessageRequest(
            sender="sender_nested", recipient="recipient_nested", content={"data": {"nested": {"deep": "value"}}}, ttl=3600
        )

        assert "nested" in request.content["data"]

    def test_subscribe_request_with_empty_filter(self):  # noqa: F811
        """Test subscribe request with empty filter"""
        request = SubscribeRequest(agent_id="agent_empty_filter", topic="general", filter={})

        assert len(request.filter) == 0

    def test_send_message_request_with_boolean_content(self):  # noqa: F811
        """Test send message request with boolean content"""
        request = SendMessageRequest(
            sender="sender_boolean", recipient="recipient_boolean", content={"enabled": True, "active": False}, ttl=3600
        )

        assert request.content["enabled"] is True
        assert request.content["active"] is False

    def test_subscribe_request_with_numeric_filter_values(self):  # noqa: F811
        """Test subscribe request with numeric filter values"""
        request = SubscribeRequest(agent_id="agent_numeric_filter", topic="alerts", filter={"level": 5, "priority": 10})

        assert request.filter["level"] == 5
        assert request.filter["priority"] == 10

    def test_send_message_request_with_array_content(self):  # noqa: F811
        """Test send message request with array content"""
        request = SendMessageRequest(
            sender="sender_array", recipient="recipient_array", content={"items": [1, 2, 3, 4, 5]}, ttl=3600
        )

        assert isinstance(request.content["items"], list)
        assert len(request.content["items"]) == 5

    def test_subscribe_request_with_multiple_filters(self):  # noqa: F811
        """Test subscribe request with multiple filter conditions"""
        request = SubscribeRequest(
            agent_id="agent_multi_filter", topic="alerts", filter={"type": "error", "level": "critical", "source": "system"}
        )

        assert len(request.filter) == 3

    def test_send_message_request_with_null_content(self):  # noqa: F811
        """Test send message request with null content value"""
        request = SendMessageRequest(sender="sender_null", recipient="recipient_null", content={"value": None}, ttl=3600)

        assert request.content["value"] is None

    def test_subscribe_request_with_boolean_filter(self):  # noqa: F811
        """Test subscribe request with boolean filter values"""
        request = SubscribeRequest(agent_id="agent_bool_filter", topic="alerts", filter={"enabled": True, "disabled": False})

        assert request.filter["enabled"] is True
        assert request.filter["disabled"] is False

    def test_send_message_request_with_string_content(self):  # noqa: F811
        """Test send message request with string content"""
        request = SendMessageRequest(
            sender="sender_string", recipient="recipient_string", content={"message": "Hello, world!"}, ttl=3600
        )

        assert isinstance(request.content["message"], str)

    def test_subscribe_request_with_string_filter_value(self):  # noqa: F811
        """Test subscribe request with string filter value"""
        request = SubscribeRequest(agent_id="agent_string_filter", topic="alerts", filter={"type": "error"})

        assert isinstance(request.filter["type"], str)

    def test_send_message_request_with_numeric_content(self):  # noqa: F811
        """Test send message request with numeric content"""
        request = SendMessageRequest(
            sender="sender_numeric", recipient="recipient_numeric", content={"value": 12345}, ttl=3600
        )

        assert isinstance(request.content["value"], int)

    def test_subscribe_request_with_numeric_filter_value(self):  # noqa: F811
        """Test subscribe request with numeric filter value"""
        request = SubscribeRequest(agent_id="agent_numeric_filter", topic="alerts", filter={"priority": 1})

        assert isinstance(request.filter["priority"], int)

    def test_send_message_request_with_empty_recipient(self):  # noqa: F811
        """Test send message request with empty recipient (edge case)"""
        request = SendMessageRequest(sender="sender_empty_recipient", recipient="", content={"message": "Hello"}, ttl=3600)

        assert request.recipient == ""

    def test_subscribe_request_with_empty_topic(self):  # noqa: F811
        """Test subscribe request with empty topic (edge case)"""
        request = SubscribeRequest(agent_id="agent_empty_topic", topic="", filter={"type": "error"})

        assert request.topic == ""

    def test_send_message_request_with_empty_sender(self):  # noqa: F811
        """Test send message request with empty sender (edge case)"""
        request = SendMessageRequest(sender="", recipient="recipient_empty_sender", content={"message": "Hello"}, ttl=3600)

        assert request.sender == ""

    def test_subscribe_request_with_empty_filter(self):  # noqa: F811
        """Test subscribe request with empty filter (edge case)"""
        request = SubscribeRequest(agent_id="agent_empty_filter", topic="alerts", filter={})

        assert len(request.filter) == 0

    def test_send_message_request_with_empty_content(self):  # noqa: F811
        """Test send message request with empty content (edge case)"""
        request = SendMessageRequest(sender="sender_empty_content", recipient="recipient_empty_content", content={}, ttl=3600)

        assert len(request.content) == 0

    def test_subscribe_request_with_empty_agent_id(self):  # noqa: F811
        """Test subscribe request with empty agent_id (edge case)"""
        request = SubscribeRequest(agent_id="", topic="alerts", filter={"type": "error"})

        assert request.agent_id == ""

    def test_send_message_request_with_zero_ttl(self):  # noqa: F811
        """Test send message request with zero TTL (edge case)"""
        request = SendMessageRequest(
            sender="sender_zero_ttl", recipient="recipient_zero_ttl", content={"message": "Hello"}, ttl=0
        )

        assert request.ttl == 0

    def test_subscribe_request_with_numeric_agent_id(self):  # noqa: F811
        """Test subscribe request with numeric characters in agent_id"""
        request = SubscribeRequest(agent_id="agent123", topic="alerts", filter={"type": "error"})

        assert "123" in request.agent_id

    def test_send_message_request_with_numeric_sender(self):  # noqa: F811
        """Test send message request with numeric characters in sender"""
        request = SendMessageRequest(sender="sender123", recipient="recipient", content={"message": "Hello"}, ttl=3600)

        assert "123" in request.sender

    def test_subscribe_request_with_mixed_case_topic(self):  # noqa: F811
        """Test subscribe request with mixed case topic"""
        request = SubscribeRequest(agent_id="agent", topic="Alerts", filter={"type": "error"})

        assert "Alerts" == request.topic

    def test_send_message_request_with_numeric_recipient(self):  # noqa: F811
        """Test send message request with numeric characters in recipient"""
        request = SendMessageRequest(sender="sender", recipient="recipient123", content={"message": "Hello"}, ttl=3600)

        assert "123" in request.recipient

    def test_subscribe_request_with_numeric_filter_value(self):  # noqa: F811
        """Test subscribe request with numeric characters in filter value"""
        request = SubscribeRequest(agent_id="agent", topic="alerts", filter={"type": "error123"})

        assert "123" in request.filter["type"]

    def test_send_message_request_with_empty_sender(self):  # noqa: F811
        """Test send message request with empty sender (edge case)"""
        request = SendMessageRequest(sender="", recipient="recipient", content={"message": "Hello"}, ttl=3600)

        assert request.sender == ""

    def test_subscribe_request_with_empty_topic(self):  # noqa: F811
        """Test subscribe request with empty topic (edge case)"""
        request = SubscribeRequest(agent_id="agent", topic="", filter={"type": "error"})

        assert request.topic == ""

    def test_send_message_request_with_single_character_sender(self):  # noqa: F811
        """Test send message request with single character sender"""
        request = SendMessageRequest(sender="S", recipient="recipient", content={"message": "Hello"}, ttl=3600)

        assert len(request.sender) == 1

    def test_subscribe_request_with_single_character_topic(self):  # noqa: F811
        """Test subscribe request with single character topic"""
        request = SubscribeRequest(agent_id="agent", topic="A", filter={"type": "error"})

        assert len(request.topic) == 1

    def test_send_message_request_with_numeric_sender(self):  # noqa: F811
        """Test send message request with numeric sender (edge case)"""
        request = SendMessageRequest(sender="123", recipient="recipient", content={"message": "Hello"}, ttl=3600)

        assert request.sender == "123"

    def test_subscribe_request_with_numeric_topic(self):  # noqa: F811
        """Test subscribe request with numeric topic (edge case)"""
        request = SubscribeRequest(agent_id="agent", topic="123", filter={"type": "error"})

        assert request.topic == "123"

    def test_send_message_request_with_special_characters_sender(self):  # noqa: F811
        """Test send message request with special characters in sender"""
        request = SendMessageRequest(sender="sender@#$", recipient="recipient", content={"message": "Hello"}, ttl=3600)

        assert "@" in request.sender
        assert "#" in request.sender
        assert "$" in request.sender

    def test_subscribe_request_with_special_characters_topic(self):  # noqa: F811
        """Test subscribe request with special characters in topic"""
        request = SubscribeRequest(agent_id="agent", topic="topic@#$", filter={"type": "error"})

        assert "@" in request.topic
        assert "#" in request.topic
        assert "$" in request.topic

    def test_send_message_request_with_spaces_sender(self):  # noqa: F811
        """Test send message request with spaces in sender (edge case)"""
        request = SendMessageRequest(sender="sender 123", recipient="recipient", content={"message": "Hello"}, ttl=3600)

        assert " " in request.sender

    def test_subscribe_request_with_spaces_topic(self):  # noqa: F811
        """Test subscribe request with spaces in topic (edge case)"""
        request = SubscribeRequest(agent_id="agent", topic="topic 123", filter={"type": "error"})

        assert " " in request.topic

    def test_send_message_request_with_underscore_sender(self):  # noqa: F811
        """Test send message request with underscore in sender"""
        request = SendMessageRequest(sender="sender_123", recipient="recipient", content={"message": "Hello"}, ttl=3600)

        assert "_" in request.sender

    def test_subscribe_request_with_underscore_topic(self):  # noqa: F811
        """Test subscribe request with underscore in topic"""
        request = SubscribeRequest(agent_id="agent", topic="topic_123", filter={"type": "error"})

        assert "_" in request.topic

    def test_send_message_request_with_colon_sender(self):  # noqa: F811
        """Test send message request with colon in sender"""
        request = SendMessageRequest(sender="sender:123", recipient="recipient", content={"message": "Hello"}, ttl=3600)

        assert ":" in request.sender

    def test_subscribe_request_with_colon_topic(self):  # noqa: F811
        """Test subscribe request with colon in topic"""
        request = SubscribeRequest(agent_id="agent", topic="topic:123", filter={"type": "error"})

        assert ":" in request.topic

    def test_send_message_request_with_equals_sender(self):  # noqa: F811
        """Test send message request with equals in sender"""
        request = SendMessageRequest(sender="sender=123", recipient="recipient", content={"message": "Hello"}, ttl=3600)

        assert "=" in request.sender

    def test_subscribe_request_with_equals_topic(self):  # noqa: F811
        """Test subscribe request with equals in topic"""
        request = SubscribeRequest(agent_id="agent", topic="topic=123", filter={"type": "error"})

        assert "=" in request.topic

    def test_send_message_request_with_bracket_sender(self):  # noqa: F811
        """Test send message request with bracket in sender"""
        request = SendMessageRequest(sender="sender[123]", recipient="recipient", content={"message": "Hello"}, ttl=3600)

        assert "[" in request.sender
        assert "]" in request.sender

    def test_subscribe_request_with_bracket_topic(self):  # noqa: F811
        """Test subscribe request with bracket in topic"""
        request = SubscribeRequest(agent_id="agent", topic="topic[123]", filter={"type": "error"})

        assert "[" in request.topic
        assert "]" in request.topic

    def test_send_message_request_with_curly_bracket_sender(self):  # noqa: F811
        """Test send message request with curly bracket in sender"""
        request = SendMessageRequest(sender="sender{123}", recipient="recipient", content={"message": "Hello"}, ttl=3600)

        assert "{" in request.sender
        assert "}" in request.sender

    def test_subscribe_request_with_curly_bracket_topic(self):  # noqa: F811
        """Test subscribe request with curly bracket in topic"""
        request = SubscribeRequest(agent_id="agent", topic="topic{123}", filter={"type": "error"})

        assert "{" in request.topic
        assert "}" in request.topic

    def test_send_message_request_with_dollar_sender(self):  # noqa: F811
        """Test send message request with dollar in sender"""
        request = SendMessageRequest(sender="sender$123", recipient="recipient", content={"message": "Hello"}, ttl=3600)

        assert "$" in request.sender

    def test_subscribe_request_with_dollar_topic(self):  # noqa: F811
        """Test subscribe request with dollar in topic"""
        request = SubscribeRequest(agent_id="agent", topic="topic$123", filter={"type": "error"})

        assert "$" in request.topic

    def test_subscribe_request_with_hash_topic(self):  # noqa: F811
        """Test subscribe request with hash in topic"""
        request = SubscribeRequest(agent_id="agent", topic="topic#123", filter={"type": "error"})

        assert "#" in request.topic

    def test_subscribe_request_with_exclamation_topic(self):  # noqa: F811
        """Test subscribe request with exclamation in topic"""
        request = SubscribeRequest(agent_id="agent", topic="topic!123", filter={"type": "error"})

        assert "!" in request.topic

    def test_subscribe_request_with_asterisk_topic(self):  # noqa: F811
        """Test subscribe request with asterisk in topic"""
        request = SubscribeRequest(agent_id="agent", topic="topic*123", filter={"type": "error"})

        assert "*" in request.topic

    def test_subscribe_request_with_equals_topic(self):  # noqa: F811
        """Test subscribe request with equals in topic"""
        request = SubscribeRequest(agent_id="agent", topic="topic=123", filter={"type": "error"})

        assert "=" in request.topic

    def test_subscribe_request_with_bracket_topic(self):  # noqa: F811
        """Test subscribe request with bracket in topic"""
        request = SubscribeRequest(agent_id="agent", topic="topic[123]", filter={"type": "error"})

        assert "[" in request.topic

    def test_subscribe_request_with_curly_brace_topic(self):  # noqa: F811
        """Test subscribe request with curly brace in topic"""
        request = SubscribeRequest(agent_id="agent", topic="topic{123}", filter={"type": "error"})

        assert "{" in request.topic

    def test_subscribe_request_with_pipe_topic(self):  # noqa: F811
        """Test subscribe request with pipe in topic"""
        request = SubscribeRequest(agent_id="agent", topic="topic|123", filter={"type": "error"})

        assert "|" in request.topic


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
