"""Unit tests for the provider-side agent task executor (A2A paid delegation)."""

import json
from unittest.mock import Mock

import agent_task_executor as ate
import pytest

PROVIDER = "0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2"
BUYER = "buyer-node0"

PRICE_TABLE = {
    "whisper": {"service_type": "whisper", "model": "base", "price": "0.02"},
    "ollama": {"service_type": "ollama", "model": "llama3.2:3b", "price": "0.001"},
    "ipfs": {"service_type": "ipfs", "model": "ipfs-host", "price": "0.01"},
}


def _resp(json_data=None, status=200, content=b""):
    r = Mock()
    r.status_code = status
    r.json.return_value = json_data if json_data is not None else {}
    r.content = content
    r.raise_for_status = Mock()
    if status >= 400:
        import requests

        r.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status}")
    return r


def _msg(msg_id: str, message_type: str, content: dict, sender: str = BUYER) -> dict:
    return {
        "message_id": msg_id,
        "message_type": message_type,
        "sender": sender,
        "recipient": "aitbc-miner-1",
        "content": json.dumps(content),
    }


@pytest.fixture(autouse=True)
def _clean_signing_env(monkeypatch):
    """Signing config comes from env — clear it so host env can't leak in.

    ``MINER_WALLET_KEY_FILE`` is pointed at a nonexistent path rather than
    deleted: on a live miner host the default path
    (``/var/lib/aitbc/wallets/default.json``) resolves a real key and would
    silently activate signing in no-key tests.
    """
    for var in ("AGENT_SIGNING_KEY", "AGENT_EXECUTOR_SIGNING_KEY", "MINER_WALLET_ADDRESS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("MINER_WALLET_KEY_FILE", "/nonexistent/test-wallet.json")


@pytest.fixture()
def executor(tmp_path, monkeypatch):
    """Isolated executor state + captured coordinator traffic."""
    monkeypatch.setattr(ate, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(ate, "COORDINATOR_URL", "http://coord.local")
    monkeypatch.setattr(ate, "AGENT_EXECUTOR_ID", "aitbc-miner-1")
    sent = []

    def fake_send(sender, recipient, message_type, content):
        sent.append((message_type, content, recipient))
        return True

    monkeypatch.setattr(ate, "_send_message", fake_send)
    monkeypatch.setattr(ate, "_mark_read", lambda mid: None)
    monkeypatch.setattr(ate, "_register_agent", lambda *a, **k: True)
    return {"sent": sent}


def _task_request(task_id="t-1", **over):
    req = {
        "task_id": task_id,
        "service_type": "whisper",
        "model": "base",
        "payload_ref": "QmPayload",
        "max_price": "0.05",
        "escrow_id": "esc-1",
    }
    req.update(over)
    return req


def _locked_escrow(task_id="t-1", agent=PROVIDER, amount=72_000_000):
    """An escrow whose lock is anchored on-chain (tx_hash_lock + contract_id)."""
    return {
        "task_id": task_id,
        "escrow_status": "locked",
        "agent": agent,
        "amount": amount,
        "tx_hash_lock": "0xlockhash",
        "contract_id": "esc-1",
    }


class TestQuoting:
    def test_quotes_when_price_ok(self, executor, monkeypatch):
        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [_msg("m1", "task_request", _task_request())])
        monkeypatch.setattr(ate, "_service_ready", lambda s: True)
        monkeypatch.setattr(ate, "_task_escrow_status", lambda t: _locked_escrow())
        stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert stats["quoted"] == 1
        mtype, content, recipient = executor["sent"][0]
        assert mtype == "task_quote" and content["price"] == "0.02" and recipient == BUYER

    def test_rejects_below_max_price(self, executor, monkeypatch):
        monkeypatch.setattr(
            ate, "_fetch_inbox", lambda *a, **k: [_msg("m1", "task_request", _task_request(max_price="0.001"))]
        )
        monkeypatch.setattr(ate, "_service_ready", lambda s: True)
        stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert stats["rejected"] == 1
        assert executor["sent"][0][0] == "task_reject"
        assert "below offer price" in executor["sent"][0][1]["reason"]

    def test_rejects_unknown_service(self, executor, monkeypatch):
        monkeypatch.setattr(
            ate, "_fetch_inbox", lambda *a, **k: [_msg("m1", "task_request", _task_request(service_type="quantum"))]
        )
        stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert stats["rejected"] == 1
        assert "unsupported service_type" in executor["sent"][0][1]["reason"]

    def test_rejects_when_service_down(self, executor, monkeypatch):
        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [_msg("m1", "task_request", _task_request())])
        monkeypatch.setattr(ate, "_service_ready", lambda s: False)
        stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert stats["rejected"] == 1
        assert "unavailable" in executor["sent"][0][1]["reason"]

    def test_rejects_when_escrow_missing_or_wrong_wallet(self, executor, monkeypatch):
        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [_msg("m1", "task_request", _task_request())])
        monkeypatch.setattr(ate, "_service_ready", lambda s: True)
        monkeypatch.setattr(ate, "_task_escrow_status", lambda t: None)
        stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert stats["rejected"] == 1
        assert "no locked escrow" in executor["sent"][0][1]["reason"]

        executor["sent"].clear()
        monkeypatch.setattr(ate, "_task_escrow_status", lambda t: _locked_escrow(agent="0xSomeoneElse"))
        monkeypatch.setattr(ate, "STATE_PATH", ate.STATE_PATH)  # fresh state file already written
        # state file persists quotes — use a new task id
        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [_msg("m2", "task_request", _task_request(task_id="t-2"))])
        stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert "not this provider" in executor["sent"][0][1]["reason"]


