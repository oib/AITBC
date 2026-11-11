"""#1281 option-3 slice: the apply-time ``uc`` unlock proof is deterministic and dormant.

Pinned: with no context (default) verdicts are the legacy ones; with a context a
valid UC bound to the EARLIER vote's block excuses a cross-round pair only; the
verdict depends on the context (block time, set, threshold), never wall clock;
every malformed/unbound/stale case fails closed.
"""

from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime

import pytest
from aitbc_chain.consensus import equivocation_policy as policy
from aitbc_chain.consensus import unavail
from aitbc_chain.consensus.equivocation_policy import JUSTIFICATION_FIELD, UcApplyContext, pair_stands_as_evidence
from aitbc_chain.consensus.unavail import UnavailabilityCertificate
from aitbc_chain.state import deactivation_evidence as de

from aitbc.crypto.signature_recovery import canonical_address

from .test_deactivation_evidence_1263 import HA, HB, _attestation_record
from .test_unavail_cert_fuzz_1281 import ADDR1, ADDR2, ADDR3, KEY1, KEY2

CHAIN = "test-chain"
HEIGHT = 11
VSET = frozenset(canonical_address(a) for a in (ADDR1, ADDR2, ADDR3))
SIGNER = "0x" + "11" * 32  # ledger-only attestation signer key (not a validator-set member)
T0 = 1_800_000_000.0


def _cert(block_hash=HA, epoch=int(T0), signers=((ADDR1, KEY1), (ADDR2, KEY2)), height=HEIGHT) -> dict:
    return UnavailabilityCertificate(
        chain_id=CHAIN,
        height=height,
        hash=block_hash,
        epoch=epoch,
        responses=tuple(
            {"validator": a, "signature": unavail.build_unavail_response(CHAIN, height, block_hash, epoch, a, k)["signature"]}
            for a, k in signers
        ),
    ).to_dict()


def _payload(rounds=(0, 5), cert=None, kind="uc") -> dict:
    atts = [
        _attestation_record(SIGNER, HA, height=HEIGHT, round_in_payload=True, request_round=rounds[0]),
        _attestation_record(SIGNER, HB, height=HEIGHT, round_in_payload=True, request_round=rounds[1]),
    ]
    return {
        "kind": "attestation_equivocation",
        "block_hash_a": HA,
        "block_hash_b": HB,
        "attestations": atts,
        JUSTIFICATION_FIELD: {"kind": kind, "cert": _cert() if cert is None else cert},
    }


def _ctx(**kw) -> UcApplyContext:
    base = {"chain_id": CHAIN, "now": T0, "validator_set": VSET, "max_age": 120.0, "min_responses": 2}
    base.update(kw)
    return UcApplyContext(**base)


def test_default_no_context_is_legacy_verdict():
    assert pair_stands_as_evidence(_payload()) is True
    assert policy.UNLOCK_PROOF_VERIFIERS == {}


def test_valid_uc_excuses_cross_round_pair():
    assert pair_stands_as_evidence(_payload(), _ctx()) is False


def test_cert_bound_to_later_vote_block_does_not_excuse():
    assert pair_stands_as_evidence(_payload(cert=_cert(block_hash=HB)), _ctx()) is True


def test_swapped_round_order_binds_the_lower_round_block():
    # HA now carries round 5 and HB round 0: the locked (earlier) vote is HB
    assert pair_stands_as_evidence(_payload(rounds=(5, 0), cert=_cert(block_hash=HB)), _ctx()) is False
    assert pair_stands_as_evidence(_payload(rounds=(5, 0)), _ctx()) is True  # cert for HA (later vote)


@pytest.mark.parametrize("rounds", [(3, 3), (None, None)])
def test_only_cross_round_is_excusable(rounds):
    p = _payload(rounds=rounds)
    if rounds[0] is None:
        for a in p["attestations"]:
            a["round_in_payload"] = False
            a["request_round"] = None
    assert pair_stands_as_evidence(p, _ctx()) is True


