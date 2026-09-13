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
    return {"task_id": task_id, "escrow_status": "locked", "agent": agent, "amount": amount}


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
        monkeypatch.setattr(ate, "_complete_task", lambda t, amount_units=None: {"tx_hash_release": "0xrel"})

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
        monkeypatch.setattr(ate, "_fail_task", lambda t: failed.append(t))
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
