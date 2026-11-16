"""#2165 — follow-ups to the #2158 deactivation floor.

1. a repeated verdict for the same refused validator is one episode (one CRITICAL log, one count);
2. reactivation restores the VALIDATOR role of a validator that is still in the configured set;
3. the reactivation CLI dry run reports the refusal a confirmed run would hit while chain slashing is armed.
"""

from __future__ import annotations

import json

import pytest

from aitbc_chain.config import settings
from aitbc_chain.consensus import reactivate_cli
from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole
from aitbc_chain.metrics import metrics_registry

A = "0x1111111111111111111111111111111111111111"
B = "0x2222222222222222222222222222222222222222"
C = "0x3333333333333333333333333333333333333333"
D = "0x4444444444444444444444444444444444444444"
COUNTER = "consensus_deactivation_floor_refused_total"


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr(settings, "consensus_byzantine_threshold", 1)
    monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", False)


def _poa() -> MultiValidatorPoA:
    poa = MultiValidatorPoA("chain-2165")
    for addr in (A, B, C, D):
        poa.add_validator(addr, 1000.0)
        poa.validators[addr].role = ValidatorRole.VALIDATOR
    return poa


def _wrongful(poa: MultiValidatorPoA, who: str, height: int) -> None:
    poa._apply_equivocation_slash(who, poa._slashing_manager.detect_double_sign(who, "0xaa", "0xbb", height))


def _refused() -> float:
    return metrics_registry._counters.get(COUNTER, 0.0)


def test_repeat_verdicts_for_the_same_refused_validator_count_once(caplog):
    poa = _poa()
    _wrongful(poa, A, 1)  # 4 -> 3 active, allowed
    base = _refused()
    with caplog.at_level("CRITICAL"):
        _wrongful(poa, B, 2)  # refused: first of the episode
        _wrongful(poa, B, 3)  # same validator, same active set: same episode
        _wrongful(poa, B, 4)
    assert _refused() == base + 1
    assert sum("deactivation REFUSED" in r.getMessage() for r in caplog.records) == 1
    _wrongful(poa, C, 5)  # a different validator is its own episode
    assert _refused() == base + 2


def test_a_new_episode_after_the_active_set_changes_counts_again():
    poa = _poa()
    _wrongful(poa, A, 1)
    _wrongful(poa, B, 2)
    base = _refused()
    poa.validators[A].is_active = True  # operator reactivated A: active set changed
    _wrongful(poa, C, 3)  # allowed again (4 -> 3)
    _wrongful(poa, D, 4)  # refused: new episode for D
    assert _refused() == base + 1


@pytest.fixture
def _validator_set(monkeypatch):
    monkeypatch.setattr(settings, "validator_set", json.dumps([{"address": A}, {"address": B}]))


def test_reactivation_restores_the_role_of_a_validator_still_in_the_configured_set(_validator_set):
    poa = _poa()
    poa.validators[A].is_active = False
    poa.validators[A].role = ValidatorRole.STANDBY  # as left by remove_validator / env diff
    assert poa.reactivate_validator(A, "re-added to VALIDATOR_SET") is True
    assert poa.validators[A].is_active is True
    assert poa.validators[A].role == ValidatorRole.VALIDATOR
    assert A in poa.get_consensus_participants()


def test_reactivation_leaves_the_role_of_a_validator_outside_the_configured_set(_validator_set):
    poa = _poa()
    poa.validators[C].is_active = False
    poa.validators[C].role = ValidatorRole.STANDBY
    assert poa.reactivate_validator(C, "operator override") is True
    assert poa.validators[C].role == ValidatorRole.STANDBY
    assert C not in poa.get_consensus_participants()


def test_reactivation_keeps_the_role_of_a_validator_that_never_lost_it(_validator_set):
    poa = _poa()
    poa.validators[B].is_active = False  # legacy flip: role untouched
    assert poa.reactivate_validator(B, "false positive") is True
    assert poa.validators[B].role == ValidatorRole.VALIDATOR


def test_cli_dry_run_reports_the_armed_refusal(monkeypatch, capsys):
    poa = _poa()
    poa.validators[A].is_active = False
    monkeypatch.setattr(reactivate_cli, "get_consensus", lambda chain: poa)
    monkeypatch.setattr(poa, "load_state", lambda **k: True)
    monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)
    code = reactivate_cli.main(["--chain", "chain-2165", "--address", A, "--reason", "r"])
    assert code == 2
    assert "would be refused" in capsys.readouterr().out
    assert poa.validators[A].is_active is False