class TestExecution:
    def _setup_accept(self, executor, monkeypatch, task_id="t-1"):
        """Pre-quote a task in executor state and queue a task_accept."""
        state = ate._load_state()
        state["quotes"][task_id] = {
            "buyer": BUYER,
            "price": "0.02",
            "offer_id": "whisper-base",
            "request": _task_request(task_id),
        }
        ate._save_state(state)
        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [_msg("m-accept", "task_accept", {"task_id": task_id})])
        monkeypatch.setattr(ate, "_task_escrow_status", lambda t: _locked_escrow(task_id))

    def test_accept_executes_and_pays(self, executor, monkeypatch):
        task_id = "t-1"
        self._setup_accept(executor, monkeypatch, task_id)
        monkeypatch.setattr(ate, "_ipfs_cat", lambda cid: b"audio-bytes")
        monkeypatch.setattr(ate, "_ipfs_add", lambda data, filename="r": "bafyResult")
        monkeypatch.setitem(ate.SERVICE_HANDLERS, "whisper", lambda req, payload: b'{"text":"hello"}')
        monkeypatch.setattr(ate, "_complete_task", lambda t, w, amount_units=None: {"tx_hash_release": "0xrel"})

        stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert stats["executed"] == 1
        types = [s[0] for s in executor["sent"]]
        assert types == ["task_result", "task_paid"]
        result_msg = executor["sent"][0][1]
        assert result_msg["result_ref"] == "bafyResult"
        assert result_msg["status"] == "success"
        assert executor["sent"][1][1]["tx_hash"] == "0xrel"

    def test_accept_without_quote_ignored(self, executor, monkeypatch):
        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [_msg("m1", "task_accept", {"task_id": "nope"})])
        stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert stats["executed"] == 0 and stats["failed"] == 0
        assert executor["sent"] == []

    def test_execution_failure_fails_task(self, executor, monkeypatch):
        self._setup_accept(executor, monkeypatch)
        monkeypatch.setattr(ate, "_ipfs_cat", lambda cid: b"audio")

        def boom(req, payload):
            raise RuntimeError("whisper exploded")

        monkeypatch.setitem(ate.SERVICE_HANDLERS, "whisper", boom)
        failed = []
        monkeypatch.setattr(ate, "_fail_task", lambda t, w, reason=None: failed.append(t))
        stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert stats["failed"] == 1
        assert failed == ["t-1"]
        assert executor["sent"][0][0] == "task_result"
        assert executor["sent"][0][1]["status"] == "failed"

    def test_unrelated_messages_skipped(self, executor, monkeypatch):
        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [_msg("m1", "direct", {"message": "hi"})])
        stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert all(v == 0 for v in stats.values())
        assert executor["sent"] == []


