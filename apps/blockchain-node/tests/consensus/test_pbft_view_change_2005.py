"""#2005 F3-C pins: dormant VIEW_CHANGE / NEW_VIEW consensus protocol.

Design of record: #2005 design comment + rulings comment — q=2f+1 uniform VC
quorum with commit certificates, full signed block in pre-prepare,
certificate view pinned to the derived round, ALL arming deferred (PBFT
stays OFF). ``pbft_view_change_height`` is the single dormant gate; while
unset every consumer is byte-identical to pre-#2005 behavior.

Real secp256k1 keys and signatures throughout, in the style of
``test_cross_view_commit_equivocation_1940.py`` / ``test_pbft_commit_lock_1940.py``.
"""

from __future__ import annotations

import itertools
import json
import uuid
from typing import Any

import pytest
from sqlmodel import Session

from aitbc_chain.base_models import ChainParameter
from aitbc_chain.config import settings
from aitbc_chain.consensus.equivocation_policy import VcApplyContext, view_change_justified
from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole
from aitbc_chain.consensus.pbft import PBFTConsensus, PBFTMessage, PBFTMessageType
from aitbc_chain.consensus.pbft_quorum import pbft_required_messages
from aitbc_chain.consensus.pbft_view_change import (
    MAX_LOCK_PROOF_MSGS,
    MAX_VC_SET_ENTRIES,
    analyze_vc_set,
    commit_digest,
    new_view_digest,
    select_forced_hash,
    verify_new_view,
    verify_view_change,
    verify_vc_lock_proof,
    view_change_active,
    view_change_digest,
    vc_signed_message,
    nv_signed_message,
    commit_signed_message,
    VC_MESSAGE_TYPE,
    NV_MESSAGE_TYPE,
)
from aitbc.crypto.consensus_signing import sign_consensus_message
from aitbc.crypto.signature_recovery import canonical_address

CHAIN = "vc-2005"
# Engine tests persist VC state on chain.db — a shared chain_id leaks floors
# and locks between tests. ``_CID`` is the chain every helper binds unless
# overridden; the engine/evidence fixtures rotate it per test.
_CID = CHAIN
SEQ = 10
VIEW = 3
HA = "0x" + "aa" * 32
HB = "0x" + "bb" * 32
HC = "0x" + "cc" * 32
HD = "0x" + "dd" * 32


def _key(byte: str) -> tuple[str, str]:
    from eth_keys import keys

    priv = "0x" + byte * 32
    return keys.PrivateKey(bytes.fromhex(priv[2:])).public_key.to_checksum_address(), priv


# Four validators: n=4 -> f=1 -> q=pbft_required_messages(4)=3.
V = [_key(c) for c in ("11", "22", "33", "44")]
MEMBERS = [a for a, _ in V]
KEYS = dict(V)
Q = pbft_required_messages(len(MEMBERS))


def _proposer(seq: int, view: int, members: list[str] | None = None) -> str:
    """``select_proposer(seq, view)`` = sorted members[(seq + view) % n]."""
    members = sorted(members if members is not None else MEMBERS)
    return members[(seq + max(0, view)) % len(members)]


def _commit_rec(
    sender: str, block_hash: str, seq: int, view: int, *, key: str | None = None, kind: str = "commit"
) -> dict[str, Any]:
    """One signed vote record (COMMIT by default) as carried in a lock proof."""
    digest = commit_digest(block_hash, seq, view)
    rec = {
        "message_type": kind,
        "sender": sender,
        "view_number": view,
        "sequence_number": seq,
        "block_hash": block_hash,
        "digest": digest,
    }
    rec["signature"] = sign_consensus_message(commit_signed_message(rec), key or KEYS[sender])
    return rec


def _proof(
    block_hash: str, seq: int, lock_view: int, voters: list[str] | None = None, kind: str = "prepare"
) -> list[dict[str, Any]]:
    """A quorum certificate: one signed ``kind`` vote per voter (default q members)."""
    return [_commit_rec(v, block_hash, seq, lock_view, kind=kind) for v in (voters if voters is not None else MEMBERS[:Q])]


def _vc(
    sender: str,
    seq: int,
    view: int,
    *,
    lock: dict[str, Any] | None = None,
    chain_id: str | None = None,
    key: str | None = None,
    sign: bool = True,
) -> dict[str, Any]:
    """A signed VIEW_CHANGE. ``lock=None`` -> no commit lock (lock_view=-1)."""
    chain_id = chain_id or _CID
    if lock is None:
        lock_view, lock_hash = -1, ""
        lock_field = None
    else:
        lock_view, lock_hash = lock["view"], lock["block_hash"]
        lock_field = lock
    vc = {
        "message_type": VC_MESSAGE_TYPE,
        "sender": sender,
        "sequence_number": seq,
        "view_number": view,
        "timestamp": 0.0,
        "lock": lock_field,
    }
    vc["digest"] = view_change_digest(chain_id, seq, view, lock_view, lock_hash)
    if sign:
        vc["signature"] = sign_consensus_message(vc_signed_message(vc), key or KEYS[sender])
    return vc


def _locked(sender: str, block_hash: str, lock_view: int, seq: int, view: int) -> dict[str, Any]:
    """A VC carrying a commit-lock for ``block_hash`` at ``lock_view``."""
    return _vc(
        sender,
        seq,
        view,
        lock={
            "view": lock_view,
            "block_hash": block_hash,
            "kind": "prepare",
            "msgs": _proof(block_hash, seq, lock_view),
        },
    )


def _nv(
    sender: str,
    seq: int,
    view: int,
    vc_set: list[dict[str, Any]],
    chosen: str | None,
    *,
    chain_id: str | None = None,
    key: str | None = None,
) -> dict[str, Any]:
    """A signed NEW_VIEW over ``vc_set`` (digest binds every carried VC)."""
    chain_id = chain_id or _CID
    digests = [str(vc.get("digest", "")) for vc in vc_set]
    nv = {
        "message_type": NV_MESSAGE_TYPE,
        "sender": sender,
        "sequence_number": seq,
        "view_number": view,
        "timestamp": 0.0,
        "vc_set": vc_set,
        "chosen_hash": chosen,
    }
    nv["digest"] = new_view_digest(chain_id, seq, view, chosen, digests)
    nv["signature"] = sign_consensus_message(nv_signed_message(nv), key or KEYS[sender])
    return nv


def _vc_set(
    seq: int, view: int, senders: list[str], *, locked_hash: str | None = None, lock_view: int = 0
) -> list[dict[str, Any]]:
    """Signed VCs for ``senders``; optionally each carries a lock on ``locked_hash``."""
    out = []
    for s in senders:
        if locked_hash is not None:
            out.append(_locked(s, locked_hash, lock_view, seq, view))
        else:
            out.append(_vc(s, seq, view))
    return out


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


class TestGate:
    def test_unset_is_inactive(self):
        assert settings.pbft_view_change_height is None
        assert view_change_active(SEQ) is False
        assert view_change_active(0) is False

    def test_armed_boundaries(self, monkeypatch):
        monkeypatch.setattr(settings, "pbft_view_change_height", 5)
        assert view_change_active(4) is False
        assert view_change_active(5) is True
        assert view_change_active(10**6) is True
        assert view_change_active(None) is False
        assert view_change_active(True) is False
        assert view_change_active("5") is False

    def test_malformed_threshold_inactive(self, monkeypatch):
        for bad in ("x", -1, True, 1.5):
            monkeypatch.setattr(settings, "pbft_view_change_height", bad)
            assert view_change_active(10**9) is False


# ---------------------------------------------------------------------------
# Digests — chain_id binding (#2102-class replay cannot cross chains here)
# ---------------------------------------------------------------------------


class TestDigests:
    def test_vc_digest_binds_chain_id(self):
        a = view_change_digest(CHAIN, SEQ, VIEW, -1, "")
        b = view_change_digest("other-chain", SEQ, VIEW, -1, "")
        assert a != b
        # And the empty-lock sentinel is explicit.
        assert view_change_digest(CHAIN, SEQ, VIEW, -1, "") == a

    def test_nv_digest_binds_chain_id_and_vc_set(self):
        vcs = _vc_set(SEQ, VIEW, MEMBERS[:Q])
        digests = [v["digest"] for v in vcs]
        a = new_view_digest(CHAIN, SEQ, VIEW, None, digests)
        b = new_view_digest("other-chain", SEQ, VIEW, None, digests)
        c = new_view_digest(CHAIN, SEQ, VIEW, None, list(reversed(digests)))
        assert a == c  # canonical: sorted join, order-independent
        assert a != b
        # Swapping one vc digest changes the preimage.
        d = new_view_digest(CHAIN, SEQ, VIEW, None, [digests[0], digests[1], "0" * 64])
        assert a != d

    def test_cross_chain_vc_rejected(self):
        """A VC signed+digested for chain A fails verification on chain B."""
        vc = _vc(MEMBERS[0], SEQ, VIEW, chain_id="other-chain")
        ok, reason = verify_view_change(vc, CHAIN)
        assert not ok
        assert "digest" in reason

    def test_cross_chain_nv_rejected(self):
        vc_set = _vc_set(SEQ, VIEW, MEMBERS[:Q])
        proposer = _proposer(SEQ, VIEW)
        nv = _nv(proposer, SEQ, VIEW, vc_set, None, chain_id="other-chain")
        ok, reason, _, _ = verify_new_view(nv, MEMBERS, chain_id=CHAIN, sequence=SEQ, view=VIEW, expected_sender=proposer)
        assert not ok


# ---------------------------------------------------------------------------
# Quorum intersection — the safety argument, enumerated
# ---------------------------------------------------------------------------


class TestQuorumIntersection:
    @pytest.mark.parametrize("n", [4, 7, 10])
    def test_any_two_q_sets_intersect_in_at_least_one_member(self, n):
        """Two q=pbft_required_messages(n) subsets of n members always share
        >= 2q-n members — and 2q-n >= f+1 by construction of q, so at least
        one honest member is in every VC∩commit intersection."""
        q = pbft_required_messages(n)
        f = (n - 1) // 3
        members = [f"0x{i:040x}" for i in range(n)]
        subsets = list(itertools.combinations(members, q))
        min_intersection = n
        for a, b in itertools.product(subsets, repeat=2):
            min_intersection = min(min_intersection, len(set(a) & set(b)))
        assert min_intersection == 2 * q - n
        assert min_intersection >= f + 1

    def test_adversarial_vc_omission_cannot_hide_a_commit_lock(self):
        """A commit quorum for H forces EVERY q-sized VC set to contain an
        honest lock-holder: pick any q senders, at least one intersects the
        commit quorum and (being honest) reports the lock — so the forced
        selection can never come out 'free' while a commit quorum exists."""
        # Commit quorum: q senders committed HA at view 0.
        commit_quorum = MEMBERS[:Q]
        # Adversary picks the vc_set most favorable to omission: the q
        # members LEAST overlapping the commit quorum.
        [m for m in MEMBERS if m not in commit_quorum]
        # With n=4, q=3, commit quorum of 3 leaves only 1 non-quorum member;
        # any 3-set must include >= 2 quorum members -> locked selection.
        for combo in itertools.combinations(MEMBERS, Q):
            senders = list(combo)
            intersect = [s for s in senders if s in commit_quorum]
            assert intersect, "q-set disjoint from a commit quorum is impossible"
            # Honest intersection members carry the lock.
            vc_set = []
            for s in senders:
                if s in intersect:
                    vc_set.append(_locked(s, HA, 0, SEQ, VIEW))
                else:
                    vc_set.append(_vc(s, SEQ, VIEW))
            by_sender = {canonical_address(v["sender"]): v for v in vc_set}
            kind, selected = select_forced_hash(by_sender)
            assert kind == "locked"
            assert selected == HA

    def test_free_selection_only_when_no_lock_reports(self):
        vc_set = _vc_set(SEQ, VIEW, MEMBERS[:Q])
        by_sender = {canonical_address(v["sender"]): v for v in vc_set}
        kind, selected = select_forced_hash(by_sender)
        assert kind == "free"
        assert selected is None

    def test_conflicting_top_lock_views_fail_closed(self):
        """Two different hashes claiming the SAME highest lock view is a
        conflict honest members cannot produce -> selection fails closed."""
        senders = MEMBERS[:Q]
        vc_set = [
            _locked(senders[0], HA, 2, SEQ, VIEW),
            _locked(senders[1], HB, 2, SEQ, VIEW),  # same top view, different hash
            _locked(senders[2], HA, 1, SEQ, VIEW),  # lower view, agrees with HA
        ]
        by_sender = {canonical_address(v["sender"]): v for v in vc_set}
        kind, selected = select_forced_hash(by_sender)
        assert kind == "conflict"
        assert selected is None

    def test_highest_lock_view_wins(self):
        senders = MEMBERS[:Q]
        vc_set = [
            _locked(senders[0], HA, 1, SEQ, VIEW),
            _locked(senders[1], HB, 3, SEQ, VIEW),  # higher view -> HB forced
            _locked(senders[2], HA, 1, SEQ, VIEW),
        ]
        by_sender = {canonical_address(v["sender"]): v for v in vc_set}
        kind, selected = select_forced_hash(by_sender)
        assert (kind, selected) == ("locked", HB)


