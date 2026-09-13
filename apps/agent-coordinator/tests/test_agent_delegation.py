"""Tests for the paid agent-to-agent task delegation protocol (v0.25 Phase 3).

Covers:
- Typed negotiation payload schemas (TaskRequest/Quote/Accept/Reject/Result/Paid)
- PaymentEscrow per-call submitter overrides
- ChainEscrowClient RPC mapping via httpx.MockTransport
"""

import json
import time

import httpx
import pytest

from aitbc.crypto import EscrowStatus, PaymentEscrow

from agent_app.protocols.communication import MessageType
from agent_app.protocols.message_types import (
    TASK_MESSAGE_TYPES,
    TaskAccept,
    TaskPaid,
    TaskQuote,
    TaskReject,
    TaskRequest,
    TaskResult,
    create_delegation_message,
    parse_task_payload,
)
from agent_app.services.chain_escrow import (
    ChainEscrowClient,
    EscrowRPCError,
    make_lock_submitter,
    make_refund_submitter,
    make_release_submitter,
)


class TestDelegationSchemas:
    """Round-trip every delegation payload through JSON + parse_task_payload."""

    def _roundtrip(self, message_type: str, model):
        data = model.model_dump(mode="json")
        parsed = parse_task_payload(message_type, data)
        assert type(parsed) is type(model)
        return parsed

    def test_task_request_roundtrip(self):
        req = TaskRequest(
            task_id="t-1",
            service_type="whisper",
            model="base",
            payload_ref="QmTest",
            max_price="0.05",
            escrow_id="esc-1",
        )
        parsed = self._roundtrip("task_request", req)
        assert parsed.task_id == "t-1"
        assert str(parsed.max_price) == "0.05"

    def test_task_quote_roundtrip(self):
        parsed = self._roundtrip("task_quote", TaskQuote(task_id="t-1", price="0.02", eta=12.5, offer_id="sw_offer_x"))
        assert parsed.offer_id == "sw_offer_x"

    def test_task_accept_reject_roundtrip(self):
        acc = self._roundtrip("task_accept", TaskAccept(task_id="t-1", offer_id="o1"))
        assert acc.task_id == "t-1"
        rej = self._roundtrip("task_reject", TaskReject(task_id="t-1", reason="price"))
        assert rej.reason == "price"

    def test_task_result_paid_roundtrip(self):
        res = self._roundtrip(
            "task_result", TaskResult(task_id="t-1", status="success", result_ref="bafyX", result_hash="ab12")
        )
        assert res.result_ref == "bafyX"
        paid = self._roundtrip("task_paid", TaskPaid(task_id="t-1", tx_hash="0xabc"))
        assert paid.tx_hash == "0xabc"

    def test_parse_unknown_type_returns_none(self):
        assert parse_task_payload("direct", {"anything": True}) is None
        assert parse_task_payload("coordination", {}) is None

    def test_parse_invalid_payload_raises(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            parse_task_payload("task_request", {"task_id": "t"})

    def test_message_type_strings_match_enum(self):
        for value, model in TASK_MESSAGE_TYPES.items():
            assert MessageType(value) is not None
            assert model is not None

    def test_create_delegation_message_envelope(self):
        req = TaskRequest(task_id="t-9", service_type="ipfs", payload_ref="bafyY", max_price="0.01")
        msg = create_delegation_message("buyer-1", "prov-1", req)
        assert msg.message_type == MessageType.TASK_REQUEST
        assert msg.receiver_id == "prov-1"
        assert msg.payload["payload_ref"] == "bafyY"
        assert msg.payload["max_price"] == "0.01"


class TestEscrowSubmitters:
    """Per-call submitter overrides on PaymentEscrow."""

    def test_per_call_submitter_overrides_constructor(self):
        ctor_calls = []
        esc = PaymentEscrow(lock_callback=lambda c, f, t, a: ctor_calls.append(1) or "ctor-tx")
        entry = esc.create_escrow(task_id="t", chain_id="c", requester="b", agent="p", amount=10)

        esc.lock(entry.escrow_id, submitter=lambda c, f, t, a: "per-call-tx")
        assert entry.tx_hash_lock == "per-call-tx"
        assert ctor_calls == []

    def test_constructor_callback_still_default(self):
        esc = PaymentEscrow(lock_callback=lambda c, f, t, a: "ctor-tx")
        entry = esc.create_escrow(task_id="t", chain_id="c", requester="b", agent="p", amount=10)
        esc.lock(entry.escrow_id)
        assert entry.tx_hash_lock == "ctor-tx"

    def test_no_callback_still_transitions(self):
        esc = PaymentEscrow()
        entry = esc.create_escrow(task_id="t", chain_id="c", requester="b", agent="p", amount=10)
        esc.lock(entry.escrow_id)
        assert entry.status == EscrowStatus.LOCKED
        assert entry.tx_hash_lock is None

    def test_expire_stale_uses_factory(self):
        esc = PaymentEscrow()
        onchain = esc.create_escrow(task_id="t1", chain_id="c", requester="b", agent="p", amount=5, timeout=0.01)
        offchain = esc.create_escrow(task_id="t2", chain_id="c", requester="b", agent="p", amount=5, timeout=0.01)
        esc.lock(onchain.escrow_id, submitter=lambda c, f, t, a: "lock1")
        esc.lock(offchain.escrow_id)  # bookkeeping-only, no tx_hash_lock
        time.sleep(0.02)

        refunded = []

        def factory(entry):
            if entry.tx_hash_lock:
                return lambda c, f, t, a: refunded.append(entry.task_id) or "refund-tx"
            return None

        expired = esc.expire_stale(refund_submitter_for=factory)
        assert len(expired) == 2
        assert onchain.tx_hash_refund == "refund-tx"
        assert offchain.tx_hash_refund is None
        assert refunded == ["t1"]

    def test_expire_stale_retries_on_failure(self):
        esc = PaymentEscrow()
        entry = esc.create_escrow(task_id="t", chain_id="c", requester="b", agent="p", amount=5, timeout=0.01)
        esc.lock(entry.escrow_id)
        time.sleep(0.02)

        def boom(c, f, t, a):
            raise RuntimeError("rpc down")

        expired = esc.expire_stale(refund_submitter_for=lambda e: boom)
        assert expired == []
        assert entry.status == EscrowStatus.LOCKED  # stays retryable

        expired = esc.expire_stale(refund_submitter_for=lambda e: lambda c, f, t, a: "ok-tx")
        assert len(expired) == 1
        assert entry.status == EscrowStatus.REFUNDED
        assert entry.tx_hash_refund == "ok-tx"


class TestChainEscrowClient:
    """RPC mapping against a mocked transport."""

    def _client(self, handler) -> ChainEscrowClient:
        return ChainEscrowClient("http://rpc.local:8202", api_key="test-key", transport=httpx.MockTransport(handler))

    def test_create_posts_lock_tx(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["body"] = json.loads(request.read())
            seen["api_key"] = request.headers.get("x-api-key")
            return httpx.Response(200, json={"contract_id": "esc-1", "lock_tx_hash": "0xlock"})

        client = self._client(handler)
        result = client.create(
            job_id="t-1",
            buyer="0xB",
            provider="0xP",
            amount_units=72_000_000,
            lock_tx={"type": "ESCROW_LOCK"},
            lock_signature="sig",
        )
        assert seen["path"] == "/rpc/escrow/create"
        assert seen["body"]["job_id"] == "t-1"
        assert seen["body"]["amount"] == "2"  # 72M units = 2 AIT
        assert seen["body"]["lock_tx"] == {"type": "ESCROW_LOCK"}
        assert seen["api_key"] == "test-key"
        assert result["contract_id"] == "esc-1"

    def test_lock_submitter_returns_tx_hash(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"contract_id": "esc-1", "lock_tx_hash": "0xlockhash"})

        client = self._client(handler)
        submitter = make_lock_submitter(client, "task-1", {"type": "ESCROW_LOCK"}, "sig")
        tx = submitter("ait-hub", "0xBuyer", "0xProv", 36_000_000)
        assert tx == "0xlockhash"
        assert submitter.last_response["contract_id"] == "esc-1"

    def test_release_refund_paths_and_amount(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.read() or b"{}")
            calls.append((request.url.path, body))
            if "release" in request.url.path:
                return httpx.Response(200, json={"tx_hash": "0xrel"})
            return httpx.Response(200, json={"refund_tx_hash": "0xref"})

        client = self._client(handler)
        rel = make_release_submitter(client, "task-9", amount_units=36_000_000)
        assert rel("c", "f", "t", 36_000_000) == "0xrel"
        ref = make_refund_submitter(client, "task-9", reason="task_failed")
        assert ref("c", "f", "t", 36_000_000) == "0xref"
        assert calls[0][0] == "/rpc/escrow/task-9/release"
        assert calls[0][1]["amount"] == "1"
        assert calls[1][0] == "/rpc/escrow/task-9/refund"
        assert calls[1][1]["reason"] == "task_failed"

    def test_node_wallet_from_health(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/health"
            return httpx.Response(200, json={"node_wallet": "0xNodeWallet", "status": "ok"})

        client = self._client(handler)
        assert client.node_wallet() == "0xNodeWallet"

    def test_node_wallet_falls_back_to_proposer(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"proposer_id": "0xProposer"})

        client = self._client(handler)
        assert client.node_wallet() == "0xProposer"

    def test_rpc_error_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"detail": "bad lock"})

        client = self._client(handler)
        submitter = make_lock_submitter(client, "task-x", None, "sig")
        with pytest.raises(EscrowRPCError):
            submitter("c", "f", "t", 100)

    def test_missing_tx_hash_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"contract_id": "esc"})

        client = self._client(handler)
        submitter = make_release_submitter(client, "task-x")
        with pytest.raises(EscrowRPCError):
            submitter("c", "f", "t", 100)
