"""Phase-0 test for AGENT-EXECUTOR-PAYLOAD-UNBOUNDED-1 (#801).

``agent_task_executor._ipfs_cat`` reads the buyer's ``payload_ref`` object and
every service response fully into memory with no size bound; a buyer who
locks a small escrow can point at a multi-GB IPFS object and the miner holds
it whole (aitbc-miner has MemoryMax=infinity).

Desired behaviour (pinned here): the cat asks IPFS for the size first or
streams with a running count and aborts at a configured per-service cap
(env: AGENT_TASK_MAX_PAYLOAD_BYTES), service responses get the same cap, and
an over-cap payload fails the task without touching the escrow release.
These tests FAIL on current main — the content is returned and the task
executes — that is the bug demonstration.
"""

from unittest.mock import Mock

import agent_task_executor as ate
import pytest

PROVIDER = "0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2"
CAP_ENV = "AGENT_TASK_MAX_PAYLOAD_BYTES"
CAP = 1024  # tiny cap for the test; the fix reads this env name


def _resp(content: bytes, status: int = 200):
    r = Mock()
    r.status_code = status
    r.content = content
    r.headers = {"Content-Length": str(len(content))}
    r.json.return_value = {}
    r.raise_for_status = Mock()
    r.iter_content = lambda chunk_size=8192: iter([content])
    return r


@pytest.fixture
def capped(monkeypatch):
    monkeypatch.setenv(CAP_ENV, str(CAP))
    return CAP


class TestIpfsCatCap:
    def test_over_cap_object_refused(self, capped, monkeypatch):
        post = Mock(return_value=_resp(b"x" * (CAP + 1)))
        monkeypatch.setattr(ate.requests, "post", post)
        with pytest.raises(ValueError):
            ate._ipfs_cat("bafyBigObject")

    def test_under_cap_object_returned(self, capped, monkeypatch):
        body = b"ok" * 10
        monkeypatch.setattr(ate.requests, "post", Mock(return_value=_resp(body)))
        assert ate._ipfs_cat("bafySmall") == body


class TestServiceResponseCap:
    def test_whisper_response_over_cap_refused(self, capped, monkeypatch):
        monkeypatch.setattr(ate.requests, "post", Mock(return_value=_resp(b"y" * (CAP + 1))))
        with pytest.raises(ValueError):
            ate._exec_whisper({"service_type": "whisper"}, b"audio")


class TestOverCapPayloadFailsTask:
    def test_task_fails_without_release(self, capped, monkeypatch):
        """A payload past the cap must end in 'failed' — never 'executed'.

        On current main the oversized cat returns and the task runs to
        'executed', so this fails today.
        """
        sent, failed = [], []
        monkeypatch.setattr(ate, "_task_escrow_status", lambda tid: {"escrow_status": "locked", "agent": PROVIDER})
        monkeypatch.setattr(ate, "_escrow_lock_confirmed", lambda escrow: True)
        monkeypatch.setattr(ate, "_send_message", lambda *a, **k: sent.append(a))
        monkeypatch.setattr(ate, "_fail_task", lambda *a, **k: failed.append(a))

        def fake_post(url, **kwargs):
            if url.endswith("/api/v0/cat"):
                return _resp(b"z" * (CAP + 1))
            if url.endswith("/api/v0/add"):
                r = _resp(b"")
                r.json.return_value = {"Hash": "bafyResult"}
                return r
            return _resp(b"result")

        monkeypatch.setattr(ate.requests, "post", fake_post)

        task_id = "task-1"
        state = {"quotes": {task_id: {"request": {"service_type": "whisper", "payload_ref": "bafyBig"}, "quoted_at": 0}}}
        acc = {"task_id": task_id}
        msg = {"sender": "buyer-1"}
        result = ate._handle_task_accept(msg, acc, "agent-1", PROVIDER, state)
        assert result == "failed"
        assert failed, "the task must be reported failed"