# ---------------------------------------------------------------------------
# VIEW_CHANGE verification
# ---------------------------------------------------------------------------


class TestVerifyViewChange:
    def test_valid_unlocked_vc_accepted(self):
        vc = _vc(MEMBERS[0], SEQ, VIEW)
        assert verify_view_change(vc, CHAIN) == (True, "")
        assert verify_vc_lock_proof(vc, set(MEMBERS), Q) == (True, "")

    def test_valid_locked_vc_accepted(self):
        vc = _locked(MEMBERS[0], HA, 0, SEQ, VIEW)
        assert verify_view_change(vc, CHAIN) == (True, "")
        assert verify_vc_lock_proof(vc, set(MEMBERS), Q) == (True, "")

    def test_digest_tamper_rejected(self):
        vc = _vc(MEMBERS[0], SEQ, VIEW)
        vc["view_number"] = VIEW + 1  # digest no longer matches
        ok, reason = verify_view_change(vc, CHAIN)
        assert not ok
        assert "digest" in reason

    def test_signature_from_wrong_key_rejected(self):
        vc = _vc(MEMBERS[0], SEQ, VIEW, key=KEYS[MEMBERS[1]])
        ok, _ = verify_view_change(vc, CHAIN)
        assert not ok

    def test_missing_signature_rejected(self):
        vc = _vc(MEMBERS[0], SEQ, VIEW, sign=False)
        ok, _ = verify_view_change(vc, CHAIN)
        assert not ok

    def test_bool_sequence_rejected(self):
        vc = _vc(MEMBERS[0], SEQ, VIEW)
        vc["sequence_number"] = True  # JSON true must not pass as 1
        # digest was computed over seq=10; recompute for the bool path:
        vc["digest"] = view_change_digest(CHAIN, True, VIEW, -1, "")
        ok, _ = verify_view_change(vc, CHAIN)
        assert not ok

    def _check(self, vc):
        return verify_vc_lock_proof(vc, {canonical_address(m) for m in MEMBERS}, Q)

    def test_lock_proof_below_quorum_rejected(self):
        """A lone member's own COMMIT (the old proof shape) is not a quorum."""
        vc = _locked(MEMBERS[0], HA, 0, SEQ, VIEW)
        vc["lock"]["msgs"] = _proof(HA, SEQ, 0, [MEMBERS[0]])
        ok, _ = self._check(vc)
        assert not ok

    def test_lock_proof_duplicate_voters_do_not_inflate(self):
        vc = _locked(MEMBERS[0], HA, 0, SEQ, VIEW)
        vc["lock"]["msgs"] = _proof(HA, SEQ, 0, [MEMBERS[0]] * Q)
        ok, reason = self._check(vc)
        assert not ok and "distinct" in reason

    def test_lock_proof_non_member_voter_rejected(self):
        vc = _locked(MEMBERS[0], HA, 0, SEQ, VIEW)
        outsider = _key("99")
        KEYS[outsider[0]] = outsider[1]
        vc["lock"]["msgs"] = _proof(HA, SEQ, 0, MEMBERS[: Q - 1] + [outsider[0]])
        ok, reason = self._check(vc)
        assert not ok and "member" in reason

    def test_lock_proof_bad_signature_rejected(self):
        vc = _locked(MEMBERS[0], HA, 0, SEQ, VIEW)
        vc["lock"]["msgs"][1]["block_hash"] = HB  # digest now stale
        ok, _ = self._check(vc)
        assert not ok

    def test_lock_proof_wrong_view_or_hash_rejected(self):
        vc = _locked(MEMBERS[0], HA, 0, SEQ, VIEW)
        vc["lock"]["msgs"] = _proof(HA, SEQ, 1)  # proof for view 1, lock claims 0
        assert not self._check(vc)[0]
        vc["lock"]["msgs"] = _proof(HB, SEQ, 0)  # proof for another hash
        assert not self._check(vc)[0]

    def test_lock_view_at_or_above_target_view_rejected(self):
        """The view:1000 PoC: a lock may only claim a view below the VC's target."""
        vc = _locked(MEMBERS[0], HA, VIEW, SEQ, VIEW)
        ok, reason = self._check(vc)
        assert not ok and "below" in reason
        vc = _locked(MEMBERS[0], HA, 1000, SEQ, VIEW)
        assert not self._check(vc)[0]

    def test_lock_proof_commit_kind_accepted_unknown_kind_rejected(self):
        vc = _locked(MEMBERS[0], HA, 0, SEQ, VIEW)
        vc["lock"]["kind"] = "commit"
        vc["lock"]["msgs"] = _proof(HA, SEQ, 0, kind="commit")
        assert self._check(vc) == (True, "")
        vc["lock"]["kind"] = "pre_prepare"
        assert not self._check(vc)[0]

    def test_lock_proof_over_cap_rejected(self):
        vc = _locked(MEMBERS[0], HA, 0, SEQ, VIEW)
        vc["lock"]["msgs"] = _proof(HA, SEQ, 0, [MEMBERS[0]] * (MAX_LOCK_PROOF_MSGS + 1))
        assert not self._check(vc)[0]

    def test_oversized_payload_rejected(self):
        vc = _vc(MEMBERS[0], SEQ, VIEW)
        vc["pad"] = "x" * 70_000
        ok, reason = verify_view_change(vc, CHAIN)
        assert not ok
        assert "size" in reason


# ---------------------------------------------------------------------------
# NEW_VIEW verification — deterministic selection, never trusted
# ---------------------------------------------------------------------------


class TestVerifyNewView:
    def _locked_set(self, seq=SEQ, view=VIEW, hash_=HA, lock_view=0):
        return _vc_set(seq, view, MEMBERS[:Q], locked_hash=hash_, lock_view=lock_view)

    def test_free_new_view_accepted(self):
        vc_set = _vc_set(SEQ, VIEW, MEMBERS[:Q])
        proposer = _proposer(SEQ, VIEW)
        nv = _nv(proposer, SEQ, VIEW, vc_set, None)
        ok, reason, kind, selected = verify_new_view(
            nv, MEMBERS, chain_id=CHAIN, sequence=SEQ, view=VIEW, expected_sender=proposer
        )
        assert ok, reason
        assert (kind, selected) == ("free", None)

    def test_locked_new_view_accepted(self):
        vc_set = self._locked_set()
        proposer = _proposer(SEQ, VIEW)
        nv = _nv(proposer, SEQ, VIEW, vc_set, HA)
        ok, reason, kind, selected = verify_new_view(
            nv, MEMBERS, chain_id=CHAIN, sequence=SEQ, view=VIEW, expected_sender=proposer
        )
        assert ok, reason
        assert (kind, selected) == ("locked", HA)

    def test_locked_wrong_chosen_rejected(self):
        """Leader picks HB while the VC locks force HA -> reject."""
        vc_set = self._locked_set()
        proposer = _proposer(SEQ, VIEW)
        nv = _nv(proposer, SEQ, VIEW, vc_set, HB)
        ok, reason, _, _ = verify_new_view(nv, MEMBERS, chain_id=CHAIN, sequence=SEQ, view=VIEW, expected_sender=proposer)
        assert not ok
        assert "chosen_hash" in reason

    def test_free_with_chosen_rejected(self):
        vc_set = _vc_set(SEQ, VIEW, MEMBERS[:Q])
        proposer = _proposer(SEQ, VIEW)
        nv = _nv(proposer, SEQ, VIEW, vc_set, HA)  # free selection must be null
        ok, reason, _, _ = verify_new_view(nv, MEMBERS, chain_id=CHAIN, sequence=SEQ, view=VIEW, expected_sender=proposer)
        assert not ok
        assert "free" in reason

    def test_below_quorum_rejected(self):
        vc_set = _vc_set(SEQ, VIEW, MEMBERS[: Q - 1])
        proposer = _proposer(SEQ, VIEW)
        nv = _nv(proposer, SEQ, VIEW, vc_set, None)
        ok, reason, _, _ = verify_new_view(nv, MEMBERS, chain_id=CHAIN, sequence=SEQ, view=VIEW, expected_sender=proposer)
        assert not ok
        assert "distinct" in reason

    def test_duplicate_sender_cannot_inflate_quorum(self):
        """q records but only q-1 distinct senders -> rejected."""
        vc_set = _vc_set(SEQ, VIEW, MEMBERS[: Q - 1]) + [_vc(MEMBERS[0], SEQ, VIEW)]
        assert len(vc_set) == Q
        proposer = _proposer(SEQ, VIEW)
        nv = _nv(proposer, SEQ, VIEW, vc_set, None)
        ok, reason, _, _ = verify_new_view(nv, MEMBERS, chain_id=CHAIN, sequence=SEQ, view=VIEW, expected_sender=proposer)
        assert not ok
        assert "duplicate" in reason

    def test_non_member_sender_rejected(self):
        outsider, outsider_key = _key("99")
        vc_set = _vc_set(SEQ, VIEW, MEMBERS[: Q - 1]) + [_vc(outsider, SEQ, VIEW, key=outsider_key)]
        proposer = _proposer(SEQ, VIEW)
        nv = _nv(proposer, SEQ, VIEW, vc_set, None)
        ok, reason, _, _ = verify_new_view(nv, MEMBERS, chain_id=CHAIN, sequence=SEQ, view=VIEW, expected_sender=proposer)
        assert not ok
        assert "member" in reason

    def test_vc_for_wrong_view_rejected(self):
        vc_set = _vc_set(SEQ, VIEW, MEMBERS[:Q])
        vc_set[0] = _vc(MEMBERS[0], SEQ, VIEW + 1)  # targets a different view
        proposer = _proposer(SEQ, VIEW)
        nv = _nv(proposer, SEQ, VIEW, vc_set, None)
        ok, reason, _, _ = verify_new_view(nv, MEMBERS, chain_id=CHAIN, sequence=SEQ, view=VIEW, expected_sender=proposer)
        assert not ok

    def test_vc_set_substitution_rejected(self):
        """Swap a vc_set member for one with different lock content after
        signing -> the NV digest (which binds every carried vc digest)
        mismatches. (Swapping between two *equivalent* unlocked VCs is not a
        mutation: the vc digest commits to (h, v', lock) only — sender is
        bound by each VC's own signature, and any q distinct member VCs are
        interchangeable quorum evidence.)"""
        vc_set = _vc_set(SEQ, VIEW, MEMBERS[:Q])
        proposer = _proposer(SEQ, VIEW)
        nv = _nv(proposer, SEQ, VIEW, vc_set, None)
        nv["vc_set"] = list(vc_set)
        nv["vc_set"][2] = _locked(MEMBERS[2], HA, 0, SEQ, VIEW)  # lock report added post-sign
        ok, reason, _, _ = verify_new_view(nv, MEMBERS, chain_id=CHAIN, sequence=SEQ, view=VIEW, expected_sender=proposer)
        assert not ok
        assert "digest" in reason

    def test_wrong_proposer_sender_rejected(self):
        vc_set = _vc_set(SEQ, VIEW, MEMBERS[:Q])
        wrong = MEMBERS[0] if _proposer(SEQ, VIEW) != MEMBERS[0] else MEMBERS[1]
        nv = _nv(wrong, SEQ, VIEW, vc_set, None)
        ok, reason, _, _ = verify_new_view(
            nv, MEMBERS, chain_id=CHAIN, sequence=SEQ, view=VIEW, expected_sender=_proposer(SEQ, VIEW)
        )
        assert not ok
        assert "proposer" in reason

    def test_conflict_selection_rejected(self):
        senders = MEMBERS[:Q]
        vc_set = [
            _locked(senders[0], HA, 2, SEQ, VIEW),
            _locked(senders[1], HB, 2, SEQ, VIEW),
            _locked(senders[2], HA, 1, SEQ, VIEW),
        ]
        proposer = _proposer(SEQ, VIEW)
        nv = _nv(proposer, SEQ, VIEW, vc_set, HA)
        ok, reason, _, _ = verify_new_view(nv, MEMBERS, chain_id=CHAIN, sequence=SEQ, view=VIEW, expected_sender=proposer)
        assert not ok
        assert "conflict" in reason

    def test_vc_set_entry_cap(self):
        vc_set = [_vc(MEMBERS[i % len(MEMBERS)], SEQ, VIEW) for i in range(MAX_VC_SET_ENTRIES + 1)]
        ok, reason, _ = analyze_vc_set(vc_set, MEMBERS, chain_id=CHAIN, sequence=SEQ, view=VIEW)
        assert not ok
        assert "cap" in reason