class TestServiceHandlers:
    def test_handlers_cover_plan_services(self):
        assert set(ate.SERVICE_HANDLERS) == {"whisper", "ffmpeg", "ollama", "ipfs"}

    def test_ollama_prompt_parsing(self, monkeypatch):
        captured = {}

        def fake_post(url, **kwargs):
            captured["url"] = url
            captured["json"] = kwargs.get("json")
            return _resp({"response": "hi"}, content=b'{"response":"hi"}')

        monkeypatch.setattr(ate.requests, "post", fake_post)
        out = ate._exec_ollama({"model": "llama3.2:3b"}, json.dumps({"prompt": "say hi"}).encode())
        assert b"hi" in out
        assert captured["url"].endswith("/api/generate")
        assert captured["json"]["prompt"] == "say hi"

    def test_ipfs_handler_pins_cid(self, monkeypatch):
        captured = {}

        def fake_post(url, **kwargs):
            captured["params"] = kwargs.get("params")
            return _resp({})

        monkeypatch.setattr(ate.requests, "post", fake_post)
        ate._exec_ipfs({"payload_ref": "QmPinned"}, b"")
        assert captured["params"]["arg"] == "QmPinned"


class TestEscrowCallerSigning:
    """complete/fail calls must carry a signature from the provider wallet key."""

    def test_signed_body_recovers_provider(self, monkeypatch):
        from aitbc.crypto.crypto import (
            derive_ethereum_address,
            generate_ethereum_private_key,
            recover_signer,
        )

        pk = generate_ethereum_private_key()
        addr = derive_ethereum_address(pk)
        monkeypatch.setenv("AGENT_EXECUTOR_SIGNING_KEY", pk)
        body = ate._signed_body("complete", "t-1", addr, {"amount_units": 5})
        signed = {k: body[k] for k in ("action", "task_id", "signed_at", "amount_units")}
        assert recover_signer(signed, body["signature"]) == addr

    def test_signing_key_from_wallet_file(self, tmp_path, monkeypatch):
        from aitbc.crypto.crypto import derive_ethereum_address, generate_ethereum_private_key

        monkeypatch.delenv("AGENT_EXECUTOR_SIGNING_KEY", raising=False)
        pk = generate_ethereum_private_key()
        addr = derive_ethereum_address(pk)
        wallet_file = tmp_path / "w.json"
        wallet_file.write_text(json.dumps({"address": addr, "private_key": pk}))
        monkeypatch.setenv("MINER_WALLET_KEY_FILE", str(wallet_file))
        assert ate._provider_signing_key(addr) == pk

    def test_signing_key_file_address_mismatch_rejected(self, tmp_path, monkeypatch):
        from aitbc.crypto.crypto import derive_ethereum_address, generate_ethereum_private_key

        monkeypatch.delenv("AGENT_EXECUTOR_SIGNING_KEY", raising=False)
        pk = generate_ethereum_private_key()
        wallet_file = tmp_path / "w.json"
        wallet_file.write_text(json.dumps({"address": derive_ethereum_address(pk), "private_key": pk}))
        monkeypatch.setenv("MINER_WALLET_KEY_FILE", str(wallet_file))
        assert ate._provider_signing_key("0x" + "ab" * 20) is None

    def test_no_key_sends_unsigned_with_warning(self, monkeypatch):
        monkeypatch.delenv("AGENT_EXECUTOR_SIGNING_KEY", raising=False)
        monkeypatch.setenv("MINER_WALLET_KEY_FILE", "/nonexistent/key.json")
        body = ate._signed_body("fail", "t-1", PROVIDER)
        assert "signature" not in body
        assert body["action"] == "fail"

    def test_complete_sends_signed_body(self, monkeypatch):
        from aitbc.crypto.crypto import derive_ethereum_address, generate_ethereum_private_key, recover_signer

        pk = generate_ethereum_private_key()
        addr = derive_ethereum_address(pk)
        monkeypatch.setenv("AGENT_EXECUTOR_SIGNING_KEY", pk)
        captured = {}

        def fake_post(url, **kwargs):
            captured["json"] = kwargs.get("json")
            return _resp({"tx_hash_release": "0xabc"})

        monkeypatch.setattr(ate.requests, "post", fake_post)
        out = ate._complete_task("t-9", addr, amount_units=7)
        assert out["tx_hash_release"] == "0xabc"
        body = captured["json"]
        signed = {k: body[k] for k in ("action", "task_id", "signed_at", "amount_units")}
        assert signed == {"action": "complete", "task_id": "t-9", "signed_at": body["signed_at"], "amount_units": 7}
        assert recover_signer(signed, body["signature"]) == addr


