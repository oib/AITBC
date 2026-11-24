"""AUDIT-EDGE pins: #2907 ipfs pin quota must account for unmeasurable pins.

object/stat is dead on current Kubo, so every pin measured None: the
sweeper stored size=None and counted the job handled forever, and the
agent executor charged unknown sizes as 0. dag/stat now measures; an
unmeasurable pin is reclaimed, legacy size=None entries re-stat each
sweep, and unknown sizes bill worst-case.
"""

import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_task_executor as ate  # noqa: E402
import ipfs_pinning_sweeper as sweeper  # noqa: E402

PROVIDER = "0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2"
CID = "QmZdJ5Pjb6XC3oSHhJYUAnHT9PaNSbMqTSdozvj1WErNbh"


def _resp(json_data=None, status=200, text=None):
    r = Mock()
    r.status_code = status
    r.json.return_value = json_data if json_data is not None else {}
    r.text = text if text is not None else (json.dumps(json_data) if json_data is not None else "")
    r.raise_for_status = Mock()
    if status >= 400:
        import requests

        r.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status}")
    return r


def _job(job_id="job-1", **over):
    job = {
        "job_id": job_id,
        "id": job_id,
        "service_type": "ipfs",
        "state": "RUNNING",
        "buyer_address": "0xBuyer",
        "payload": {"cid": CID},
        "constraints": {"disk_quota_mb": 100},
    }
    job.update(over)
    return job


@pytest.fixture()
def state_path(tmp_path):
    return tmp_path / "ipfs-pinning.json"


def _sweeper_stub(calls, dag_stat_text='{"TotalSize": 1000}'):
    def fake_post(url, **kwargs):
        calls["ipfs"].append(url)
        if url.endswith("/api/v0/dag/stat"):
            return _resp(text=dag_stat_text) if dag_stat_text is not None else _resp(status=500)
        return _resp({})

    return fake_post


def test_unmeasurable_pin_is_reclaimed(state_path, monkeypatch):
    """dag/stat failing -> size None -> pin must be reclaimed, not stored."""
    monkeypatch.setattr(sweeper, "IPFS_API_URL", "http://127.0.0.1:5002")
    monkeypatch.setattr(
        sweeper,
        "_signed_request_params",
        lambda *a, **k: {"signer_address": PROVIDER, "chain_id": "c", "issued_at": 1, "signature": "s"},
    )
    calls = {"ipfs": []}
    jobs = [_job()]

    def fake_get(url, **kwargs):
        if "/v1/market/jobs/" in url:
            return _resp(jobs[0] if url.endswith("/job-1") else {}, status=200 if url.endswith("/job-1") else 404)
        return _resp(jobs)

    with (
        patch.object(sweeper.requests, "post", side_effect=_sweeper_stub(calls, dag_stat_text=None)),
        patch.object(sweeper.requests, "get", side_effect=fake_get),
    ):
        result = sweeper.sweep_once(PROVIDER, state_path)
    assert any(u.endswith("/api/v0/pin/add") for u in calls["ipfs"])
    assert any(u.endswith("/api/v0/pin/rm") for u in calls["ipfs"]), "unmeasurable pin must be reclaimed"
    assert result["pinned"] == 0
    assert not state_path.exists() or json.loads(state_path.read_text()) == {}


def test_object_size_reads_dag_stat_total(monkeypatch):
    monkeypatch.setattr(sweeper, "_valid_cid_arg", lambda c: True)

    def fake_post(path, **kwargs):
        return _resp(text='{"TotalSize": 10}\n{"TotalSize": 4242}\n{"TotalSize": 4242}\n')

    monkeypatch.setattr(sweeper, "_ipfs_post", fake_post)
    assert sweeper._object_size(CID) == 4242


def test_account_ipfs_pin_unknown_size_bills_worst_case(monkeypatch, tmp_path):
    monkeypatch.setattr(ate, "STATE_PATH", tmp_path / "s.json")
    monkeypatch.setattr(ate, "_task_max_payload_bytes", lambda: 100)
    monkeypatch.setattr(ate, "_IPFS_DEFAULT_BUYER_QUOTA_BYTES", 150)
    state = {}
    # result JSON reports size:null (stat failed) -> charged the 100-byte cap;
    # 100 + already-used 100 > 150 quota -> reclaim + raise.
    state["ipfs_usage"] = {"0xBuyer": 100}
    unpinned = []
    monkeypatch.setattr(ate, "_ipfs_unpin", lambda cid: unpinned.append(cid))
    with pytest.raises(ValueError, match="quota"):
        ate._account_ipfs_pin(state, "0xBuyer", {"payload_ref": CID}, b'{"size": null}')
    assert unpinned == [CID]


def test_account_ipfs_pin_known_size_unchanged(monkeypatch, tmp_path):
    monkeypatch.setattr(ate, "STATE_PATH", tmp_path / "s.json")
    monkeypatch.setattr(ate, "_task_max_payload_bytes", lambda: 100)
    monkeypatch.setattr(ate, "_IPFS_DEFAULT_BUYER_QUOTA_BYTES", 150)
    state = {"ipfs_usage": {"0xBuyer": 100}}
    ate._account_ipfs_pin(state, "0xBuyer", {"payload_ref": CID}, b'{"size": 40}')
    assert state["ipfs_usage"]["0xBuyer"] == 140