# ---------------------------------------------------------------------------
# view_change unlock proof (equivocation_policy side)
# ---------------------------------------------------------------------------


def _evidence_payload(seq: int = SEQ, view_a: int = 0, view_b: int = 1, hash_a: str = HA, hash_b: str = HB) -> dict[str, Any]:
    """A pbft_cross_view_vote_equivocation payload: two COMMITs, different views."""
    return {
        "kind": "pbft_cross_view_vote_equivocation",
        "sequence": seq,
        "phase": "commit",
        "views": sorted([view_a, view_b]),
        "messages": [
            {
                "message_type": "commit",
                "sender": MEMBERS[0],
                "view_number": view_a,
                "sequence_number": seq,
                "block_hash": hash_a,
                "digest": commit_digest(hash_a, seq, view_a),
            },
            {
                "message_type": "commit",
                "sender": MEMBERS[0],
                "view_number": view_b,
                "sequence_number": seq,
                "block_hash": hash_b,
                "digest": commit_digest(hash_b, seq, view_b),
            },
        ],
    }


class TestViewChangeUnlock:
    """The NEW_VIEW proof excuses a cross-view COMMIT pair only when the
    deterministic selection permits the higher-view vote's hash."""

    def _ctx(self, seq: int = SEQ) -> VcApplyContext:
        return VcApplyContext(chain_id=CHAIN, sequence=seq, validator_set=frozenset(MEMBERS))

    def _justification(self, nv: dict[str, Any]) -> dict[str, Any]:
        return {"kind": "view_change", "new_view": nv}

    def test_locked_nv_permitting_later_vote_accepted(self):
        """Votes: H_a@v0, H_b@v1. A NEW_VIEW at v1 whose VC locks force H_b
        permits the later vote -> pair excused."""
        seq, v_later = SEQ, 1
        vc_set = _vc_set(seq, v_later, MEMBERS[:Q], locked_hash=HB, lock_view=0)
        proposer = _proposer(seq, v_later)
        nv = _nv(proposer, seq, v_later, vc_set, HB)
        payload = _evidence_payload(seq=seq, view_a=0, view_b=v_later, hash_a=HA, hash_b=HB)
        assert view_change_justified(payload, self._justification(nv), self._ctx(seq)) is True

    def test_locked_nv_permitting_wrong_hash_rejected(self):
        """Votes HA@v0, HB@v1; a NEW_VIEW forcing HA does NOT permit the
        later HB vote -> the pair stands."""
        seq, v_later = SEQ, 1
        vc_set = _vc_set(seq, v_later, MEMBERS[:Q], locked_hash=HA, lock_view=0)
        proposer = _proposer(seq, v_later)
        nv = _nv(proposer, seq, v_later, vc_set, HA)
        payload = _evidence_payload(seq=seq, view_a=0, view_b=v_later, hash_a=HA, hash_b=HB)
        assert view_change_justified(payload, self._justification(nv), self._ctx(seq)) is False

    def test_free_nv_permits_any_later_vote(self):
        seq, v_later = SEQ, 2
        vc_set = _vc_set(seq, v_later, MEMBERS[:Q])
        proposer = _proposer(seq, v_later)
        nv = _nv(proposer, seq, v_later, vc_set, None)
        payload = _evidence_payload(seq=seq, view_a=0, view_b=v_later, hash_a=HA, hash_b=HB)
        assert view_change_justified(payload, self._justification(nv), self._ctx(seq)) is True

    def test_wrong_kind_rejected(self):
        payload = _evidence_payload()
        assert view_change_justified(payload, {"kind": "operator"}, self._ctx()) is False
        assert view_change_justified(payload, {"kind": "time"}, self._ctx()) is False

    def test_missing_new_view_rejected(self):
        payload = _evidence_payload()
        assert view_change_justified(payload, {"kind": "view_change"}, self._ctx()) is False
        assert view_change_justified(payload, None, self._ctx()) is False

    def test_nv_for_wrong_view_rejected(self):
        """NV at v1 cannot excuse a pair whose later vote is at v2."""
        seq = SEQ
        vc_set = _vc_set(seq, 1, MEMBERS[:Q])
        proposer = _proposer(seq, 1)
        nv = _nv(proposer, seq, 1, vc_set, None)
        payload = _evidence_payload(seq=seq, view_a=0, view_b=2, hash_a=HA, hash_b=HB)
        assert view_change_justified(payload, self._justification(nv), self._ctx(seq)) is False

    def test_nv_for_wrong_sequence_rejected(self):
        seq = SEQ
        vc_set = _vc_set(seq + 1, 1, MEMBERS[:Q])
        proposer = _proposer(seq + 1, 1)
        nv = _nv(proposer, seq + 1, 1, vc_set, None)
        payload = _evidence_payload(seq=seq, view_a=0, view_b=1)
        assert view_change_justified(payload, self._justification(nv), self._ctx(seq)) is False

    def test_ctx_none_fails_closed(self):
        seq, v_later = SEQ, 1
        vc_set = _vc_set(seq, v_later, MEMBERS[:Q])
        proposer = _proposer(seq, v_later)
        nv = _nv(proposer, seq, v_later, vc_set, None)
        payload = _evidence_payload(seq=seq, view_a=0, view_b=v_later)
        assert view_change_justified(payload, self._justification(nv), None) is False

    def test_same_view_pair_rejected(self):
        payload = _evidence_payload(view_a=1, view_b=1)
        assert view_change_justified(payload, {"kind": "view_change", "new_view": {}}, self._ctx()) is False


# ---------------------------------------------------------------------------
# Engine-level: intake, quorum, NEW_VIEW build, floors, persistence
# ---------------------------------------------------------------------------


def _chain_db(chain_id: str):
    from pathlib import Path

    from aitbc_chain.database import get_engine
    from aitbc_chain.metadata import chain_metadata

    Path(settings.get_db_path(chain_id)).parent.mkdir(parents=True, exist_ok=True)
    engine = get_engine(chain_id, create_ok=True)
    chain_metadata.create_all(engine)
    return engine


def _make_consensus(n: int = 4, chain_id: str | None = None) -> MultiValidatorPoA:
    chain_id = chain_id or _CID
    _chain_db(chain_id)
    consensus = MultiValidatorPoA(chain_id)
    for a, _k in V[:n]:
        consensus.add_validator(a, 1000.0)
        consensus.validators[a].role = ValidatorRole.PROPOSER
    return consensus


def _pbft(consensus: MultiValidatorPoA, local: str, key: str, chain_id: str | None = None) -> PBFTConsensus:
    return PBFTConsensus(consensus, private_key=key, chain_id=chain_id or _CID, local_validator=local)


@pytest.fixture
def _fresh_chain():
    """Unique chain_id per engine test — persisted VC state must not leak."""
    global _CID
    _CID = f"{CHAIN}-{uuid.uuid4().hex[:10]}"
    yield _CID
    _CID = CHAIN


@pytest.fixture
def vc_armed(monkeypatch):
    monkeypatch.setattr(settings, "pbft_view_change_height", 0)
    yield


class TestEngineIntake:
    @pytest.fixture(autouse=True)
    def _iso(self, _fresh_chain):
        return _fresh_chain

    @pytest.mark.asyncio
    async def test_view_change_intake_stores_verified_only(self, vc_armed):
        consensus = _make_consensus()
        local = MEMBERS[0]
        pbft = _pbft(consensus, local, KEYS[local])
        good = _vc(MEMBERS[1], SEQ, VIEW)
        bad = _vc(MEMBERS[2], SEQ, VIEW)
        bad["digest"] = "0" * 64  # digest tamper
        foreign = _vc(MEMBERS[3], SEQ, VIEW, chain_id="other-chain")
        await pbft._handle_view_change_payload(good)
        await pbft._handle_view_change_payload(bad)
        await pbft._handle_view_change_payload(foreign)
        bucket = pbft._vc_messages.get((SEQ, VIEW), {})
        assert set(bucket) == {canonical_address(MEMBERS[1])}

    @pytest.mark.asyncio
    async def test_new_view_intake_verifies_and_stores(self, vc_armed):
        consensus = _make_consensus()
        local = _proposer(SEQ, VIEW)
        pbft = _pbft(consensus, local, KEYS[local])
        vc_set = _vc_set(SEQ, VIEW, MEMBERS[:Q])
        proposer = _proposer(SEQ, VIEW)
        nv = _nv(proposer, SEQ, VIEW, vc_set, None)
        await pbft._handle_new_view_payload(nv)
        entry = pbft._new_views.get((SEQ, VIEW))
        assert entry is not None
        assert entry["kind"] == "free"
        # A second NEW_VIEW for the same (seq, view) is refused — first wins.
        nv2 = _nv(proposer, SEQ, VIEW, _vc_set(SEQ, VIEW, MEMBERS[1:Q] + [MEMBERS[0]]), None)
        await pbft._handle_new_view_payload(nv2)
        assert pbft._new_views[(SEQ, VIEW)]["payload"] is nv

    @pytest.mark.asyncio
    async def test_new_view_below_quorum_dropped(self, vc_armed):
        consensus = _make_consensus()
        pbft = _pbft(consensus, MEMBERS[0], KEYS[MEMBERS[0]])
        vc_set = _vc_set(SEQ, VIEW, MEMBERS[: Q - 1])
        nv = _nv(_proposer(SEQ, VIEW), SEQ, VIEW, vc_set, None)
        await pbft._handle_new_view_payload(nv)
        assert (SEQ, VIEW) not in pbft._new_views

    @pytest.mark.asyncio
    async def test_dormant_gate_drops_vc_and_nv(self, monkeypatch):
        """With the gate unset the engine ignores VC/NEW_VIEW entirely."""
        monkeypatch.setattr(settings, "pbft_view_change_height", None)
        consensus = _make_consensus()
        pbft = _pbft(consensus, MEMBERS[0], KEYS[MEMBERS[0]])
        await pbft._handle_view_change_payload(_vc(MEMBERS[1], SEQ, VIEW))
        await pbft._handle_new_view_payload(_nv(_proposer(SEQ, VIEW), SEQ, VIEW, _vc_set(SEQ, VIEW, MEMBERS[:Q]), None))
        assert pbft._vc_messages == {}
        assert pbft._new_views == {}


