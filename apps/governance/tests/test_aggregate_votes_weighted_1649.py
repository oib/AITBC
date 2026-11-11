"""#1649: aggregate-votes reports token-weighted tallies and safe fields only.

Operator ruling A: totals sum ``voting_power_used`` (not Vote row counts),
and the ``votes`` list serializes a curated public dict instead of raw ORM
rows. Direct DB seeding bypasses the server-side weight computation so the
pin can prove weights — not counts — drive the totals.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from governance_service.domain.governance import Proposal, Vote
from governance_service.main import app
from governance_service.storage import get_session


@pytest.mark.asyncio
async def test_aggregate_votes_is_token_weighted(client) -> None:
    now = datetime.now(UTC)
    async with get_session() as session:
        proposal = Proposal(
            proposer_id="proposer-1",
            title="Weighted tally",
            description="test",
            voting_starts=now - timedelta(hours=1),
            voting_ends=now + timedelta(days=7),
            status="active",
        )
        session.add(proposal)
        await session.commit()
        pid = proposal.proposal_id
        for i, weight in enumerate((Decimal("5"), Decimal("10"))):
            session.add(
                Vote(
                    proposal_id=pid,
                    voter_id=f"voter-{i}",
                    vote_type="for",
                    voting_power_used=weight,
                    power_at_snapshot=weight,
                    voting_power=weight,
                    vote_weight=weight,
                    chain_id="ait-hub",
                )
            )
        await session.commit()

    r = client.post(f"/v1/governance/proposals/{pid}/aggregate-votes", json=_signed({}))
    assert r.status_code == 200, r.text
    body = r.json()
    # Two vote ROWS but weight 15 — row-count semantics would say 2.
    assert body["total_for"] == 15
    assert body["total_against"] == 0
    assert body["total_abstain"] == 0
    assert len(body["votes"]) == 2
    # Safe-fields contract: curated dict, no ORM internals, no signature.
    for v in body["votes"]:
        assert "signature" not in v
        assert v["voting_power_used"] in (5, 10)
        assert v["vote_type"] == "for"


@pytest.mark.asyncio
async def test_aggregate_votes_zero_weight_votes_sum_to_zero(client) -> None:
    """Zero-power votes contribute 0 to the tally — not 1 per row."""
    now = datetime.now(UTC)
    async with get_session() as session:
        proposal = Proposal(
            proposer_id="proposer-1",
            title="Zero weight",
            description="test",
            voting_starts=now - timedelta(hours=1),
            voting_ends=now + timedelta(days=7),
            status="active",
        )
        session.add(proposal)
        await session.commit()
        pid = proposal.proposal_id
        session.add(
            Vote(
                proposal_id=pid,
                voter_id="voter-z",
                vote_type="for",
                voting_power_used=Decimal("0"),
                chain_id="ait-hub",
            )
        )
        await session.commit()

    r = client.post(f"/v1/governance/proposals/{pid}/aggregate-votes", json=_signed({}))
    assert r.status_code == 200, r.text
    assert r.json()["total_for"] == 0


# ── signature helpers (same scheme as test_piapi002_write_surface) ──

PRIVKEY = "0x" + "11" * 32


def _address(privkey: str) -> str:
    from eth_keys import keys

    return keys.PrivateKey(bytes.fromhex(privkey.removeprefix("0x"))).public_key.to_checksum_address()


def _sign_body(private_key: str, payload: dict[str, Any]) -> str:
    from eth_keys import keys
    from eth_utils import keccak

    msg = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    pk = keys.PrivateKey(bytes.fromhex(private_key.removeprefix("0x")))
    return pk.sign_msg_hash(keccak(msg)).to_hex()


def _signed(body: dict[str, Any], privkey: str = PRIVKEY) -> dict[str, Any]:
    out = dict(body)
    out["caller_address"] = _address(privkey)
    out["timestamp"] = time.time()
    out["signature"] = _sign_body(privkey, {k: v for k, v in out.items() if k != "signature"})
    return out


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
