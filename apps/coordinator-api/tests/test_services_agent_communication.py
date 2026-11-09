"""Service-layer tests for agent_coordination/services/communication.py
(#1289 round 8) — AgentCommunicationService, the in-memory agent
messaging layer with contacts/blocks, channels, templates, payments and
auto-channel creation. initialize() is NOT called — it spawns infinite
background loops (queue processor, cleanup) by design, so messages stay
PENDING until deliver_message is invoked explicitly.

The three defects originally pinned strict-xfail here were fixed in
#1320 (this branch): AES256 now uses real AES-256-GCM (service-held
key, nonce-prefixed ciphertext), RSA/HYBRID are rejected loudly at send
time (no PKI exists to decrypt them), and export/import round-trips
through an explicit JSON-safe codec.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest

from coordinator_api.contexts.agent_coordination.services.communication import (
    AgentCommunicationService,
    ChannelType,
    EncryptionType,
    MessageStatus,
    MessageType,
)


@pytest.fixture
def svc() -> AgentCommunicationService:
    return AgentCommunicationService(config={})


async def _pair(svc: AgentCommunicationService, a: str = "ag1", b: str = "ag2") -> None:
    await svc.authorize_agent(a)
    await svc.authorize_agent(b)
    await svc.add_contact(a, b)
    await svc.add_contact(b, a)


async def _send_deliver(svc: AgentCommunicationService, **kwargs: Any) -> str:
    params: dict[str, Any] = {"sender": "ag1", "recipient": "ag2", "message_type": MessageType.TEXT, "content": "hello"}
    params.update(kwargs)
    mid = await svc.send_message(**params)
    await svc.deliver_message(mid)
    return mid


class TestAuthorization:
    async def test_authorize_and_stats_created(self, svc: AgentCommunicationService) -> None:
        assert await svc.authorize_agent("ag1") is True
        stats = await svc.get_communication_stats("ag1")
        assert stats.total_messages == 0
        assert stats.total_earnings == Decimal("0.0")
        with pytest.raises(ValueError, match="not found"):
            await svc.get_communication_stats("ghost")

    async def test_revoke_clears_state_and_blocks_send(self, svc: AgentCommunicationService) -> None:
        await _pair(svc)
        mid = await svc.send_message("ag1", "ag2", MessageType.TEXT, "hi")
        assert await svc.revoke_agent("ag1") is True
        assert svc.authorized_agents["ag1"] is False
        assert "ag1" not in svc.agent_messages
        assert "ag1" not in svc.communication_stats
        # messages themselves persist in the store
        assert mid in svc.messages
        with pytest.raises(PermissionError):
            await svc.send_message("ag1", "ag2", MessageType.TEXT, "again")


class TestContactsAndBlocks:
    async def test_contact_lifecycle(self, svc: AgentCommunicationService) -> None:
        await svc.authorize_agent("ag1")
        assert await svc.add_contact("ag1", "ag2") is True
        assert svc.contact_lists["ag1"]["ag2"] is True
        assert await svc.remove_contact("ag1", "ag2") is True
        assert "ag2" not in svc.contact_lists["ag1"]
        # removing a non-contact is a silent no-op returning True
        assert await svc.remove_contact("ag1", "ghost") is True

    async def test_block_removes_contact_and_blocks_comms(self, svc: AgentCommunicationService) -> None:
        await _pair(svc)
        assert await svc.block_agent("ag1", "ag2") is True
        assert "ag2" not in svc.contact_lists.get("ag1", {})
        assert await svc.can_communicate("ag1", "ag2") is False
        assert await svc.can_communicate("ag2", "ag1") is False  # block checked both directions
        assert await svc.unblock_agent("ag1", "ag2") is True
        # unblock does NOT restore the contact — comms stay denied
        assert await svc.can_communicate("ag1", "ag2") is False
        await svc.add_contact("ag1", "ag2")
        await svc.add_contact("ag2", "ag1")
        assert await svc.can_communicate("ag1", "ag2") is True

    async def test_block_is_directional(self, svc: AgentCommunicationService) -> None:
        """Documents: ag1 blocking ag2 stops ag1->ag2 AND ag2->ag1
        (can_communicate checks both directions), but the contact entry is
        only removed from ag1's list."""
        await _pair(svc)
        await svc.block_agent("ag1", "ag2")
        assert "ag1" in svc.contact_lists.get("ag2", {})  # ag2's contact list untouched

    async def test_can_communicate_requires_authorization(self, svc: AgentCommunicationService) -> None:
        await svc.authorize_agent("ag1")
        await svc.add_contact("ag1", "ag2")
        assert await svc.can_communicate("ag1", "ag2") is False  # ag2 unauthorized

    async def test_can_communicate_via_reputation(self, svc: AgentCommunicationService) -> None:
        await svc.authorize_agent("ag1")
        await svc.authorize_agent("ag2")

        class _Rep:
            async def get_reputation_score(self, agent_id: str) -> int:
                return 1500

        svc.set_reputation_service(_Rep())  # type: ignore[arg-type]
        assert await svc.can_communicate("ag1", "ag2") is True

        class _LowRep:
            async def get_reputation_score(self, agent_id: str) -> int:
                return 500

        svc.set_reputation_service(_LowRep())  # type: ignore[arg-type]
        assert await svc.can_communicate("ag1", "ag2") is False

    async def test_no_contact_no_reputation_denied(self, svc: AgentCommunicationService) -> None:
        await svc.authorize_agent("ag1")
        await svc.authorize_agent("ag2")
        assert await svc.can_communicate("ag1", "ag2") is False
        with pytest.raises(PermissionError, match="Not authorized"):
            await svc.send_message("ag1", "ag2", MessageType.TEXT, "hi")


