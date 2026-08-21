"""
Delivery-guarantee tests for agent messaging:
- message status tracking (pending, delivered, read)
- idempotent sends by message_id
- SQLite fallback when Redis is unavailable
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_app.routers import messages as messages_router
from agent_app.storage.message_storage import MessageStorage


@pytest.fixture
def messaging_app():
    """A FastAPI app with only the messaging router."""
    app = FastAPI()
    app.include_router(messages_router.router)
    return app


@pytest.fixture
def fake_storage():
    """A MessageStorage whose store_message, get_message, and update_message_status succeed."""
    storage = MagicMock()
    storage.store_message = AsyncMock(return_value=True)
    storage.get_message = AsyncMock(return_value=None)
    storage.update_message_status = AsyncMock(return_value=True)
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


class TestDeliveryGuarantees:
    """Status tracking and idempotency via POST /send."""

    def test_send_returns_message_status(self, client, fake_connection_manager):
        """A delivered message reports status 'delivered'."""
        fake_connection_manager.send_personal_message.return_value = True
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
        assert data["message_status"] == "delivered"
        assert data["message_id"].startswith("msg_")

    def test_send_pending_when_offline(self, client, fake_connection_manager):
        """A message that cannot be delivered over WebSocket reports status 'pending'."""
        fake_connection_manager.send_personal_message.return_value = False
        payload = {
            "sender": "agent-a",
            "recipient": "agent-b",
            "content": {"text": "hello"},
            "message_type": "direct",
            "encrypt": False,
            "priority": "normal",
        }

        response = client.post("/api/v1/agent/messages/send", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["ws_delivered"] is False
        assert data["message_status"] == "pending"

    def test_send_is_idempotent(self, client, fake_storage, fake_connection_manager):
        """Re-sending with the same message_id returns the stored record."""
        existing = {
            "sender": "agent-a",
            "recipient": "agent-b",
            "encrypted": "False",
            "ws_delivered": "True",
            "status": "delivered",
            "sent_at": "2026-08-21T12:00:00+00:00",
        }
        fake_storage.get_message.return_value = existing

        payload = {
            "sender": "agent-a",
            "recipient": "agent-b",
            "content": {"text": "hello"},
            "message_type": "direct",
            "encrypt": False,
            "message_id": "msg-idempotent-1",
        }

        response = client.post("/api/v1/agent/messages/send", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["message_id"] == "msg-idempotent-1"
        assert data["ws_delivered"] is True
        assert data["message_status"] == "delivered"

        fake_storage.store_message.assert_not_called()
        fake_connection_manager.send_personal_message.assert_not_called()


class TestReadStatus:
    """Marking messages as read."""

    def test_mark_message_read(self, client, fake_storage):
        """POST /id/{message_id}/read updates status to 'read'."""
        fake_storage.get_message.return_value = {
            "message_id": "msg-read-1",
            "sender": "agent-a",
            "recipient": "agent-b",
            "status": "delivered",
        }

        response = client.post("/api/v1/agent/messages/id/msg-read-1/read")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["message_id"] == "msg-read-1"
        assert data["message_status"] == "read"
        fake_storage.update_message_status.assert_called_once_with("msg-read-1", "read")


class TestSQLiteFallback:
    """SQLite fallback for MessageStorage when Redis is unavailable."""

    @pytest.fixture
    def sqlite_storage(self, tmp_path):
        db_path = tmp_path / "messages.db"
        storage = MessageStorage(
            redis_url="redis://localhost:1",
            database_url=f"sqlite:///{db_path}",
        )
        asyncio.run(storage.start())
        storage.redis = None  # Force SQLite-only path for all operations.
        yield storage
        asyncio.run(storage.stop())

    def test_store_and_retrieve_without_redis(self, sqlite_storage):
        """Messages can be stored and retrieved using SQLite only."""
        message_id = "msg-sqlite-1"
        data = {
            "sender": "agent-a",
            "recipient": "agent-b",
            "content": "hello",
            "timestamp": "2026-08-21T12:00:00+00:00",
            "status": "pending",
        }
        stored = asyncio.run(sqlite_storage.store_message(message_id, data))
        assert stored is True

        fetched = asyncio.run(sqlite_storage.get_message(message_id))
        assert fetched is not None
        assert fetched["sender"] == "agent-a"
        assert fetched["recipient"] == "agent-b"
        assert fetched["status"] == "pending"

    def test_update_status_without_redis(self, sqlite_storage):
        """Message status can be updated via SQLite."""
        message_id = "msg-sqlite-2"
        data = {
            "sender": "agent-a",
            "recipient": "agent-b",
            "content": "hello",
            "timestamp": "2026-08-21T12:00:00+00:00",
            "status": "pending",
        }
        asyncio.run(sqlite_storage.store_message(message_id, data))
        asyncio.run(sqlite_storage.update_message_status(message_id, "delivered"))

        fetched = asyncio.run(sqlite_storage.get_message(message_id))
        assert fetched["status"] == "delivered"

    def test_get_messages_by_receiver_without_redis(self, sqlite_storage):
        """Inbox queries fall back to SQLite."""
        for i in range(3):
            asyncio.run(
                sqlite_storage.store_message(
                    f"msg-recv-{i}",
                    {
                        "sender": "agent-a",
                        "recipient": "agent-b",
                        "content": f"msg {i}",
                        "timestamp": f"2026-08-21T12:00:0{i}+00:00",
                        "status": "pending",
                    },
                )
            )

        messages = asyncio.run(sqlite_storage.get_messages_by_receiver("agent-b", limit=10))
        assert len(messages) == 3
