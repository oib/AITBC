"""#1940: UC excuse producer→consumer wiring, abandoned-height fail-closed,
cert version enforcement, validator-set key scoping, and the
justification-without-round-lock startup guard.

Pins the F1 contract end-to-end: the producer bundle shape
(``unavailability_cert`` + ``certs[]``) must surface in slashing evidence as
``{"kind": "uc", "cert": <cert bound to the earlier-round vote's hash>}`` —
the only shape ``equivocation_policy.justified_unlock`` accepts.
"""

from __future__ import annotations

import json

import pytest
from aitbc_chain.config import ChainSettings, uc_combo_findings
from aitbc_chain.consensus import unavail
from aitbc_chain.consensus.equivocation_policy import JUSTIFICATION_FIELD, UcApplyContext, pair_stands_as_evidence
from aitbc_chain.consensus.remote_attestation_evidence import _EvidenceMixin
from aitbc_chain.consensus.slashing import SlashingManager
from aitbc_chain.consensus.unavail import UnavailabilityCertificate

from aitbc.crypto.signature_recovery import canonical_address

from .test_deactivation_evidence_1263 import HA, HB, _attestation_record
from .test_unavail_cert_fuzz_1281 import ADDR1, ADDR2, ADDR3, KEY1, KEY2

CHAIN = "test-chain"
HEIGHT = 11
VSET = frozenset(canonical_address(a) for a in (ADDR1, ADDR2, ADDR3))
SIGNER = "0x" + "11" * 32
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


def _bundle(*hashes: str) -> dict:
    """The real producer shape emitted by ``unavail.unlock_justification``."""
    hs = sorted(hashes)
    return {
        "kind": "unavailability_cert",
        "height": HEIGHT,
        "hashes": hs,
        "index": {},
        "certs": [_cert(block_hash=h) for h in hs],
    }


def _records(round_a: int, round_b: int) -> list[dict]:
    return [
        _attestation_record(SIGNER, HA, height=HEIGHT, round_in_payload=True, request_round=round_a),
        _attestation_record(SIGNER, HB, height=HEIGHT, round_in_payload=True, request_round=round_b),
    ]


def _ctx() -> UcApplyContext:
    return UcApplyContext(chain_id=CHAIN, now=T0, validator_set=VSET, max_age=120.0, min_responses=2)


def _evidence_mixin() -> _EvidenceMixin:
    obj = _EvidenceMixin.__new__(_EvidenceMixin)
    obj._abandoned_heights = {}
    obj._abandoned_rounds = {}
    return obj


# ---------- F1: cert selection helper ----------


def test_uc_selection_picks_cert_for_earlier_round_hash():
    m = _evidence_mixin()
    prior = {"hash": HA, "request_round": 0, "round_in_payload": True}
    current = {"hash": HB, "request_round": 5, "round_in_payload": True}
    out = m._uc_unlock_justification(_bundle(HA), prior, current)
    assert out == {"kind": "uc", "cert": _cert(block_hash=HA)}


def test_uc_selection_binds_locked_record_not_prior_position():
    # Re-vote edge: the NEW vote can be the earlier-round record — the cert
    # must bind whichever record _uc_justified will lock (min request_round).
    m = _evidence_mixin()
    prior = {"hash": HA, "request_round": 7, "round_in_payload": True}
    current = {"hash": HB, "request_round": 2, "round_in_payload": True}
    # bundle certifies HA (the already-voted hash); locked=HB has no cert → None
    assert m._uc_unlock_justification(_bundle(HA), prior, current) is None
    # bundle certifies HB → excuse binds HB
    out = m._uc_unlock_justification(_bundle(HB), prior, current)
    assert out == {"kind": "uc", "cert": _cert(block_hash=HB)}


@pytest.mark.parametrize(
    "bundle,prior,current",
    [
        (None, {"hash": HA, "request_round": 0}, {"hash": HB, "request_round": 5}),
        (_bundle(HA), None, {"hash": HB, "request_round": 5}),
        (_bundle(HA), {"hash": HA, "request_round": 3}, {"hash": HB, "request_round": 3}),  # same round
        (_bundle(HA), {"hash": HA, "request_round": None}, {"hash": HB, "request_round": 5}),  # legacy
        (_bundle(HB), {"hash": HA, "request_round": 0}, {"hash": HB, "request_round": 5}),  # cert for wrong hash
    ],
)
def test_uc_selection_fails_closed(bundle, prior, current):
    m = _evidence_mixin()
    assert m._uc_unlock_justification(bundle, prior, current) is None


# ---------- F1: evidence → apply-gate end to end ----------


