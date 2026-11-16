"""#2135 — residuals of the #2130 equivocation verify gate.

R2: the module-global ``SlashingManager`` fallback recorder had no stake source,
so the armed gate's zero-stake refusal was skipped there. R3: the gate passed a
hard-coded cross-view height of 0 (always armed) while apply-time reads the real
parameter — now the local ``pbft_cross_view_commit_lock_height`` mirror, fail
closed when unset.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus import slashing as slashing_mod
from aitbc_chain.consensus.remote_attestation_evidence import _EvidenceMixin
from aitbc_chain.consensus.slashing import SlashingManager
from aitbc_chain.metrics import metrics_registry

from .test_deactivation_evidence_1263 import ADDR, ADDR_KEY, HA, HB, _attestation_record

H = 11


@pytest.fixture(autouse=True)
def _arm(monkeypatch):
    metrics_registry.reset()
    monkeypatch.setattr(settings, "equivocation_verify_before_record", True)
    monkeypatch.setattr(settings, "slashing_max_events_per_height", 0)


def _evidence_host(chain_id: str = "c2135") -> _EvidenceMixin:
    host = _EvidenceMixin.__new__(_EvidenceMixin)
    host._chain_id = chain_id
    return host


def _atts():
    return [_attestation_record(ADDR_KEY, h, height=H, round_in_payload=False, request_round=None) for h in (HA, HB)]


def _record(mgr: SlashingManager, **extra):
    return mgr.record_attestation_equivocation(
        validator_address=ADDR,
        height=H,
        round_number=None,
        block_hash_a=HA,
        block_hash_b=HB,
        attestations=_atts(),
        **extra,
    )


class TestR2FallbackRecorderStake:
    def test_stake_resolved_from_chain_consensus(self, monkeypatch):
        fake = SimpleNamespace(_accused_stake=lambda v: Decimal("0"))
        monkeypatch.setattr("aitbc_chain.consensus.multi_validator_poa.get_consensus", lambda cid: fake)
        kw = _evidence_host()._recorder_stake_kwargs(SlashingManager(), ADDR)
        assert kw == {"accused_stake": Decimal("0")}

    def test_zero_stake_accused_is_refused_on_the_fallback_path(self, monkeypatch):
        fake = SimpleNamespace(_accused_stake=lambda v: Decimal("0"))
        monkeypatch.setattr("aitbc_chain.consensus.multi_validator_poa.get_consensus", lambda cid: fake)
        mgr = SlashingManager()
        _record(mgr, **_evidence_host()._recorder_stake_kwargs(mgr, ADDR))
        assert mgr.slashing_events == []
        assert metrics_registry._counters["slashing_equivocation_gate_refused_total"] == 1

    def test_staked_accused_is_still_recorded(self, monkeypatch):
        fake = SimpleNamespace(_accused_stake=lambda v: Decimal("1000"))
        monkeypatch.setattr("aitbc_chain.consensus.multi_validator_poa.get_consensus", lambda cid: fake)
        mgr = SlashingManager()
        _record(mgr, **_evidence_host()._recorder_stake_kwargs(mgr, ADDR))
        assert len(mgr.slashing_events) == 1

    def test_self_resolving_recorder_gets_no_extra_kwarg(self):
        recorder = SimpleNamespace(_accused_stake=lambda v: Decimal("1"))
        assert _evidence_host()._recorder_stake_kwargs(recorder, ADDR) == {}

    def test_no_consensus_for_chain_keeps_legacy_none(self, monkeypatch):
        def boom(cid):
            raise KeyError(cid)

        monkeypatch.setattr("aitbc_chain.consensus.multi_validator_poa.get_consensus", boom)
        assert _evidence_host()._recorder_stake_kwargs(SlashingManager(), ADDR) == {}


class TestR3CrossViewHeight:
    def _capture(self, monkeypatch):
        seen = {}

        def fake(ep, event, addr, uc_ctx, uc_contexts, cross_view_height, apply_height):
            seen["cvh"] = cross_view_height
            return True, None

        monkeypatch.setattr("aitbc_chain.state.deactivation_evidence._verify_equivocation_claim", fake)
        monkeypatch.setattr(slashing_mod, "_pair_shape_ok", lambda e, p: True)
        monkeypatch.setattr(slashing_mod, "event_signature_evidence", lambda e: {"kind": "x"})
        return seen

    def test_gate_uses_the_local_cross_view_height_not_zero(self, monkeypatch):
        seen = self._capture(monkeypatch)
        monkeypatch.setattr(settings, "pbft_cross_view_commit_lock_height", 500)
        assert slashing_mod.equivocation_evidence_verifies(SimpleNamespace(validator_address=ADDR, block_height=H))
        assert seen["cvh"] == 500

    def test_unset_height_is_passed_as_none_fail_closed(self, monkeypatch):
        seen = self._capture(monkeypatch)
        monkeypatch.setattr(settings, "pbft_cross_view_commit_lock_height", None)
        slashing_mod.equivocation_evidence_verifies(SimpleNamespace(validator_address=ADDR, block_height=H))
        assert seen["cvh"] is None


class TestR2CallSiteWiring:
    """The real local-detection call site must hand the stake to the fallback recorder."""

    def _host(self, monkeypatch, stake: str):
        host = _evidence_host()
        a, b = _atts()
        key = lambda h, p, s, d: (h, p, s)  # noqa: E731
        host._signed_attestations = {(H, HA, ADDR): a, (H, HB, ADDR): b}
        host._vote_justifications = {}
        host._prior_signed_hashes = lambda h, bh, s: {HA}
        host._signed_attestation_key = key
        host._pairing_priors = lambda h, s, d, prior: sorted(prior)
        host._uc_unlock_justification = lambda *args: None
        host._emit_evidence = lambda *args: None
        fake = SimpleNamespace(_accused_stake=lambda v: Decimal(stake))
        monkeypatch.setattr("aitbc_chain.consensus.multi_validator_poa.get_consensus", lambda cid: fake)
        mgr = SlashingManager()
        host._equivocation_recorder = lambda: mgr
        return host, mgr

    def test_zero_stake_accused_never_reaches_history(self, monkeypatch):
        host, mgr = self._host(monkeypatch, "0")
        host._record_attestation_equivocation_evidence(H, HB, ADDR, "0xprop", None)
        assert mgr.slashing_events == []

    def test_staked_accused_is_recorded(self, monkeypatch):
        host, mgr = self._host(monkeypatch, "1000")
        host._record_attestation_equivocation_evidence(H, HB, ADDR, "0xprop", None)
        assert len(mgr.slashing_events) == 1
