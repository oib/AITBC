"""#2124/#2125/#2127 — slashing-cap hardening on top of #2118.

#2124 (+#2127 item 1): ``apply_slashing`` at the per-height cap refused a signed
equivocation while forged unsigned records kept their slots, so a flood could
suppress a later signed slash; it now displaces an unsigned advisory record, the
same rule as the advisory path. #2127 item 2: a levied event (``stake_before`` /
``slashed_amount`` set) is the record of a deducted penalty and is never evicted
or compacted away. #2125: eviction removes the victim by identity, not by
dataclass equality. All dormant at ``slashing_max_events_per_height = 0``.
"""

from __future__ import annotations

import copy
from decimal import Decimal

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus import slashing
from aitbc_chain.consensus.slashing import SlashingManager, _remove_by_identity, cap_history_per_height
from aitbc_chain.metrics import metrics_registry

from .test_slashing_history_cap_2118 import V1, _advisory, _event, _val

_SIG = '{"kind": "attestation_equivocation", "attestations": [{"a": 1}]}'


def _signed_event(mgr: SlashingManager, i: int, height: int = 100):
    event = _event(mgr, i, height)
    event.evidence = _SIG
    return event


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    metrics_registry.reset()
    monkeypatch.setattr(settings, "slashing_max_events_per_height", 0)
    yield
    metrics_registry.reset()


def _counter(name: str) -> float:
    return metrics_registry._counters.get(name, 0.0)


class TestSignedPriorityInApplySlashing:
    def test_signed_slash_displaces_unsigned_flood_and_levies(self, monkeypatch):
        """The Validator's reproduction: bucket full of unsigned advisories, then a
        signed equivocation through the levying path."""
        monkeypatch.setattr(settings, "slashing_max_events_per_height", 3)
        mgr = SlashingManager()
        for i in range(3):
            _advisory(mgr, i)  # unsigned, stake_before None
        v = _val()
        signed = _signed_event(mgr, 99)
        assert mgr.apply_slashing(v, signed) is True
        assert v.stake == Decimal("500")  # levied
        assert signed in mgr.slashing_events and len(mgr.slashing_events) == 3
        assert _counter("slashing_events_cap_evicted_total") == 1
        assert _counter("slashing_events_cap_refused_total") == 0

    def test_unsigned_slash_at_the_cap_is_still_refused(self, monkeypatch):
        monkeypatch.setattr(settings, "slashing_max_events_per_height", 2)
        mgr = SlashingManager()
        for i in range(2):
            _advisory(mgr, i)
        v = _val()
        assert mgr.apply_slashing(v, _event(mgr, 99)) is False
        assert v.stake == Decimal("1000")
        assert _counter("slashing_events_cap_refused_total") == 1

    def test_signed_slash_refused_when_the_bucket_holds_only_signed_or_levied(self, monkeypatch):
        monkeypatch.setattr(settings, "slashing_max_events_per_height", 1)
        mgr = SlashingManager()
        v = _val()
        assert mgr.apply_slashing(v, _signed_event(mgr, 1)) is True
        assert mgr.apply_slashing(v, _signed_event(mgr, 2)) is False
        assert len(mgr.slashing_events) == 1

    def test_dormant_cap_zero_changes_nothing(self):
        mgr = SlashingManager()
        for i in range(5):
            _advisory(mgr, i)
        assert mgr.apply_slashing(_val(), _signed_event(mgr, 99)) is True
        assert len(mgr.slashing_events) == 6
        assert _counter("slashing_events_cap_evicted_total") == 0


class TestLeviedEventsArePinned:
    def test_levied_unsigned_event_is_not_an_eviction_victim(self, monkeypatch):
        """Cap 2: one unsigned event already levied, one advisory. A signed event
        must displace the advisory, never the levied record."""
        monkeypatch.setattr(settings, "slashing_max_events_per_height", 2)
        mgr = SlashingManager()
        v = _val()
        levied = _event(mgr, 1)
        assert mgr.apply_slashing(v, levied) is True and levied.is_applied
        advisory = _advisory(mgr, 2)
        assert mgr.apply_slashing(v, _signed_event(mgr, 99)) is True
        assert levied in mgr.slashing_events and advisory not in mgr.slashing_events
        assert mgr.calculate_total_slashed(V1) > 0

    def test_only_levied_records_left_means_refusal_not_eviction(self, monkeypatch):
        monkeypatch.setattr(settings, "slashing_max_events_per_height", 1)
        mgr = SlashingManager()
        v = _val()
        levied = _event(mgr, 1)
        mgr.apply_slashing(v, levied)
        stake = v.stake
        assert mgr.apply_slashing(v, _signed_event(mgr, 99)) is False
        assert mgr.slashing_events == [levied] and v.stake == stake

    def test_compaction_keeps_levied_before_signed_before_unsigned(self):
        mgr = SlashingManager()
        v = _val()
        unsigned = [_advisory(mgr, i) for i in range(4)]
        signed = _advisory(mgr, 50, signed=True)
        levied = _event(mgr, 60)
        mgr.apply_slashing(v, levied)
        events = unsigned[:2] + [signed] + unsigned[2:] + [levied]
        kept = cap_history_per_height(events, 2)
        assert levied in kept and signed in kept and len(kept) == 2

    def test_newest_unsigned_helper_skips_levied(self):
        mgr = SlashingManager()
        v = _val()
        advisory = _advisory(mgr, 1)
        levied = _event(mgr, 2)
        mgr.apply_slashing(v, levied)  # newest in the bucket, unsigned, levied
        index = mgr._history_index()
        assert index.newest_unsigned_at(levied) is advisory


class TestIdentityRemoval:
    def test_remove_by_identity_removes_the_victim_not_an_equal_sibling(self):
        mgr = SlashingManager()
        a = _event(mgr, 1)
        b = copy.copy(a)  # field-equal twin of a (same pair, same height, same timestamp)
        assert a == b and a is not b
        events = [a, b]
        assert _remove_by_identity(events, b) is True
        assert len(events) == 1 and events[0] is a

    def test_remove_by_identity_missing_is_false(self):
        mgr = SlashingManager()
        assert _remove_by_identity([_event(mgr, 1)], _event(mgr, 2)) is False

    def test_eviction_keeps_list_and_index_consistent_with_equal_siblings(self, monkeypatch):
        """Two field-equal advisory records (one appended outside dedup, as a
        persisted history or a test can); evicting the newest must leave the
        OLDER object in the list and the index agreeing with the list."""
        monkeypatch.setattr(settings, "slashing_max_events_per_height", 2)
        mgr = SlashingManager()
        first = _advisory(mgr, 1)
        twin = copy.copy(first)  # equal to `first`, a distinct object
        assert twin == first
        mgr.slashing_events.append(twin)  # bypasses dedup, like a loaded history
        newest = mgr._history_index().newest_unsigned_at(twin)
        assert newest is twin
        signed = _advisory(mgr, 99, signed=True)
        ids = [id(e) for e in mgr.slashing_events]
        assert id(first) in ids and id(signed) in ids and id(twin) not in ids
        index = mgr._history_index()
        assert sorted(id(e) for e in index.by_height[slashing._height_key(first)]) == sorted(
            id(e) for e in mgr.slashing_events
        )
