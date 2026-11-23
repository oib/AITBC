"""#2755: energy provider EVM writes estimate gas instead of hardcoded limits.

``provider register`` and ``provider rate --publish`` used to submit
``registerEnergyProfile``/``publishEnergyRate`` with fixed gas limits
(300_000 / 200_000) that could under- or over-shoot. They now call
``eth_estimateGas`` and apply a 25% headroom, failing loud when the
estimate itself fails.
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.energy as energy_mod
from aitbc_cli.commands.energy import energy

ADDR = "0x" + "11" * 20
CONTRACT = "0x" + "33" * 20
ESTIMATE = 160_000
EXPECTED_GAS = math.ceil(ESTIMATE * 5 / 4)


@pytest.fixture
def runner():
    return CliRunner()


def _config():
    c = MagicMock()
    c.evm_rpc_url = "http://evm.test"
    c.energy_pricing_contract_address = CONTRACT
    c.energy_pricing_chain_id = 11155111
    c.native_chain_id = ""
    c.blockchain_rpc_url = "http://localhost:8202"
    c.coordinator_api_url = "http://localhost:8203"
    c.native_coordinator_url = None
    c.energy_operator_address = None
    c.energy_quote_domain = "aitbc.energy.quote.v1"
    c.energy_max_rate_age_seconds = 86400
    c.energy_eur_per_kwh = None
    c.shop_region = None
    c.api_key = None
    return c


def _rpc(estimate=ESTIMATE):
    rpc = MagicMock(name="EthereumRPCClient")
    rpc.encode_function_call.return_value = "0xcalldata"
    rpc.estimate_gas.return_value = estimate
    rpc.get_gas_price.return_value = {"wei": 1_000_000_000}
    rpc._get_web3.return_value.eth.get_transaction_count.return_value = 7
    rpc.sign_transaction.return_value = "0xsigned"
    rpc.send_raw_transaction.return_value = "0xtxhash"
    rpc.wait_for_transaction.return_value = {"status": 1}
    return rpc


def _invoke_with_rpc(runner, monkeypatch, args, rpc):
    config = _config()
    monkeypatch.setattr(energy_mod, "get_config", lambda: config)
    monkeypatch.setattr("aitbc_cli.config.get_config", lambda: config)
    monkeypatch.setattr("aitbc.ethereum_rpc.EthereumRPCClient", lambda *a, **k: rpc)
    monkeypatch.setattr(
        "aitbc_cli.utils.wallet_loader.load_wallet_for_payment",
        lambda *a, **k: (ADDR, "0x" + "ab" * 32, None),
    )
    return runner.invoke(energy, args, obj={"output_format": "table"})


REGISTER_ARGS = [
    "provider",
    "register",
    "--resource-id",
    "res-1",
    "--provider-address",
    "0x" + "22" * 20,
    "--model-id",
    "gpu-x",
    "--tbp-watts",
    "300",
    "--eur-per-kwh",
    "0.30",
]

RATE_ARGS = [
    "provider",
    "rate",
    "--publish",
    "--ait-per-eur",
    "4.0",
]


def test_register_uses_estimated_gas_with_headroom(runner, monkeypatch):
    rpc = _rpc()
    result = _invoke_with_rpc(runner, monkeypatch, REGISTER_ARGS, rpc)
    assert result.exit_code == 0, result.output
    rpc.estimate_gas.assert_called_once()
    est_tx = rpc.estimate_gas.call_args[0][0]
    assert est_tx["from"] == ADDR
    assert est_tx["to"] == CONTRACT
    assert est_tx["data"] == "0xcalldata"
    assert est_tx["value"] == 0
    tx = rpc.sign_transaction.call_args[0][0]
    assert tx["gas"] == EXPECTED_GAS
    assert tx["gas"] != 300_000  # not the old hardcoded limit


def test_rate_publish_uses_estimated_gas_with_headroom(runner, monkeypatch):
    rpc = _rpc(estimate=240_000)
    result = _invoke_with_rpc(runner, monkeypatch, RATE_ARGS, rpc)
    assert result.exit_code == 0, result.output
    rpc.estimate_gas.assert_called_once()
    est_tx = rpc.estimate_gas.call_args[0][0]
    assert est_tx["from"] == ADDR
    assert est_tx["to"] == CONTRACT
    assert est_tx["data"] == "0xcalldata"
    assert est_tx["value"] == 0
    tx = rpc.sign_transaction.call_args[0][0]
    assert tx["gas"] == math.ceil(240_000 * 5 / 4)  # 300_000, not the old 200_000


def test_register_estimate_failure_aborts_before_signing(runner, monkeypatch):
    rpc = _rpc()
    rpc.estimate_gas.side_effect = ValueError("node says revert")
    result = _invoke_with_rpc(runner, monkeypatch, REGISTER_ARGS, rpc)
    assert result.exit_code != 0
    assert "eth_estimateGas failed for registerEnergyProfile" in result.output
    rpc.sign_transaction.assert_not_called()
    rpc.send_raw_transaction.assert_not_called()


def test_rate_publish_estimate_failure_aborts_before_signing(runner, monkeypatch):
    rpc = _rpc()
    rpc.estimate_gas.side_effect = ValueError("node says revert")
    result = _invoke_with_rpc(runner, monkeypatch, RATE_ARGS, rpc)
    assert result.exit_code != 0
    assert "eth_estimateGas failed for publishEnergyRate" in result.output
    rpc.sign_transaction.assert_not_called()
    rpc.send_raw_transaction.assert_not_called()
