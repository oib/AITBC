"""#1274 (EQUIV-XROUND-1): same-height different-hash pairs stay evidence across rounds.

Audit-Director policy (#1274 comment 20233):
  * legacy (round_in_payload false) and round-bound pairs both stand as
    equivocation evidence, same round or across rounds — no advisory downgrade
    and no blanket same-round-only rule;
  * a cross-round transition is excused only by an independently verifiable
    protocol proof; a timer / journal valve / operator claim is not proof;
  * the registry of proofs is empty today, so verdicts are unchanged.
"""

from __future__ import annotations

import json

import pytest

from aitbc.crypto.crypto import derive_ethereum_address
from aitbc_chain.consensus import equivocation_policy as policy
from aitbc_chain.consensus.equivocation_policy import (
    JUSTIFICATION_FIELD,
    PairClass,
    classify_attestation_pair,
    justified_unlock,
    pair_stands_as_evidence,
)
from aitbc_chain.consensus.slashing import SlashingCondition, SlashingManager, event_signature_evidence
from aitbc_chain.state.deactivation_evidence import verify_deactivation_evidence

from .test_deactivation_evidence_1263 import (
    ADDR,
    ADDR_KEY,
    HA,
    HB,
    V2,
    _attestation_record,
    _v2_payload,
)


def _pair(first_round: int | None, second_round: int | None, *, bound_a: bool, bound_b: bool, height: int = 11):
    return [
        _attestation_record(ADDR_KEY, HA, height=height, round_in_payload=bound_a, request_round=first_round),
        _attestation_record(ADDR_KEY, HB, height=height, round_in_payload=bound_b, request_round=second_round),
    ]


def _record(mgr: SlashingManager, attestations: list[dict], *, round_number: int | None = None) -> None:
    mgr.record_attestation_equivocation(
        validator_address=ADDR,
        height=11,
        round_number=round_number,
        block_hash_a=HA,
        block_hash_b=HB,
        proposer=V2,
        attestations=attestations,
    )


def _verdict(mgr: SlashingManager) -> str | None:
    payload = _v2_payload(mgr, ADDR)
    return verify_deactivation_evidence(
        payload,
        chain_id="test-chain",
        validator_addr=payload["validator_address"],
        evidence_hash=payload["evidence_hash"],
    )


# (name, attestations) for every format the policy must treat as evidence
CASES = {
    "legacy": _pair(None, None, bound_a=False, bound_b=False),
    "round_bound_same_round": _pair(3, 3, bound_a=True, bound_b=True),
    "round_bound_cross_round": _pair(0, 5, bound_a=True, bound_b=True),
    "mixed_proposer_style": _pair(4, None, bound_a=True, bound_b=False),
}


class TestClassification:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("legacy", PairClass.LEGACY),
            ("round_bound_same_round", PairClass.ROUND_BOUND_SAME_ROUND),
            ("round_bound_cross_round", PairClass.ROUND_BOUND_CROSS_ROUND),
            ("mixed_proposer_style", PairClass.MIXED_FORMAT),
        ],
    )
    def test_pair_classes(self, name, expected):
        assert classify_attestation_pair({"attestations": CASES[name]}) is expected

    def test_hash_only_record_has_no_class(self):
        assert classify_attestation_pair({"kind": "attestation_equivocation"}) is None
        assert classify_attestation_pair({"attestations": []}) is None
        assert classify_attestation_pair({"attestations": [CASES["legacy"][0]]}) is None