def _new_keypair():
    from aitbc.crypto.crypto import derive_ethereum_address, generate_ethereum_private_key

    pk = generate_ethereum_private_key()
    return pk, derive_ethereum_address(pk)


def _recover_req_payload(payload: dict, signature: str) -> str | None:
    """Recover the signer of an aitbc-agent-req-v1 request payload."""
    from aitbc.crypto.agent_envelope import domain_digest
    from aitbc.crypto.signature_recovery import SignatureMalformed, recover_address

    try:
        return recover_address(domain_digest(payload, ate.AGENT_REQ_DOMAIN), signature)
    except SignatureMalformed:
        return None


class TestAgentSigningKey:
    """Key custody: env/file resolution, address derivation, fail-fast mismatch."""

    def test_env_key_loads_and_derives_address(self, monkeypatch):
        pk, addr = _new_keypair()
        monkeypatch.setenv("AGENT_SIGNING_KEY", pk)
        key, address = ate._signing_material()
        assert key == pk
        assert address == addr

    def test_legacy_env_key_still_works(self, monkeypatch):
        pk, addr = _new_keypair()
        monkeypatch.setenv("AGENT_EXECUTOR_SIGNING_KEY", pk)
        key, address = ate._signing_material()
        assert key == pk and address == addr

    def test_agent_signing_key_takes_precedence(self, monkeypatch):
        pk_new, addr_new = _new_keypair()
        pk_old, _addr_old = _new_keypair()
        monkeypatch.setenv("AGENT_SIGNING_KEY", pk_new)
        monkeypatch.setenv("AGENT_EXECUTOR_SIGNING_KEY", pk_old)
        key, address = ate._signing_material()
        assert key == pk_new and address == addr_new

    def test_miner_wallet_address_mismatch_fails_fast(self, monkeypatch):
        pk, _addr = _new_keypair()
        _other_pk, other_addr = _new_keypair()
        monkeypatch.setenv("AGENT_SIGNING_KEY", pk)
        monkeypatch.setenv("MINER_WALLET_ADDRESS", other_addr)
        with pytest.raises(RuntimeError, match="does not match"):
            ate._signing_material()

    def test_miner_wallet_address_match_accepted(self, monkeypatch):
        pk, addr = _new_keypair()
        monkeypatch.setenv("AGENT_SIGNING_KEY", pk)
        monkeypatch.setenv("MINER_WALLET_ADDRESS", addr)
        key, address = ate._signing_material()
        assert key == pk and address == addr

    def test_provider_wallet_mismatch_disables_signing(self, monkeypatch):
        pk, _addr = _new_keypair()
        monkeypatch.setenv("AGENT_SIGNING_KEY", pk)
        key, address = ate._signing_material(provider_wallet="0x" + "cd" * 20)
        assert key is None and address is None

    def test_no_key_returns_none(self, monkeypatch):
        monkeypatch.setenv("MINER_WALLET_KEY_FILE", "/nonexistent/key.json")
        key, address = ate._signing_material()
        assert key is None and address is None