class TestEngineNewViewBuild:
    @pytest.fixture(autouse=True)
    def _iso(self, _fresh_chain):
        return _fresh_chain

    @pytest.mark.asyncio
    async def test_proposer_builds_new_view_at_quorum(self, vc_armed):
        consensus = _make_consensus()
        local = _proposer(SEQ, VIEW)
        pbft = _pbft(consensus, local, KEYS[local])
        # Seed q-1 peer VCs + send our own -> quorum incl. self.
        for s in MEMBERS:
            if s == local:
                continue
            await pbft._handle_view_change_payload(_vc(s, SEQ, VIEW))
            if len(pbft._vc_messages.get((SEQ, VIEW), {})) >= Q - 1:
                break
        assert await pbft._send_view_change(SEQ, VIEW)
        nv = await pbft._build_new_view(SEQ, VIEW)
        assert nv is not None
        assert nv["sender"] == local
        assert nv["chosen_hash"] is None  # free selection
        ok, reason, kind, _ = verify_new_view(nv, MEMBERS, chain_id=_CID, sequence=SEQ, view=VIEW, expected_sender=local)
        assert ok, reason
        assert kind == "free"

    @pytest.mark.asyncio
    async def test_non_proposer_cannot_build(self, vc_armed):
        consensus = _make_consensus()
        local = MEMBERS[0]
        if local == _proposer(SEQ, VIEW):
            local = MEMBERS[1]
        pbft = _pbft(consensus, local, KEYS[local])
        for s in MEMBERS:
            if s != local:
                await pbft._handle_view_change_payload(_vc(s, SEQ, VIEW))
        await pbft._send_view_change(SEQ, VIEW)
        assert await pbft._build_new_view(SEQ, VIEW) is None

    @pytest.mark.asyncio
    async def test_below_quorum_cannot_build(self, vc_armed):
        consensus = _make_consensus()
        local = _proposer(SEQ, VIEW)
        pbft = _pbft(consensus, local, KEYS[local])
        # Q-2 peers + own VC = Q-1 distinct senders < required quorum.
        peers = [s for s in MEMBERS if s != local][: Q - 2]
        for s in peers:
            await pbft._handle_view_change_payload(_vc(s, SEQ, VIEW))
        await pbft._send_view_change(SEQ, VIEW)
        assert await pbft._build_new_view(SEQ, VIEW) is None

    @pytest.mark.asyncio
    async def test_locked_selection_builds_forced_new_view(self, vc_armed):
        """VCs carrying a commit-lock force chosen_hash — the re-seal path."""
        consensus = _make_consensus()
        local = _proposer(SEQ, VIEW)
        pbft = _pbft(consensus, local, KEYS[local])
        # Two peers + self all locked on HA at view 0.
        peers = [s for s in MEMBERS if s != local][: Q - 1]
        for s in peers:
            await pbft._handle_view_change_payload(_locked(s, HA, 0, SEQ, VIEW))
        await pbft._send_view_change(SEQ, VIEW)  # own VC: unlocked -> still q senders
        nv = await pbft._build_new_view(SEQ, VIEW)
        assert nv is not None
        assert nv["chosen_hash"] == HA
        ok, reason, kind, selected = verify_new_view(
            nv, MEMBERS, chain_id=_CID, sequence=SEQ, view=VIEW, expected_sender=local
        )
        assert ok, reason
        assert (kind, selected) == ("locked", HA)


class TestEngineFloorsAndPersistence:
    @pytest.fixture(autouse=True)
    def _iso(self, _fresh_chain):
        return _fresh_chain

    @pytest.mark.asyncio
    async def test_floor_blocks_lower_view_vote(self, vc_armed):
        consensus = _make_consensus()
        local = MEMBERS[0]
        pbft = _pbft(consensus, local, KEYS[local])
        assert pbft._view_change_permit(SEQ, 0, HA) is True  # no floor yet
        await pbft._send_view_change(SEQ, VIEW)  # floor := VIEW
        assert consensus.pbft_vc_floor(SEQ) == VIEW
        assert pbft._view_change_permit(SEQ, VIEW - 1, HA) is False  # below floor
        # At/above floor still needs a verified NEW_VIEW for that view.
        assert pbft._view_change_permit(SEQ, VIEW, HA) is False
        # Feed a verified free NEW_VIEW for (SEQ, VIEW).
        vc_set = _vc_set(SEQ, VIEW, MEMBERS[:Q])
        await pbft._handle_new_view_payload(_nv(_proposer(SEQ, VIEW), SEQ, VIEW, vc_set, None))
        assert pbft._view_change_permit(SEQ, VIEW, HA) is True
        assert pbft._view_change_permit(SEQ, VIEW, HB) is True  # free permits any

    @pytest.mark.asyncio
    async def test_locked_new_view_permits_only_forced_hash(self, vc_armed):
        consensus = _make_consensus()
        local = MEMBERS[0]
        pbft = _pbft(consensus, local, KEYS[local])
        await pbft._send_view_change(SEQ, VIEW)
        vc_set = _vc_set(SEQ, VIEW, MEMBERS[:Q], locked_hash=HA, lock_view=0)
        await pbft._handle_new_view_payload(_nv(_proposer(SEQ, VIEW), SEQ, VIEW, vc_set, HA))
        assert pbft._view_change_permit(SEQ, VIEW, HA) is True
        assert pbft._view_change_permit(SEQ, VIEW, HB) is False

    @pytest.mark.asyncio
    async def test_vc_state_survives_restart(self, vc_armed):
        """Floor + commit-lock + proposal body persist across a reload."""
        consensus = _make_consensus()
        local = MEMBERS[0]
        _pbft(consensus, local, KEYS[local])
        commit = _commit_rec(local, HA, SEQ, 0)
        assert consensus.pbft_vc_floor_raise(SEQ, VIEW)
        assert consensus.pbft_vc_commit_lock_arm(SEQ, 0, HA, commit, _proof(HA, SEQ, 0))
        assert consensus.pbft_vc_proposal_store(SEQ, HA, {"block": {"txs": []}})
        # "Restart": a fresh MultiValidatorPoA on the same chain loads state.
        consensus2 = MultiValidatorPoA(_CID)
        assert consensus2.pbft_vc_floor(SEQ) == VIEW
        lock = consensus2.pbft_vc_commit_lock(SEQ)
        assert lock is not None and lock["block_hash"] == HA and lock["view"] == 0
        assert lock["commit"]["signature"]
        assert consensus2.pbft_vc_proposal_get(SEQ, HA) == {"block": {"txs": []}}
        pbft2 = _pbft(consensus2, local, KEYS[local])
        assert pbft2._vc_floor(SEQ) == VIEW
        # Floor still enforced after restart: lower view refused, and the
        # persisted lock feeds the next VIEW_CHANGE.
        assert pbft2._view_change_permit(SEQ, VIEW - 1, HA) is False

    @pytest.mark.asyncio
    async def test_commit_lock_first_wins(self, vc_armed):
        consensus = _make_consensus()
        commit_a = _commit_rec(MEMBERS[0], HA, SEQ, 0)
        commit_b = _commit_rec(MEMBERS[0], HB, SEQ, 1)
        assert consensus.pbft_vc_commit_lock_arm(SEQ, 0, HA, commit_a, _proof(HA, SEQ, 0))
        # Same (view, hash) idempotent; a DIFFERENT hash is refused at any view.
        assert consensus.pbft_vc_commit_lock_arm(SEQ, 0, HA, commit_a, _proof(HA, SEQ, 0))
        assert not consensus.pbft_vc_commit_lock_arm(SEQ, 1, HB, commit_b, _proof(HB, SEQ, 1))
        assert consensus.pbft_vc_commit_lock(SEQ)["block_hash"] == HA

    @pytest.mark.asyncio
    async def test_floor_persist_failure_blocks_vc(self, vc_armed, monkeypatch):
        """If the floor cannot be persisted, no VC may be sent (fail closed)."""
        consensus = _make_consensus()
        local = MEMBERS[0]
        pbft = _pbft(consensus, local, KEYS[local])
        monkeypatch.setattr(consensus, "pbft_vc_floor_raise", lambda s, v: False)
        assert await pbft._send_view_change(SEQ, VIEW) is False
        assert (SEQ, VIEW) not in pbft._vc_messages

    @pytest.mark.asyncio
    async def test_vc_flood_bucket_cap(self, vc_armed):
        """Distinct (seq, view) buckets are bounded — flood drops, not grows."""
        from aitbc_chain.consensus.pbft_view_change import MAX_VC_BUCKETS

        consensus = _make_consensus()
        pbft = _pbft(consensus, MEMBERS[0], KEYS[MEMBERS[0]])
        # seq is unique per bucket key (seq, view); view_change_active(seq) needs seq>=0.
        for i in range(MAX_VC_BUCKETS + 4):
            await pbft._handle_view_change_payload(_vc(MEMBERS[1], SEQ + i, VIEW))
        assert len(pbft._vc_messages) <= MAX_VC_BUCKETS

    @pytest.mark.asyncio
    async def test_vc_set_entry_cap_on_intake(self, vc_armed):
        """A (seq, view) bucket at MAX_VC_SET_ENTRIES drops further VCs."""
        from aitbc_chain.consensus.pbft_view_change import MAX_VC_SET_ENTRIES

        consensus = _make_consensus()
        pbft = _pbft(consensus, MEMBERS[0], KEYS[MEMBERS[0]])
        bucket = pbft._vc_messages.setdefault((SEQ, VIEW), {})
        for i in range(MAX_VC_SET_ENTRIES):
            bucket[f"0xpad{i:040x}"] = {"sender": f"0xpad{i:040x}"}
        # A perfectly valid member VC is still dropped — the bucket is full.
        await pbft._handle_view_change_payload(_vc(MEMBERS[1], SEQ, VIEW))
        assert canonical_address(MEMBERS[1]) not in bucket
        assert len(bucket) == MAX_VC_SET_ENTRIES


class _FakeGossip:
    def __init__(self) -> None:
        self.published: list[tuple[str, Any]] = []

    async def publish(self, topic: str, payload: Any) -> None:
        self.published.append((topic, payload))


def _proposal_body(proposer: str, block_hash: str = HA) -> dict[str, Any]:
    """The full signed-block payload a producer attaches to PRE_PREPARE (2A)."""
    body = {
        "chain_id": _CID,
        "height": SEQ,
        "hash": block_hash,
        "parent_hash": "0x" + "00" * 32,
        "proposer": proposer,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "tx_count": 0,
        "state_root": "0x" + "11" * 32,
        "bridge_state_root": None,
        "aux_state_root": None,
        "signature": "",
        "block_metadata": None,
        "transactions": [],
    }
    from aitbc.crypto.consensus_signing import sign_block_hash

    body["signature"] = sign_block_hash(body, KEYS[proposer]) if proposer in KEYS else "0xsig"
    return body


