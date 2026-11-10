"""#1724 — evidence classification of the attestation pair an abandon-release produces.

A validator signs A, the proposer's signed abandon statement releases the vote, then it signs a
rival B at the same height. What a peer sees is the pair (A, B) of round-bound attestations.
Pinned here: a later-round rival is context-only (ROUND_BOUND_CROSS_ROUND), a same-round rival is
ROUND_BOUND_SAME_ROUND (slashable) — the latter is current behaviour, tracked as a finding, and
must be revisited if the attester starts refusing same-round rivals after a release.
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
async def test_same_round_rival_after_release_is_slashable_today(monkeypatch, tmp_path, justification):
    """Characterisation (finding): the released validator also signs a same-round rival."""
    pubs = await _release_then_rival(monkeypatch, tmp_path, 0, justification)
    assert [m["round"] for m in pubs] == [0, 0]
    assert _pair(pubs) is PairClass.ROUND_BOUND_SAME_ROUND