class TestSignedEnvelopeSend:
    """_send_message must emit the Phase-A signed envelope when a key exists."""

    def test_signed_envelope_fields_and_recovers(self, monkeypatch):
        from aitbc.crypto.agent_envelope import AGENT_MSG_SIGNATURE_VERSION, verify_agent_envelope

        pk, addr = _new_keypair()
        monkeypatch.setenv("AGENT_SIGNING_KEY", pk)
        captured = {}

        def fake_post(url, **kwargs):
            captured["json"] = kwargs.get("json")
            return _resp({"status": "success"})

        monkeypatch.setattr(ate.requests, "post", fake_post)
        assert ate._send_message("aitbc-miner-1", BUYER, "task_quote", {"task_id": "t-1", "price": "0.02"})
        body = captured["json"]
        assert body["signer"] == addr
        assert body["signature_version"] == AGENT_MSG_SIGNATURE_VERSION
        assert body["timestamp"] and body["nonce"]
        # The signature covers the full request minus "signature" — the
        # coordinator's signing_payload() is model_dump(exclude={"signature"}).
        payload = {k: v for k, v in body.items() if k != "signature"}
        assert verify_agent_envelope(payload, body["signature"], addr)

    def test_unsigned_body_unchanged_without_key(self, monkeypatch):
        captured = {}

        def fake_post(url, **kwargs):
            captured["json"] = kwargs.get("json")
            return _resp({"status": "success"})

        monkeypatch.setattr(ate.requests, "post", fake_post)
        assert ate._send_message("aitbc-miner-1", BUYER, "task_quote", {"task_id": "t-1"})
        body = captured["json"]
        assert body == {
            "sender": "aitbc-miner-1",
            "recipient": BUYER,
            "content": {"task_id": "t-1"},
            "message_type": "task_quote",
            "encrypt": False,
            "ttl": 3600,
        }


class TestSignedRequestHeaders:
    """X-Agent-* headers on read calls, fresh nonce+timestamp per call."""

    def _capture_get(self, monkeypatch):
        captured = []

        def fake_get(url, **kwargs):
            captured.append(kwargs)
            return _resp({"messages": []})

        monkeypatch.setattr(ate.requests, "get", fake_get)
        return captured

    def test_inbox_headers_verify_and_are_fresh(self, monkeypatch):
        pk, addr = _new_keypair()
        monkeypatch.setenv("AGENT_SIGNING_KEY", pk)
        calls = self._capture_get(monkeypatch)
        ate._fetch_inbox("aitbc-miner-1")
        ate._fetch_inbox("aitbc-miner-1")
        assert len(calls) == 2
        nonces = set()
        for call in calls:
            headers = call["headers"]
            assert headers["X-Agent-Id"] == "aitbc-miner-1"
            payload = {
                "agent_id": headers["X-Agent-Id"],
                "timestamp": headers["X-Agent-Timestamp"],
                "nonce": headers["X-Agent-Nonce"],
            }
            assert _recover_req_payload(payload, headers["X-Agent-Signature"]) == addr
            nonces.add(headers["X-Agent-Nonce"])
        assert len(nonces) == 2  # no replay-collision across sweep calls

    def test_mark_read_carries_headers(self, monkeypatch):
        pk, addr = _new_keypair()
        monkeypatch.setenv("AGENT_SIGNING_KEY", pk)
        captured = {}

        def fake_post(url, **kwargs):
            captured["headers"] = kwargs.get("headers")
            return _resp({})

        monkeypatch.setattr(ate.requests, "post", fake_post)
        ate._mark_read("m-1")
        headers = captured["headers"]
        assert headers["X-Agent-Id"] == ate.AGENT_EXECUTOR_ID
        payload = {
            "agent_id": headers["X-Agent-Id"],
            "timestamp": headers["X-Agent-Timestamp"],
            "nonce": headers["X-Agent-Nonce"],
        }
        assert _recover_req_payload(payload, headers["X-Agent-Signature"]) == addr

    def test_no_headers_without_key(self, monkeypatch):
        calls = self._capture_get(monkeypatch)
        ate._fetch_inbox("aitbc-miner-1")
        assert calls[0]["headers"] == {}