def test_verdict_uses_context_time_not_wall_clock():
    p = _payload()
    assert pair_stands_as_evidence(p, _ctx(now=T0 + 60)) is False
    assert pair_stands_as_evidence(p, _ctx(now=T0 + 500)) is True  # stale vs BLOCK time
    # same context, asserted twice at different wall clock: identical verdict
    first = pair_stands_as_evidence(p, _ctx())
    time.sleep(0.01)
    assert pair_stands_as_evidence(p, _ctx()) is first


def test_threshold_and_set_come_from_context():
    assert pair_stands_as_evidence(_payload(), _ctx(min_responses=3)) is True
    assert pair_stands_as_evidence(_payload(), _ctx(validator_set=frozenset({canonical_address(ADDR1)}))) is True


def test_forged_signature_and_junk_fail_closed():
    bad = _cert()
    bad["responses"][0]["signature"] = bad["responses"][1]["signature"]
    assert pair_stands_as_evidence(_payload(cert=bad), _ctx()) is True
    for junk in ({"kind": "uc"}, {"kind": "uc", "cert": "x"}, {"kind": "uc", "cert": {"a": 1}}):
        p = _payload()
        p[JUSTIFICATION_FIELD] = junk
        assert pair_stands_as_evidence(p, _ctx()) is True
    p = _payload()
    p["attestations"][0]["height"] = "nan"
    assert pair_stands_as_evidence(p, _ctx()) is True


def test_other_kinds_still_not_proof_even_with_context():
    for kind in ("time", "journal_valve", "operator"):
        assert pair_stands_as_evidence(_payload(kind=kind), _ctx()) is True


def test_wrong_chain_fails_closed():
    assert pair_stands_as_evidence(_payload(), _ctx(chain_id="other")) is True


class TestUcContext:
    DIGEST = hashlib.sha256("\n".join(sorted(VSET)).encode()).hexdigest()
    BT = datetime.fromtimestamp(T0, UTC)

    def _params(self, monkeypatch, **over):
        params = {
            "unlock_proof_uc_enabled": "true",
            "unlock_proof_uc_min_responses": "2",
            "unlock_proof_uc_max_age_seconds": "120",
            "unlock_proof_uc_validator_set_digest": self.DIGEST,
        }
        params.update(over)
        import aitbc_chain.state.state_transition as st

        monkeypatch.setattr(st, "_chain_parameter_value", lambda s, c, name, h=None: params.get(name))
        monkeypatch.setattr(unavail, "validator_addresses", lambda: set(VSET))

    def test_armed_context_built(self, monkeypatch):
        self._params(monkeypatch)
        ctx = de._uc_context(object(), CHAIN, 100, self.BT)
        assert ctx == _ctx(now=T0)

    @pytest.mark.parametrize(
        "over",
        [
            {"unlock_proof_uc_enabled": None},
            {"unlock_proof_uc_enabled": "false"},
            {"unlock_proof_uc_min_responses": "0"},
            {"unlock_proof_uc_min_responses": "x"},
            {"unlock_proof_uc_max_age_seconds": "-1"},
            {"unlock_proof_uc_max_age_seconds": None},
            {"unlock_proof_uc_validator_set_digest": "deadbeef"},
            {"unlock_proof_uc_validator_set_digest": None},
        ],
    )
    def test_fail_closed_on_missing_or_bad_param(self, monkeypatch, over):
        self._params(monkeypatch, **over)
        assert de._uc_context(object(), CHAIN, 100, self.BT) is None

    def test_no_height_or_time_is_none(self, monkeypatch):
        self._params(monkeypatch)
        assert de._uc_context(object(), CHAIN, None, self.BT) is None
        assert de._uc_context(object(), CHAIN, 100, None) is None

    def test_local_set_differing_from_onchain_digest_fails_closed(self, monkeypatch):
        self._params(monkeypatch)
        monkeypatch.setattr(unavail, "validator_addresses", lambda: set(list(VSET)[:2]))
        assert de._uc_context(object(), CHAIN, 100, self.BT) is None

    def test_naive_block_time_is_treated_as_utc(self, monkeypatch):
        self._params(monkeypatch)
        ctx = de._uc_context(object(), CHAIN, 100, datetime.fromtimestamp(T0, UTC).replace(tzinfo=None))
        assert ctx is not None and ctx.now == T0
