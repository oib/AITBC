"""#2147 — vote equivocation is keyed on (sequence, view), not the view alone.

The view is a timestamp-derived proposer round and repeats across heights, so honest
prepares/commits at different sequences share a view. Keyed on the view alone they were
flagged as ``vote_equivocation`` and, at the byzantine threshold, every validator persisted
``is_active=False`` (live drill: permanent halt ~10 min in).
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole
from aitbc_chain.config import settings

A = "0x1111111111111111111111111111111111111111"
B = "0x2222222222222222222222222222222222222222"
C = "0x3333333333333333333333333333333333333333"
D = "0x4444444444444444444444444444444444444444"


def _poa() -> MultiValidatorPoA:
    poa = MultiValidatorPoA("chain-2147")
    for addr in (A, B, C, D):
        poa.add_validator(addr, 1000.0)
        poa.validators[addr].role = ValidatorRole.VALIDATOR
    return poa


def _msg(sender: str, block_hash: str, seq: int, view: int, kind: str = "prepare") -> SimpleNamespace:
    return SimpleNamespace(
        message_type=SimpleNamespace(value=kind),
        sender=sender,
        view_number=view,
        sequence_number=seq,
        digest=hashlib.sha256(f"{block_hash}:{seq}:{view}".encode()).hexdigest(),
        block_hash=block_hash,
        signature="0x" + "11" * 65,
    )


def _prepare(poa: MultiValidatorPoA, who: str, h: str, seq: int, view: int) -> bool:
    return poa.record_prepare(who, h, view, message=_msg(who, h, seq, view))


def _commit(poa: MultiValidatorPoA, who: str, h: str, seq: int, view: int) -> bool:
    return poa.record_commit(who, h, view, message=_msg(who, h, seq, view, "commit"))


def test_honest_prepares_at_different_sequences_sharing_a_view_are_not_equivocation():
    poa = _poa()
    assert _prepare(poa, A, "0xaa", 6786, 1) is True
    assert _prepare(poa, A, "0xbb", 6787, 1) is True  # different height, same round
    assert poa.detect_byzantine_behavior(A) is False
    assert poa.get_slashing_history() == []


def test_honest_commits_at_different_sequences_sharing_a_view_are_not_equivocation():
    poa = _poa()
    assert _commit(poa, A, "0xaa", 10, 2) is True
    assert _commit(poa, A, "0xbb", 13, 2) is True
    assert poa.detect_byzantine_behavior(A) is False
    assert poa.get_slashing_history() == []


def test_same_sequence_and_view_different_hash_is_still_equivocation():
    poa = _poa()
    assert _prepare(poa, A, "0xaa", 6786, 1) is True
    assert _prepare(poa, A, "0xbb", 6786, 1) is False
    events = poa.get_slashing_history()
    assert len(events) == 1
    assert '"sequence": 6786' in events[0].evidence  # evidence pair is from one sequence


def test_equivocation_pair_never_mixes_sequences():
    """A real conflict at seq 20 plus an honest vote at seq 21 (same view): the event's two
    signed messages both come from seq 20, so the on-chain verifier can accept it."""
    poa = _poa()
    _prepare(poa, A, "0xaa", 19, 3)
    _prepare(poa, A, "0xbb", 20, 3)
    _prepare(poa, A, "0xcc", 20, 3)  # conflict at (20, 3)
    _prepare(poa, A, "0xdd", 21, 3)
    events = poa.get_slashing_history()
    assert len(events) == 1
    import json

    msgs = json.loads(events[0].evidence)["messages"]
    assert {m["sequence_number"] for m in msgs} == {20}
    assert {m["block_hash"] for m in msgs} == {"0xbb", "0xcc"}


def test_same_sequence_different_view_prepare_is_rotation_not_equivocation():
    """Cross-view prepare rotation is the liveness mechanism; cross-view COMMIT conflicts are the
    separate, armed #1940 path — the same-slot detector must stay out of both."""
    poa = _poa()
    assert _prepare(poa, A, "0xaa", 30, 1) is True
    assert _prepare(poa, A, "0xbb", 30, 2) is True
    assert poa.detect_byzantine_behavior(A) is False


def test_legacy_votes_without_a_sequence_keep_view_only_conflict():
    poa = _poa()
    assert poa.record_prepare(A, "hashA", 5) is True
    assert poa.record_prepare(A, "hashB", 5) is False


def test_drill_shape_sequential_heights_sharing_rounds_never_deactivate(monkeypatch):
    """Four validators voting honestly over many heights whose rounds repeat must stay active."""
    monkeypatch.setattr(settings, "consensus_byzantine_threshold", 3)
    poa = _poa()
    for seq in range(6784, 6800):
        view = 1 + (seq % 2)  # rounds repeat across heights
        h = f"0x{seq:064x}"
        for who in (A, B, C, D):
            _prepare(poa, who, h, seq, view)
            _commit(poa, who, h, seq, view)
            poa.detect_byzantine_behavior(who)
    assert all(poa.validators[a].is_active for a in (A, B, C, D))
    assert poa.get_slashing_history() == []


def test_evidence_pair_skips_an_earlier_record_of_the_same_hash_at_another_sequence():
    """The hash 0xbb was first recorded at seq 19 (same view); the conflict is at seq 20. The
    event must pair the seq-20 records, not the earlier seq-19 copy."""
    import json

    poa = _poa()
    _prepare(poa, A, "0xbb", 19, 3)
    _prepare(poa, A, "0xbb", 20, 3)
    _prepare(poa, A, "0xcc", 20, 3)  # conflict at (20, 3)
    events = poa.get_slashing_history()
    assert len(events) == 1
    msgs = json.loads(events[0].evidence)["messages"]
    assert {m["sequence_number"] for m in msgs} == {20}
