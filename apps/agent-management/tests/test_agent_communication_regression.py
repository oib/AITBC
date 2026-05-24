"""
Regression tests for agent_communication.py
These tests capture current behavior before extracting shared logic.
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from app.services.agent_communication import (
    MessageType,
    ChannelType,
    MessageStatus,
    EncryptionType,
    Message,
    CommunicationChannel,
)


@pytest.mark.unit
class TestMessageType:
    """Test MessageType enum"""

    def test_message_type_values(self):
        """Test that all expected message type values exist"""
        assert MessageType.TEXT == "text"
        assert MessageType.DATA == "data"
        assert MessageType.TASK_REQUEST == "task_request"
        assert MessageType.TASK_RESPONSE == "task_response"
        assert MessageType.COLLABORATION == "collaboration"
        assert MessageType.NOTIFICATION == "notification"
        assert MessageType.SYSTEM == "system"
        assert MessageType.URGENT == "urgent"
        assert MessageType.BULK == "bulk"


@pytest.mark.unit
class TestChannelType:
    """Test ChannelType enum"""

    def test_channel_type_values(self):
        """Test that all expected channel type values exist"""
        assert ChannelType.DIRECT == "direct"
        assert ChannelType.GROUP == "group"
        assert ChannelType.BROADCAST == "broadcast"
        assert ChannelType.PRIVATE == "private"


@pytest.mark.unit
class TestMessageStatus:
    """Test MessageStatus enum"""

    def test_message_status_values(self):
        """Test that all expected message status values exist"""
        assert MessageStatus.PENDING == "pending"
        assert MessageStatus.DELIVERED == "delivered"
        assert MessageStatus.READ == "read"
        assert MessageStatus.FAILED == "failed"
        assert MessageStatus.EXPIRED == "expired"


@pytest.mark.unit
class TestEncryptionType:
    """Test EncryptionType enum"""

    def test_encryption_type_values(self):
        """Test that all expected encryption type values exist"""
        assert EncryptionType.AES256 == "aes256"
        assert EncryptionType.RSA == "rsa"
        assert EncryptionType.HYBRID == "hybrid"
        assert EncryptionType.NONE == "none"


@pytest.mark.unit
class TestMessage:
    """Test Message dataclass"""

    def test_message_creation(self):
        """Test creating a message with default values"""
        msg = Message(
            id="msg_123",
            sender="agent1",
            recipient="agent2",
            message_type=MessageType.TEXT,
            content=b"test content",
            encryption_key=b"key",
            encryption_type=EncryptionType.AES256,
            size=12,
            timestamp=datetime.now(timezone.utc)
        )
        
        assert msg.id == "msg_123"
        assert msg.sender == "agent1"
        assert msg.recipient == "agent2"
        assert msg.message_type == MessageType.TEXT
        assert msg.content == b"test content"
        assert msg.encryption_key == b"key"
        assert msg.encryption_type == EncryptionType.AES256
        assert msg.size == 12
        assert msg.status == MessageStatus.PENDING
        assert msg.paid is False
        assert msg.price == 0.0
        assert msg.metadata == {}
        assert msg.delivery_timestamp is None
        assert msg.read_timestamp is None
        assert msg.expires_at is None
        assert msg.reply_to is None
        assert msg.thread_id is None

    def test_message_with_optional_fields(self):
        """Test creating a message with optional fields set"""
        now = datetime.now(timezone.utc)
        msg = Message(
            id="msg_456",
            sender="agent1",
            recipient="agent2",
            message_type=MessageType.TASK_REQUEST,
            content=b"task data",
            encryption_key=b"key",
            encryption_type=EncryptionType.HYBRID,
            size=9,
            timestamp=now,
            delivery_timestamp=now + timedelta(seconds=1),
            read_timestamp=now + timedelta(seconds=2),
            status=MessageStatus.READ,
            paid=True,
            price=0.5,
            metadata={"priority": "high"},
            expires_at=now + timedelta(hours=1),
            reply_to="msg_123",
            thread_id="thread_1"
        )
        
        assert msg.delivery_timestamp is not None
        assert msg.read_timestamp is not None
        assert msg.status == MessageStatus.READ
        assert msg.paid is True
        assert msg.price == 0.5
        assert msg.metadata == {"priority": "high"}
        assert msg.expires_at is not None
        assert msg.reply_to == "msg_123"
        assert msg.thread_id == "thread_1"


@pytest.mark.unit
class TestCommunicationChannel:
    """Test CommunicationChannel dataclass"""

    def test_channel_creation(self):
        """Test creating a communication channel with default values"""
        now = datetime.now(timezone.utc)
        channel = CommunicationChannel(
            id="channel_123",
            agent1="agent1",
            agent2="agent2",
            channel_type=ChannelType.DIRECT,
            is_active=True,
            created_timestamp=now,
            last_activity=now,
            message_count=0
        )
        
        assert channel.id == "channel_123"
        assert channel.agent1 == "agent1"
        assert channel.agent2 == "agent2"
        assert channel.channel_type == ChannelType.DIRECT
        assert channel.is_active is True
        assert channel.message_count == 0
        assert channel.participants == []
        assert channel.encryption_enabled is True

    def test_channel_with_optional_fields(self):
        """Test creating a channel with optional fields set"""
        now = datetime.now(timezone.utc)
        channel = CommunicationChannel(
            id="channel_456",
            agent1="agent1",
            agent2="agent2",
            channel_type=ChannelType.GROUP,
            is_active=True,
            created_timestamp=now,
            last_activity=now,
            message_count=10,
            participants=["agent1", "agent2", "agent3"],
            encryption_enabled=False
        )
        
        assert channel.channel_type == ChannelType.GROUP
        assert channel.message_count == 10
        assert channel.participants == ["agent1", "agent2", "agent3"]
        assert channel.encryption_enabled is False