class TestRegisterIdentity:
    """Registration carries the §3 identity attestation when a key exists."""

    def _fake_get(self, monkeypatch, nonce="n-1", chain_id="ait-hub", agent=None):
        def fake_get(url, **kwargs):
            if url.endswith("/v1/agents/nonce"):
                return _resp({"nonce": nonce, "chain_id": chain_id})
            if "/v1/agents/" in url:
                return _resp({"agent": agent or {}})
            return _resp({})

        monkeypatch.setattr(ate.requests, "get", fake_get)

    def test_register_sends_identity_proof(self, monkeypatch):
        from aitbc.crypto.agent_envelope import identity_claim, verify_identity_claim

        pk, addr = _new_keypair()
        monkeypatch.setenv("AGENT_SIGNING_KEY", pk)
        self._fake_get(monkeypatch, nonce="nonce-123", chain_id="ait-hub")
        captured = {}

        def fake_post(url, **kwargs):
            captured["json"] = kwargs.get("json")
            return _resp({"status": "success"})

        monkeypatch.setattr(ate.requests, "post", fake_post)
        assert ate._register_agent("aitbc-miner-1", addr, ["whisper"])
        body = captured["json"]
        assert body["identity_address"] == addr
        assert body["identity_nonce"] == "nonce-123"
        assert body["chain_id"] == "ait-hub"
        claim = identity_claim(
            agent_id="aitbc-miner-1",
            identity_address=addr,
            chain_id="ait-hub",
            nonce="nonce-123",
            registered_at=body["registered_at"],
        )
        assert verify_identity_claim(claim, body["identity_proof"], addr)

    def test_register_409_bound_to_same_key_is_benign(self, monkeypatch):
        pk, addr = _new_keypair()
        monkeypatch.setenv("AGENT_SIGNING_KEY", pk)
        self._fake_get(monkeypatch, agent={"identity_address": addr})

        def fake_post(url, **kwargs):
            return _resp({"detail": "bound"}, status=409)

        monkeypatch.setattr(ate.requests, "post", fake_post)
        assert ate._register_agent("aitbc-miner-1", addr, ["whisper"]) is True

    def test_register_409_foreign_identity_is_loud_failure(self, monkeypatch):
        pk, addr = _new_keypair()
        _other_pk, foreign = _new_keypair()
        monkeypatch.setenv("AGENT_SIGNING_KEY", pk)
        self._fake_get(monkeypatch, agent={"identity_address": foreign})

        def fake_post(url, **kwargs):
            return _resp({"detail": "bound"}, status=409)

        monkeypatch.setattr(ate.requests, "post", fake_post)
        assert ate._register_agent("aitbc-miner-1", addr, ["whisper"]) is False

    def test_register_without_key_unchanged(self, monkeypatch):
        calls = []

        def fake_get(url, **kwargs):
            calls.append(url)
            return _resp({})

        monkeypatch.setattr(ate.requests, "get", fake_get)
        captured = {}

        def fake_post(url, **kwargs):
            captured["json"] = kwargs.get("json")
            return _resp({"status": "success"})

        monkeypatch.setattr(ate.requests, "post", fake_post)
        assert ate._register_agent("aitbc-miner-1", PROVIDER, ["whisper"])
        body = captured["json"]
        assert "identity_address" not in body and "identity_proof" not in body
        assert not any("nonce" in u for u in calls)  # no key → no nonce round-trip