class TestMessageLifecycle:
    async def test_send_sets_pending_and_metadata(self, svc: AgentCommunicationService) -> None:
        await _pair(svc)
        mid = await svc.send_message(
            "ag1", "ag2", MessageType.TASK_REQUEST, "do it", metadata={"k": "v"}, reply_to="m0", thread_id="t1"
        )
        msg = svc.messages[mid]
        assert msg.status == MessageStatus.PENDING
        assert msg.paid is False
        assert msg.metadata == {"k": "v"}
        assert msg.reply_to == "m0" and msg.thread_id == "t1"
        assert msg.expires_at is not None
        # queued for the (not-running) processor and indexed for both agents
        assert msg in svc.message_queue
        assert mid in svc.agent_messages["ag1"] and mid in svc.agent_messages["ag2"]
        # auto-created DIRECT channel between the pair
        channels = svc.agent_channels["ag1"]
        assert len(channels) == 1
        assert svc.channels[channels[0]].channel_type == ChannelType.DIRECT

    async def test_send_oversize_rejected(self, svc: AgentCommunicationService) -> None:
        await _pair(svc)
        with pytest.raises(ValueError, match="too large"):
            await svc.send_message("ag1", "ag2", MessageType.TEXT, "x" * 100001)

    async def test_deliver_and_read_roundtrip_plain(self, svc: AgentCommunicationService) -> None:
        await _pair(svc)
        mid = await _send_deliver(svc, encryption_type=EncryptionType.NONE, content="plain-text")
        msg = svc.messages[mid]
        assert msg.status == MessageStatus.DELIVERED
        assert msg.delivery_timestamp is not None
        content = await svc.read_message(mid, "ag2")
        assert content == "plain-text"
        msg = svc.messages[mid]
        assert msg.status == MessageStatus.READ
        assert msg.read_timestamp is not None

    async def test_read_requires_delivered_and_recipient(self, svc: AgentCommunicationService) -> None:
        await _pair(svc)
        mid = await svc.send_message("ag1", "ag2", MessageType.TEXT, "hi", encryption_type=EncryptionType.NONE)
        # not yet delivered -> None (errors collapse to None)
        assert await svc.read_message(mid, "ag2") is None
        await svc.deliver_message(mid)
        assert await svc.read_message(mid, "ag1") is None  # not recipient -> PermissionError -> None
        assert await svc.read_message("missing", "ag2") is None
        # second read -> already-read error -> None
        assert await svc.read_message(mid, "ag2") == "hi"
        assert await svc.read_message(mid, "ag2") is None

    async def test_deliver_message_contract(self, svc: AgentCommunicationService) -> None:
        """deliver_message returns False on error rather than raising
        (inconsistent with the rest of the service which raises)."""
        await _pair(svc)
        mid = await svc.send_message("ag1", "ag2", MessageType.TEXT, "hi")
        assert await svc.deliver_message(mid) is True
        assert await svc.deliver_message(mid) is False  # not pending
        assert await svc.deliver_message("missing") is False

    async def test_aes256_roundtrip(self, svc: AgentCommunicationService) -> None:
        await _pair(svc)
        mid = await _send_deliver(svc, content="aes-secret")
        assert svc.messages[mid].encryption_type == EncryptionType.AES256
        assert await svc.read_message(mid, "ag2") == "aes-secret"

    async def test_aes256_content_is_actually_encrypted(self, svc: AgentCommunicationService) -> None:
        """#1320: AES256 stores real AES-256-GCM ciphertext — plaintext is
        not recoverable from message.content and ciphertext differs per
        send (random nonce)."""
        await _pair(svc)
        mid = await svc.send_message("ag1", "ag2", MessageType.TEXT, "topsecret", encryption_type=EncryptionType.AES256)
        stored = svc.messages[mid].content
        assert b"topsecret" not in stored
        assert stored != b"topsecret"
        # a second send of identical plaintext produces different ciphertext
        mid2 = await svc.send_message("ag1", "ag2", MessageType.TEXT, "topsecret", encryption_type=EncryptionType.AES256)
        assert svc.messages[mid2].content != stored

    async def test_unsupported_encryption_types_rejected(self, svc: AgentCommunicationService) -> None:
        """#1320 correct-contract decision: RSA and HYBRID are rejected at
        send time — no key registry/PKI exists, so they could never be
        decrypted by the recipient (previously RSA reads always returned
        None)."""
        await _pair(svc)
        for enc in (EncryptionType.RSA, EncryptionType.HYBRID):
            with pytest.raises(ValueError, match="Unsupported encryption type"):
                await svc.send_message("ag1", "ag2", MessageType.TEXT, "msg", encryption_type=enc)
        # nothing was stored for the rejected sends
        assert len(svc.messages) == 0

    async def test_price_calculation(self, svc: AgentCommunicationService) -> None:
        await _pair(svc)
        mid_text = await svc.send_message("ag1", "ag2", MessageType.TEXT, "hi")
        mid_bulk = await svc.send_message("ag1", "ag2", MessageType.BULK, "x" * 2000)
        assert svc.messages[mid_text].price == Decimal("0.001")
        # BULK 10x * size 2.0 = 0.02
        assert svc.messages[mid_bulk].price == Decimal("0.02")

    async def test_pay_for_message(self, svc: AgentCommunicationService) -> None:
        await _pair(svc)
        mid = await svc.send_message("ag1", "ag2", MessageType.TEXT, "paid")
        price = svc.messages[mid].price
        assert await svc.pay_for_message(mid, "ag2", price) is True
        assert svc.messages[mid].paid is True
        stats = await svc.get_communication_stats("ag1")
        assert stats.total_earnings == price
        # underpay -> False, not marked paid
        mid2 = await svc.send_message("ag1", "ag2", MessageType.TEXT, "paid2")
        assert await svc.pay_for_message(mid2, "ag2", Decimal("0.000001")) is False
        assert svc.messages[mid2].paid is False
        assert await svc.pay_for_message("missing", "ag2", Decimal("1")) is False