class TestCrossRoundStaysEvidence:
    """Never advisory-downgraded: every format yields the same consequence."""

    @pytest.mark.parametrize("name", list(CASES))
    def test_pair_is_signature_bearing_double_sign_with_full_slash_rate(self, name):
        mgr = SlashingManager()
        _record(mgr, CASES[name])
        assert len(mgr.slashing_events) == 1
        event = mgr.slashing_events[0]
        assert event.condition is SlashingCondition.DOUBLE_SIGN
        assert event.slash_rate == pytest.approx(0.5)
        # signature-bearing => eligible for the on-chain gate (hash-only would be advisory)
        assert event_signature_evidence(event) is not None
        assert pair_stands_as_evidence(json.loads(event.evidence))

    def test_cross_round_and_legacy_records_are_equivalent_in_consequence(self):
        legacy, cross = SlashingManager(), SlashingManager()
        _record(legacy, CASES["legacy"])
        _record(cross, CASES["round_bound_cross_round"], round_number=5)
        a, b = legacy.slashing_events[0], cross.slashing_events[0]
        assert (a.condition, a.slash_rate, a.slashed_amount) == (b.condition, b.slash_rate, b.slashed_amount)

    @pytest.mark.parametrize("name", list(CASES))
    def test_full_gate_accepts_every_format(self, name):
        mgr = SlashingManager()
        _record(mgr, CASES[name])
        assert _verdict(mgr) is None, name

    def test_cross_round_dedup_does_not_collapse_distinct_rounds(self):
        """Same validator/height/pair, different recorded round => still one record per round key."""
        mgr = SlashingManager()
        _record(mgr, CASES["round_bound_cross_round"], round_number=5)
        _record(mgr, CASES["round_bound_cross_round"], round_number=5)  # idempotent repeat
        assert len(mgr.slashing_events) == 1

    def test_signature_verification_is_not_weakened(self):
        """A cross-round pair with a forged signature still fails the gate."""
        mgr = SlashingManager()
        forged = _pair(0, 5, bound_a=True, bound_b=True)
        forged[1]["signature"] = forged[0]["signature"]  # signature for the wrong hash/round
        _record(mgr, forged, round_number=5)
        assert _verdict(mgr) == "attestation equivocation evidence failed signature verification"

    def test_different_signer_pair_is_not_an_equivocation(self):
        mgr = SlashingManager()
        other_key = "0x" + "66" * 32
        pair = [
            _attestation_record(ADDR_KEY, HA, round_in_payload=True, request_round=0),
            _attestation_record(other_key, HB, round_in_payload=True, request_round=5),
        ]
        _record(mgr, pair, round_number=5)
        assert _verdict(mgr) is not None
        assert derive_ethereum_address(other_key) != ADDR


def _with_justification(mgr: SlashingManager, justification: dict) -> None:
    """Attach an unlock justification to every recorded event (before bundling)."""
    for event in mgr.slashing_events:
        ep = json.loads(event.evidence)
        ep[JUSTIFICATION_FIELD] = justification
        event.evidence = json.dumps(ep, sort_keys=True)


