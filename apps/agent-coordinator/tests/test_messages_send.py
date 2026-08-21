"""
Regression tests for agent messaging REST send with WebSocket first delivery.
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_app.routers import messages as messages_router


@pytest.fixture
def messaging_app():
    """A FastAPI app with only the messaging router."""
    app = FastAPI()
    app.include_router(messages_router.router)
    return app


@pytest.fixture
def fake_storage():
    """A MessageStorage whose store_message always succeeds."""
    storage = MagicMock()
    storage.store_message = AsyncMock(return_value=True)
    return storage


@pytest.fixture
def fake_connection_manager():
    """A ConnectionManager whose send_personal_message can be toggled."""
    cm = MagicMock()
    cm.send_personal_message = AsyncMock(return_value=True)
    return cm


@pytest.fixture
def client(
    monkeypatch, tmp_path, messaging_app, fake_storage, fake_connection_manager
):
    """TestClient with messaging dependencies patched."""
    os.environ["AITBC_ENABLE_RATE_LIMITING"] = "false"
    monkeypatch.setattr(messages_router, "state", MagicMock(message_storage=fake_storage))
    monkeypatch.setattr(messages_router, "get_connection_manager", lambda: fake_connection_manager)
    return TestClient(messaging_app)


class TestMessageSend:
    """POST /api/v1/agent/messages/send tries WebSocket then Redis."""

    def test_send_delivers_to_online_recipient(self, client, fake_storage, fake_connection_manager):
        """When recipient is connected, ws_delivered is true and message is stored."""
        payload = {
            "sender": "agent-a",
            "recipient": "agent-b",
            "content": {"text": "hello"},
            "message_type": "direct",
            "encrypt": False,
            "priority": "high",
        }

        response = client.post("/api/v1/agent/messages/send", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["ws_delivered"] is True
        assert data["sender"] == "agent-a"
        assert data["recipient"] == "agent-b"

        fake_connection_manager.send_personal_message.assert_called_once()
        call_args = fake_connection_manager.send_personal_message.call_args
        assert call_args[0][1] == "agent-b"  # recipient
        message_data = call_args[0][0]
        assert message_data["sender"] == "agent-a"
        assert message_data["recipient"] == "agent-b"
        assert message_data["message_type"] == "direct"
        assert message_data["priority"] == "high"

        fake_storage.store_message.assert_called_once()
        stored_message_id, stored_data = fake_storage.store_message.call_args[0]
        assert stored_data["sender"] == "agent-a"
        assert stored_data["recipient"] == "agent-b"
        assert stored_data["priority"] == "high"

    def test_send_falls_back_to_storage_when_recipient_offline(
        self, client, fake_storage, fake_connection_manager
    ):
        """When recipient is not connected, message is still stored."""
        fake_connection_manager.send_personal_message.return_value = False

        payload = {
            "sender": "agent-a",
            "recipient": "agent-b",
            "content": {"text": "hello"},
            "encrypt": False,
            "priority": "normal",
        }

        response = client.post("/api/v1/agent/messages/send", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["ws_delivered"] is False
        fake_storage.store_message.assert_called_once()

    def test_send_indexes_encrypted_payload(self, client, fake_storage, fake_connection_manager, monkeypatch):
        """Encrypted messages carry sender/recipient/priority keys for storage and delivery."""
        from agent_app.encryption import EncryptedMessage

        fake_encryptor = MagicMock()
        fake_encryptor.encrypt_message.return_value = EncryptedMessage(
            ciphertext=b"ciphertext",
            session_key=b"session-key",
            nonce=b"nonce",
            signature=b"signature",
            sender_id="agent-a",
        )
        monkeypatch.setattr(messages_router, "get_encryptor", lambda: fake_encryptor)

        payload = {
            "sender": "agent-a",
            "recipient": "agent-b",
            "content": {"text": "secret"},
            "message_type": "direct",
            "encrypt": True,
            "priority": "critical",
        }

        response = client.post("/api/v1/agent/messages/send", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["ws_delivered"] is True
        assert data["encrypted"] is True

        fake_storage.store_message.assert_called_once()
        stored_message_id, stored_data = fake_storage.store_message.call_args[0]
        assert stored_data["sender"] == "agent-a"
        assert stored_data["recipient"] == "agent-b"
        assert stored_data["priority"] == "critical"
        assert stored_data["encrypted"] == "True"  # stringified for Redis hash


class TestMessageStorageIndexing:
    """MessageStorage indexes by sender_id/receiver_id as well as sender/recipient."""

    def test_store_message_uses_sender_id_and_receiver_id(self):
        """If the keys are sender_id/receiver_id, the index sets are still updated."""
        from agent_app.storage.message_storage import MessageStorage

        storage = MessageStorage(redis_url="redis://localhost:6379/1")
        storage.redis = AsyncMock()

        asyncio.run(
            storage.store_message(
                "msg-1",
                {
                    "sender_id": "agent-a",
                    "receiver_id": "agent-b",
                    "content": "hello",
                    "timestamp": "2026-08-21T12:00:00+00:00",
                },
            )
        )

        storage.redis.sadd.assert_any_call("messages:sender:agent-a", "msg-1")
        storage.redis.sadd.assert_any_call("messages:receiver:agent-b", "msg-1")
