"""#2970: market IPFS escrow rails are not production-miner executable work."""

from __future__ import annotations

import production_miner
from aitbc.market import is_market_ipfs_escrow_rail


def _rail_job() -> dict:
    return {
        "job_id": "coord-job-ipfs-rail",
        "payload": {
            "type": "ipfs",
            "source": "market_host",
            "market_job_id": "sw_job_ipfs_test",
        },
    }


def test_marker_matches_only_the_market_host_escrow_rail():
    assert is_market_ipfs_escrow_rail(_rail_job()["payload"])
    assert not is_market_ipfs_escrow_rail({"type": "ipfs"})
    assert not is_market_ipfs_escrow_rail({"type": "ipfs", "source": "market_host"})
    assert not is_market_ipfs_escrow_rail({"type": "inference", "source": "market_host", "market_job_id": "x"})


def test_execute_job_ignores_rail_without_submitting_success_or_failure(monkeypatch):
    submitted = []
    monkeypatch.setattr(production_miner, "_submit_failure", lambda *args: submitted.append(("failure", args)))
    monkeypatch.setattr(production_miner, "_submit_success", lambda *args, **kwargs: submitted.append(("success", args)))

    assert production_miner.execute_job(_rail_job(), []) is False

    assert submitted == []


def test_dispatch_does_not_hold_a_local_slot_for_rail(monkeypatch):
    claims = []
    monkeypatch.setattr(production_miner, "_claim_job_slot", lambda job_id: claims.append(job_id) or True)

    production_miner._dispatch_job(_rail_job(), [])

    assert claims == []
    assert "coord-job-ipfs-rail" not in production_miner.ACTIVE_JOB_IDS
