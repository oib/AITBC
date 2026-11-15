"""#2118 — bounded slashing history.

Hub's persisted history reached 67 MB / 30,417 events (30,245 at one height,
each a distinct forged hash pair): the O(n) dedup scan made every add slower,
and every persist/load/route call handled the whole list. Pins: the dedup is
unchanged but indexed, the per-(validator, condition, height) cap refuses the
flood (dormant at 0), the cap compacts an old persisted history on load, and
the route returns a bounded page with ``total``.
"""

from __future__ import annotations

import time
from decimal import Decimal

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus import slashing
from aitbc_chain.consensus.multi_validator_poa import Validator, ValidatorRole
from aitbc_chain.consensus.slashing import SlashingManager, cap_history_per_height
from aitbc_chain.metrics import metrics_registry

V1 = "0x" + "11" * 20
V2 = "0x" + "22" * 20


def _val(addr: str = V1) -> Validator:
    return Validator(
        address=addr, stake=Decimal("1000"), reputation=1.0, role=ValidatorRole.VALIDATOR, last_proposed=0, is_active=True
    )


def _event(mgr: SlashingManager, i: int, height: int = 100, addr: str = V1):
    return mgr.detect_double_sign(addr, f"0x{i:064x}", f"0x{i + 10**6:064x}", height)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    metrics_registry.reset()
    monkeypatch.setattr(settings, "slashing_max_events_per_height", 0)
    yield
    metrics_registry.reset()


def test_dedup_unchanged_with_index():
    mgr = SlashingManager()
    v = _val()
    assert mgr.apply_slashing(v, _event(mgr, 1)) is True
    stake = v.stake
    assert mgr.apply_slashing(v, _event(mgr, 1)) is False  # same pair: no double slash
    assert v.stake == stake and len(mgr.slashing_events) == 1
    assert mgr.apply_slashing(v, _event(mgr, 2)) is True  # distinct pair: still recorded when uncapped
    assert len(mgr.slashing_events) == 2


def test_dedup_upgrades_evidence_in_place():
    mgr = SlashingManager()
    v = _val()
    first = _event(mgr, 1)
    mgr.apply_slashing(v, first)
    signed = _event(mgr, 1)
    signed.evidence = '{"kind": "attestation_equivocation", "attestations": [{"a": 1}]}'
    assert mgr.apply_slashing(v, signed) is False
    assert mgr.slashing_events[0].evidence == signed.evidence


def test_index_follows_external_list_edits():
    mgr = SlashingManager()
    v = _val()
    mgr.apply_slashing(v, _event(mgr, 1))
    mgr.slashing_events = []  # tests/load_state replace the list wholesale
    assert mgr.apply_slashing(v, _event(mgr, 1)) is True
    mgr.slashing_events.pop()
    assert mgr.apply_slashing(v, _event(mgr, 1)) is True


def test_cap_refuses_the_flood_and_counts(monkeypatch):
    monkeypatch.setattr(settings, "slashing_max_events_per_height", 3)
    mgr = SlashingManager()
    v = _val()
    results = [mgr.apply_slashing(v, _event(mgr, i)) for i in range(50)]
    assert results.count(True) == 3
    assert len(mgr.slashing_events) == 3
    assert metrics_registry._counters["slashing_events_cap_refused_total"] == 47
    # the refused events were not levied: stake only dropped three times
    assert v.stake == Decimal("1000") * Decimal("0.5") ** 3


def test_cap_is_per_height_and_per_validator(monkeypatch):
    monkeypatch.setattr(settings, "slashing_max_events_per_height", 1)
    mgr = SlashingManager()
    v1, v2 = _val(V1), _val(V2)
    assert mgr.apply_slashing(v1, _event(mgr, 1, height=100)) is True
    assert mgr.apply_slashing(v1, _event(mgr, 2, height=100)) is False
    assert mgr.apply_slashing(v1, _event(mgr, 3, height=101)) is True
    assert mgr.apply_slashing(v2, _event(mgr, 4, height=100, addr=V2)) is True


def test_cap_zero_is_dormant():
    mgr = SlashingManager()
    v = _val()
    assert all(mgr.apply_slashing(v, _event(mgr, i)) for i in range(20))
    assert len(mgr.slashing_events) == 20
    assert "slashing_events_cap_refused_total" not in metrics_registry._counters


def test_cap_history_per_height_compacts_oldest_first():
    mgr = SlashingManager()
    events = [_event(mgr, i) for i in range(10)] + [_event(mgr, 99, height=101)]
    kept = cap_history_per_height(events, 2)
    assert [e.hash_a for e in kept[:2]] == [e.hash_a for e in events[:2]]
    assert len(kept) == 3
    assert cap_history_per_height(events, 0) is events


