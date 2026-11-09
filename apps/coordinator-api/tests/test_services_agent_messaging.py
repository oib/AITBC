"""Service-layer tests for agent_coordination/services/agent_service.py
(#1289 round 7) — the in-memory agent-to-agent messaging service.

Covers registration, direct/broadcast send, offline queueing, delivery
receipts, read marking, filtering, profiles and stats. No DB involved —
AgentService is pure in-memory state.

The defect originally pinned strict-xfail was fixed in #1318 (same
branch): ``broadcast`` now validates the sender up front and raises
``ValueError`` instead of silently returning ``[]``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from coordinator_api.contexts.agent_coordination.services.agent_service import (
    AgentService,
    MessageStatus,
    MessageType,
    get_agent_service,
)


@pytest.fixture
def svc() -> AgentService:
    return AgentService()


def _register(svc: AgentService, *ids: str) -> None:
    for i, agent_id in enumerate(ids):
        svc.register_agent(agent_id, public_key=f"pk-{agent_id}", capabilities=[f"cap-{i}"])


class TestRegistration:
    def test_register_agent(self, svc: AgentService) -> None:
        profile = svc.register_agent("ag1", "pk1", ["chat"])
        assert profile.agent_id == "ag1"
        assert profile.public_key == "pk1"
        assert profile.capabilities == ["chat"]
        assert profile.online is True
        assert svc.get_agent_profile("ag1") is profile
        assert svc.get_agent_profile("ghost") is None

    def test_reregister_overwrites(self, svc: AgentService) -> None:
        svc.register_agent("ag1", "pk-old")
        svc.register_agent("ag1", "pk-new", ["x"])
        profile = svc.get_agent_profile("ag1")
        assert profile is not None
        assert profile.public_key == "pk-new"
        assert profile.capabilities == ["x"]

    def test_list_agents_online_filter(self, svc: AgentService) -> None:
        _register(svc, "a1", "a2", "a3")
        svc.update_agent_status("a2", online=False)
        assert len(svc.list_agents()) == 3
        online = svc.list_agents(online_only=True)
        assert {a.agent_id for a in online} == {"a1", "a3"}

    def test_update_agent_status(self, svc: AgentService) -> None:
        svc.register_agent("ag1", "pk")
        assert svc.update_agent_status("ag1", online=False) is True
        assert svc.get_agent_profile("ag1").online is False  # type: ignore[union-attr]
        assert svc.update_agent_status("ghost", online=True) is False


class TestSendMessage:
    def test_direct_to_online_delivers(self, svc: AgentService) -> None:
        _register(svc, "a1", "a2")
        msg = svc.send_message("a1", "a2", "hello")
        assert msg.id == "MSG-00000001"
        assert msg.status == MessageStatus.delivered
        assert msg.delivered_at is not None
        assert msg.message_type == MessageType.direct

    def test_unregistered_sender_raises(self, svc: AgentService) -> None:
        _register(svc, "a2")
        with pytest.raises(ValueError, match="Sender agent not registered"):
            svc.send_message("ghost", "a2", "hi")

    def test_unregistered_recipient_raises(self, svc: AgentService) -> None:
        _register(svc, "a1")
        with pytest.raises(ValueError, match="Recipient agent not found"):
            svc.send_message("a1", "ghost", "hi")

    def test_offline_recipient_queues_pending(self, svc: AgentService) -> None:
        _register(svc, "a1", "a2")
        svc.update_agent_status("a2", online=False)
        msg = svc.send_message("a1", "a2", "later")
        assert msg.status == MessageStatus.pending
        assert msg.delivered_at is None
        assert svc.get_stats()["queued_messages"] == 1

    def test_unknown_message_type_coerced_to_direct(self, svc: AgentService) -> None:
        """Documents silent coercion: an unrecognized message_type falls back
        to 'direct' rather than raising."""
        _register(svc, "a1", "a2")
        msg = svc.send_message("a1", "a2", "hi", message_type="carrier-pigeon")
        assert msg.message_type == MessageType.direct

    def test_message_fields_and_to_dict(self, svc: AgentService) -> None:
        _register(svc, "a1", "a2")
        msg = svc.send_message(
            "a1",
            "a2",
            "secret",
            message_type="request",
            encrypted=True,
            reply_to="MSG-00000000",
            metadata={"k": "v"},
        )
        assert msg.encrypted is True
        assert msg.reply_to == "MSG-00000000"
        d = msg.to_dict()
        assert d["type"] == "request"
        assert d["status"] == "delivered"
        assert d["timestamp"] == msg.timestamp.isoformat()
        assert d["read_at"] is None

    def test_send_to_none_recipient_blackholes(self, svc: AgentService) -> None:
        """Documents edge: recipient=None bypasses the registered-recipient
        check and the queue, status stays 'sent', and no agent can ever
        retrieve the message via get_messages."""
        svc.register_agent("a1", "pk")
        msg = svc.send_message("a1", None, "void")  # type: ignore[arg-type]
        assert msg.status == MessageStatus.sent
        assert svc.get_message(msg.id) is msg


class TestBroadcast:
    def test_broadcast_reaches_all_except_sender(self, svc: AgentService) -> None:
        _register(svc, "a1", "a2", "a3")
        msgs = svc.broadcast("a1", "announcement")
        assert len(msgs) == 2
        assert {m.recipient for m in msgs} == {"a2", "a3"}
        assert all(m.message_type == MessageType.broadcast for m in msgs)

    def test_broadcast_to_offline_queues(self, svc: AgentService) -> None:
        _register(svc, "a1", "a2")
        svc.update_agent_status("a2", online=False)
        msgs = svc.broadcast("a1", "news")
        assert len(msgs) == 1
        assert msgs[0].status == MessageStatus.pending

    def test_broadcast_unregistered_sender_raises(self, svc: AgentService) -> None:
        _register(svc, "a2")
        with pytest.raises(ValueError, match="Sender agent not registered"):
            svc.broadcast("ghost", "hi")


class TestGetMessages:
    def test_get_messages_returns_recipient_only(self, svc: AgentService) -> None:
        _register(svc, "a1", "a2")
        svc.send_message("a1", "a2", "for-a2")
        svc.send_message("a2", "a1", "for-a1")
        a2_msgs = svc.get_messages("a2")
        assert len(a2_msgs) == 1
        assert a2_msgs[0].content == "for-a2"
        assert svc.get_messages("a1")[0].content == "for-a1"

    def test_get_messages_unknown_agent_raises(self, svc: AgentService) -> None:
        with pytest.raises(ValueError, match="Agent not found"):
            svc.get_messages("ghost")

    def test_queued_message_delivered_on_poll(self, svc: AgentService) -> None:
        _register(svc, "a1", "a2")
        svc.update_agent_status("a2", online=False)
        msg = svc.send_message("a1", "a2", "queued")
        assert msg.status == MessageStatus.pending
        msgs = svc.get_messages("a2")
        assert len(msgs) == 1
        assert msgs[0].status == MessageStatus.delivered
        assert msgs[0].delivered_at is not None
        assert svc.get_stats()["queued_messages"] == 0

    def test_get_messages_side_effect_marks_online(self, svc: AgentService) -> None:
        """Documents: polling get_messages flips profile.online=True and
        refreshes last_seen — a read is also a presence signal."""
        _register(svc, "a1")
        svc.update_agent_status("a1", online=False)
        svc.get_messages("a1")
        assert svc.get_agent_profile("a1").online is True  # type: ignore[union-attr]

    def test_filters_since_type_unread(self, svc: AgentService) -> None:
        _register(svc, "a1", "a2")
        old = svc.send_message("a1", "a2", "old", message_type="request")
        new = svc.send_message("a1", "a2", "new", message_type="direct")
        # backdate 'old' beyond the since cutoff
        old.timestamp = datetime.now(UTC) - timedelta(hours=2)
        since = datetime.now(UTC) - timedelta(hours=1)
        msgs = svc.get_messages("a2", since=since)
        assert [m.id for m in msgs] == [new.id]
        msgs = svc.get_messages("a2", message_type="request")
        assert [m.id for m in msgs] == [old.id]
        svc.mark_read("a2", new.id)
        unread = svc.get_messages("a2", unread_only=True)
        assert new.id not in [m.id for m in unread]

    def test_messages_sorted_newest_first(self, svc: AgentService) -> None:
        _register(svc, "a1", "a2")
        m1 = svc.send_message("a1", "a2", "first")
        m2 = svc.send_message("a1", "a2", "second")
        m1.timestamp = datetime.now(UTC) - timedelta(seconds=5)
        msgs = svc.get_messages("a2")
        assert [m.id for m in msgs] == [m2.id, m1.id]


class TestMarkRead:
    def test_mark_read_happy_and_guards(self, svc: AgentService) -> None:
        _register(svc, "a1", "a2", "a3")
        msg = svc.send_message("a1", "a2", "hi")
        assert svc.mark_read("a3", msg.id) is False  # not the recipient
        assert svc.mark_read("a2", "MSG-99999999") is False  # unknown
        assert svc.mark_read("a2", msg.id) is True
        assert msg.status == MessageStatus.read
        assert msg.read_at is not None

    def test_mark_read_pending_message_allowed(self, svc: AgentService) -> None:
        """Documents: mark_read does not require delivery — a queued/pending
        message can be marked read."""
        _register(svc, "a1", "a2")
        svc.update_agent_status("a2", online=False)
        msg = svc.send_message("a1", "a2", "queued")
        assert msg.status == MessageStatus.pending
        assert svc.mark_read("a2", msg.id) is True
        assert msg.status == MessageStatus.read


class TestStats:
    def test_stats_counts(self, svc: AgentService) -> None:
        _register(svc, "a1", "a2")
        svc.update_agent_status("a2", online=False)
        svc.send_message("a1", "a2", "q1")
        svc.send_message("a1", "a2", "q2")
        stats = svc.get_stats()
        assert stats["total_messages"] == 2
        assert stats["by_status"]["pending"] == 2
        assert stats["registered_agents"] == 2
        assert stats["online_agents"] == 1
        assert stats["queued_messages"] == 2


def test_get_agent_service_singleton() -> None:
    first = get_agent_service()
    assert get_agent_service() is first
