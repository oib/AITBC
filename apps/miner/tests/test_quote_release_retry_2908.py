"""AUDIT-EDGE pin: #2908 escrow release failure must retain the quote.

_complete_task returning None used to still pop state['quotes'], so paid
work completed, the result was sent, and the buyer's redelivered
task_accept hit 'unknown/unquoted task' — escrow locked forever. The
quote now survives with the result snapshot; a retry replays the result
and re-calls only /complete, and terminal execution failure pops it.
"""

import json

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


def _locked_escrow(task_id="t-1"):
    return {
        "task_id": task_id,
        "escrow_status": "locked",
        "agent": PROVIDER,
        "amount": 72_000_000,
        "tx_hash_lock": "0xlockhash",
        "contract_id": "esc-1",
    }


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
    monkeypatch.setattr(ate, "_task_escrow_status", lambda t: _locked_escrow(t))
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


def _wire_successful_exec(monkeypatch):
    monkeypatch.setattr(ate, "_ipfs_cat", lambda cid, **k: b"audio-bytes")
    monkeypatch.setattr(ate, "_ipfs_add", lambda data, filename="r": "bafyResult")
    handler_calls = []

    def handler(req, payload):
        handler_calls.append(req)
        return b'{"text":"hello"}'

    monkeypatch.setitem(ate.SERVICE_HANDLERS, "whisper", handler)
    return handler_calls


def test_release_failure_retains_quote_and_retry_releases(executor, monkeypatch):
    task_id = "t-rel"
    _seed_quote(task_id)
    handler_calls = _wire_successful_exec(monkeypatch)
    completes = iter([None, {"tx_hash_release": "0xrel"}])
    monkeypatch.setattr(ate, "_complete_task", lambda t, w, amount_units=None: next(completes))

    inbox1 = [_msg("m-a1", "task_accept", {"task_id": task_id})]
    monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: inbox1)
    stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
    assert stats["executed"] == 1
    # work done + result sent, but release failed: no task_paid, quote kept
    types = [s[0] for s in executor["sent"]]
    assert types == ["task_result"]
    state = ate._load_state()
    assert task_id in state["quotes"]
    assert state["quotes"][task_id]["result"]["result_ref"] == "bafyResult"

    # buyer redelivers task_accept (new message id): result replayed, handler
    # NOT re-run, release retried and confirmed, quote popped.
    inbox2 = [_msg("m-a2", "task_accept", {"task_id": task_id})]
    monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: inbox2)
    stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
    assert stats["executed"] == 1
    assert len(handler_calls) == 1, "paid work must not re-run on release retry"
    types = [s[0] for s in executor["sent"]]
    assert types == ["task_result", "task_result", "task_paid"]
    state = ate._load_state()
    assert task_id not in state["quotes"]


def test_terminal_failure_pops_quote(executor, monkeypatch):
    task_id = "t-fail"
    _seed_quote(task_id)
    monkeypatch.setattr(ate, "_ipfs_cat", lambda cid, **k: b"audio")

    def boom(req, payload):
        raise RuntimeError("whisper exploded")

    monkeypatch.setitem(ate.SERVICE_HANDLERS, "whisper", boom)
    monkeypatch.setattr(ate, "_fail_task", lambda t, w, reason=None: None)
    monkeypatch.setattr(ate, "_fetch_inbox", lambda *a, **k: [_msg("m-f1", "task_accept", {"task_id": task_id})])
    stats = ate.sweep_once(PROVIDER, PRICE_TABLE)
    assert stats["failed"] == 1
    state = ate._load_state()
    assert task_id not in state["quotes"], "terminal failure must not leave a retryable quote"
