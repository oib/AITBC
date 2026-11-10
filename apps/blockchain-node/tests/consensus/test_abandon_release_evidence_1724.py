"""#1724 — evidence classification of the attestation pair an abandon-release produces.

A validator signs A, the proposer's signed abandon statement releases the vote, then it signs a
rival B at the same height. What a peer sees is the pair (A, B) of round-bound attestations.
Pinned here: a later-round rival is context-only (ROUND_BOUND_CROSS_ROUND), a same-round rival is
refused outright (#1736, option A): a same-round pair would be slashable (ROUND_BOUND_SAME_ROUND)
and an abandon carries no unlock proof, so the attester never signs it.
"""

from __future__ import annotations

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus import abandon, vote_fetch, vote_journal
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.equivocation_policy import PairClass, classify_attestation_pair
from aitbc_chain.consensus.vote_journal import reset_vote_journals

from . import test_round_lock as rl

_round_lock_on = rl._round_lock_on  # reuse the round-lock fixture (autouse)
CHAIN = "test-chain"
A = "0x" + "aa" * 32
B = "0x" + "bb" * 32


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    reset_vote_journals()
    vote_fetch.reset_throttle()
    monkeypatch.setattr(vote_journal, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ra_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "vote_journal_enabled", True)
    monkeypatch.setattr(settings, "vote_journal_abandon_enabled", True)
    yield
    reset_vote_journals()


def _pair(pubs):
    return classify_attestation_pair(
        {"attestations": [{"round_in_payload": "round" in m, "request_round": m.get("round")} for m in pubs]}
    )


async def _release_then_rival(monkeypatch, tmp_path, rival_round, justification):
    monkeypatch.setattr(settings, "vote_journal_justification_enabled", justification)
    our, our_key, prop, prop_key = rl._keys()
    svc, broker = rl._service(monkeypatch, our, our_key, prop, tmp_path)
    await svc._handle_request(rl._header(100, A, prop, 0))
    assert len(broker.published) == 1
    assert svc.handle_abandon(abandon.build_abandon(CHAIN, 100, A, 0, prop, prop_key)) >= 1
    await svc._handle_request(rl._header(100, B, prop, rival_round))
    return [m for _, m in broker.published]


@pytest.mark.asyncio
@pytest.mark.parametrize("justification", [False, True])
async def test_later_round_rival_after_release_is_context_only(monkeypatch, tmp_path, justification):
    pubs = await _release_then_rival(monkeypatch, tmp_path, 1, justification)
    assert [m["round"] for m in pubs] == [0, 1]
    assert _pair(pubs) is PairClass.ROUND_BOUND_CROSS_ROUND


@pytest.mark.asyncio
@pytest.mark.parametrize("justification", [False, True])
async def test_same_round_rival_after_release_is_refused(monkeypatch, tmp_path, justification):
    """#1736: signing a same-round rival would be a slashable pair, so the attester refuses it."""
    pubs = await _release_then_rival(monkeypatch, tmp_path, 0, justification)
    assert [m["round"] for m in pubs] == [0]
    assert _pair(pubs) is None


@pytest.mark.asyncio
async def test_same_round_resign_of_abandoned_hash_is_allowed(monkeypatch, tmp_path):
    """Re-signing the abandoned hash itself is not equivocation."""
    monkeypatch.setattr(settings, "vote_journal_justification_enabled", False)
    our, our_key, prop, prop_key = rl._keys()
    svc, broker = rl._service(monkeypatch, our, our_key, prop, tmp_path)
    await svc._handle_request(rl._header(100, A, prop, 0))
    svc.handle_abandon(abandon.build_abandon(CHAIN, 100, A, 0, prop, prop_key))
    await svc._handle_request(rl._header(100, A, prop, 0))
    assert [m["hash"] for _, m in broker.published] == [A, A]


@pytest.mark.asyncio
async def test_abandon_without_release_does_not_block_same_round(monkeypatch, tmp_path):
    """No vote was cast for the abandoned hash, so nothing is recorded or refused."""
    our, our_key, prop, prop_key = rl._keys()
    svc, broker = rl._service(monkeypatch, our, our_key, prop, tmp_path)
    assert svc.handle_abandon(abandon.build_abandon(CHAIN, 100, A, 0, prop, prop_key)) == 0
    await svc._handle_request(rl._header(100, B, prop, 0))
    assert [m["hash"] for _, m in broker.published] == [B]
