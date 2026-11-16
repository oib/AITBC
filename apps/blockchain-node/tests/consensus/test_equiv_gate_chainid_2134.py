"""#2134 pins: the #2130 equivocation record gate forwards ``chain_id``.

#2102 binds ``chain_id`` into PBFT vote signature preimages; the gate's
``equivocation_evidence_verifies`` previously called the evidence verifier
without it, so once #2102 signatures exist a chain-bound vote-equivocation
pair would fail the armed record gate on its own chain (fail-closed slash
efficacy loss). ``SlashingManager`` now carries the apply chain id and the
module helper forwards it; legacy-signed pairs still verify via fallback.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, Validator, ValidatorRole
from aitbc_chain.consensus.slashing import SlashingManager
from aitbc_chain.metrics import metrics_registry

from .test_pbft_chainid_2102 import ADDR, BH, BH2, CHAIN_A, CHAIN_B, KEY, VIEW, _commit


def _val() -> Validator:
    return Validator(
        address=ADDR, stake=Decimal("1000"), reputation=1.0, role=ValidatorRole.VALIDATOR, last_proposed=0, is_active=True
    )


def _vote_event(mgr: SlashingManager, chain_id: str | None) -> object:
    msg_a = _commit(ADDR, KEY, chain_id=chain_id, block_hash=BH)
    msg_b = _commit(ADDR, KEY, chain_id=chain_id, block_hash=BH2)
    return mgr.vote_equivocation_event(ADDR, VIEW, "commit", msg_a, msg_b)


@pytest.fixture(autouse=True)
def _arm(monkeypatch):
    metrics_registry.reset()
    monkeypatch.setattr(settings, "equivocation_verify_before_record", True)
    monkeypatch.setattr(settings, "slashing_max_events_per_height", 0)


def test_chain_bound_vote_pair_levied_on_own_chain():
    mgr = SlashingManager(chain_id=CHAIN_A)
    assert mgr.apply_slashing(_val(), _vote_event(mgr, CHAIN_A)) is True
    assert len(mgr.slashing_events) == 1


def test_chain_bound_vote_pair_refused_on_foreign_chain():
    mgr = SlashingManager(chain_id=CHAIN_B)
    assert mgr.apply_slashing(_val(), _vote_event(mgr, CHAIN_A)) is False
    assert mgr.slashing_events == []
    assert metrics_registry._counters["slashing_equivocation_gate_refused_total"] == 1


def test_legacy_signed_vote_pair_still_verifies():
    mgr = SlashingManager(chain_id=CHAIN_A)
    assert mgr.apply_slashing(_val(), _vote_event(mgr, None)) is True
    assert len(mgr.slashing_events) == 1


def test_poa_manager_carries_chain_id():
    assert MultiValidatorPoA(CHAIN_A)._slashing_manager._chain_id == CHAIN_A


def _legacy_record(mgr: SlashingManager, monkeypatch) -> None:
    monkeypatch.setattr(settings, "equivocation_verify_before_record", False)
    assert mgr.apply_slashing(_val(), mgr.detect_double_sign(ADDR, BH, BH2, VIEW)) is True
    monkeypatch.setattr(settings, "equivocation_verify_before_record", True)


def test_graft_of_chain_bound_evidence_gated_by_chain(monkeypatch):
    """The _upgrade_evidence graft path forwards chain_id too (#2130 follow-up)."""
    bound = SlashingManager(chain_id=CHAIN_B)
    _legacy_record(bound, monkeypatch)
    bound.apply_slashing(_val(), _vote_event(bound, CHAIN_A))  # CHAIN_A-bound evidence judged on CHAIN_B
    assert bound.slashing_events[0].evidence.startswith("Double sign detected")  # graft refused
    own = SlashingManager(chain_id=CHAIN_A)
    _legacy_record(own, monkeypatch)
    own.apply_slashing(_val(), _vote_event(own, CHAIN_A))
    assert json.loads(own.slashing_events[0].evidence).get("kind") == "vote_equivocation"
