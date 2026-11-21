"""#2448: reinvest simulate honesty + staking wallet-gate consistency.

- ``reinvest simulate`` warned silently invented a plausible result for an
  agent with no recorded policy, emitted placeholder ``0xSTAKE``/``0xRESERVE``
  contract addresses, and dropped the unallocated remainder of earnings.
- ``liquidity-stake``/``liquidity-unstake``/``liquidity-claim`` wallet-gate
  refusals bypassed ``abort()`` — exit 1 + plain stderr under ``--output
  json`` where ``stake``/``unstake`` gave a JSON error object.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


def _reinvest_store(monkeypatch, tmp_path):
    from aitbc_cli.commands import reinvest

    monkeypatch.setattr(reinvest, "_POLICY_STORE", tmp_path / "reinvest_policies.json")
    return reinvest


def _stub_config(monkeypatch, reinvest, **fields):
    defaults = {"staking_contract_address": None, "reinvest_reserve_address": None}
    defaults.update(fields)
    monkeypatch.setattr(reinvest, "get_config", lambda: SimpleNamespace(**defaults))


def test_simulate_unknown_agent_warns_and_accounts_full_earnings(runner, tmp_path, monkeypatch):
    """#2448 items 1-3: unknown agent warns (not silent), unconfigured
    addresses serialize as null, and the unallocated remainder is named."""
    reinvest = _reinvest_store(monkeypatch, tmp_path)
    _stub_config(monkeypatch, reinvest)

    result = runner.invoke(
        reinvest.simulate, ["--agent-id", "nosuch-agent", "--earnings", "10"], obj={"output_format": "json"}
    )
    assert result.exit_code == 0, result.output
    assert "no recorded reinvestment policy" in result.stderr

    body = json.loads(result.stdout)
    assert body["policy_source"] == "default"
    # earnings 10 -> reinvest 5 (engine reinvest_pct 50) -> stake 3 + reserve 2;
    # the remaining 5 is the retained line, so actions account for all of it.
    assert body["actions"] == [
        {"action_type": "stake", "contract_address": None, "amount": "3"},
        {"action_type": "transfer", "contract_address": None, "amount": "2"},
        {"action_type": "retain", "contract_address": None, "amount": "5"},
    ]


def test_simulate_strict_refuses_unknown_agent(runner, tmp_path, monkeypatch):
    """#2448 item 1: --strict turns the unknown-agent warning into a refusal."""
    reinvest = _reinvest_store(monkeypatch, tmp_path)
    _stub_config(monkeypatch, reinvest)

    result = runner.invoke(reinvest.simulate, ["--agent-id", "nosuch-agent", "--strict"], obj={"output_format": "table"})
    assert result.exit_code != 0
    assert "no recorded reinvestment policy" in result.stdout
    # abort() categorises the not-found refusal as NotFoundError -> exit 2.
    assert getattr(result.exception, "exit_code", None) == 2


def test_simulate_saved_policy_stays_quiet(runner, tmp_path, monkeypatch):
    """A recorded policy means the agent is registered — no warning."""
    reinvest = _reinvest_store(monkeypatch, tmp_path)
    _stub_config(monkeypatch, reinvest)
    store = tmp_path / "reinvest_policies.json"
    store.write_text(json.dumps({"agent-1": {"staking_pct": "60", "reserve_pct": "40", "min_reinvest": "0.01"}}))

    result = runner.invoke(reinvest.simulate, ["--agent-id", "agent-1", "--earnings", "10"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    assert "no recorded reinvestment policy" not in result.stderr
    body = json.loads(result.stdout)
    assert body["policy_source"] == "saved"


def test_simulate_resolves_contracts_from_config(runner, tmp_path, monkeypatch):
    """#2448 item 2: defaults come from config, never a placeholder."""
    reinvest = _reinvest_store(monkeypatch, tmp_path)
    _stub_config(
        monkeypatch,
        reinvest,
        staking_contract_address="0xCfgStake",
        reinvest_reserve_address="0xCfgReserve",
    )

    result = runner.invoke(reinvest.simulate, ["--agent-id", "a", "--earnings", "10"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["actions"][0]["contract_address"] == "0xCfgStake"
    assert body["actions"][1]["contract_address"] == "0xCfgReserve"


def test_simulate_explicit_contract_options_win(runner, tmp_path, monkeypatch):
    reinvest = _reinvest_store(monkeypatch, tmp_path)
    _stub_config(
        monkeypatch,
        reinvest,
        staking_contract_address="0xCfgStake",
        reinvest_reserve_address="0xCfgReserve",
    )

    result = runner.invoke(
        reinvest.simulate,
        ["--agent-id", "a", "--earnings", "10", "--staking-contract", "0xOptStake", "--reserve-address", "0xOptReserve"],
        obj={"output_format": "json"},
    )
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["actions"][0]["contract_address"] == "0xOptStake"
    assert body["actions"][1]["contract_address"] == "0xOptReserve"


@pytest.mark.parametrize(
    "argv",
    [
        ["stake", "--amount", "1", "--duration", "1", "--wallet-name", "nosuch2448"],
        ["unstake", "--stake-id", "1", "--wallet-name", "nosuch2448"],
        ["liquidity-stake", "--amount", "1", "--wallet-name", "nosuch2448"],
        ["wallet", "liquidity-unstake", "--wallet-name", "nosuch2448", "--stake-id", "1"],
        ["wallet", "liquidity-claim", "--wallet-name", "nosuch2448", "--stake-id", "1"],
    ],
)
def test_staking_wallet_gate_one_exit_class_and_json(argv, tmp_path, monkeypatch, capsys):
    """#2448 items 4-5: the wallet-gate refusal exits 2 with a JSON error
    object under --output json for stake, unstake and liquidity-stake."""
    from aitbc_cli.core.main import main

    monkeypatch.setenv("HOME", str(tmp_path))
    code = main(["--output", "json", *argv])
    out = capsys.readouterr().out
    body = json.loads(out)
    assert body["error"] == "NotFoundError"
    assert body["exit_code"] == 2
    assert code == 2
