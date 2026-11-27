"""#3080 (AUDIT-ATASK-ESCROW-1): provider-side escrow gates.

HIGH-3: the executor used to start paid work on mempool admission — a
``tx_hash_lock``/``contract_id`` pair that only proves the lock tx was
*seen*, not sealed. A buyer can replace-by-fee evict an unsealed lock and
keep the result unpaid. The accept gate now requires ``lock_sealed is
True`` (the coordinator probes ``/rpc/transaction/{hash}``) plus a readable,
future ``expires_at`` (HIGH-4: the expire sweep refunds past it mid-work).

CRIT-1: an on-chain escrow no longer releases on delivery — the result goes
out, the quote parks on ``needs_attestation``, and only the buyer's
``task_attest`` (carrying the sealed buyer-signed ``software_job`` hash)
unblocks ``/complete`` with ``job_tx_hash`` + ``result_hash``.
"""

import json
import time

import agent_task_executor as ate
import pytest

PROVIDER = "0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2"
BUYER = "buyer-node0"

PRICE_TABLE = {"whisper": {"service_type": "whisper", "model": "base", "price": "0.02"}}


def _msg(msg_id, message_type, content, sender=BUYER):
    return {
        "message_id": msg_id,
        "message_type": message_type,
        "sender": sender,
        "recipient": "aitbc-miner-1",
        "content": json.dumps(content),
    }


def _task_request(task_id="t-1"):
    return {
        "task_id": task_id,
        "service_type": "whisper",
        "model": "base",
        "payload_ref": "QmPayload",
        "max_price": "0.05",
        "escrow_id": "esc-1",
    }


def _escrow(task_id="t-1", **over):
    escrow = {
        "task_id": task_id,
        "escrow_status": "locked",
        "agent": PROVIDER,
        "amount": 72_000_000,
        "tx_hash_lock": "0xlockhash",
        "contract_id": "esc-1",
        "lock_sealed": True,
        "expires_at": time.time() + 3600,
    }
    escrow.update(over)
    return escrow


@pytest.fixture(autouse=True)
def _clean_signing_env(monkeypatch):
    for var in ("AGENT_SIGNING_KEY", "AGENT_EXECUTOR_SIGNING_KEY", "MINER_WALLET_ADDRESS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("MINER_WALLET_KEY_FILE", "/nonexistent/test-wallet.json")


@pytest.fixture()
def executor(tmp_path, monkeypatch):
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


def _seed_quote(task_id="t-1"):
    state = ate._load_state()
    state["quotes"][task_id] = {
        "buyer": BUYER,
        "price": "0.02",
        "offer_id": "whisper-base",
        "request": _task_request(task_id),
    }
    ate._save_state(state)


def _wire_exec(monkeypatch):
    """Successful whisper run: cat payload, add result, handler returns bytes."""
    monkeypatch.setattr(ate, "_ipfs_cat", lambda cid, **k: b"audio-bytes")
    monkeypatch.setattr(ate, "_ipfs_add", lambda data, filename="r": "bafyResult")
    monkeypatch.setitem(
        ate.SERVICE_HANDLERS,
        "whisper",
        lambda req, payload: b'{"text":"hello"}',
    )


class TestSealedLockGate:
    """HIGH-3/HIGH-4: work starts only on a sealed, unexpired lock."""

    def test_mempool_only_lock_defers_work(self, executor, monkeypatch):
        """lock_sealed absent/False → the accept parks; no work, no result."""
        task_id = "t-unsealed"
        _seed_quote(task_id)
        escrow = _escrow(task_id)
        del escrow["lock_sealed"]  # older coordinator / mempool-only view
        monkeypatch.setattr(ate, "_task_escrow_status", lambda t: escrow)
        calls = []
        monkeypatch.setattr(ate, "_ipfs_cat", lambda *a, **k: calls.append(a) or b"x")
        monkeypatch.setattr(ate, "_fetch_task_payload", lambda *a, **k: calls.append(a) or b"x")

        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [_msg("m-a", "task_accept", {"task_id": task_id})])
        stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert stats["executed"] == 0
        assert calls == [], "no work may run on an unproven lock"
        state = ate._load_state()
        assert state["quotes"][task_id].get("await_ready") is True
        assert [s[0] for s in executor["sent"]] == []

        # The lock seals before the next sweep — the parked accept runs.
        escrow["lock_sealed"] = True
        _wire_exec(monkeypatch)
        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [])
        ate.sweep_once(PROVIDER, PRICE_TABLE)
        types = [s[0] for s in executor["sent"]]
        assert "task_result" in types

    def test_expired_escrow_rejects_work(self, executor, monkeypatch):
        task_id = "t-expired"
        _seed_quote(task_id)
        escrow = _escrow(task_id, expires_at=time.time() - 5)
        monkeypatch.setattr(ate, "_task_escrow_status", lambda t: escrow)
        calls = []
        monkeypatch.setattr(ate, "_fetch_task_payload", lambda *a, **k: calls.append(a) or b"x")

        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [_msg("m-a", "task_accept", {"task_id": task_id})])
        ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert calls == []
        types = [s[0] for s in executor["sent"]]
        assert types == ["task_reject"]
        assert executor["sent"][0][1]["reason"] == "escrow expired"
        assert task_id not in ate._load_state()["quotes"]

    def test_missing_expires_at_refuses_work(self, executor, monkeypatch):
        task_id = "t-noexp"
        _seed_quote(task_id)
        escrow = _escrow(task_id)
        escrow["expires_at"] = None
        monkeypatch.setattr(ate, "_task_escrow_status", lambda t: escrow)
        calls = []
        monkeypatch.setattr(ate, "_fetch_task_payload", lambda *a, **k: calls.append(a) or b"x")

        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [_msg("m-a", "task_accept", {"task_id": task_id})])
        ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert calls == []
        assert [s[0] for s in executor["sent"]] == []