class TestDeadAfterQuorumReseal:
    """Design §5/§7 test 6: proposer dies after a commit quorum; any honest
    holder of the persisted body re-publishes the ORIGINAL block + commit
    certificate — importers accept it because the certificate is coherent
    for (height, original derived round)."""

    @pytest.fixture(autouse=True)
    def _iso(self, _fresh_chain):
        return _fresh_chain

    def _seed_quorum(self, pbft: PBFTConsensus, proposer: str, block_hash: str = HA) -> None:
        key = f"{SEQ}:{VIEW}"
        pbft.state.pre_prepare_messages[key] = PBFTMessage(
            message_type=PBFTMessageType.PRE_PREPARE,
            sender=proposer,
            view_number=VIEW,
            sequence_number=SEQ,
            digest=pbft.get_message_digest(block_hash, SEQ, VIEW),
            signature="",
            timestamp=0.0,
            block_hash=block_hash,
            block=_proposal_body(proposer, block_hash),
        )
        pbft.state.committed_messages[key] = [
            PBFTMessage(
                message_type=PBFTMessageType.COMMIT,
                sender=s,
                view_number=VIEW,
                sequence_number=SEQ,
                digest=pbft.get_message_digest(block_hash, SEQ, VIEW),
                signature="",
                timestamp=0.0,
                block_hash=block_hash,
            )
            for s in MEMBERS[:Q]
        ]

    @pytest.mark.asyncio
    async def test_follower_reseals_committed_block(self, vc_armed):
        consensus = _make_consensus()
        proposer = _proposer(SEQ, VIEW)
        follower = next(s for s in MEMBERS if s != proposer)
        pbft = _pbft(consensus, follower, KEYS[follower])
        gossip = _FakeGossip()
        pbft.set_gossip_backend(gossip)
        body = _proposal_body(proposer)
        assert consensus.pbft_vc_proposal_store(SEQ, HA, body)
        self._seed_quorum(pbft, proposer)
        assert await pbft.execute_phase(f"{SEQ}:{VIEW}") is True
        block_publishes = [p for t, p in gossip.published if t == f"blocks.{_CID}"]
        assert len(block_publishes) == 1
        payload = block_publishes[0]
        assert payload["hash"] == HA
        assert payload["height"] == SEQ
        assert payload["proposer"] == proposer
        assert payload["signature"] == body["signature"]  # original proposer signature, as-is
        cert = payload["block_metadata"]["pbft_certificate"]
        assert len(cert) == Q
        assert {c["sender"] for c in cert} == set(MEMBERS[:Q])

    @pytest.mark.asyncio
    async def test_proposer_does_not_reseal(self, vc_armed):
        """The scheduled proposer seals via the normal broadcast path — the
        re-seal publisher is any OTHER quorum holder."""
        consensus = _make_consensus()
        proposer = _proposer(SEQ, VIEW)
        pbft = _pbft(consensus, proposer, KEYS[proposer])
        gossip = _FakeGossip()
        pbft.set_gossip_backend(gossip)
        assert consensus.pbft_vc_proposal_store(SEQ, HA, _proposal_body(proposer))
        self._seed_quorum(pbft, proposer)
        assert await pbft.execute_phase(f"{SEQ}:{VIEW}") is True
        assert [p for t, p in gossip.published if t.startswith("blocks.")] == []

    @pytest.mark.asyncio
    async def test_missing_body_cannot_reseal(self, vc_armed):
        """No persisted proposal body -> nothing to publish (fail closed)."""
        consensus = _make_consensus()
        proposer = _proposer(SEQ, VIEW)
        follower = next(s for s in MEMBERS if s != proposer)
        pbft = _pbft(consensus, follower, KEYS[follower])
        gossip = _FakeGossip()
        pbft.set_gossip_backend(gossip)
        self._seed_quorum(pbft, proposer)  # body deliberately NOT stored
        assert await pbft.execute_phase(f"{SEQ}:{VIEW}") is True
        assert gossip.published == []

    @pytest.mark.asyncio
    async def test_reseal_dormant_when_gate_unset(self, monkeypatch):
        monkeypatch.setattr(settings, "pbft_view_change_height", None)
        consensus = _make_consensus()
        proposer = _proposer(SEQ, VIEW)
        follower = next(s for s in MEMBERS if s != proposer)
        pbft = _pbft(consensus, follower, KEYS[follower])
        gossip = _FakeGossip()
        pbft.set_gossip_backend(gossip)
        assert consensus.pbft_vc_proposal_store(SEQ, HA, _proposal_body(proposer))
        self._seed_quorum(pbft, proposer)
        assert await pbft.execute_phase(f"{SEQ}:{VIEW}") is True
        assert gossip.published == []


# ---------------------------------------------------------------------------
# On-chain evidence gate: validator_deactivation_pbft_view_change_evidence_height
# ---------------------------------------------------------------------------


def _seed_param(session: Session, chain_id: str, name: str, value: str, applied_height: int = 0) -> None:
    session.add(ChainParameter(chain_id=chain_id, parameter=name, value=value, applied_height=applied_height))


def _vc_digest_for(vset: frozenset[str]) -> str:
    import hashlib

    return hashlib.sha256("\n".join(sorted(vset)).encode()).hexdigest()


class TestEvidenceGate:
    """``view_change`` unlock is registered only when the on-chain parameter
    ``validator_deactivation_pbft_view_change_evidence_height`` is armed —
    dormant by default, fail closed on unset/malformed."""

    APPLY = 20

    @pytest.fixture(autouse=True)
    def _validator_set_env(self, monkeypatch):
        """``validator_addresses()`` parses ``settings.validator_set`` — arm it
        with the test member set so ``_vc_validator_set`` can build a context
        (the digest parameter then binds it, exactly like the ``uc`` path).
        ``_CID`` becomes the evidence chain_id so every helper-signed VC/NV
        digest binds the same chain the verifier uses."""
        global _CID
        _CID = "test-chain"
        monkeypatch.setattr(settings, "validator_set", json.dumps([{"address": a} for a in MEMBERS]))
        yield
        _CID = CHAIN

    def _session(self, tmp_path, params: dict[str, str] | None, name: str = "vc.db"):
        from .test_validator_deactivation_1198 import _engine

        session = Session(_engine(tmp_path, name=name))
        for pname, pvalue in (params or {}).items():
            _seed_param(session, "test-chain", pname, pvalue)
        session.commit()
        return session

    def _payload_with_unlock(self, nv: dict[str, Any] | None, seq: int = SEQ) -> dict[str, Any]:
        from aitbc_chain.consensus.slashing import SlashingManager, slashing_event_record

        mgr = SlashingManager()
        # Build the cross-view event from two signed commits (reuse the F3-A
        # event constructor via the policy test's signed-fields shape).
        from .test_cross_view_commit_equivocation_1940 import _signed_fields

        m_a = _signed_fields(MEMBERS[0], KEYS[MEMBERS[0]], block_hash=HA, seq=seq, view=0)
        m_b = _signed_fields(MEMBERS[0], KEYS[MEMBERS[0]], block_hash=HB, seq=seq, view=1)
        event = mgr.cross_view_vote_equivocation_event(MEMBERS[0], seq, "commit", m_b, m_a)
        if nv is not None:
            ep = json.loads(event.evidence)
            ep["unlock_justification"] = {"kind": "view_change", "new_view": nv}
            event.evidence = json.dumps(ep, sort_keys=True)
        mgr.slashing_events = [event]
        canon = canonical_address(MEMBERS[0])
        return {
            "validator_address": canon,
            "evidence_hash": mgr.evidence_hash(canon),
            "bond_id": "bond-x",
            "evidence_version": 2,
            "evidence": [slashing_event_record(e) for e in mgr.slashing_events],
        }

    def _verify(self, payload, session, block_height=APPLY):
        from aitbc_chain.state.deactivation_evidence import verify_deactivation_evidence

        return verify_deactivation_evidence(
            payload,
            chain_id="test-chain",
            validator_addr=payload["validator_address"],
            evidence_hash=payload["evidence_hash"],
            session=session,
            block_height=block_height,
        )

    def _armed_params(self) -> dict[str, str]:
        vset = frozenset(MEMBERS)
        return {
            "validator_deactivation_pbft_view_change_evidence_height": "5",
            "validator_deactivation_pbft_view_change_validator_set_digest": _vc_digest_for(vset),
            # The F3-A cross-view gate must also be armed for the pair to be
            # evidence at all.
            "validator_deactivation_pbft_cross_view_evidence_height": "5",
        }

    def _valid_nv(self, seq: int = SEQ, view: int = 1, chosen: str | None = HB) -> dict[str, Any]:
        vc_set = (
            _vc_set(seq, view, MEMBERS[:Q], locked_hash=chosen, lock_view=0) if chosen else _vc_set(seq, view, MEMBERS[:Q])
        )
        return _nv(_proposer(seq, view), seq, view, vc_set, chosen)

    def test_unset_param_pair_stands(self, tmp_path):
        """Without the VC evidence parameter the unlock kind is unregistered:
        even a perfect NEW_VIEW proof cannot excuse the pair."""
        payload = self._payload_with_unlock(self._valid_nv())
        params = self._armed_params()
        del params["validator_deactivation_pbft_view_change_evidence_height"]
        with self._session(tmp_path, params, name="a.db") as session:
            assert self._verify(payload, session=session) is None  # verified -> stands

    def test_armed_valid_unlock_excuses_pair(self, tmp_path):
        payload = self._payload_with_unlock(self._valid_nv())
        with self._session(tmp_path, self._armed_params(), name="b.db") as session:
            reason = self._verify(payload, session=session)
        assert reason is not None  # excused -> NOT verified equivocation evidence

    def test_armed_invalid_unlock_pair_stands(self, tmp_path):
        """A NEW_VIEW that does not permit the later vote leaves the pair standing."""
        # NV forces HA but the later vote (view 1) was HB.
        nv = self._valid_nv(chosen=HA)
        payload = self._payload_with_unlock(nv)
        with self._session(tmp_path, self._armed_params(), name="c.db") as session:
            assert self._verify(payload, session=session) is None

    def test_armed_wrong_digest_param_pair_stands(self, tmp_path):
        """Validator-set digest mismatch -> context unbuildable -> stands."""
        params = self._armed_params()
        params["validator_deactivation_pbft_view_change_validator_set_digest"] = "0" * 64
        payload = self._payload_with_unlock(self._valid_nv())
        with self._session(tmp_path, params, name="d.db") as session:
            assert self._verify(payload, session=session) is None

    def test_armed_below_activation_pair_stands(self, tmp_path):
        """Sequence below the armed height can never be excused."""
        params = self._armed_params()
        params["validator_deactivation_pbft_view_change_evidence_height"] = "15"  # SEQ=10 < 15
        payload = self._payload_with_unlock(self._valid_nv(), seq=SEQ)
        with self._session(tmp_path, params, name="e.db") as session:
            assert self._verify(payload, session=session) is None


# ---------------------------------------------------------------------------
# Respin (#2005 B review): Q1 quorum-backed locks, Q2 NEW_VIEW on VC quorum,
# fail-closed persistence, bounded proposal store.
# ---------------------------------------------------------------------------


