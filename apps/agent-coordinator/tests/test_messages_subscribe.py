"""
Tests for agent messaging REST subscribe/unsubscribe and WebSocket restore.
"""
from __future__ import annotations

import asyncio
import json
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
    """A MessageStorage whose subscription methods can be inspected."""
    storage = MagicMock()
    storage.add_subscription = AsyncMock(return_value=True)
    storage.remove_subscription = AsyncMock(return_value=True)
    storage.get_subscriptions = AsyncMock(return_value=[])
    storage.get_topic_subscribers = AsyncMock(return_value=[])
    return storage


@pytest.fixture
def fake_connection_manager():
    """A ConnectionManager whose subscribe/unsubscribe can be inspected."""
    from agent_app.websocket.agent_stream import ConnectionManager

    cm = ConnectionManager()
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


class TestMessageSubscribe:
    """POST /api/v1/agent/messages/subscribe persists and activates subscriptions."""

    def test_subscribe_persists_and_activates_online_agent(
        self, client, fake_storage, fake_connection_manager
    ):
        """An online agent is both persisted and subscribed in memory."""
        fake_connection_manager.active_connections["agent-a"] = MagicMock()

        response = client.post(
            "/api/v1/agent/messages/subscribe",
            json={"agent_id": "agent-a", "topic": "jobs", "filter": {"min_priority": "high"}},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["agent_id"] == "agent-a"
        assert data["topic"] == "jobs"

        fake_storage.add_subscription.assert_called_once_with(
            "agent-a", "jobs", {"min_priority": "high"}
        )
        assert "agent-a" in fake_connection_manager.agent_topics
        assert "jobs" in fake_connection_manager.agent_topics["agent-a"]
        assert "agent-a" in fake_connection_manager.topic_subscriptions["jobs"]

    def test_subscribe_persists_offline_agent(
        self, client, fake_storage, fake_connection_manager
    ):
        """An offline agent is persisted but not activated in memory."""
        response = client.post(
            "/api/v1/agent/messages/subscribe",
            json={"agent_id": "agent-a", "topic": "jobs"},
        )

        assert response.status_code == 200
        fake_storage.add_subscription.assert_called_once_with("agent-a", "jobs", {})
        assert "agent-a" not in fake_connection_manager.active_connections

    def test_subscribe_without_storage_returns_503(self, client, monkeypatch):
        """If Redis/storage is not available, subscribe returns 503."""
        monkeypatch.setattr(messages_router, "state", MagicMock(message_storage=None))
        response = client.post(
            "/api/v1/agent/messages/subscribe",
            json={"agent_id": "agent-a", "topic": "jobs"},
        )
        assert response.status_code == 503

    def test_unsubscribe_removes_and_deactivates(
        self, client, fake_storage, fake_connection_manager
    ):
        """Unsubscribe removes from Redis and from in-memory topics."""
        fake_connection_manager.active_connections["agent-a"] = MagicMock()
        asyncio.run(fake_connection_manager.subscribe("agent-a", "jobs"))
        assert "jobs" in fake_connection_manager.agent_topics["agent-a"]

        response = client.post(
            "/api/v1/agent/messages/unsubscribe",
            json={"agent_id": "agent-a", "topic": "jobs"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        fake_storage.remove_subscription.assert_called_once_with("agent-a", "jobs")
        assert "jobs" not in fake_connection_manager.agent_topics["agent-a"]

    def test_get_subscriptions_returns_list(self, client, fake_storage):
        """GET /subscriptions/{agent_id} returns the persisted list."""
        fake_storage.get_subscriptions.return_value = [
            {"agent_id": "agent-a", "topic": "jobs", "filter": {"min_priority": "high"}},
            {"agent_id": "agent-a", "topic": "alerts", "filter": {}},
        ]

        response = client.get("/api/v1/agent/messages/subscriptions/agent-a")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["count"] == 2
        assert {s["topic"] for s in data["subscriptions"]} == {"jobs", "alerts"}


class TestMessageStorageSubscriptions:
    """MessageStorage subscription persistence with a mocked Redis."""

    def test_add_and_remove_subscription(self):
        """add_subscription and remove_subscription update Redis sets."""
        from agent_app.storage.message_storage import MessageStorage

        storage = MessageStorage(redis_url="redis://localhost:6379/1")
        storage.redis = AsyncMock()

        asyncio.run(storage.add_subscription("agent-a", "jobs", {"min_priority": "high"}))

        storage.redis.hset.assert_called_once()
        storage.redis.sadd.assert_any_call("subscriptions:agent:agent-a", "jobs")
        storage.redis.sadd.assert_any_call("subscriptions:topic:jobs", "agent-a")

        asyncio.run(storage.remove_subscription("agent-a", "jobs"))
        storage.redis.srem.assert_any_call("subscriptions:agent:agent-a", "jobs")
        storage.redis.srem.assert_any_call("subscriptions:topic:jobs", "agent-a")
        storage.redis.delete.assert_called_with("subscription:agent-a:jobs")

    def test_get_subscriptions_parses_filter_json(self):
        """get_subscriptions deserializes the stored JSON filter."""
        from agent_app.storage.message_storage import MessageStorage

        storage = MessageStorage(redis_url="redis://localhost:6379/1")
        storage.redis = AsyncMock()
        storage.redis.smembers.return_value = ["jobs"]
        storage.redis.hgetall.return_value = {
            "agent_id": "agent-a",
            "topic": "jobs",
            "filter": json.dumps({"min_priority": "high"}),
            "subscribed_at": "2026-08-21T12:00:00+00:00",
        }

        subs = asyncio.run(storage.get_subscriptions("agent-a"))

        assert len(subs) == 1
        assert subs[0]["topic"] == "jobs"
        assert subs[0]["filter"] == {"min_priority": "high"}

    def test_get_topic_subscribers(self):
        """get_topic_subscribers returns the agent set."""
        from agent_app.storage.message_storage import MessageStorage

        storage = MessageStorage(redis_url="redis://localhost:6379/1")
        storage.redis = AsyncMock()
        storage.redis.smembers.return_value = ["agent-a", "agent-b"]

        subscribers = asyncio.run(storage.get_topic_subscribers("jobs"))

        assert set(subscribers) == {"agent-a", "agent-b"}


class TestConnectionManagerSubscriptionRestore:
    """WebSocket ConnectionManager restores persisted subscriptions on connect."""

    def test_connect_loads_persisted_subscriptions(self):
        """connect() loads subscriptions from storage and subscribes the agent."""
        from agent_app.websocket.agent_stream import ConnectionManager

        storage = MagicMock()
        storage.get_subscriptions = AsyncMock(
            return_value=[
                {"agent_id": "agent-a", "topic": "jobs"},
                {"agent_id": "agent-a", "topic": "alerts"},
            ]
        )

        cm = ConnectionManager()
        cm.message_storage = storage
        websocket = AsyncMock()

        asyncio.run(cm.connect(websocket, "agent-a"))

        websocket.accept.assert_called_once()
        assert "agent-a" in cm.active_connections
        assert cm.agent_topics["agent-a"] == {"jobs", "alerts"}
        assert "agent-a" in cm.topic_subscriptions["jobs"]
        assert "agent-a" in cm.topic_subscriptions["alerts"]