class TestBuyerAttestedRelease:
    """CRIT-1: /complete waits for the buyer's task_attest on-chain escrows."""

    def test_result_sent_but_no_release_until_attest(self, executor, monkeypatch):
        task_id = "t-att"
        _seed_quote(task_id)
        _wire_exec(monkeypatch)
        monkeypatch.setattr(ate, "_task_escrow_status", lambda t: _escrow(task_id))
        completes = []
        monkeypatch.setattr(
            ate,
            "_complete_task",
            lambda t, w, **kw: completes.append(kw) or {"tx_hash_release": "0xrel"},
        )

        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [_msg("m-a", "task_accept", {"task_id": task_id})])
        stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert stats["executed"] == 1
        # The provider must NOT self-release: result delivered, release parked.
        assert completes == []
        types = [s[0] for s in executor["sent"]]
        assert types == ["task_result"]
        quote = ate._load_state()["quotes"][task_id]
        assert quote["needs_attestation"] is True
        assert quote["result"]["result_hash"]

        # Buyer attests → release fires with the attestation forwarded.
        job_tx = "0x" + "ab" * 32
        attest = _msg(
            "m-at",
            "task_attest",
            {"task_id": task_id, "job_tx_hash": job_tx, "result_hash": quote["result"]["result_hash"]},
        )
        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [attest])
        stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert stats["executed"] == 1
        assert len(completes) == 1
        assert completes[0]["job_tx_hash"] == job_tx
        assert completes[0]["result_hash"] == quote["result"]["result_hash"]
        types = [s[0] for s in executor["sent"]]
        assert types[-1] == "task_paid"
        assert task_id not in ate._load_state()["quotes"]

    def test_attest_from_wrong_sender_ignored(self, executor, monkeypatch):
        task_id = "t-spoof"
        _seed_quote(task_id)
        _wire_exec(monkeypatch)
        monkeypatch.setattr(ate, "_task_escrow_status", lambda t: _escrow(task_id))
        completes = []
        monkeypatch.setattr(ate, "_complete_task", lambda t, w, **kw: completes.append(kw) or {"tx_hash_release": "0x"})

        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [_msg("m-a", "task_accept", {"task_id": task_id})])
        ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert completes == []

        spoof = _msg(
            "m-spoof",
            "task_attest",
            {"task_id": task_id, "job_tx_hash": "0x" + "ab" * 32},
            sender="attacker-node",
        )
        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [spoof])
        ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert completes == [], "a non-buyer attestation must not release the escrow"
        assert task_id in ate._load_state()["quotes"]

    def test_attest_before_result_ignored(self, executor, monkeypatch):
        """A buyer cannot attest work it has not seen — quote stays clean."""
        task_id = "t-early"
        _seed_quote(task_id)
        monkeypatch.setattr(ate, "_task_escrow_status", lambda t: _escrow(task_id))
        completes = []
        monkeypatch.setattr(ate, "_complete_task", lambda t, w, **kw: completes.append(kw) or {"tx_hash_release": "0x"})

        early = _msg("m-early", "task_attest", {"task_id": task_id, "job_tx_hash": "0x" + "ab" * 32})
        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [early])
        ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert completes == []
        quote = ate._load_state()["quotes"][task_id]
        assert "attestation" not in quote
        assert "needs_attestation" not in quote

    def test_failed_release_retries_after_attest(self, executor, monkeypatch):
        """Attestation recorded but /complete keeps failing → sweep retries."""
        task_id = "t-retry"
        _seed_quote(task_id)
        _wire_exec(monkeypatch)
        monkeypatch.setattr(ate, "_task_escrow_status", lambda t: _escrow(task_id))
        # The attest handler and the same-sweep pending-release retry each
        # consume one failure before the quote is retained for the next pass.
        completes = iter([None, None, {"tx_hash_release": "0xrel"}])
        monkeypatch.setattr(
            ate,
            "_complete_task",
            lambda t, w, **kw: next(completes),
        )

        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [_msg("m-a", "task_accept", {"task_id": task_id})])
        ate.sweep_once(PROVIDER, PRICE_TABLE)
        attest = _msg("m-at", "task_attest", {"task_id": task_id, "job_tx_hash": "0x" + "ab" * 32})
        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [attest])
        ate.sweep_once(PROVIDER, PRICE_TABLE)
        # Both release attempts failed — quote retained WITH the attestation.
        quote = ate._load_state()["quotes"][task_id]
        assert quote["attestation"]["job_tx_hash"] == "0x" + "ab" * 32

        monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [])
        stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
        assert stats["released"] == 1
        assert task_id not in ate._load_state()["quotes"]
        assert executor["sent"][-1][0] == "task_paid"