class TestChannels:
    async def test_create_channel_and_dedup(self, svc: AgentCommunicationService) -> None:
        await _pair(svc)
        ch1 = await svc.create_channel("ag1", "ag2", ChannelType.PRIVATE)
        assert ch1 in svc.agent_channels["ag1"] and ch1 in svc.agent_channels["ag2"]
        # send_message reuses the existing channel instead of duplicating
        await svc.send_message("ag1", "ag2", MessageType.TEXT, "hi")
        assert len(svc.agent_channels["ag1"]) == 1
        # explicit second channel still creates a new id
        ch2 = await svc.create_channel("ag1", "ag2", ChannelType.GROUP)
        assert ch2 != ch1
        assert len(await svc.get_agent_channels("ag1")) == 2

    async def test_create_channel_guards(self, svc: AgentCommunicationService) -> None:
        await svc.authorize_agent("ag1")
        await svc.authorize_agent("ag2")
        with pytest.raises(ValueError, match="with self"):
            await svc.create_channel("ag1", "ag1")
        await svc.revoke_agent("ag2")
        with pytest.raises(PermissionError, match="not authorized"):
            await svc.create_channel("ag1", "ag2")

    async def test_get_agent_channels_empty(self, svc: AgentCommunicationService) -> None:
        assert await svc.get_agent_channels("ghost") == []


