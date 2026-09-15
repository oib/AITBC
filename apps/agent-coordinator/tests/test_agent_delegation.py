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
        assert seen["body"]["lock_tx"] == {"type": "ESCROW_LOCK", "signature": "sig"}
        assert seen["api_key"] == "test-key"
        assert result["contract_id"] == "esc-1"

    def test_create_embeds_signature_in_lock_tx(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.read())
            return httpx.Response(200, json={"contract_id": "c", "lock_tx_hash": "0x1"})

        client = self._client(handler)
        client.create(
            job_id="t",
            buyer="0xB",
            provider="0xP",
            amount_units=100,
            lock_tx={"type": "ESCROW_LOCK"},
            lock_signature="sig",
        )
        assert seen["body"]["lock_tx"]["signature"] == "sig"

        # An already-signed tx is left untouched.
        client.create(
            job_id="t2",
            buyer="0xB",
            provider="0xP",
            amount_units=100,
            lock_tx={"type": "ESCROW_LOCK", "signature": "orig"},
            lock_signature="other",
        )
        assert seen["body"]["lock_tx"]["signature"] == "orig"

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

    def test_release_forwards_auto_reinvest_pct(self):
        """GAP-43: the chain stakes a share of the release when asked -- the
        percentage is all this side sends; the stake address is derived from
        the escrow contract on the chain, never from the request."""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.read() or b"{}")
            return httpx.Response(200, json={"tx_hash": "0xrel", "reinvest_stake_id": "7", "reinvest_amount": "0.5"})

        client = self._client(handler)
        submitter = make_release_submitter(client, "task-rv", auto_reinvest_pct=50.0)
        assert submitter("c", "f", "t", 100) == "0xrel"
        assert seen["body"]["auto_reinvest_pct"] == "50.0"

    def test_release_omits_auto_reinvest_pct_when_unset(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.read() or b"{}")
            return httpx.Response(200, json={"tx_hash": "0xrel"})

        client = self._client(handler)
        submitter = make_release_submitter(client, "task-plain")
        assert submitter("c", "f", "t", 100) == "0xrel"
        assert "auto_reinvest_pct" not in seen["body"]

    def test_release_submitter_stashes_the_reinvest_response(self):
        """The escrow callback signature returns only the tx hash, so the
        reinvest outcome rides on `last_response` like the lock path's does."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"tx_hash": "0xrel", "reinvest_stake_id": "7", "reinvest_amount": "0.5"})

        client = self._client(handler)
        submitter = make_release_submitter(client, "task-rv")
        submitter("c", "f", "t", 100)
        assert submitter.last_response["reinvest_stake_id"] == "7"
        assert submitter.last_response["reinvest_amount"] == "0.5"


class TestTaskPaymentReinvestField:
    """`TaskPayment.auto_reinvest_pct` is what a submission asks the release to stake."""

    def test_accepts_a_percentage(self):
        from agent_app.models import TaskPayment

        payment = TaskPayment(amount=100, requester="0xB", agent="0xA", auto_reinvest_pct=50.0)
        assert payment.auto_reinvest_pct == 50.0

    def test_defaults_to_no_reinvest(self):
        from agent_app.models import TaskPayment

        assert TaskPayment(amount=100, requester="0xB", agent="0xA").auto_reinvest_pct is None

    def test_out_of_range_is_refused(self):
        from pydantic import ValidationError

        from agent_app.models import TaskPayment

        with pytest.raises(ValidationError):
            TaskPayment(amount=100, requester="0xB", agent="0xA", auto_reinvest_pct=150.0)


class TestCompleteReinvestWiring:
    """complete_task forwards the stored percentage and records the outcome."""

    def _client(self, monkeypatch, rpc):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from agent_app import state
        from agent_app.routers import tasks as tasks_router

        escrow = PaymentEscrow()
        monkeypatch.setattr(state, "payment_escrow", escrow)
        monkeypatch.setattr(state, "escrow_rpc", rpc)
        app = FastAPI()
        app.include_router(tasks_router.router, prefix="/v1")
        return TestClient(app), escrow

    def _locked(self, escrow, task_id: str, agent: str, amount: int = 100, **metadata):
        entry = escrow.create_escrow(task_id=task_id, chain_id="c", requester="0xBuyer", agent=agent, amount=amount)
        escrow.lock(entry.escrow_id)
        entry.tx_hash_lock = "0xlock"  # pretend the lock settled on-chain
        entry.metadata.update(metadata)
        return entry

    def test_complete_forwards_and_records_reinvest(self, monkeypatch):
        from aitbc.crypto.crypto import derive_ethereum_address, generate_ethereum_private_key

        class FakeRPC:
            def __init__(self):
                self.release_kwargs = {}

            def release(self, job_id, **kwargs):
                self.release_kwargs = kwargs
                return {"tx_hash": "0xrel", "reinvest_stake_id": "9", "reinvest_amount": "0.5"}

        rpc = FakeRPC()
        pk = generate_ethereum_private_key()
        client, escrow = self._client(monkeypatch, rpc)
        self._locked(escrow, "t-rv", derive_ethereum_address(pk), auto_reinvest_pct="50")

        from aitbc.crypto.crypto import sign_transaction_data

        signed_at = int(time.time())
        # The verifier rebuilds the signed fields as
        # {action, task_id, signed_at, amount_units:0} when the body omits it.
        sig = sign_transaction_data(
            {"action": "complete", "task_id": "t-rv", "signed_at": signed_at, "amount_units": 0}, pk
        )
        resp = client.post("/v1/tasks/t-rv/complete", json={"signed_at": signed_at, "signature": sig})

        assert resp.status_code == 200, resp.text
        assert rpc.release_kwargs["auto_reinvest_pct"] == 50.0
        body = resp.json()
        assert body["reinvest_status"] == "staked"
        assert body["reinvest_stake_id"] == "9"
        entry = escrow.get_escrow_for_task("t-rv")
        assert entry.metadata["reinvest_stake_id"] == "9"
        assert entry.metadata["reinvest_status"] == "staked"

    def test_complete_without_reinvest_sends_no_pct(self, monkeypatch):
        class FakeRPC:
            def __init__(self):
                self.release_kwargs = {}

            def release(self, job_id, **kwargs):
                self.release_kwargs = kwargs
                return {"tx_hash": "0xrel"}

        rpc = FakeRPC()
        client, escrow = self._client(monkeypatch, rpc)
        self._locked(escrow, "t-plain", "")  # no bound agent: unsigned bookkeeping path
        resp = client.post("/v1/tasks/t-plain/complete")
        assert resp.status_code == 200, resp.text
        assert rpc.release_kwargs["auto_reinvest_pct"] is None
        assert resp.json()["reinvest_status"] is None


class TestEscrowCallerBinding:
    """complete/fail must be signed by the escrow's provider wallet (entry.agent)."""

    def _client(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from agent_app import state
        from agent_app.routers import tasks as tasks_router

        escrow = PaymentEscrow()
        monkeypatch.setattr(state, "payment_escrow", escrow)
        monkeypatch.setattr(state, "escrow_rpc", None)
        app = FastAPI()
        app.include_router(tasks_router.router, prefix="/v1")
        return TestClient(app), escrow

    def _locked(self, escrow, task_id: str, agent: str, amount: int = 100):
        entry = escrow.create_escrow(task_id=task_id, chain_id="c", requester="0xBuyer", agent=agent, amount=amount)
        escrow.lock(entry.escrow_id)
        return entry

    def _sign(self, action: str, task_id: str, pk: str, signed_at: int | None = None, **extra):
        from aitbc.crypto.crypto import sign_transaction_data

        fields: dict = {"action": action, "task_id": task_id, "signed_at": signed_at or int(time.time())}
        fields.update(extra)
        return sign_transaction_data(fields, pk), fields["signed_at"]

    def test_complete_signed_by_provider_releases(self, monkeypatch):
        from aitbc.crypto.crypto import derive_ethereum_address, generate_ethereum_private_key

        pk = generate_ethereum_private_key()
        client, escrow = self._client(monkeypatch)
        self._locked(escrow, "t-sig", derive_ethereum_address(pk))
        sig, ts = self._sign("complete", "t-sig", pk, amount_units=30)
        resp = client.post("/v1/tasks/t-sig/complete", json={"amount_units": 30, "signed_at": ts, "signature": sig})
        assert resp.status_code == 200
        entry = escrow.get_escrow_for_task("t-sig")
        assert entry.status == EscrowStatus.RELEASED

    def test_complete_wrong_signer_403(self, monkeypatch):
        from aitbc.crypto.crypto import derive_ethereum_address, generate_ethereum_private_key

        provider = derive_ethereum_address(generate_ethereum_private_key())
        attacker = generate_ethereum_private_key()
        client, escrow = self._client(monkeypatch)
        self._locked(escrow, "t-bad", provider)
        sig, ts = self._sign("complete", "t-bad", attacker, amount_units=30)
        resp = client.post("/v1/tasks/t-bad/complete", json={"amount_units": 30, "signed_at": ts, "signature": sig})
        assert resp.status_code == 403
        assert escrow.get_escrow_for_task("t-bad").status == EscrowStatus.LOCKED

    def test_complete_unsigned_403(self, monkeypatch):
        from aitbc.crypto.crypto import derive_ethereum_address, generate_ethereum_private_key

        client, escrow = self._client(monkeypatch)
        self._locked(escrow, "t-nosig", derive_ethereum_address(generate_ethereum_private_key()))
        resp = client.post("/v1/tasks/t-nosig/complete", json={"amount_units": 10})
        assert resp.status_code == 403
        assert escrow.get_escrow_for_task("t-nosig").status == EscrowStatus.LOCKED

    def test_complete_tampered_amount_403(self, monkeypatch):
        from aitbc.crypto.crypto import derive_ethereum_address, generate_ethereum_private_key

        pk = generate_ethereum_private_key()
        client, escrow = self._client(monkeypatch)
        self._locked(escrow, "t-tamp", derive_ethereum_address(pk))
        sig, ts = self._sign("complete", "t-tamp", pk, amount_units=30)
        # Body claims a different amount than was signed.
        resp = client.post("/v1/tasks/t-tamp/complete", json={"amount_units": 99, "signed_at": ts, "signature": sig})
        assert resp.status_code == 403

    def test_complete_stale_signed_at_403(self, monkeypatch):
        from aitbc.crypto.crypto import derive_ethereum_address, generate_ethereum_private_key

        pk = generate_ethereum_private_key()
        client, escrow = self._client(monkeypatch)
        self._locked(escrow, "t-stale", derive_ethereum_address(pk))
        sig, ts = self._sign("complete", "t-stale", pk, signed_at=int(time.time()) - 3600)
        resp = client.post("/v1/tasks/t-stale/complete", json={"signed_at": ts, "signature": sig})
        assert resp.status_code == 403

    def test_complete_unsigned_ok_when_no_agent(self, monkeypatch):
        """Bookkeeping escrows without a bound provider stay callable (test path)."""
        client, escrow = self._client(monkeypatch)
        self._locked(escrow, "t-free", "")
        resp = client.post("/v1/tasks/t-free/complete")
        assert resp.status_code == 200

    def test_fail_signed_by_provider_refunds(self, monkeypatch):
        from aitbc.crypto.crypto import derive_ethereum_address, generate_ethereum_private_key

        pk = generate_ethereum_private_key()
        client, escrow = self._client(monkeypatch)
        self._locked(escrow, "t-fail", derive_ethereum_address(pk))
        sig, ts = self._sign("fail", "t-fail", pk)
        resp = client.post("/v1/tasks/t-fail/fail", json={"signed_at": ts, "signature": sig})
        assert resp.status_code == 200
        assert escrow.get_escrow_for_task("t-fail").status == EscrowStatus.REFUNDED

    def test_fail_unsigned_403(self, monkeypatch):
        from aitbc.crypto.crypto import derive_ethereum_address, generate_ethereum_private_key

        client, escrow = self._client(monkeypatch)
        self._locked(escrow, "t-failnosig", derive_ethereum_address(generate_ethereum_private_key()))
        resp = client.post("/v1/tasks/t-failnosig/fail")
        assert resp.status_code == 403
        assert escrow.get_escrow_for_task("t-failnosig").status == EscrowStatus.LOCKED
