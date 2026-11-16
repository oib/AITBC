"""#2119 — attestation-equivocation pairing is linear when armed.

Each newly signed hash used to be paired with EVERY prior signed hash at the
height: n hashes -> n(n-1)/2 recorded events (hub, h27301: 602 hashes, 30,245
signature-bearing events, a 67 MB history). One signed pair already proves the
equivocation. ``equivocation_max_pairs_per_signature`` (default 0 = legacy)
limits the priors a new hash pairs with; when the cap trims, #2126 prefers
priors that still carry a signature record under the same domain (kept pairs
stay gate-verifiable) over lower-sorted hash-only priors.
"""

from __future__ import annotations

from aitbc.crypto.consensus_signing import DOMAIN_BLOCK_ATTESTATION, sign_consensus_message
from aitbc_chain.config import settings
from aitbc_chain.consensus import remote_attestation_evidence  # noqa: F401
from aitbc_chain.consensus.slashing import event_signature_evidence

from .test_proposer_equivocation_1278 import H, OTHER, _header, _seed_prior_attestation, _setup
from .test_vote_journal_1268 import _counter, _env  # noqa: F401


def _hash(i: int) -> str:
    return "0x" + f"{i:064x}"


def _sign_and_record(svc, mgr, addr, key, block_hash):
    """A validator signing one more hash at the height, then the real recorder."""
    _seed_prior_attestation(svc, addr, key, block_hash, round_bound_round=None)
    svc._record_attestation_equivocation_evidence(H, block_hash, addr, OTHER, None)


def _run(monkeypatch, n_hashes: int, cap: int):
    monkeypatch.setattr(settings, "equivocation_max_pairs_per_signature", cap)
    # #2169: this module tests the pair cap, not the per-height cap (bounded by default now).
    monkeypatch.setattr(settings, "slashing_max_events_per_height", 0)
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


# --- #2126: armed cap must prefer signature-bearing priors -----------------


def _hash_only_prior(svc, block_hash):
    """A prior the signer voted for whose signature record was never retained."""
    svc._signed_once_add(H, block_hash, None)


def _domain_signed(svc, addr, key, block_hash, domain):
    """A prior signed under ``domain`` — retained record + domain-keyed gate."""
    message = _header(block_hash, OTHER)
    signature = sign_consensus_message(message, key)
    svc._record_signed_attestation(H, block_hash, addr, message, None, False, signature, domain)
    svc._signed_once_add(H, block_hash, domain)


def _mixed_prior_run(monkeypatch, cap: int, seed_order=(1, 2, 3, 8, 9)):
    """Priors 1-3 hash-only (sort low), 8-9 signature-bearing (sort high); new hash 10."""
    monkeypatch.setattr(settings, "equivocation_max_pairs_per_signature", cap)
    svc, mgr, addr, key, _other, _clock = _setup(monkeypatch)
    for i in seed_order:
        if i <= 3:
            _hash_only_prior(svc, _hash(i))
        else:
            _seed_prior_attestation(svc, addr, key, _hash(i), round_bound_round=None)
    _seed_prior_attestation(svc, addr, key, _hash(10), round_bound_round=None)
    svc._record_attestation_equivocation_evidence(H, _hash(10), addr, OTHER, None)
    return mgr


def test_armed_cap_prefers_signature_bearing_over_lower_sorted_hash_only(monkeypatch):
    """#2126 regression: the lowest-sorted priors are hash-only, but a
    higher-sorted prior carries signatures — the kept pair must be the
    gate-verifiable one, not the advisory hash-only pair."""
    mgr = _mixed_prior_run(monkeypatch, cap=1)
    assert len(mgr.slashing_events) == 1
    event = mgr.slashing_events[0]
    assert {event.hash_a, event.hash_b} == {_hash(8), _hash(10)}
    assert event_signature_evidence(event) is not None  # gate-verifiable, not advisory


def test_armed_cap_keeps_every_signature_bearing_prior_before_hash_only(monkeypatch):
    """Cap 2 with 2 signed + 3 hash-only priors keeps BOTH signed priors."""
    mgr = _mixed_prior_run(monkeypatch, cap=2)
    assert len(mgr.slashing_events) == 2
    kept = {frozenset((e.hash_a, e.hash_b)) for e in mgr.slashing_events}
    assert kept == {frozenset((_hash(8), _hash(10))), frozenset((_hash(9), _hash(10)))}
    for event in mgr.slashing_events:
        assert event_signature_evidence(event) is not None


def test_armed_cap_selection_is_deterministic_across_seed_order(monkeypatch):
    """Same prior set seeded in a different order keeps the same pair."""
    first = _mixed_prior_run(monkeypatch, cap=1, seed_order=(1, 2, 3, 8, 9))
    second = _mixed_prior_run(monkeypatch, cap=1, seed_order=(9, 8, 3, 2, 1))

    def pairs(mgr):
        return sorted((e.hash_a, e.hash_b) for e in mgr.slashing_events)

    assert pairs(first) == pairs(second) == [(_hash(8), _hash(10))]


def test_cap_zero_still_pairs_every_prior_including_hash_only(monkeypatch):
    """cap=0 (legacy dormant default): all 5 priors pair; hash-only stay advisory."""
    mgr = _mixed_prior_run(monkeypatch, cap=0)
    assert len(mgr.slashing_events) == 5
    assert sum(1 for e in mgr.slashing_events if event_signature_evidence(e) is not None) == 2
    assert _counter("equivocation_pairs_trimmed_total") == 0


def test_armed_cap_signature_preference_is_domain_scoped(monkeypatch):
    """A prior signed only under ANOTHER domain is hash-only for this pairing —
    the preference lookup must use the same domain-scoped key as the pair loop."""
    monkeypatch.setattr(settings, "equivocation_max_pairs_per_signature", 1)
    svc, mgr, addr, key, _other, _clock = _setup(monkeypatch)
    # Low-sorted prior signed under the LEGACY (None) domain only.
    _seed_prior_attestation(svc, addr, key, _hash(1), round_bound_round=None)
    # High-sorted prior + the new signature, both under DOMAIN_BLOCK_ATTESTATION.
    _domain_signed(svc, addr, key, _hash(9), DOMAIN_BLOCK_ATTESTATION)
    _domain_signed(svc, addr, key, _hash(10), DOMAIN_BLOCK_ATTESTATION)
    svc._record_attestation_equivocation_evidence(H, _hash(10), addr, OTHER, None, signature_domain=DOMAIN_BLOCK_ATTESTATION)
    assert len(mgr.slashing_events) == 1
    event = mgr.slashing_events[0]
    assert {event.hash_a, event.hash_b} == {_hash(9), _hash(10)}
    assert event_signature_evidence(event) is not None