class TestRespinQ1Q2:
    @pytest.fixture(autouse=True)
    def _iso(self, _fresh_chain):
        return _fresh_chain

    @pytest.mark.asyncio
    async def test_fabricated_single_voter_lock_dropped_at_intake(self, vc_armed):
        """PoC: one Byzantine voter's own signed lock (same-view fabricated
        lock / view:1000) must not enter the VC bucket."""
        consensus = _make_consensus()
        local = MEMBERS[0]
        pbft = _pbft(consensus, local, KEYS[local])
        for lock_view in (0, 1000):
            vc = _vc(
                MEMBERS[1],
                SEQ,
                VIEW,
                lock={
                    "view": lock_view,
                    "block_hash": HB,
                    "kind": "prepare",
                    "msgs": _proof(HB, SEQ, lock_view, [MEMBERS[1]]),
                },
            )
            await pbft._handle_view_change_payload(vc)
        assert pbft._vc_messages.get((SEQ, VIEW), {}) == {}

    @pytest.mark.asyncio
    async def test_quorum_backed_lock_accepted_at_intake(self, vc_armed):
        consensus = _make_consensus()
        local = MEMBERS[0]
        pbft = _pbft(consensus, local, KEYS[local])
        await pbft._handle_view_change_payload(_locked(MEMBERS[1], HA, 0, SEQ, VIEW))
        assert set(pbft._vc_messages[(SEQ, VIEW)]) == {canonical_address(MEMBERS[1])}

    @pytest.mark.asyncio
    async def test_new_view_built_when_vcs_arrive_after_first_pre_prepare(self, vc_armed):
        """Q2: the proposer publishes NEW_VIEW the moment the bucket reaches
        quorum — without waiting for a (re-)pre-prepare."""
        consensus = _make_consensus()
        proposer = _proposer(SEQ, VIEW)
        pbft = _pbft(consensus, proposer, KEYS[proposer])
        others = [m for m in MEMBERS if m != proposer]
        await pbft._handle_view_change_payload(_vc(others[0], SEQ, VIEW))
        assert (SEQ, VIEW) not in pbft._new_views  # sub-quorum: never built
        await pbft._handle_view_change_payload(_vc(others[1], SEQ, VIEW))
        assert (SEQ, VIEW) not in pbft._new_views
        await pbft._handle_view_change_payload(_vc(others[2], SEQ, VIEW))
        assert (SEQ, VIEW) in pbft._new_views
        assert pbft._new_views[(SEQ, VIEW)]["kind"] == "free"

    @pytest.mark.asyncio
    async def test_non_proposer_never_builds_new_view(self, vc_armed):
        consensus = _make_consensus()
        proposer = _proposer(SEQ, VIEW)
        local = next(m for m in MEMBERS if m != proposer)
        pbft = _pbft(consensus, local, KEYS[local])
        for m in [m for m in MEMBERS if m != local][:Q]:
            await pbft._handle_view_change_payload(_vc(m, SEQ, VIEW))
        assert (SEQ, VIEW) not in pbft._new_views

    @pytest.mark.asyncio
    async def test_new_view_dropped_when_schedule_unavailable(self, vc_armed, monkeypatch):
        consensus = _make_consensus()
        local = _proposer(SEQ, VIEW)
        pbft = _pbft(consensus, local, KEYS[local])
        nv = _nv(local, SEQ, VIEW, _vc_set(SEQ, VIEW, MEMBERS[:Q]), None)

        def _boom(*_a, **_k):
            raise RuntimeError("schedule unavailable")

        monkeypatch.setattr(consensus, "select_proposer", _boom)
        await pbft._handle_new_view_payload(nv)
        assert (SEQ, VIEW) not in pbft._new_views

    @pytest.mark.asyncio
    async def test_duplicate_new_view_skips_signature_verification(self, vc_armed, monkeypatch):
        """ECDSA DoS guard: a repeat NEW_VIEW is dropped before any crypto."""
        import aitbc_chain.consensus.pbft as pbft_mod

        consensus = _make_consensus()
        local = _proposer(SEQ, VIEW)
        pbft = _pbft(consensus, local, KEYS[local])
        nv = _nv(local, SEQ, VIEW, _vc_set(SEQ, VIEW, MEMBERS[:Q]), None)
        await pbft._handle_new_view_payload(nv)
        assert (SEQ, VIEW) in pbft._new_views
        calls = []
        monkeypatch.setattr(pbft_mod, "verify_new_view", lambda *a, **k: calls.append(1))
        await pbft._handle_new_view_payload(nv)
        assert calls == []

    def test_padded_vc_set_rejected_before_signatures(self):
        vc_set = _vc_set(SEQ, VIEW, MEMBERS[:Q])
        padded = vc_set + [dict(vc_set[0]) for _ in range(len(MEMBERS))]
        ok, reason, _ = analyze_vc_set(padded, MEMBERS, chain_id=CHAIN, sequence=SEQ, view=VIEW)
        assert not ok and "cap" in reason

    def test_proposal_store_evicts_oldest_instead_of_refusing(self, vc_armed):
        from aitbc_chain.consensus.pbft_view_change import MAX_PROPOSALS_PER_SEQUENCE

        consensus = _make_consensus()
        for i in range(MAX_PROPOSALS_PER_SEQUENCE + 3):
            assert consensus.pbft_vc_proposal_store(SEQ, f"0x{i:064x}", {"block": {"i": i}})
        held = consensus._pbft_view_change[SEQ]["proposals"]
        assert len(held) == MAX_PROPOSALS_PER_SEQUENCE
        assert f"0x{MAX_PROPOSALS_PER_SEQUENCE + 2:064x}" in held and f"0x{0:064x}" not in held

    def test_proposal_store_never_evicts_the_locked_body(self, vc_armed):
        from aitbc_chain.consensus.pbft_view_change import MAX_PROPOSALS_PER_SEQUENCE

        consensus = _make_consensus()
        assert consensus.pbft_vc_proposal_store(SEQ, HA, {"block": {"locked": True}})
        assert consensus.pbft_vc_commit_lock_arm(SEQ, 0, HA, _commit_rec(MEMBERS[0], HA, SEQ, 0), _proof(HA, SEQ, 0))
        for i in range(MAX_PROPOSALS_PER_SEQUENCE + 3):
            consensus.pbft_vc_proposal_store(SEQ, f"0x{i:064x}", {"block": {"i": i}})
        assert consensus.pbft_vc_proposal_get(SEQ, HA) == {"block": {"locked": True}}

    def test_commit_lock_arm_refuses_empty_proof(self, vc_armed):
        consensus = _make_consensus()
        assert not consensus.pbft_vc_commit_lock_arm(SEQ, 0, HA, _commit_rec(MEMBERS[0], HA, SEQ, 0), [])

    def test_corrupt_persisted_vc_state_fails_closed(self, vc_armed):
        """A corrupt record must not read as 'no floor, no lock': VC-armed
        persistence refuses until repaired."""
        with pytest.raises(ValueError):
            MultiValidatorPoA._parse_view_change_records("{not json")
        consensus = _make_consensus()
        consensus._pbft_vc_corrupt = True
        assert not consensus.pbft_vc_floor_raise(SEQ, VIEW)
        assert not consensus.pbft_vc_prepared_arm(SEQ, 0, HA)


class TestLockProofCostBound:
    """The cheap structural/member/distinct checks must reject BEFORE any ECDSA
    verification (they are masked by the later voter count otherwise)."""

    @staticmethod
    def _count(monkeypatch):
        import aitbc_chain.consensus.pbft_view_change as core

        calls: list[int] = []
        real = core._verify_signature
        monkeypatch.setattr(core, "_verify_signature", lambda *a, **k: calls.append(1) or real(*a, **k))
        return calls

    def _run(self, vc):
        return verify_vc_lock_proof(vc, {canonical_address(m) for m in MEMBERS}, Q)

    def test_sub_quorum_proof_costs_no_signature_verification(self, monkeypatch):
        calls = self._count(monkeypatch)
        vc = _locked(MEMBERS[0], HA, 0, SEQ, VIEW)
        vc["lock"]["msgs"] = _proof(HA, SEQ, 0, [MEMBERS[0]] * (Q - 1))
        assert not self._run(vc)[0]
        assert calls == []

    def test_padded_duplicate_proof_costs_no_signature_verification(self, monkeypatch):
        calls = self._count(monkeypatch)
        vc = _locked(MEMBERS[0], HA, 0, SEQ, VIEW)
        vc["lock"]["msgs"] = _proof(HA, SEQ, 0, [MEMBERS[0]] * (MAX_LOCK_PROOF_MSGS))
        assert not self._run(vc)[0]
        assert calls == []

    def test_valid_proof_verifies_exactly_q_signatures(self, monkeypatch):
        calls = self._count(monkeypatch)
        assert self._run(_locked(MEMBERS[0], HA, 0, SEQ, VIEW)) == (True, "")
        assert len(calls) == Q


