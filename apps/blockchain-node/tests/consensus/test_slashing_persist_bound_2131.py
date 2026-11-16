"""#2131 — bounded persisted slashing history (per-validator newest-N + count/digest).

Hub's 67 MB blob made every ``_persist_state`` rewrite stall the RPC worker. Armed
(``slashing_history_persist_max_per_validator``), the persisted history keeps the
newest N events per validator — levied events always, then signed evidence, then
advisory — and carries a deterministic pruned count + digest per validator.
Dormant at 0.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus.slashing import SlashingManager, bound_history_per_validator
from aitbc_chain.metrics import metrics_registry

V1 = "0x" + "11" * 20
V2 = "0x" + "22" * 20


def _ev(mgr: SlashingManager, i: int, addr: str = V1):
    ev = mgr.detect_double_sign(addr, f"0x{i:064x}", f"0x{i + 10**6:064x}", 100 + i)
    assert ev is not None
    return ev


def _fill(mgr: SlashingManager, n: int, addr: str = V1):
    events = [_ev(mgr, i, addr) for i in range(n)]
    mgr.slashing_events.extend(events)
    return events


@pytest.fixture(autouse=True)
def _reset():
    metrics_registry.reset()


def test_limit_zero_is_unchanged():
    mgr = SlashingManager()
    events = _fill(mgr, 20)
    kept, summary = bound_history_per_validator(mgr.slashing_events, 0)
    assert kept == events and summary == {}


def test_keeps_newest_n_per_validator_and_counts_rest():
    mgr = SlashingManager()
    events = _fill(mgr, 10) + _fill(mgr, 3, V2)
    kept, summary = bound_history_per_validator(mgr.slashing_events, 4)
    v1 = [e for e in kept if e.validator_address == V1]
    assert v1 == events[6:10]  # newest 4, order preserved
    assert len([e for e in kept if e.validator_address == V2]) == 3  # under the limit
    assert summary[V1]["count"] == 6 and len(summary[V1]["digest"]) == 64
    assert V2 not in summary


def test_levied_events_always_survive():
    mgr = SlashingManager()
    events = _fill(mgr, 6)
    for e in events[:2]:
        e.slashed_amount = Decimal("1")  # levied = on-record penalty
    kept, _ = bound_history_per_validator(mgr.slashing_events, 3)
    assert events[0] in kept and events[1] in kept
    assert len(kept) == 3


def test_digest_is_deterministic_and_chains():
    a, b = SlashingManager(), SlashingManager()
    _fill(a, 8)
    _fill(b, 8)
    _, sa = bound_history_per_validator(a.slashing_events, 3)
    _, sb = bound_history_per_validator(b.slashing_events, 3)
    assert sa == sb
    kept, _ = bound_history_per_validator(a.slashing_events, 3)
    kept2, again = bound_history_per_validator(kept, 3, sa)  # re-bounding the trimmed list drops nothing
    assert kept2 == kept and again == sa


def test_manager_bound_for_persist_trims_memory(monkeypatch):
    monkeypatch.setattr(settings, "slashing_history_persist_max_per_validator", 5)
    mgr = SlashingManager()
    _fill(mgr, 12)
    mgr.bound_for_persist()
    assert len(mgr.slashing_events) == 5
    assert mgr.pruned_summary[V1]["count"] == 7
    assert metrics_registry._counters["slashing_events_persist_pruned_total"] == 1


def test_manager_dormant_when_zero(monkeypatch):
    monkeypatch.setattr(settings, "slashing_history_persist_max_per_validator", 0)
    mgr = SlashingManager()
    _fill(mgr, 12)
    mgr.bound_for_persist()
    assert len(mgr.slashing_events) == 12 and mgr.pruned_summary == {}


def test_summary_round_trips_through_persisted_json():
    from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA
    from aitbc_chain.consensus.slashing import slashing_event_record

    mgr = SlashingManager()
    _fill(mgr, 6)
    kept, summary = bound_history_per_validator(mgr.slashing_events, 2)
    blob = json.loads(json.dumps([slashing_event_record(e) for e in kept] + [{"_pruned_summary": summary}]))
    records, back = MultiValidatorPoA._split_pruned_summary(blob)
    assert back == summary and len(records) == 2
    assert len(MultiValidatorPoA._parse_slashing_events(records)) == 2


def test_legacy_blob_without_summary_loads_empty():
    from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA

    records, summary = MultiValidatorPoA._split_pruned_summary([{"validator_address": V1}])
    assert summary == {} and len(records) == 1
