"""#2955: agent-task payload fetch falls back to the coordinator proxy.

The buyer pins its input on its own island daemon; the provider-side swarm
read is best-effort and a broken bitswap path used to hang the cat to the
full 120s timeout and fail the paid task. ``_fetch_task_payload`` gives the
local daemon a short fuse and then reads the same bytes through the
coordinator's party-scoped payload proxy.
"""

from unittest.mock import Mock

import agent_task_executor as ate
import pytest
import requests


def _resp(json_data=None, status=200, content=b"", text=""):
    r = Mock()
    r.status_code = status
    r.json.return_value = json_data if json_data is not None else {}
    r.content = content
    r.text = text
    r.iter_content = lambda n=8192, *a, **k: iter([content] if content else [b""])
    r.close = Mock()
    r.raise_for_status = Mock()
    if status >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status}")
    return r


class TestFetchTaskPayload:
    def test_local_success_skips_proxy(self, monkeypatch):
        monkeypatch.setattr(ate, "_ipfs_cat", lambda cid, **k: b"local-bytes")
        proxy_calls = []
        monkeypatch.setattr(ate, "_coordinator_payload_cat", lambda tid: proxy_calls.append(tid) or b"proxy")
        assert ate._fetch_task_payload("t-1", "QmX") == b"local-bytes"
        assert proxy_calls == []

    def test_local_timeout_passed(self, monkeypatch):
        seen = {}

        def fake_cat(cid, timeout=120, max_bytes=None):
            seen["timeout"] = timeout
            return b"x"

        monkeypatch.setattr(ate, "_ipfs_cat", fake_cat)
        monkeypatch.setenv("AGENT_TASK_PAYLOAD_LOCAL_TIMEOUT", "7")
        ate._fetch_task_payload("t-1", "QmX")
        assert seen["timeout"] == 7

    def test_local_failure_falls_back_to_proxy(self, monkeypatch):
        def boom(cid, **k):
            raise requests.ReadTimeout("120s read timeout")

        monkeypatch.setattr(ate, "_ipfs_cat", boom)
        monkeypatch.setattr(ate, "_coordinator_payload_cat", lambda tid: b"proxy-bytes")
        assert ate._fetch_task_payload("t-1", "QmX") == b"proxy-bytes"

    def test_both_fail_raises_with_both_errors(self, monkeypatch):
        def boom(cid, **k):
            raise requests.ReadTimeout("local timeout")

        def proxy_boom(tid):
            raise requests.HTTPError("HTTP 502")

        monkeypatch.setattr(ate, "_ipfs_cat", boom)
        monkeypatch.setattr(ate, "_coordinator_payload_cat", proxy_boom)
        with pytest.raises(RuntimeError) as excinfo:
            ate._fetch_task_payload("t-1", "QmX")
        msg = str(excinfo.value)
        assert "local timeout" in msg and "HTTP 502" in msg


class TestCoordinatorPayloadCat:
    def test_reads_party_scoped_endpoint_bounded(self, monkeypatch):
        monkeypatch.setattr(ate, "COORDINATOR_URL", "http://coord.local")
        monkeypatch.setattr(ate, "AGENT_EXECUTOR_ID", "aitbc-miner-1")
        monkeypatch.setattr(ate, "_agent_request_headers", lambda agent_id: {"X-Agent-Id": agent_id})
        captured = {}

        def fake_get(url, headers=None, timeout=None, stream=None):
            captured["url"] = url
            captured["headers"] = headers
            return _resp(content=b"payload-bytes")

        monkeypatch.setattr(ate.requests, "get", fake_get)
        assert ate._coordinator_payload_cat("t-1") == b"payload-bytes"
        assert captured["url"] == "http://coord.local/v1/tasks/t-1/payload"
        assert captured["headers"]["X-Agent-Id"] == "aitbc-miner-1"

    def test_caps_oversized_body(self, monkeypatch):
        monkeypatch.setattr(ate, "COORDINATOR_URL", "http://coord.local")
        monkeypatch.setattr(ate, "_agent_request_headers", lambda agent_id: {})

        def fake_get(url, headers=None, timeout=None, stream=None):
            return _resp(content=b"x" * 2048)

        monkeypatch.setattr(ate.requests, "get", fake_get)
        with pytest.raises(ValueError, match="cap"):
            ate._coordinator_payload_cat("t-1", max_bytes=1024)