class TestRespinRemainder:
    """Rest of B's review list: schedule reuse, body binding, F3-B precedence,
    unlock producer, VC re-send, floor rule."""

    @pytest.fixture(autouse=True)
    def _iso(self, _fresh_chain):
        return _fresh_chain

    def test_schedule_is_one_function_shared_by_engine_and_evidence(self):
        from aitbc_chain.consensus.equivocation_policy import _pbft_proposer_for
        from aitbc_chain.consensus.pbft_view_change import scheduled_proposer

        consensus = _make_consensus()
        ctx = VcApplyContext(chain_id=CHAIN, sequence=SEQ, validator_set=frozenset(MEMBERS))
        for view in range(0, 9):
            expected = scheduled_proposer(MEMBERS, SEQ, view)
            assert _pbft_proposer_for(ctx, view) == expected
            assert consensus.select_proposer(SEQ, view) == expected
        assert scheduled_proposer([], SEQ, 0) is None

    def test_proposal_body_must_match_hash_and_height(self):
        from aitbc_chain.consensus.pbft_view_change import proposal_body_bound

        good = {"hash": HA, "height": SEQ}
        assert proposal_body_bound(good, HA, SEQ)
        assert not proposal_body_bound(good, HB, SEQ)  # body names another hash
        assert not proposal_body_bound(good, HA, SEQ + 1)
        assert not proposal_body_bound({"hash": HA}, HA, SEQ)
        assert not proposal_body_bound(None, HA, SEQ)

    @pytest.mark.asyncio
    async def test_unbound_body_is_not_persisted_at_intake(self, vc_armed):
        consensus = _make_consensus()
        local = MEMBERS[0]
        pbft = _pbft(consensus, local, KEYS[local])
        pp = PBFTMessage(
            message_type=PBFTMessageType.PRE_PREPARE,
            sender=_proposer(SEQ, 0),
            view_number=0,
            sequence_number=SEQ,
            digest="d",
            signature="",
            timestamp=0.0,
            block_hash=HA,
            block={"hash": HB, "height": SEQ},  # swapped body
        )
        assert not await pbft._view_change_prepare_allows(SEQ, 0, pp)
        assert consensus.pbft_vc_proposal_get(SEQ, HA) is None
        assert consensus.pbft_vc_proposal_get(SEQ, HB) is None

    @pytest.mark.asyncio
    async def test_proposer_refuses_unbound_payload(self, vc_armed):
        consensus = _make_consensus()
        local = _proposer(SEQ, 0)
        pbft = _pbft(consensus, local, KEYS[local])
        assert await pbft._prepare_view_change_proposal(SEQ, 0, HA, {"hash": HB, "height": SEQ}) is None

    @pytest.mark.asyncio
    async def test_new_view_supersedes_stale_f3b_lock(self, vc_armed, monkeypatch):
        """F3-B pinned HA; a verified NEW_VIEW selecting HB must let this node
        commit HB. Without a stored NEW_VIEW the F3-B refusal is unchanged."""
        monkeypatch.setattr(settings, "pbft_cross_view_commit_lock_height", 0)
        consensus = _make_consensus()
        local = MEMBERS[0]
        pbft = _pbft(consensus, local, KEYS[local])
        assert pbft._commit_lock_allows(SEQ, HA, 0)  # arms the pin on HA
        assert not pbft._commit_lock_allows(SEQ, HB, 1)  # no NV: refused
        assert pbft._vc_floor_raise(SEQ, 1)
        vc_set = _vc_set(SEQ, 1, MEMBERS[:Q])
        await pbft._handle_new_view_payload(_nv(_proposer(SEQ, 1), SEQ, 1, vc_set, None))
        assert pbft._commit_lock_allows(SEQ, HB, 1)  # free NV at view 1 supersedes
        assert not pbft._commit_lock_allows(SEQ, HB, 2)  # no NV for view 2

    @pytest.mark.asyncio
    async def test_locked_new_view_does_not_supersede_for_other_hash(self, vc_armed, monkeypatch):
        monkeypatch.setattr(settings, "pbft_cross_view_commit_lock_height", 0)
        consensus = _make_consensus()
        local = MEMBERS[0]
        pbft = _pbft(consensus, local, KEYS[local])
        assert pbft._commit_lock_allows(SEQ, HA, 0)
        assert pbft._vc_floor_raise(SEQ, 1)
        vc_set = _vc_set(SEQ, 1, MEMBERS[:Q], locked_hash=HC, lock_view=0)
        await pbft._handle_new_view_payload(_nv(_proposer(SEQ, 1), SEQ, 1, vc_set, HC))
        assert pbft._commit_lock_allows(SEQ, HC, 1)
        assert not pbft._commit_lock_allows(SEQ, HB, 1)  # NV forces HC, not HB

    @pytest.mark.asyncio
    async def test_f3b_unchanged_when_view_change_gate_dormant(self, monkeypatch):
        monkeypatch.setattr(settings, "pbft_cross_view_commit_lock_height", 0)
        consensus = _make_consensus()
        local = MEMBERS[0]
        pbft = _pbft(consensus, local, KEYS[local])
        assert pbft._commit_lock_allows(SEQ, HA, 0)
        assert not pbft._commit_lock_allows(SEQ, HB, 1)

    @pytest.mark.asyncio
    async def test_unlock_producer_round_trips_through_the_verifier(self, vc_armed):
        """The producer's output is accepted by ``view_change_justified``."""
        consensus = _make_consensus()
        local = MEMBERS[0]
        pbft = _pbft(consensus, local, KEYS[local])
        assert pbft.view_change_unlock_justification(SEQ, 1) is None  # no NV yet
        vc_set = _vc_set(SEQ, 1, MEMBERS[:Q])
        await pbft._handle_new_view_payload(_nv(_proposer(SEQ, 1), SEQ, 1, vc_set, None))
        just = pbft.view_change_unlock_justification(SEQ, 1)
        assert just is not None and just["kind"] == "view_change"
        payload = _evidence_payload(seq=SEQ, view_a=0, view_b=1, hash_a=HA, hash_b=HB)
        ctx = VcApplyContext(chain_id=_CID, sequence=SEQ, validator_set=frozenset(MEMBERS))
        assert view_change_justified(payload, just, ctx) is True

    def test_unlock_producer_dormant_without_gate(self):
        consensus = _make_consensus()
        pbft = _pbft(consensus, MEMBERS[0], KEYS[MEMBERS[0]])
        pbft._new_views[(SEQ, 1)] = {"payload": {"x": 1}, "kind": "free", "selected": None}
        assert pbft.view_change_unlock_justification(SEQ, 1) is None

    @pytest.mark.asyncio
    async def test_own_vc_is_resent_until_a_new_view_arrives(self, vc_armed):
        consensus = _make_consensus()
        local = MEMBERS[0]
        pbft = _pbft(consensus, local, KEYS[local])
        gossip = _FakeGossip()
        pbft.set_gossip_backend(gossip)
        assert await pbft._send_view_change(SEQ, VIEW)
        sent = len(gossip.published)
        await pbft._resend_view_change_if_due(SEQ, VIEW)
        assert len(gossip.published) == sent + 1  # first re-send goes out
        await pbft._resend_view_change_if_due(SEQ, VIEW)
        assert len(gossip.published) == sent + 1  # rate-limited
        pbft._vc_last_resend.clear()
        pbft._new_views[(SEQ, VIEW)] = {"payload": {"sender": MEMBERS[1]}, "kind": "free", "selected": None}
        await pbft._resend_view_change_if_due(SEQ, VIEW)
        assert len(gossip.published) == sent + 1  # NV known (not ours): stop re-sending the VC

    @pytest.mark.asyncio
    async def test_resend_is_dormant_without_gate(self):
        consensus = _make_consensus()
        pbft = _pbft(consensus, MEMBERS[0], KEYS[MEMBERS[0]])
        gossip = _FakeGossip()
        pbft.set_gossip_backend(gossip)
        await pbft._resend_view_change_if_due(SEQ, VIEW)
        assert gossip.published == []

    @pytest.mark.asyncio
    async def test_floor_rule_refuses_lower_view_vote(self, vc_armed):
        """Floor rule: after a VC for view v the node never votes below v."""
        consensus = _make_consensus()
        local = MEMBERS[0]
        pbft = _pbft(consensus, local, KEYS[local])
        assert await pbft._send_view_change(SEQ, 4)
        for v in (0, 1, 2, 3):
            # Even a verified free NEW_VIEW at the lower view cannot reopen it:
            # only the floor check refuses here (a missing NV would too).
            pbft._new_views[(SEQ, v)] = {"payload": {}, "kind": "free", "selected": None}
            assert pbft._view_change_permit(SEQ, v, HA) is False


class TestQuorumIntersectionWithCertificates:
    """Exhaustive n=4, f=1: with lock proofs now certificate-backed, every NEW_VIEW
    quorum that overlaps a committing quorum forces exactly the committed hash,
    and a lone Byzantine voter cannot inject a rival lock."""

    def test_every_vc_quorum_forces_the_committed_hash(self):
        import itertools

        byz = MEMBERS[3]
        commit_quorum = MEMBERS[:Q]  # honest members that prepared+committed HA at view 0
        proposer = _proposer(SEQ, 1)
        for vc_senders in itertools.combinations(MEMBERS, Q):
            vcs = []
            for s in vc_senders:
                if s in commit_quorum:
                    vcs.append(_locked(s, HA, 0, SEQ, 1))
                elif s == byz:
                    # Byzantine: lock on HB backed only by its own signature.
                    vcs.append(
                        _vc(
                            s,
                            SEQ,
                            1,
                            lock={"view": 0, "block_hash": HB, "kind": "prepare", "msgs": _proof(HB, SEQ, 0, [s] * Q)},
                        )
                    )
                else:
                    vcs.append(_vc(s, SEQ, 1))
            nv = _nv(proposer, SEQ, 1, vcs, HA)
            ok, reason, kind, selected = verify_new_view(
                nv, MEMBERS, chain_id=CHAIN, sequence=SEQ, view=1, expected_sender=proposer
            )
            if byz in vc_senders:
                # The fabricated lock is rejected outright — the NV cannot carry it.
                assert not ok, vc_senders
            else:
                assert ok, (vc_senders, reason)
                assert (kind, selected) == ("locked", HA)


class TestR3Blockers:
    """#2005 r3: the three release-blocking r2 findings plus durable prepared."""

    @pytest.fixture(autouse=True)
    def _iso(self, _fresh_chain):
        return _fresh_chain

    def test_same_hash_commit_lock_advances_to_higher_view(self, vc_armed):
        """r2 B1: a committer of H at v must be able to commit H again at v' > v."""
        consensus = _make_consensus()
        c0 = _commit_rec(MEMBERS[0], HA, SEQ, 0)
        c1 = _commit_rec(MEMBERS[0], HA, SEQ, 1)
        assert consensus.pbft_vc_commit_lock_arm(SEQ, 0, HA, c0, _proof(HA, SEQ, 0))
        assert consensus.pbft_vc_commit_lock_arm(SEQ, 1, HA, c1, _proof(HA, SEQ, 1))
        lock = consensus.pbft_vc_commit_lock(SEQ)
        assert lock["view"] == 1 and lock["commit"]["view_number"] == 1
        # Never backwards, never a different hash.
        assert not consensus.pbft_vc_commit_lock_arm(SEQ, 0, HA, c0, _proof(HA, SEQ, 0))
        assert not consensus.pbft_vc_commit_lock_arm(SEQ, 2, HB, _commit_rec(MEMBERS[0], HB, SEQ, 2), _proof(HB, SEQ, 2))
        assert consensus.pbft_vc_commit_lock(SEQ)["view"] == 1

    def test_commit_lock_advance_survives_restart(self, vc_armed):
        consensus = _make_consensus()
        consensus.pbft_vc_commit_lock_arm(SEQ, 0, HA, _commit_rec(MEMBERS[0], HA, SEQ, 0), _proof(HA, SEQ, 0))
        consensus.pbft_vc_commit_lock_arm(SEQ, 2, HA, _commit_rec(MEMBERS[0], HA, SEQ, 2), _proof(HA, SEQ, 2))
        consensus2 = _make_consensus()
        consensus2.load_state()
        assert consensus2.pbft_vc_commit_lock(SEQ)["view"] == 2

    @pytest.mark.asyncio
    async def test_vc_outside_window_dropped(self, vc_armed):
        consensus = _make_consensus()
        pbft = _pbft(consensus, MEMBERS[0], KEYS[MEMBERS[0]])
        pbft.state.current_sequence = SEQ
        far_view = pbft.state.current_view + getattr(settings, "pbft_max_view_ahead", 64) + 1
        far_seq = SEQ + getattr(settings, "pbft_max_sequence_ahead", 512) + 1
        await pbft._handle_view_change_payload(_vc(MEMBERS[1], SEQ + 1, far_view))
        await pbft._handle_view_change_payload(_vc(MEMBERS[1], far_seq, VIEW))
        await pbft._handle_view_change_payload(_vc(MEMBERS[1], SEQ - 1, VIEW))
        assert pbft._vc_messages == {}
        await pbft._handle_view_change_payload(_vc(MEMBERS[1], SEQ + 1, VIEW))
        assert (SEQ + 1, VIEW) in pbft._vc_messages

    @pytest.mark.asyncio
    async def test_honest_vc_survives_junk_flood(self, vc_armed):
        """r2 B3: a flood of junk (seq, view) buckets must not starve the real pair."""
        from aitbc_chain.consensus.pbft_view_change import MAX_VC_BUCKETS

        consensus = _make_consensus()
        pbft = _pbft(consensus, MEMBERS[0], KEYS[MEMBERS[0]])
        pbft.state.current_sequence = SEQ - 1
        for i in range(MAX_VC_BUCKETS + 20):
            await pbft._handle_view_change_payload(_vc(MEMBERS[3], SEQ + 1 + i, VIEW))
        # #2133: one sender is capped at its per-sender budget, well under the table cap.
        from aitbc_chain.consensus.pbft_view_change import MAX_VC_BUCKETS_PER_SENDER

        assert len(pbft._vc_messages) == MAX_VC_BUCKETS_PER_SENDER < MAX_VC_BUCKETS
        await pbft._handle_view_change_payload(_vc(MEMBERS[1], SEQ, VIEW))
        await pbft._handle_view_change_payload(_vc(MEMBERS[2], SEQ, VIEW))
        assert set(pbft._vc_messages[(SEQ, VIEW)]) == {canonical_address(MEMBERS[1]), canonical_address(MEMBERS[2])}
        assert len(pbft._vc_messages) <= MAX_VC_BUCKETS

    @pytest.mark.asyncio
    async def test_stale_buckets_pruned_on_intake(self, vc_armed):
        consensus = _make_consensus()
        pbft = _pbft(consensus, MEMBERS[0], KEYS[MEMBERS[0]])
        pbft.state.current_sequence = SEQ - 1
        await pbft._handle_view_change_payload(_vc(MEMBERS[1], SEQ, VIEW))
        pbft.state.current_sequence = SEQ + 5
        await pbft._handle_view_change_payload(_vc(MEMBERS[1], SEQ + 6, VIEW))
        assert (SEQ, VIEW) not in pbft._vc_messages

    @staticmethod
    def _cross_view_setup(monkeypatch, with_new_view: bool):
        from types import SimpleNamespace

        monkeypatch.setattr(settings, "pbft_cross_view_commit_lock_height", SEQ)
        consensus = _make_consensus()
        pbft = _pbft(consensus, MEMBERS[0], KEYS[MEMBERS[0]])
        if with_new_view:
            nv = _nv(_proposer(SEQ, 1), SEQ, 1, _vc_set(SEQ, 1, MEMBERS[:Q]), None)
            pbft._new_views[(SEQ, 1)] = {"payload": nv, "kind": "free", "selected": None}
        voter = MEMBERS[1]
        for view, block_hash in ((0, HA), (1, HB)):
            rec = _commit_rec(voter, block_hash, SEQ, view)
            consensus.record_commit(voter, block_hash, view, message=SimpleNamespace(**rec))
        return consensus

    def test_justified_cross_view_commit_is_not_slashed(self, vc_armed, monkeypatch):
        """r2 B2: an honest node committing B after a free NEW_VIEW is not DOUBLE_SIGN."""
        consensus = self._cross_view_setup(monkeypatch, with_new_view=True)
        assert consensus._slashing_manager.slashing_events == []

    def test_unjustified_cross_view_commit_still_slashed_with_no_proof(self, vc_armed, monkeypatch):
        consensus = self._cross_view_setup(monkeypatch, with_new_view=False)
        events = consensus._slashing_manager.slashing_events
        assert len(events) == 1
        assert "unlock_justification" not in json.loads(events[0].evidence)

    def test_event_carries_unlock_justification_when_supplied(self, vc_armed):
        from aitbc_chain.consensus.slashing import SlashingManager

        a = _commit_rec(MEMBERS[1], HA, SEQ, 0)
        b = _commit_rec(MEMBERS[1], HB, SEQ, 1)
        proof = {"kind": "view_change", "new_view": {"x": 1}}
        event = SlashingManager().cross_view_vote_equivocation_event(
            MEMBERS[1], SEQ, "commit", a, b, unlock_justification=proof
        )
        assert json.loads(event.evidence)["unlock_justification"] == proof

    @pytest.mark.asyncio
    async def test_prepared_record_blocks_same_view_second_block_after_restart(self, vc_armed):
        """r2 durable-prepared: restart must not forget the prepared (view, hash)."""
        consensus = _make_consensus()
        local = MEMBERS[0]
        assert consensus.pbft_vc_prepared_arm(SEQ, VIEW, HA)
        pbft = _pbft(consensus, local, KEYS[local])  # fresh engine: _prepared_heights empty
        assert pbft._prepared_heights == {}
        assert pbft._durable_prepared(SEQ) == (VIEW, HA)
        assert pbft._prepared_heights[SEQ] == (VIEW, HA)

    @pytest.mark.asyncio
    async def test_restart_cannot_prepare_a_second_block_in_the_same_view(self, vc_armed):
        """The prepare path itself honours the durable record — even when a FREE
        NEW_VIEW would otherwise permit any hash at that view (the amnesia hole)."""
        consensus = _make_consensus()
        local = MEMBERS[0]
        assert consensus.pbft_vc_prepared_arm(SEQ, VIEW, HA)
        pbft = _pbft(consensus, local, KEYS[local])  # restart: no in-memory prepared height
        nv = _nv(_proposer(SEQ, VIEW), SEQ, VIEW, _vc_set(SEQ, VIEW, MEMBERS[:Q]), None)
        pbft._new_views[(SEQ, VIEW)] = {"payload": nv, "kind": "free", "selected": None}
        key = f"{SEQ}:{VIEW}"
        proposer = _proposer(SEQ, VIEW)
        signer = _pbft(consensus, proposer, KEYS[proposer])

        def _offer(block_hash: str) -> PBFTMessage:
            msg = PBFTMessage(
                message_type=PBFTMessageType.PRE_PREPARE,
                sender=proposer,
                view_number=VIEW,
                sequence_number=SEQ,
                digest=pbft.get_message_digest(block_hash, SEQ, VIEW),
                signature="",
                timestamp=0.0,
                block_hash=block_hash,
                block=_proposal_body(proposer, block_hash),
            )
            signer._sign_message(msg)
            return msg

        offered_b = _offer(HB)
        pbft.state.pre_prepare_messages[key] = offered_b
        await pbft.prepare_phase(local, offered_b)
        assert key not in pbft._local_prepared
        assert not pbft.state.prepared_messages.get(key)
        # Control: the same gate lets the previously prepared hash through, so
        # the refusal above is the durable record and nothing else.
        offered_a = _offer(HA)
        pbft.state.pre_prepare_messages[key] = offered_a
        await pbft.prepare_phase(local, offered_a)
        assert key in pbft._local_prepared

    def test_malformed_floor_fails_closed(self, vc_armed):
        consensus = _make_consensus()
        with pytest.raises(ValueError):
            consensus._parse_view_change_records(json.dumps({str(SEQ): {"floor": "three", "proposals": {}}}))


