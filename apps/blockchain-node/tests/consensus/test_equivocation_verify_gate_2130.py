"""#2130 — verify equivocation evidence before slash()/record appends.

Hub's blob held 30k forged hash pairs that were recorded without a signature
check. Armed (``equivocation_verify_before_record``), an equivocation claim is
admitted only when both signatures verify against the accused at one height and
round with differing hashes, the accused has stake, and no signed or levied
record already stands at that height. Disarmed = byte-identical legacy.
"""

from __future__ import annotations

import copy
from decimal import Decimal

import pytest
from aitbc.crypto.crypto import derive_ethereum_address
from aitbc_chain.config import settings
from aitbc_chain.consensus.multi_validator_poa import Validator, ValidatorRole
from aitbc_chain.consensus.slashing import SlashingManager
from aitbc_chain.metrics import metrics_registry

from .test_deactivation_evidence_1263 import ADDR, ADDR_KEY, HA, HB, _attestation_record

OTHER_KEY = "0x" + "66" * 32
H = 11


def _val(stake: str = "1000") -> Validator:
    return Validator(
        address=ADDR, stake=Decimal(stake), reputation=1.0, role=ValidatorRole.VALIDATOR, last_proposed=0, is_active=True
    )


def _atts(key=ADDR_KEY, hashes=(HA, HB), height=H, rounds=(None, None)):
    return [
        _attestation_record(key, h, height=height, round_in_payload=r is not None, request_round=r)
        for h, r in zip(hashes, rounds, strict=True)
    ]


def _event(atts=None, hashes=(HA, HB), height=H):
    """A signed-evidence event built on a scratch manager (gate off)."""
    armed = settings.equivocation_verify_before_record
    settings.equivocation_verify_before_record = False
    try:
        return SlashingManager().record_attestation_equivocation(
            validator_address=ADDR,
            height=height,
            round_number=None,
            block_hash_a=hashes[0],
            block_hash_b=hashes[1],
            attestations=atts if atts is not None else _atts(hashes=hashes, height=height),
        )
    finally:
        settings.equivocation_verify_before_record = armed


@pytest.fixture(autouse=True)
def _arm(monkeypatch):
    metrics_registry.reset()
    monkeypatch.setattr(settings, "equivocation_verify_before_record", True)
    monkeypatch.setattr(settings, "slashing_max_events_per_height", 0)


def test_valid_signed_pair_is_levied():
    mgr, val = SlashingManager(), _val()
    assert mgr.apply_slashing(val, _event()) is True
    assert val.stake == Decimal("500")
    assert len(mgr.slashing_events) == 1


def test_wrong_signer_signature_refused():
    mgr, val = SlashingManager(), _val()
    forged = _atts()
    forged[1] = _attestation_record(OTHER_KEY, HB, height=H, round_in_payload=False, request_round=None)
    assert mgr.apply_slashing(val, _event(forged)) is False
    assert val.stake == Decimal("1000")
    assert mgr.slashing_events == []
    assert metrics_registry._counters["slashing_equivocation_gate_refused_total"] == 1


def test_tampered_signature_refused():
    mgr, val = SlashingManager(), _val()
    atts = copy.deepcopy(_atts())
    atts[0]["state_root"] = "0x" + "99" * 32  # signed message no longer matches
    assert mgr.apply_slashing(val, _event(atts)) is False
    assert mgr.slashing_events == []


def test_same_hash_pair_refused():
    mgr, val = SlashingManager(), _val()
    atts = _atts(hashes=(HA, HA))
    ev = _event(atts, hashes=(HA, HA))
    assert mgr.apply_slashing(val, ev) is False
    assert mgr.record_attestation_equivocation(ADDR, H, None, HA, HA, attestations=atts, accused_stake=Decimal(5)) is not None
    assert mgr.slashing_events == []


def test_mismatched_height_in_attestation_refused():
    mgr, val = SlashingManager(), _val()
    atts = _atts()
    atts[1] = _attestation_record(ADDR_KEY, HB, height=H + 1, round_in_payload=False, request_round=None)
    assert mgr.apply_slashing(val, _event(atts)) is False


def test_mismatched_round_refused():
    mgr, val = SlashingManager(), _val()
    atts = _atts(rounds=(1, 2))
    assert mgr.apply_slashing(val, _event(atts)) is False


def test_unsigned_claim_refused():
    mgr, val = SlashingManager(), _val()
    ev = mgr.detect_double_sign(ADDR, HA, HB, H)
    assert mgr.apply_slashing(val, ev) is False
    assert mgr.slashing_events == []


def test_zero_stake_accused_refused():
    mgr = SlashingManager()
    assert mgr.apply_slashing(_val("0"), _event()) is False
    assert mgr.slashing_events == []
    rec = mgr.record_attestation_equivocation(ADDR, H, None, HA, HB, attestations=_atts(), accused_stake=Decimal(0))
    assert mgr.slashing_events == [] and rec is not None


def test_already_levied_height_refuses_second_pair():
    mgr, val = SlashingManager(), _val()
    assert mgr.apply_slashing(val, _event()) is True
    hc, hd = "0x" + "cc" * 32, "0x" + "dd" * 32
    second = _event(_atts(hashes=(hc, hd)), hashes=(hc, hd))
    assert mgr.apply_slashing(val, second) is False
    assert val.stake == Decimal("500")
    assert len(mgr.slashing_events) == 1


def test_already_signed_advisory_height_refuses_second_pair():
    mgr = SlashingManager()
    mgr.record_attestation_equivocation(ADDR, H, None, HA, HB, attestations=_atts(), accused_stake=Decimal(5))
    hc, hd = "0x" + "cc" * 32, "0x" + "dd" * 32
    mgr.record_attestation_equivocation(ADDR, H, None, hc, hd, attestations=_atts(hashes=(hc, hd)), accused_stake=Decimal(5))
    assert len(mgr.slashing_events) == 1


def test_advisory_valid_pair_recorded_and_other_height_allowed():
    mgr = SlashingManager()
    mgr.record_attestation_equivocation(ADDR, H, None, HA, HB, attestations=_atts(), accused_stake=Decimal(5))
    mgr.record_attestation_equivocation(ADDR, H + 1, None, HA, HB, attestations=_atts(height=H + 1), accused_stake=Decimal(5))
    assert len(mgr.slashing_events) == 2


def test_non_equivocation_event_unaffected():
    mgr, val = SlashingManager(), _val()
    ev = mgr.detect_unavailability(ADDR, 5, 100)
    assert mgr.apply_slashing(val, ev) is True


def test_gate_off_is_legacy(monkeypatch):
    monkeypatch.setattr(settings, "equivocation_verify_before_record", False)
    mgr = SlashingManager()
    assert mgr.apply_slashing(_val("0"), mgr.detect_double_sign(ADDR, HA, HB, H)) is True
    assert len(mgr.slashing_events) == 1
    assert "slashing_equivocation_gate_refused_total" not in metrics_registry._counters


def test_derive_address_sanity():
    assert derive_ethereum_address(ADDR_KEY) == ADDR