def test_recorded_evidence_carries_uc_proof_and_is_excused():
    mgr = SlashingManager()
    records = _records(0, 5)
    unlock = {"kind": "uc", "cert": _cert(block_hash=HA)}
    event = mgr.record_attestation_equivocation(
        validator_address=SIGNER,
        height=HEIGHT,
        round_number=5,
        block_hash_a=HA,
        block_hash_b=HB,
        proposer="0x" + "22" * 32,
        attestations=records,
        justification="unavailability_cert",
        unlock_justification=unlock,
    )
    payload = json.loads(event.evidence)
    assert payload[JUSTIFICATION_FIELD] == unlock
    assert payload["justification"] == "unavailability_cert"
    # The apply gate must now excuse the pair (cert binds HA = earlier round).
    assert pair_stands_as_evidence(payload, _ctx()) is False


def test_recorded_evidence_without_proof_still_slashable():
    mgr = SlashingManager()
    event = mgr.record_attestation_equivocation(
        validator_address=SIGNER,
        height=HEIGHT,
        round_number=5,
        block_hash_a=HA,
        block_hash_b=HB,
        proposer="0x" + "22" * 32,
        attestations=_records(0, 5),
        justification="unjustified",
    )
    payload = json.loads(event.evidence)
    assert JUSTIFICATION_FIELD not in payload
    assert pair_stands_as_evidence(payload, _ctx()) is True


# ---------- F2: height-level abandoned index ----------


def test_abandoned_height_rival_fails_closed_only_for_different_hash():
    m = _evidence_mixin()
    m._note_abandoned_height(HEIGHT, HA)
    assert m._abandoned_height_rival(HEIGHT, HB) == HA
    assert m._abandoned_height_rival(HEIGHT, HA) is None  # re-sign allowed
    assert m._abandoned_height_rival(HEIGHT + 1, HB) is None


def test_abandoned_height_index_prunes():
    m = _evidence_mixin()
    m._note_abandoned_height(HEIGHT, HA)
    m._note_abandoned_height(HEIGHT + 100, HB)  # prunes HEIGHT (< h-64)
    assert HEIGHT not in m._abandoned_heights
    assert m._abandoned_heights[HEIGHT + 100] == {HB}


# ---------- F6a: cert version enforcement ----------


def test_from_dict_rejects_foreign_version():
    raw = _cert()
    raw["version"] = 99
    assert UnavailabilityCertificate.from_dict(raw) is None


def test_from_dict_accepts_current_and_absent_version():
    assert UnavailabilityCertificate.from_dict(_cert()) is not None
    raw = _cert()
    del raw["version"]
    assert UnavailabilityCertificate.from_dict(raw) is not None


# ---------- F6b: local attestations scoped to validator set ----------


def test_attestable_addresses_env_set_wins(monkeypatch):
    from aitbc_chain.consensus import poa as poa_mod

    obj = poa_mod._PoaBaseMixin.__new__(poa_mod._PoaBaseMixin)
    obj._multi_validator = None
    monkeypatch.setattr(
        poa_mod.settings,
        "validator_set",
        json.dumps([{"address": ADDR1, "stake": "1"}, {"address": ADDR2, "stake": "1"}]),
    )
    assert obj._attestable_addresses() == {canonical_address(ADDR1), canonical_address(ADDR2)}


def test_attestable_addresses_falls_back_to_multi_validator(monkeypatch):
    from aitbc_chain.consensus import poa as poa_mod

    class _MV:
        validators = {ADDR3: object()}

    obj = poa_mod._PoaBaseMixin.__new__(poa_mod._PoaBaseMixin)
    obj._multi_validator = _MV()
    monkeypatch.setattr(poa_mod.settings, "validator_set", "")
    assert obj._attestable_addresses() == {canonical_address(ADDR3)}


def test_attestable_addresses_none_when_unconfigured(monkeypatch):
    from aitbc_chain.consensus import poa as poa_mod

    obj = poa_mod._PoaBaseMixin.__new__(poa_mod._PoaBaseMixin)
    obj._multi_validator = None
    monkeypatch.setattr(poa_mod.settings, "validator_set", "")
    assert obj._attestable_addresses() is None


# ---------- guard: justification without round-bound attestations ----------


_BASE = {
    "vote_journal_enabled": True,
    "vote_journal_justification_enabled": True,
    "attestation_round_lock_enabled": False,
    "consensus_domain_separation_height": None,
    # timing-safe window (45s < 60s header max) so only the round-binding
    # guard is under test
    "unavail_evidence_seconds": 30.0,
    "unavail_collect_seconds": 10.0,
}


def test_guard_errors_when_justification_armed_without_round_binding():
    errors, _ = uc_combo_findings(ChainSettings(**_BASE))
    assert any("attestation_round_lock_enabled" in e for e in errors)


def test_guard_clean_with_round_lock_or_domain_separation():
    errors, _ = uc_combo_findings(ChainSettings(**{**_BASE, "attestation_round_lock_enabled": True}))
    assert errors == []
    errors, _ = uc_combo_findings(ChainSettings(**{**_BASE, "consensus_domain_separation_height": 100}))
    assert errors == []


def test_guard_inert_when_justification_off():
    errors, _ = uc_combo_findings(ChainSettings(**{**_BASE, "vote_journal_justification_enabled": False}))
    assert errors == []