class TestR4VcSetOrderInsensitive:
    """#2005 r4: one NEW_VIEW signature validates every vc_set ordering, so a
    duplicate sender must be rejected or the forced hash becomes order-dependent."""

    def _equivocating_set(self):
        s = MEMBERS[0]
        return [
            _locked(s, HA, 1, SEQ, VIEW),
            _locked(s, HB, 2, SEQ, VIEW),
            _vc(MEMBERS[1], SEQ, VIEW),
            _vc(MEMBERS[2], SEQ, VIEW),
        ]

    def test_duplicate_sender_rejected_in_every_order(self):
        base = self._equivocating_set()
        for vc_set in (base, list(reversed(base))):
            ok, reason, _ = analyze_vc_set(vc_set, MEMBERS, chain_id=CHAIN, sequence=SEQ, view=VIEW)
            assert not ok and "duplicate" in reason

    def test_new_view_with_duplicate_sender_fails_verification(self):
        proposer = _proposer(SEQ, VIEW)
        for vc_set in (self._equivocating_set(), list(reversed(self._equivocating_set()))):
            nv = _nv(proposer, SEQ, VIEW, vc_set, HB)
            ok, reason, _, _ = verify_new_view(nv, MEMBERS, chain_id=CHAIN, sequence=SEQ, view=VIEW, expected_sender=proposer)
            assert not ok and "duplicate" in reason

    def test_duplicate_rejected_before_signature_work(self, monkeypatch):
        import aitbc_chain.consensus.pbft_view_change as vcm

        calls = []
        monkeypatch.setattr(vcm, "_vc_record_acceptable", lambda *a, **k: calls.append(1) or (True, ""))
        analyze_vc_set(self._equivocating_set(), MEMBERS, chain_id=CHAIN, sequence=SEQ, view=VIEW)
        assert calls == []

    @pytest.mark.asyncio
    async def test_new_view_outside_window_dropped(self, vc_armed):
        consensus = _make_consensus()
        pbft = _pbft(consensus, MEMBERS[0], KEYS[MEMBERS[0]])
        pbft.state.current_sequence = SEQ
        far_view = pbft.state.current_view + getattr(settings, "pbft_max_view_ahead", 64) + 1
        proposer = _proposer(SEQ, far_view)
        await pbft._handle_new_view_payload(_nv(proposer, SEQ, far_view, _vc_set(SEQ, far_view, MEMBERS[:Q]), None))
        assert pbft._new_views == {}

    @pytest.mark.asyncio
    async def test_new_view_wrong_sender_skips_signature_verification(self, vc_armed, monkeypatch):
        import aitbc_chain.consensus.pbft as pbft_mod

        consensus = _make_consensus()
        pbft = _pbft(consensus, MEMBERS[0], KEYS[MEMBERS[0]])
        proposer = _proposer(SEQ, VIEW)
        impostor = next(m for m in MEMBERS if m != proposer)
        calls = []
        monkeypatch.setattr(pbft_mod, "verify_new_view", lambda *a, **k: calls.append(1))
        await pbft._handle_new_view_payload(_nv(impostor, SEQ, VIEW, _vc_set(SEQ, VIEW, MEMBERS[:Q]), None))
        assert calls == [] and pbft._new_views == {}


class TestR4NearerFlood:
    """#2133 (reviewer B's R1): a Byzantine validator flooding keys NEARER than the
    stalled pair must not starve the honest VCs for it."""

    @pytest.mark.asyncio
    async def test_nearer_flood_cannot_starve_honest_vcs(self, vc_armed):
        from aitbc_chain.consensus.pbft_view_change import MAX_VC_BUCKETS, MAX_VC_BUCKETS_PER_SENDER

        consensus = _make_consensus()
        pbft = _pbft(consensus, MEMBERS[0], KEYS[MEMBERS[0]])
        pbft.state.current_sequence = SEQ - 5
        pbft.state.current_view = 0
        attacker = MEMBERS[3]
        # 325 signed VCs, every key nearer than (SEQ, VIEW): seqs SEQ-5..SEQ-1 x views 0..64
        for s in range(SEQ - 5, SEQ):
            for v in range(65):
                await pbft._handle_view_change_payload(_vc(attacker, s, v))
        assert len(pbft._vc_messages) <= MAX_VC_BUCKETS_PER_SENDER < MAX_VC_BUCKETS
        await pbft._handle_view_change_payload(_vc(MEMBERS[1], SEQ, VIEW))
        await pbft._handle_view_change_payload(_vc(MEMBERS[2], SEQ, VIEW))
        assert set(pbft._vc_messages[(SEQ, VIEW)]) == {canonical_address(MEMBERS[1]), canonical_address(MEMBERS[2])}

    @pytest.mark.asyncio
    async def test_sender_displaces_its_own_farthest_for_a_nearer_key_only(self, vc_armed):
        from aitbc_chain.consensus.pbft_view_change import MAX_VC_BUCKETS_PER_SENDER

        consensus = _make_consensus()
        pbft = _pbft(consensus, MEMBERS[0], KEYS[MEMBERS[0]])
        pbft.state.current_sequence = SEQ
        sender = MEMBERS[1]
        for v in range(1, MAX_VC_BUCKETS_PER_SENDER + 1):
            await pbft._handle_view_change_payload(_vc(sender, SEQ, v))
        assert (SEQ, MAX_VC_BUCKETS_PER_SENDER) in pbft._vc_messages
        await pbft._handle_view_change_payload(_vc(sender, SEQ, MAX_VC_BUCKETS_PER_SENDER + 1))  # farther: refused
        assert (SEQ, MAX_VC_BUCKETS_PER_SENDER + 1) not in pbft._vc_messages
        await pbft._handle_view_change_payload(_vc(sender, SEQ, 0))  # nearer: displaces the farthest own
        assert (SEQ, 0) in pbft._vc_messages and (SEQ, MAX_VC_BUCKETS_PER_SENDER) not in pbft._vc_messages
        assert len(pbft._vc_messages) == MAX_VC_BUCKETS_PER_SENDER


class TestItem2ProposalBodySignature:
    """#2133 item 2: the stored proposal body must carry the scheduled
    proposer's block signature — a substituted body (valid hash/height
    labels, forged or foreign signature) is refused at intake."""

    def _engine(self):
        consensus = _make_consensus()
        proposer = _proposer(SEQ, VIEW)
        follower = next(s for s in MEMBERS if s != proposer)
        return consensus, proposer, _pbft(consensus, follower, KEYS[follower])

    def test_signed_body_is_stored(self, vc_armed):
        consensus, proposer, pbft = self._engine()
        assert pbft._vc_proposal_store(SEQ, HA, _proposal_body(proposer)) is True
        assert consensus.pbft_vc_proposal_get(SEQ, HA)

    def test_substituted_body_is_refused(self, vc_armed):
        """Same hash/height labels, tampered header, original signature."""
        consensus, proposer, pbft = self._engine()
        body = _proposal_body(proposer)
        body["state_root"] = "0x" + "22" * 32
        assert pbft._vc_proposal_store(SEQ, HA, body) is False

    def test_foreign_signature_is_refused(self, vc_armed):
        consensus, proposer, pbft = self._engine()
        body = _proposal_body(proposer)
        other = next(a for a in MEMBERS if a != proposer)
        from aitbc.crypto.consensus_signing import sign_block_hash

        body["signature"] = sign_block_hash(body, KEYS[other])
        assert pbft._vc_proposal_store(SEQ, HA, body) is False

    def test_unsigned_body_is_refused(self, vc_armed):
        consensus, proposer, pbft = self._engine()
        body = _proposal_body(proposer)
        body["signature"] = ""
        assert pbft._vc_proposal_store(SEQ, HA, body) is False