class TestEscrowCallSigning:
    """complete/fail carry the live legacy signature AND the req-v1 fields."""

    def test_complete_has_dual_signatures_and_headers(self, monkeypatch):
        from aitbc.crypto.crypto import recover_signer

        pk, addr = _new_keypair()
        monkeypatch.setenv("AGENT_SIGNING_KEY", pk)
        captured = {}

        def fake_post(url, **kwargs):
            captured["json"] = kwargs.get("json")
            captured["headers"] = kwargs.get("headers")
            return _resp({"tx_hash_release": "0xrel"})

        monkeypatch.setattr(ate.requests, "post", fake_post)
        out = ate._complete_task("t-9", addr, amount_units=7)
        assert out["tx_hash_release"] == "0xrel"
        body = captured["json"]
        # Legacy live check (23ad910d6): recover_signer over action/task_id/signed_at/amount_units.
        signed = {k: body[k] for k in ("action", "task_id", "signed_at", "amount_units")}
        assert recover_signer(signed, body["signature"]) == addr
        # New req-v1 field: {task_id, amount_units, timestamp, nonce}.
        req_payload = {
            "task_id": "t-9",
            "amount_units": 7,
            "timestamp": body["timestamp"],
            "nonce": body["nonce"],
        }
        assert _recover_req_payload(req_payload, body["agent_signature"]) == addr
        headers = captured["headers"]
        assert headers["X-Agent-Id"] == ate.AGENT_EXECUTOR_ID
        assert headers["X-Agent-Nonce"] == body["nonce"]

    def test_fail_signs_reason_field(self, monkeypatch):
        pk, addr = _new_keypair()
        monkeypatch.setenv("AGENT_SIGNING_KEY", pk)
        captured = {}

        def fake_post(url, **kwargs):
            captured["json"] = kwargs.get("json")
            captured["headers"] = kwargs.get("headers")
            return _resp({})

        monkeypatch.setattr(ate.requests, "post", fake_post)
        ate._fail_task("t-2", addr, reason="whisper exploded")
        body = captured["json"]
        assert body["reason"] == "whisper exploded"
        req_payload = {
            "task_id": "t-2",
            "reason": "whisper exploded",
            "timestamp": body["timestamp"],
            "nonce": body["nonce"],
        }
        assert _recover_req_payload(req_payload, body["agent_signature"]) == addr
        assert "X-Agent-Signature" in captured["headers"]

    def test_unsigned_mode_has_no_new_fields(self, monkeypatch):
        captured = {}

        def fake_post(url, **kwargs):
            captured["json"] = kwargs.get("json")
            captured["headers"] = kwargs.get("headers")
            return _resp({"tx_hash_release": "0xrel"})

        monkeypatch.setattr(ate.requests, "post", fake_post)
        ate._complete_task("t-9", PROVIDER, amount_units=1)
        body = captured["json"]
        assert "signature" not in body
        assert "agent_signature" not in body and "timestamp" not in body and "nonce" not in body
        assert captured["headers"] == {}


class TestEscrowGateAndInboundSig:
    def test_quote_rejects_unanchored_lock(self, executor, monkeypatch):
        escrow = _locked_escrow()
        del escrow["tx_hash_lock"]
        del escrow["contract_id"]
        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [_msg("m1", "task_request", _task_request())])
        monkeypatch.setattr(ate, "_service_ready", lambda s: True)
        monkeypatch.setattr(ate, "_task_escrow_status", lambda t: escrow)
        stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert stats["rejected"] == 1
        assert "not anchored on-chain" in executor["sent"][0][1]["reason"]

    def test_accept_skips_unanchored_lock(self, executor, monkeypatch):
        state = ate._load_state()
        state["quotes"]["t-1"] = {
            "buyer": BUYER,
            "price": "0.02",
            "offer_id": "whisper-base",
            "request": _task_request("t-1"),
        }
        ate._save_state(state)
        escrow = _locked_escrow()
        del escrow["tx_hash_lock"]
        del escrow["contract_id"]
        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [_msg("m-a", "task_accept", {"task_id": "t-1"})])
        monkeypatch.setattr(ate, "_task_escrow_status", lambda t: escrow)
        called = []
        monkeypatch.setattr(ate, "_ipfs_cat", lambda cid: called.append(cid) or b"x")
        stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert stats["executed"] == 0 and stats["failed"] == 0
        assert called == []  # no work performed against a bookkeeping-only lock

    def test_invalid_signature_message_dropped(self, executor, monkeypatch):
        msg = _msg("m-bad", "task_request", _task_request())
        msg["signature_status"] = "invalid"
        marked = []
        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [msg])
        monkeypatch.setattr(ate, "_mark_read", lambda mid: marked.append(mid))
        monkeypatch.setattr(ate, "_service_ready", lambda s: True)
        stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert all(v == 0 for v in stats.values())
        assert executor["sent"] == []
        assert marked == ["m-bad"]  # consumed once — not re-polled forever

    def test_verified_signature_message_processed(self, executor, monkeypatch):
        msg = _msg("m-ok", "task_request", _task_request())
        msg["signature_status"] = "verified"
        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [msg])
        monkeypatch.setattr(ate, "_service_ready", lambda s: True)
        monkeypatch.setattr(ate, "_task_escrow_status", lambda t: _locked_escrow())
        stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert stats["quoted"] == 1
