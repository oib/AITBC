"""AUDIT-EDGE pins: #2914 — ids interpolated into outbound URL paths.

job_id / task_id / message_id / agent_id / provider_id arrive from
coordinator or buyer-influenced payloads. Interpolated raw, a value
containing '/', '..', '?' or '#' rewrites the request path while the
auth headers (X-Api-Key, X-Miner-ID, X-Agent-*) still attach — a
confused-request / credential-forwarding primitive. Every site now
percent-encodes the id as a single path segment.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

import agent_task_executor as ate
import ipfs_pinning_sweeper as sweeper
import production_miner as pm


@pytest.mark.unit
def test_url_id_encodes_path_metacharacters() -> None:
    assert ate._url_id("plain_id-1") == "plain_id-1"
    assert ate._url_id("a/b?c#d") == "a%2Fb%3Fc%23d"
    assert ate._url_id("../admin") == "..%2Fadmin"


@pytest.mark.unit
def test_task_endpoints_encode_task_id(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_get(url, **kwargs):
        seen.append(url)
        resp = Mock()
        resp.status_code = 200
        resp.json.return_value = {"escrow": {"state": "locked"}}
        return resp

    monkeypatch.setattr(ate.requests, "get", fake_get)
    out = ate._task_escrow_status("task/../../admin?x=1")
    assert out == {"state": "locked"}
    assert seen == [f"{ate.COORDINATOR_URL}/v1/tasks/task%2F..%2F..%2Fadmin%3Fx%3D1/escrow"]


@pytest.mark.unit
def test_market_job_lookup_encodes_job_id(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_get(url, **kwargs):
        seen.append(url)
        resp = Mock()
        resp.status_code = 404
        return resp

    monkeypatch.setattr(sweeper, "_signed_request_params", lambda address, route, binding=None: {})
    monkeypatch.setattr(sweeper.requests, "get", fake_get)
    job, known = sweeper._fetch_job("http://market.test", "j/../secret", "0xProvider")
    assert job is None and known is True
    assert seen == ["http://market.test/v1/market/jobs/j%2F..%2Fsecret"]


@pytest.mark.unit
def test_pin_confirm_encodes_job_id(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_post(url, **kwargs):
        seen.append(url)
        resp = Mock()
        resp.raise_for_status = Mock()
        return resp

    monkeypatch.setattr(sweeper, "_signed_request_params", lambda address, route, binding=None: {})
    monkeypatch.setattr(sweeper.requests, "post", fake_post)
    assert sweeper._confirm_pin("http://market.test", "j/?x", 10, "0xProvider", cid="bafy") is True
    assert seen == ["http://market.test/v1/market/jobs/j%2F%3Fx/pin-confirm"]


@pytest.mark.unit
def test_submit_result_encodes_job_id(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    class _FakeClient:
        def __init__(self, **kwargs):
            pass

        def post(self, path, json=None):
            seen.append(path)
            return Mock()

    monkeypatch.setattr(pm, "AITBCHTTPClient", _FakeClient)
    pm.submit_result("job/../admin", {"ok": True})
    assert seen == ["/v1/miners/job%2F..%2Fadmin/result"]
