"""#2875: cross-chain governance routes need lifecycle guards, bounded
target lists, and per-chain execution records.

Before the fix ``propagate`` had no status check at all (draft/defeated/
cancelled proposals fanned out GOVERNANCE_PROPOSE txs), ``execute-cross-chain``
accepted already-executed proposals and re-relayed EXECUTE txs to every
target on every call, and both took unbounded ``target_chains`` lists.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

import pytest
from eth_keys import keys
from eth_utils import keccak
from fastapi.testclient import TestClient

from governance_service.main import app

PRIVKEY = "0x" + "11" * 32


def _address(privkey: str) -> str:
    return keys.PrivateKey(bytes.fromhex(privkey.removeprefix("0x"))).public_key.to_checksum_address()


def _sign_body(private_key: str, payload: dict[str, Any]) -> str:
    msg = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    pk = keys.PrivateKey(bytes.fromhex(private_key.removeprefix("0x")))
    return pk.sign_msg_hash(keccak(msg)).to_hex()


def _signed(body: dict[str, Any]) -> dict[str, Any]:
    out = dict(body)
    addr = _address(PRIVKEY)
    out["caller_address"] = addr
    out["timestamp"] = time.time()
    out["signature"] = _sign_body(PRIVKEY, {k: v for k, v in out.items() if k != "signature"})
    return out


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _create_proposal(client: TestClient) -> str:
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    body = _signed(
        {
            "proposer_address": _address(PRIVKEY),
            "title": "t",
            "description": "d",
            "category": "general",
            "voting_starts": now.isoformat(),
            "voting_ends": (now + timedelta(hours=4)).isoformat(),
        }
    )
    r = client.post("/v1/governance/proposals", json=body)
    assert r.status_code == 200, r.text
    return r.json()["proposal_id"]


def _set_proposal(test_database_path, pid: str, **cols) -> None:
    conn = sqlite3.connect(test_database_path)
    try:
        for k, v in cols.items():
            conn.execute(f"UPDATE proposals SET {k}=? WHERE proposal_id=?", (v, pid))
        conn.commit()
    finally:
        conn.close()


def test_propagate_refuses_defeated_proposal(client: TestClient, test_database_path) -> None:
    pid = _create_proposal(client)
    _set_proposal(test_database_path, pid, status="defeated")
    r = client.post(
        f"/v1/governance/proposals/{pid}/propagate",
        json=_signed({"target_chains": ["ait-side-1"]}),
    )
    assert r.status_code == 400, r.text
    assert "propagate" in r.json()["error"]


def test_propagate_refuses_draft_proposal(client: TestClient, test_database_path) -> None:
    pid = _create_proposal(client)
    _set_proposal(test_database_path, pid, status="draft")
    r = client.post(
        f"/v1/governance/proposals/{pid}/propagate",
        json=_signed({"target_chains": ["ait-side-1"]}),
    )
    assert r.status_code == 400, r.text


def test_propagate_allows_active_proposal(client: TestClient) -> None:
    pid = _create_proposal(client)
    r = client.post(
        f"/v1/governance/proposals/{pid}/propagate",
        json=_signed({"target_chains": []}),
    )
    # Empty target list is valid; per-chain submits may fail but the route answers.
    assert r.status_code == 200, r.text
    assert r.json()["propagated_to"] == []


def test_propagate_rejects_over_cap_target_chains(client: TestClient) -> None:
    pid = _create_proposal(client)
    r = client.post(
        f"/v1/governance/proposals/{pid}/propagate",
        json=_signed({"target_chains": [f"chain-{i}" for i in range(40)]}),
    )
    assert r.status_code == 400, r.text


def _succeeded_proposal(client: TestClient, test_database_path, target_chains: list[str]) -> str:
    import json as _json

    pid = _create_proposal(client)
    _set_proposal(
        test_database_path,
        pid,
        status="succeeded",
        block_height=100,
        voting_ends_block=100,
        proposal_value=_json.dumps({"target_chains": target_chains}),
    )
    return pid


def test_execute_cross_chain_is_idempotent_per_chain(client: TestClient, test_database_path, monkeypatch) -> None:
    from governance_service.clients.blockchain import BlockchainClient

    pid = _succeeded_proposal(client, test_database_path, ["ait-side-1", "ait-side-2"])

    async def _head(self, chain_id=None):
        return 10**9

    submitted: list[str] = []

    async def _submit(self, tx_data):
        submitted.append(tx_data["chain_id"])
        return {"tx_hash": f"0x{tx_data['chain_id']}"}

    monkeypatch.setattr(BlockchainClient, "get_block_height", _head)
    monkeypatch.setattr(BlockchainClient, "submit_transaction", _submit)

    r1 = client.post(f"/v1/governance/proposals/{pid}/execute-cross-chain", json=_signed({}))
    assert r1.status_code == 200, r1.text
    assert sorted(r1.json()["executed_on"]) == ["ait-side-1", "ait-side-2"]
    assert sorted(submitted) == ["ait-side-1", "ait-side-2"]

    # Second call: both chains already recorded — no resubmission.
    r2 = client.post(f"/v1/governance/proposals/{pid}/execute-cross-chain", json=_signed({}))
    assert r2.status_code == 200, r2.text
    assert r2.json()["executed_on"] == []
    assert sorted(r2.json()["skipped_already_executed"]) == ["ait-side-1", "ait-side-2"]
    assert submitted == ["ait-side-1", "ait-side-2"]


def test_execute_cross_chain_rejects_over_cap_targets(client: TestClient, test_database_path, monkeypatch) -> None:
    from governance_service.clients.blockchain import BlockchainClient

    pid = _succeeded_proposal(client, test_database_path, [f"chain-{i}" for i in range(40)])

    async def _head(self, chain_id=None):
        return 10**9

    monkeypatch.setattr(BlockchainClient, "get_block_height", _head)

    r = client.post(f"/v1/governance/proposals/{pid}/execute-cross-chain", json=_signed({}))
    assert r.status_code == 400, r.text