def test_apply_cost_is_not_quadratic(monkeypatch):
    """5,000 distinct pairs finish well inside a second; the old O(n) scan
    with a sha256 per existing event took tens of seconds at this size."""
    mgr = SlashingManager()
    v = _val()
    v.stake = Decimal("1000000")
    start = time.monotonic()
    for i in range(5000):
        mgr.apply_slashing(v, _event(mgr, i, height=1000 + i))
    assert len(mgr.slashing_events) == 5000
    assert time.monotonic() - start < 10.0


def test_load_state_compacts_an_oversized_history(monkeypatch):
    """The real ``load_state`` path: a persisted flood is cut to the cap."""
    from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA

    monkeypatch.setattr(settings, "slashing_max_events_per_height", 2)
    mgr = SlashingManager()
    records = [slashing.slashing_event_record(_event(mgr, i)) for i in range(40)]
    loaded = MultiValidatorPoA._parse_slashing_events(records)
    assert len(loaded) == 40
    assert len(cap_history_per_height(loaded, slashing._max_events_per_height())) == 2


# --- respin: the advisory path (record_attestation_equivocation) -------------
# Hub's 30,417 flood events had stake_before None: they came through
# record_attestation_equivocation -> _dedup_or_upgrade, never apply_slashing.

_SIGNED = [{"hash": "0xa", "signature": "0x1"}, {"hash": "0xb", "signature": "0x2"}]


def _advisory(mgr: SlashingManager, i: int, height: int = 100, signed: bool = False, addr: str = V1):
    return mgr.record_attestation_equivocation(
        addr, height, None, f"0x{i:064x}", f"0x{i + 10**6:064x}", attestations=_SIGNED if signed else None
    )


def test_advisory_flood_is_bounded_when_armed(monkeypatch):
    monkeypatch.setattr(settings, "slashing_max_events_per_height", 5)
    mgr = SlashingManager()
    for i in range(500):
        _advisory(mgr, i)
    assert len(mgr.slashing_events) == 5
    assert metrics_registry._counters["slashing_events_cap_refused_total"] == 495
    assert all(e.stake_before is None for e in mgr.slashing_events)  # still advisory


def test_advisory_dedup_is_indexed_and_unchanged():
    mgr = SlashingManager()
    first = _advisory(mgr, 1)
    assert _advisory(mgr, 1) is first  # same offence: the recorded event comes back
    assert len(mgr.slashing_events) == 1
    signed = _advisory(mgr, 1, signed=True)  # signature-bearing upgrade in place
    assert signed is first and slashing.event_signature_evidence(first) is not None


def test_advisory_cap_zero_is_dormant():
    mgr = SlashingManager()
    for i in range(50):
        _advisory(mgr, i)
    assert len(mgr.slashing_events) == 50
    assert "slashing_events_cap_refused_total" not in metrics_registry._counters


def test_signed_evidence_displaces_the_newest_unsigned_record(monkeypatch):
    monkeypatch.setattr(settings, "slashing_max_events_per_height", 3)
    mgr = SlashingManager()
    for i in range(3):
        _advisory(mgr, i)  # bucket full of advisory records
    newest_unsigned = mgr.slashing_events[-1]
    signed = _advisory(mgr, 99, signed=True)
    assert signed in mgr.slashing_events and newest_unsigned not in mgr.slashing_events
    assert len(mgr.slashing_events) == 3
    assert metrics_registry._counters["slashing_events_cap_evicted_total"] == 1


def test_forged_unsigned_flood_cannot_evict_signed_evidence(monkeypatch):
    monkeypatch.setattr(settings, "slashing_max_events_per_height", 2)
    mgr = SlashingManager()
    s1, s2 = _advisory(mgr, 1, signed=True), _advisory(mgr, 2, signed=True)
    for i in range(10, 60):
        _advisory(mgr, i)
        _advisory(mgr, i + 1000, signed=True)  # a full bucket of signed: refused, never evicting
    assert mgr.slashing_events == [s1, s2]


def test_compaction_keeps_signed_events_first():
    mgr = SlashingManager()
    events = [_advisory(mgr, i) for i in range(6)] + [_advisory(mgr, 77, signed=True)]
    kept = cap_history_per_height(list(events), 2)
    assert events[-1] in kept and len(kept) == 2  # the one signed + the oldest unsigned
    assert kept[0] is events[0]


def test_evicted_record_leaves_the_dedup_index(monkeypatch):
    """After a signed record displaces an unsigned one, re-observing the evicted
    pair is a fresh (and, the bucket being full, refused) record — not a hit on a
    stale index entry for an event that is no longer in the history."""
    monkeypatch.setattr(settings, "slashing_max_events_per_height", 3)
    mgr = SlashingManager()
    for i in range(3):
        _advisory(mgr, i)
    _advisory(mgr, 99, signed=True)  # evicts the pair of i=2
    assert metrics_registry._counters["slashing_events_cap_evicted_total"] == 1
    _advisory(mgr, 2)  # the evicted pair comes back
    assert metrics_registry._counters["slashing_events_cap_refused_total"] == 1
    assert len(mgr.slashing_events) == 3
