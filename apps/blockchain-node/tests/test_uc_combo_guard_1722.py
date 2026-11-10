"""#1722 — settings guard for UC flag combinations that freeze the chain.

Temporary by design: remove or invert with ``unavail_prewarm_enabled`` (#1701).
"""

from __future__ import annotations

import logging

import pytest
from aitbc_chain.config import ChainSettings, uc_combo_findings

ARMED = {"vote_journal_enabled": True, "vote_journal_justification_enabled": True}


def _cfg(**kw):
    return ChainSettings(**kw)


def test_defaults_are_clean():
    assert uc_combo_findings(_cfg()) == ([], [])


def test_default_timings_armed_exceed_header_bound(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    errors, _ = uc_combo_findings(_cfg(**ARMED))
    # 90 + 15 + 5 = 110 >= header 60, but < cert max 120
    assert len(errors) == 1
    assert "attestation_header_max_age_seconds" in errors[0]


def test_production_refuses_to_start(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(ValueError, match="unsafe UC flag combination"):
        _cfg(**ARMED)


def test_non_production_warns_and_starts(monkeypatch, caplog):
    monkeypatch.setenv("ENVIRONMENT", "development")
    with caplog.at_level(logging.WARNING):
        cfg = _cfg(**ARMED)
    assert cfg.vote_journal_justification_enabled is True
    assert any("UC flag guard" in r.getMessage() for r in caplog.records)


def test_safe_timings_pass_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    cfg = _cfg(**ARMED, unavail_evidence_seconds=30.0, unavail_collect_seconds=10.0)
    assert uc_combo_findings(cfg) == ([], [])


def test_exact_boundary_is_refused():
    # 40 + 15 + 5 = 60 == header max age: not strictly below the bound
    errors, _ = uc_combo_findings(_cfg(**ARMED, unavail_evidence_seconds=40.0))
    assert len(errors) == 1


def test_cert_bound_checked_separately():
    errors, _ = uc_combo_findings(
        _cfg(**ARMED, unavail_evidence_seconds=30.0, unavail_collect_seconds=10.0, unavail_cert_max_age_seconds=45.0)
    )
    assert len(errors) == 1 and "unavail_cert_max_age_seconds" in errors[0]


def test_header_age_disabled_skips_header_bound():
    errors, _ = uc_combo_findings(_cfg(**ARMED, attestation_header_max_age_seconds=0.0))
    assert errors == []


def test_unarmed_timings_are_not_checked():
    assert uc_combo_findings(_cfg(unavail_evidence_seconds=500.0)) == ([], [])
    # justification flag alone, journal master off: inert, warned about
    errors, warnings = uc_combo_findings(_cfg(vote_journal_justification_enabled=True))
    assert errors == [] and len(warnings) == 1 and "vote_journal_enabled is off" in warnings[0]


@pytest.mark.parametrize(
    "flag",
    ["vote_journal_abandon_enabled", "vote_journal_sealed_rival_pull", "unavail_nonblocking_persist_enabled"],
)
def test_inert_flags_warn_when_journal_off(flag):
    _, warnings = uc_combo_findings(_cfg(**{flag: True}))
    assert [w for w in warnings if flag in w]


def test_journal_on_flags_not_warned():
    _, warnings = uc_combo_findings(_cfg(vote_journal_enabled=True, vote_journal_abandon_enabled=True))
    assert warnings == []


def test_zero_same_hash_retry_horizon_warns():
    _, warnings = uc_combo_findings(
        _cfg(
            proposer_same_hash_retry_enabled=True,
            multi_validator_attestation_timeout_seconds=15.0,
            attestation_header_max_age_seconds=20.0,
        )
    )
    assert len(warnings) == 1 and "retry horizon is 0" in warnings[0]


def test_positive_same_hash_retry_horizon_is_quiet():
    _, warnings = uc_combo_findings(_cfg(proposer_same_hash_retry_enabled=True))
    assert warnings == []
