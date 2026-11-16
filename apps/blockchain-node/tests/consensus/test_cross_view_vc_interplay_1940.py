"""#1940 F3 — cross-view COMMIT detector x the #2005 NEW_VIEW excuse.

The detector evidences ONE canonical conflicting pair per (validator, sequence). A pair is
excused by the NEW_VIEW for its LATER view, so excusing that one pair must not hide a real
double-sign: a validator that rotated legitimately (NEW_VIEW at view 1) and then also committed
a third hash at an unjustified view 2 has equivocated, and the evidence must name that pair.
"""

from __future__ import annotations

import json

import pytest
from aitbc_chain.config import settings

from .test_pbft_view_change_2005 import (
    HA,
    HB,
    HC,
    MEMBERS,
    Q,
    SEQ,
    _commit_rec,
    _make_consensus,
    _nv,
    _pbft,
    _proposer,
    _vc_set,
    KEYS,
    vc_armed,  # noqa: F401  (fixture)
    _fresh_chain,  # noqa: F401  (fixture)
)

ACCUSED = MEMBERS[1]


@pytest.fixture(autouse=True)
def _armed(monkeypatch, vc_armed, _fresh_chain):  # noqa: F811
    monkeypatch.setattr(settings, "pbft_cross_view_commit_lock_height", 0)
    yield


def _store(consensus, rows):
    consensus.commit_messages[ACCUSED] = [
        {"block_hash": h, "round": 0, "timestamp": 0.0, **_commit_rec(ACCUSED, h, SEQ, v)} for h, v in rows
    ]


async def _engine_with_nv(consensus, *views):
    """One engine holding a verified free NEW_VIEW for every ``view``."""
    pbft = _pbft(consensus, MEMBERS[0], KEYS[MEMBERS[0]])
    for view in views:
        assert pbft._vc_floor_raise(SEQ, view)
        vc_set = _vc_set(SEQ, view, MEMBERS[:Q])
        await pbft._handle_new_view_payload(_nv(_proposer(SEQ, view), SEQ, view, vc_set, None))
        assert pbft.view_change_unlock_justification(SEQ, view) is not None
    return pbft


def _events(consensus):
    return list(consensus._slashing_manager.slashing_events)


@pytest.mark.asyncio
async def test_sanctioned_rotation_alone_is_not_slashed():
    consensus = _make_consensus()
    await _engine_with_nv(consensus, 1)
    _store(consensus, [(HA, 0), (HB, 1)])
    assert consensus._detect_cross_view_commit_equivocations(ACCUSED) is False
    assert _events(consensus) == []


@pytest.mark.asyncio
async def test_unsanctioned_rival_without_any_new_view_is_slashed():
    consensus = _make_consensus()
    _store(consensus, [(HA, 0), (HB, 1)])
    assert consensus._detect_cross_view_commit_equivocations(ACCUSED) is True
    assert len(_events(consensus)) == 1


@pytest.mark.asyncio
async def test_excused_pair_does_not_mask_a_later_unjustified_double_sign():
    """A (v0), B (v1, NEW_VIEW-sanctioned), C (v2, NO NEW_VIEW): the (A|B, C) pair is real."""
    consensus = _make_consensus()
    await _engine_with_nv(consensus, 1)
    _store(consensus, [(HA, 0), (HB, 1), (HC, 2)])
    assert consensus._detect_cross_view_commit_equivocations(ACCUSED) is True
    events = _events(consensus)
    assert len(events) == 1
    evidence = json.loads(events[0].evidence)
    assert evidence["views"][-1] == 2  # the unjustified later vote is the evidenced one
    assert HC.lower() in {m["block_hash"].lower() for m in evidence["messages"]}


@pytest.mark.asyncio
async def test_fully_sanctioned_rotation_chain_is_not_slashed():
    consensus = _make_consensus()
    await _engine_with_nv(consensus, 1, 2)
    _store(consensus, [(HA, 0), (HB, 1), (HC, 2)])
    assert consensus._detect_cross_view_commit_equivocations(ACCUSED) is False
    assert _events(consensus) == []


@pytest.mark.asyncio
async def test_locked_new_view_permits_only_the_forced_hash():
    """NEW_VIEW(v1) forces HB: committing HB is sanctioned, committing HC at v1 is not."""
    consensus = _make_consensus()
    pbft = _pbft(consensus, MEMBERS[0], KEYS[MEMBERS[0]])
    assert pbft._vc_floor_raise(SEQ, 1)
    vc_set = _vc_set(SEQ, 1, MEMBERS[:Q], locked_hash=HB, lock_view=0)
    await pbft._handle_new_view_payload(_nv(_proposer(SEQ, 1), SEQ, 1, vc_set, HB))
    _store(consensus, [(HA, 0), (HB, 1), (HC, 1)])
    assert consensus._detect_cross_view_commit_equivocations(ACCUSED) is True
    evidence = json.loads(_events(consensus)[0].evidence)
    assert HC.lower() in {m["block_hash"].lower() for m in evidence["messages"]}


@pytest.mark.asyncio
async def test_evidence_is_observation_order_independent():
    first = _make_consensus()
    await _engine_with_nv(first, 1)
    _store(first, [(HA, 0), (HB, 1), (HC, 2)])
    first._detect_cross_view_commit_equivocations(ACCUSED)
    second = _make_consensus()
    await _engine_with_nv(second, 1)
    _store(second, [(HC, 2), (HB, 1), (HA, 0)])
    second._detect_cross_view_commit_equivocations(ACCUSED)
    a, b = json.loads(_events(first)[0].evidence), json.loads(_events(second)[0].evidence)
    assert a["messages"] == b["messages"]


@pytest.mark.asyncio
async def test_new_view_verifications_stay_bounded_per_view(monkeypatch):
    """A free NEW_VIEW at v1 with many distinct hashes costs at most 2 proofs there."""
    consensus = _make_consensus()
    await _engine_with_nv(consensus, 1)
    hashes = ["0x" + f"{i:02x}" * 32 for i in range(1, 9)]
    _store(consensus, [(HA, 0)] + [(h, 1) for h in hashes])
    calls = []
    real = consensus._cross_view_pair_justified
    monkeypatch.setattr(consensus, "_cross_view_pair_justified", lambda *a: calls.append(1) or real(*a))
    assert consensus._detect_cross_view_commit_equivocations(ACCUSED) is False
    assert len(calls) <= 3  # canonical pair + 2 per view
