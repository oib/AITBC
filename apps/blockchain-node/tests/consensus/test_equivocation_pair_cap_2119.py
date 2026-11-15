"""#2119 — attestation-equivocation pairing is linear when armed.

Each newly signed hash used to be paired with EVERY prior signed hash at the
height: n hashes -> n(n-1)/2 recorded events (hub, h27301: 602 hashes, 30,245
signature-bearing events, a 67 MB history). One signed pair already proves the
equivocation. ``equivocation_max_pairs_per_signature`` (default 0 = legacy)
limits the priors a new hash pairs with; the lowest-sorted are kept, which is
deterministic.
"""

from __future__ import annotations

from aitbc_chain.config import settings
from aitbc_chain.consensus import remote_attestation_evidence  # noqa: F401
from aitbc_chain.consensus.slashing import event_signature_evidence

from .test_proposer_equivocation_1278 import H, OTHER, _seed_prior_attestation, _setup
from .test_vote_journal_1268 import _counter, _env  # noqa: F401


def _hash(i: int) -> str:
    return "0x" + f"{i:064x}"


def _sign_and_record(svc, mgr, addr, key, block_hash):
    """A validator signing one more hash at the height, then the real recorder."""
    _seed_prior_attestation(svc, addr, key, block_hash, round_bound_round=None)
    svc._record_attestation_equivocation_evidence(H, block_hash, addr, OTHER, None)


def _run(monkeypatch, n_hashes: int, cap: int):
    monkeypatch.setattr(settings, "equivocation_max_pairs_per_signature", cap)
    svc, mgr, addr, key, _other, _clock = _setup(monkeypatch)
    for i in range(1, n_hashes + 1):
        _sign_and_record(svc, mgr, addr, key, _hash(i))
    return mgr


def test_legacy_default_is_quadratic(monkeypatch):
    mgr = _run(monkeypatch, 6, 0)
    assert len(mgr.slashing_events) == 6 * 5 // 2
    assert _counter("equivocation_pairs_trimmed_total") == 0


def test_cap_one_is_linear_and_counts_trims(monkeypatch):
    mgr = _run(monkeypatch, 6, 1)
    assert len(mgr.slashing_events) == 5  # one pair per hash after the first
    assert _counter("equivocation_pairs_trimmed_total") == 10  # priors 1..5 per new hash, one kept each: 0+1+2+3+4 trimmed


def test_capped_pairs_keep_lowest_sorted_prior_and_stay_signature_bearing(monkeypatch):
    mgr = _run(monkeypatch, 5, 1)
    for event in mgr.slashing_events:
        assert event.hash_a == _hash(1)  # always paired with the lowest prior
        assert event_signature_evidence(event) is not None  # still gate-verifiable


def test_cap_larger_than_priors_changes_nothing(monkeypatch):
    mgr = _run(monkeypatch, 4, 50)
    assert len(mgr.slashing_events) == 4 * 3 // 2
    assert _counter("equivocation_pairs_trimmed_total") == 0


def test_growth_is_linear_at_scale(monkeypatch):
    mgr = _run(monkeypatch, 40, 2)
    assert len(mgr.slashing_events) <= 2 * 40  # the legacy count at 40 hashes would be 780
