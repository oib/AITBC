"""#2158 — wrongful deactivation can no longer take the active set below quorum.

Drill-1: a false-positive equivocation reached the byzantine threshold on all four
validators, each flipped ``is_active=False`` and the chain halted for good. The legacy
(node-local) flip now keeps at least the quorum of the CONFIGURED set active.
"""

from __future__ import annotations

import pytest

from aitbc_chain.config import settings
from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole

A = "0x1111111111111111111111111111111111111111"
B = "0x2222222222222222222222222222222222222222"
C = "0x3333333333333333333333333333333333333333"
D = "0x4444444444444444444444444444444444444444"


@pytest.fixture(autouse=True)
def _threshold(monkeypatch):
    monkeypatch.setattr(settings, "consensus_byzantine_threshold", 1)
    monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", False)


def _poa(members=(A, B, C, D)) -> MultiValidatorPoA:
    poa = MultiValidatorPoA("chain-2158")
    for addr in members:
        poa.add_validator(addr, 1000.0)
        poa.validators[addr].role = ValidatorRole.VALIDATOR
    return poa


def _wrongful(poa: MultiValidatorPoA, who: str, height: int) -> None:
    event = poa._slashing_manager.detect_double_sign(who, "0xaa", "0xbb", height)
    poa._apply_equivocation_slash(who, event)


def _active(poa: MultiValidatorPoA) -> int:
    return sum(1 for v in poa.validators.values() if v.is_active)


def test_four_wrongful_verdicts_leave_exactly_the_quorum_active():
    poa = _poa()
    for i, who in enumerate((A, B, C, D)):
        _wrongful(poa, who, 100 + i)
    assert _active(poa) == 3  # n=4 -> quorum 3: at most f=1 deactivated
    assert poa.select_proposer(101) is not None  # the chain can still propose


def test_refused_deactivation_still_records_the_event_and_slashes_stake():
    poa = _poa()
    for i, who in enumerate((A, B, C)):
        _wrongful(poa, who, 100 + i)
    refused = B
    assert poa.validators[refused].is_active is True
    assert len(poa.get_slashing_history()) == 3
    assert poa.validators[refused].stake < 1000.0


def test_refusal_bumps_the_metric():
    from aitbc_chain.metrics import metrics_registry

    poa = _poa()
    before = metrics_registry._counters.get("consensus_deactivation_floor_refused_total", 0.0)
    _wrongful(poa, A, 1)  # first deactivation: 4 -> 3 active, allowed
    assert metrics_registry._counters.get("consensus_deactivation_floor_refused_total", 0.0) == before
    _wrongful(poa, B, 2)  # would leave 2 < quorum 3
    assert metrics_registry._counters.get("consensus_deactivation_floor_refused_total", 0.0) == before + 1
    assert poa.quorum_health()["below_quorum"] is False


@pytest.mark.parametrize("members", [(A,), (A, B), (A, B, C)])
def test_small_sets_deactivate_no_more_than_the_floor_allows(members):
    poa = _poa(members)
    for i, who in enumerate(members):
        _wrongful(poa, who, 100 + i)
    from aitbc_chain.consensus.pbft_quorum import pbft_required_messages

    assert _active(poa) >= pbft_required_messages(len(members))


def test_already_inactive_validator_is_not_treated_as_a_refused_deactivation():
    from aitbc_chain.metrics import metrics_registry

    poa = _poa()
    poa.validators[A].is_active = False  # e.g. a real, earlier deactivation
    before = metrics_registry._counters.get("consensus_deactivation_floor_refused_total", 0.0)
    _wrongful(poa, A, 1)
    assert poa.validators[A].is_active is False
    assert metrics_registry._counters.get("consensus_deactivation_floor_refused_total", 0.0) == before


def test_quorum_health_uses_the_configured_set_not_the_shrinking_one():
    poa = _poa()
    poa.validators[A].is_active = False
    poa.validators[B].is_active = False
    health = poa.quorum_health()
    assert health == {"configured": 4, "active": 2, "required": 3, "below_quorum": True}


def test_reactivate_requires_a_reason_and_restores_the_validator():
    poa = _poa()
    poa.validators[A].is_active = False
    with pytest.raises(ValueError):
        poa.reactivate_validator(A, "  ")
    assert poa.reactivate_validator(A, "false positive, see #2147") is True
    assert poa.validators[A].is_active is True
    assert poa.reactivate_validator(A, "again") is False  # already active
    assert poa.reactivate_validator("0x" + "9" * 40, "unknown") is False


def test_reactivate_refuses_while_chain_slashing_is_armed(monkeypatch):
    poa = _poa()
    poa.validators[A].is_active = False
    monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)
    with pytest.raises(ValueError):
        poa.reactivate_validator(A, "reason")
    assert poa.validators[A].is_active is False


def test_status_reports_a_halt_when_validators_are_configured_but_none_active(monkeypatch):
    from types import SimpleNamespace

    from aitbc_chain.consensus import multi_validator_poa as mvp
    from aitbc_chain.rpc.routers import consensus as route

    poa = _poa()
    for v in poa.validators.values():
        v.is_active = False
    monkeypatch.setitem(mvp.consensus_instances, "chain-2158", poa)
    monkeypatch.setattr(poa, "load_state", lambda **k: True)
    monkeypatch.setattr(settings, "multi_validator_consensus_enabled", True)
    monkeypatch.setattr(settings, "validator_set", "[{}]")
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={}, scope={})
    result = route.consensus_status_route(request, chain_id="chain-2158")
    assert result["halted"] is True
    assert result["below_quorum"] is True
    assert result["active_validators"] == 0


def test_reactivate_cli_is_a_dry_run_without_confirm_and_writes_with_it(monkeypatch, capsys):
    from aitbc_chain.consensus import reactivate_cli

    poa = _poa()
    poa.validators[A].is_active = False
    monkeypatch.setattr(reactivate_cli, "get_consensus", lambda chain: poa)
    monkeypatch.setattr(poa, "load_state", lambda **k: True)
    args = ["--chain", "chain-2158", "--address", A, "--reason", "false positive"]
    assert reactivate_cli.main(args) == 0
    assert poa.validators[A].is_active is False  # dry run
    assert reactivate_cli.main([*args, "--confirm"]) == 0
    assert poa.validators[A].is_active is True
    assert "after: active=4" in capsys.readouterr().out
