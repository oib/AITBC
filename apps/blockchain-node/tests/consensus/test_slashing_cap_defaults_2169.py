"""#2169 — the slashing-history caps are bounded by default.

#2118 / #2131 shipped the per-height cap and the persisted per-validator bound
dormant (0). Hub grew a 67 MB history before they were armed by hand. The
defaults are now 8 events per (validator, condition, height) and 1000 persisted
events per validator; 0 stays the explicit legacy opt-out.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from aitbc_chain.config import ChainSettings, settings
from aitbc_chain.consensus.multi_validator_poa import Validator, ValidatorRole
from aitbc_chain.consensus.slashing import SlashingManager
from aitbc_chain.metrics import metrics_registry

V1 = "0x" + "11" * 20


@pytest.fixture(autouse=True)
def _reset():
    metrics_registry.reset()
    yield
    metrics_registry.reset()


def _val() -> Validator:
    return Validator(
        address=V1, stake=Decimal("1000"), reputation=1.0, role=ValidatorRole.VALIDATOR, last_proposed=0, is_active=True
    )


def _flood(mgr: SlashingManager, n: int, height: int = 100) -> None:
    v = _val()
    for i in range(n):
        ev = mgr.detect_double_sign(V1, f"0x{i:064x}", f"0x{i + 10**6:064x}", height)
        if ev is not None:
            mgr.apply_slashing(v, ev)


def test_shipped_defaults_are_bounded():
    assert ChainSettings.model_fields["slashing_max_events_per_height"].default == 8
    assert ChainSettings.model_fields["slashing_history_persist_max_per_validator"].default == 1000


def test_default_manager_caps_events_per_height():
    assert settings.slashing_max_events_per_height == 8
    mgr = SlashingManager()
    _flood(mgr, 50)
    assert len(mgr.slashing_events) == 8


def test_zero_is_the_unbounded_opt_out(monkeypatch):
    monkeypatch.setattr(settings, "slashing_max_events_per_height", 0)
    mgr = SlashingManager()
    _flood(mgr, 50)
    assert len(mgr.slashing_events) == 50


def _unlevied(mgr: SlashingManager, n: int) -> None:
    for h in range(n):
        ev = mgr.detect_double_sign(V1, f"0x{h:064x}", f"0x{h + 10**6:064x}", h)
        assert ev is not None
        mgr.slashing_events.append(ev)


def test_default_persist_bound_trims_a_long_history(monkeypatch):
    monkeypatch.setattr(settings, "slashing_max_events_per_height", 0)
    mgr = SlashingManager()
    _unlevied(mgr, 1200)
    mgr.bound_for_persist()
    assert len(mgr.slashing_events) == 1000
    assert mgr.pruned_summary[V1]["count"] == 200


def test_persist_bound_zero_keeps_everything(monkeypatch):
    monkeypatch.setattr(settings, "slashing_max_events_per_height", 0)
    monkeypatch.setattr(settings, "slashing_history_persist_max_per_validator", 0)
    mgr = SlashingManager()
    _unlevied(mgr, 1200)
    mgr.bound_for_persist()
    assert len(mgr.slashing_events) == 1200 and mgr.pruned_summary == {}