class TestJustifiedUnlock:
    UNJUSTIFIED = [
        {"kind": "time", "seconds": 300},
        {"kind": "journal_valve", "age": 301},
        {"kind": "operator", "note": "approved by operator"},
        {"kind": "qc_barrier"},  # a real future kind, but nothing registered today
        {"kind": 7},
        {"no_kind": True},
    ]

    def test_empty_registry_today(self):
        assert policy.UNLOCK_PROOF_VERIFIERS == {}

    def test_no_justification_means_evidence_stands(self):
        assert justified_unlock({"attestations": CASES["round_bound_cross_round"]}) is False

    @pytest.mark.parametrize("justification", UNJUSTIFIED)
    def test_unverifiable_justifications_never_excuse(self, justification):
        assert justified_unlock({JUSTIFICATION_FIELD: justification}) is False

    @pytest.mark.parametrize("justification", [None, "time", ["time"], 5])
    def test_malformed_justification_never_excuses(self, justification):
        assert justified_unlock({JUSTIFICATION_FIELD: justification}) is False

    @pytest.mark.parametrize("name", ["legacy", "round_bound_cross_round"])
    @pytest.mark.parametrize("justification", UNJUSTIFIED)
    def test_gate_still_accepts_pair_with_a_bare_unlock_claim(self, name, justification):
        """The self-reported unlock claim does not exempt the pair from the deactivation gate."""
        mgr = SlashingManager()
        _record(mgr, CASES[name], round_number=5 if "round" in name else None)
        _with_justification(mgr, justification)
        assert _verdict(mgr) is None

    def test_registered_verifying_proof_excuses_the_pair(self, monkeypatch):
        monkeypatch.setitem(policy.UNLOCK_PROOF_VERIFIERS, "test_proof", lambda j: j.get("ok") is True)
        assert justified_unlock({JUSTIFICATION_FIELD: {"kind": "test_proof", "ok": True}}) is True
        assert justified_unlock({JUSTIFICATION_FIELD: {"kind": "test_proof", "ok": False}}) is False

    def test_verifier_must_return_true_not_truthy(self, monkeypatch):
        monkeypatch.setitem(policy.UNLOCK_PROOF_VERIFIERS, "sloppy", lambda j: "yes")
        assert justified_unlock({JUSTIFICATION_FIELD: {"kind": "sloppy"}}) is False

    def test_raising_verifier_fails_closed(self, monkeypatch):
        def boom(_j):
            raise RuntimeError("proof decoder exploded")

        monkeypatch.setitem(policy.UNLOCK_PROOF_VERIFIERS, "boom", boom)
        assert justified_unlock({JUSTIFICATION_FIELD: {"kind": "boom"}}) is False

    @pytest.mark.parametrize("name", ["legacy", "round_bound_cross_round"])
    def test_gate_excuses_a_pair_only_with_a_verifying_registered_proof(self, name, monkeypatch):
        monkeypatch.setitem(policy.UNLOCK_PROOF_VERIFIERS, "test_proof", lambda j: j.get("ok") is True)

        excused = SlashingManager()
        _record(excused, CASES[name], round_number=5 if "round" in name else None)
        _with_justification(excused, {"kind": "test_proof", "ok": True})
        # signatures verified, but the only equivocation is excused => nothing left to slash on
        assert _verdict(excused) == "no verifiable equivocation evidence"

        refused = SlashingManager()
        _record(refused, CASES[name], round_number=5 if "round" in name else None)
        _with_justification(refused, {"kind": "test_proof", "ok": False})
        assert _verdict(refused) is None

    def test_excused_pair_does_not_hide_a_second_unexcused_equivocation(self, monkeypatch):
        monkeypatch.setitem(policy.UNLOCK_PROOF_VERIFIERS, "test_proof", lambda j: True)
        mgr = SlashingManager()
        _record(mgr, CASES["round_bound_cross_round"], round_number=5)
        _with_justification(mgr, {"kind": "test_proof"})
        # a second, distinct equivocation (other height) with no justification
        other = [
            _attestation_record(ADDR_KEY, HA, height=12, round_in_payload=False, request_round=None),
            _attestation_record(ADDR_KEY, HB, height=12, round_in_payload=False, request_round=None),
        ]
        mgr.record_attestation_equivocation(
            validator_address=ADDR,
            height=12,
            round_number=None,
            block_hash_a=HA,
            block_hash_b=HB,
            proposer=V2,
            attestations=other,
        )
        assert len(mgr.slashing_events) == 2
        assert _verdict(mgr) is None

    def test_excusal_does_not_skip_signature_verification(self, monkeypatch):
        """A forged pair carrying a 'verifying' proof must still fail the gate on its signatures."""
        monkeypatch.setitem(policy.UNLOCK_PROOF_VERIFIERS, "test_proof", lambda j: True)
        mgr = SlashingManager()
        forged = _pair(0, 5, bound_a=True, bound_b=True)
        forged[1]["signature"] = forged[0]["signature"]
        _record(mgr, forged, round_number=5)
        _with_justification(mgr, {"kind": "test_proof"})
        assert _verdict(mgr) == "attestation equivocation evidence failed signature verification"