class TestTemplates:
    async def test_default_templates_exist(self, svc: AgentCommunicationService) -> None:
        assert "task_request_default" in svc.message_templates
        assert "collaboration_invite" in svc.message_templates
        assert "notification_update" in svc.message_templates

    async def test_use_template_substitutes_and_counts(self, svc: AgentCommunicationService) -> None:
        await _pair(svc)
        mid = await svc.use_template(
            "task_request_default", "ag1", "ag2", {"task_description": "audit", "budget": "5", "deadline": "friday"}
        )
        msg = svc.messages[mid]
        assert msg.metadata["template_id"] == "task_request_default"
        assert msg.message_type == MessageType.TASK_REQUEST
        assert svc.message_templates["task_request_default"].usage_count == 1
        # message is PENDING (no processor) — deliver then read
        await svc.deliver_message(mid)
        content = await svc.read_message(mid, "ag2")
        assert "audit" in (content or "")
        assert "{task_description}" not in (content or "")

    async def test_use_template_guards(self, svc: AgentCommunicationService) -> None:
        await _pair(svc)
        with pytest.raises(ValueError, match="not found"):
            await svc.use_template("nope", "ag1", "ag2", {})
        # unknown variables stay literal
        tid = await svc.create_message_template("ag1", "t", "d", MessageType.TEXT, "Hi {name}!", ["name"])
        mid = await svc.use_template(tid, "ag1", "ag2", {"name": "bob", "extra": "x"})
        await svc.deliver_message(mid)
        assert await svc.read_message(mid, "ag2") == "Hi bob!"

    async def test_create_template(self, svc: AgentCommunicationService) -> None:
        tid = await svc.create_message_template(
            "ag1", "Custom", "desc", MessageType.DATA, "payload {x}", ["x"], base_price=Decimal("0.01")
        )
        t = svc.message_templates[tid]
        assert t.creator == "ag1" and t.is_active and t.usage_count == 0


class TestQueriesAndStats:
    async def test_get_agent_messages_filter_sort(self, svc: AgentCommunicationService) -> None:
        await _pair(svc)
        m1 = await svc.send_message("ag1", "ag2", MessageType.TEXT, "one")
        m2 = await svc.send_message("ag2", "ag1", MessageType.URGENT, "two")
        msgs = await svc.get_agent_messages("ag1")
        assert {m.id for m in msgs} == {m1, m2}
        urgent = await svc.get_agent_messages("ag1", status=MessageStatus.PENDING)
        assert len(urgent) == 2
        # limit/offset
        page = await svc.get_agent_messages("ag1", limit=1)
        assert len(page) == 1

    async def test_get_unread_only_delivered_to_recipient(self, svc: AgentCommunicationService) -> None:
        await _pair(svc)
        inbound = await svc.send_message("ag2", "ag1", MessageType.TEXT, "for-ag1")
        outbound = await svc.send_message("ag1", "ag2", MessageType.TEXT, "for-ag2")
        await svc.deliver_message(inbound)
        await svc.deliver_message(outbound)
        unread = await svc.get_unread_messages("ag1")
        assert [m.id for m in unread] == [inbound]
        await svc.read_message(inbound, "ag1")
        assert await svc.get_unread_messages("ag1") == []

    async def test_stats_counters(self, svc: AgentCommunicationService) -> None:
        await _pair(svc)
        mid = await _send_deliver(svc)
        await svc.read_message(mid, "ag2")
        s1 = await svc.get_communication_stats("ag1")
        s2 = await svc.get_communication_stats("ag2")
        assert s1.messages_sent == 1 and s1.total_messages == 1
        assert s2.messages_received == 1 and s2.total_messages == 1
        assert s1.active_channels == 1 and s2.active_channels == 1


class TestExportImport:
    async def test_export_import_roundtrip(self, svc: AgentCommunicationService) -> None:
        """#1320: export/import round-trips types correctly — bytes stay
        bytes, datetimes stay datetime, enums/Decimals restore."""
        await _pair(svc)
        mid = await _send_deliver(svc, encryption_type=EncryptionType.NONE, content="export-me")
        data = await svc.export_communication_data()
        svc2 = AgentCommunicationService(config={})
        await svc2.import_communication_data(data)
        imported = svc2.messages[mid]
        assert isinstance(imported.content, bytes)
        assert imported.content == b"export-me"
        assert imported.expires_at is not None and isinstance(imported.expires_at, datetime)
        assert imported.status == MessageStatus.DELIVERED
        assert imported.price == svc.messages[mid].price
        # imported plaintext message is readable by its recipient
        assert await svc2.read_message(mid, "ag2") == "export-me"
        # channels and templates also round-trip
        assert len(svc2.channels) == len(svc.channels)
        assert "task_request_default" in svc2.message_templates
