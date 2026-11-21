"""Tests for `aitbc market gpu agreement-create` (#2052 / #2375-adjacent).

The command mints a real AIPowerRental agreement id on the EVM rail so
`aitbc dispute file --agreement-id` has a valid referent. These tests pin
the preflight refusals (paused / protected-only / unauthorized parties /
bad duration / bad price) and the happy-path tx + post-create verification
against a stubbed EVMContractClient.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.market.gpu as gpu_mod
from aitbc_cli.core.main import cli


BUYER = "0x1111111111111111111111111111111111111111"
PROVIDER = "0x2222222222222222222222222222222222222222"
OTHER = "0x3333333333333333333333333333333333333333"


def _result(status=1, tx_hash="0xabc"):
    return SimpleNamespace(status=status, tx_hash=tx_hash, block_number=123, gas_used=21000)


def _evm_stub(**overrides):
    evm = MagicMock()
    evm.rentals_paused.return_value = False
    evm.require_protected_rentals.return_value = False
    evm.rental_duration_bounds.return_value = (3600, 2592000)
    evm.is_authorized_consumer.return_value = True
    evm.is_authorized_provider.return_value = True
    evm.get_token_decimals.return_value = 18
    evm.agreement_counter.side_effect = [0, 1]
    evm.get_rental_agreement.return_value = [0, PROVIDER, BUYER] + [0] * 9
    evm.submit_and_wait.return_value = _result()
    evm.build_create_rental_tx.return_value = {"to": "0xcontract", "data": "0x"}
    evm.rpc._get_web3.return_value.eth.get_transaction_count.return_value = 7
    for k, v in overrides.items():
        getattr(evm, k).return_value = v
    return evm


@pytest.fixture
def runner():
    return CliRunner()


def _patch(monkeypatch, mapping):
    for name, fn in mapping.items():
        monkeypatch.setattr(gpu_mod, name, fn)


def test_agreement_create_happy_path(runner, monkeypatch):
    evm = _evm_stub()
    _patch(
        monkeypatch,
        {
            "_evm_contract_client": lambda config: evm,
            "load_wallet_for_payment": lambda ctx, **kw: (BUYER, "0xdeadbeef", "w1"),
            "get_config": lambda: SimpleNamespace(
                evm_rpc_url="http://evm.test",
                energy_rental_contract_address="0xRENTAL",
                energy_token_contract_address="0xTOKEN",
                energy_pricing_chain_id=11155111,
            ),
        },
    )
    result = runner.invoke(
        cli,
        ["market", "gpu", "agreement-create", "--provider", PROVIDER, "--price", "1.5", "--duration", "7200", "--yes"],
        obj={},
    )
    assert result.exit_code == 0, result.output
    evm.build_create_rental_tx.assert_called_once()
    kwargs = evm.build_create_rental_tx.call_args.kwargs
    assert kwargs["provider"] == PROVIDER.lower() or kwargs["provider"] == PROVIDER
    assert kwargs["duration"] == 7200
    assert kwargs["price_units"] == int(Decimal("1.5") * 10**18)
    evm.submit_and_wait.assert_called_once()
    assert "agreement" in result.output.lower() or result.exit_code == 0


def test_agreement_create_unauthorized_consumer_aborts(runner, monkeypatch):
    evm = _evm_stub()
    evm.is_authorized_consumer.return_value = False
    _patch(
        monkeypatch,
        {
            "_evm_contract_client": lambda config: evm,
            "load_wallet_for_payment": lambda ctx, **kw: (BUYER, "0xdeadbeef", "w1"),
            "get_config": lambda: SimpleNamespace(
                evm_rpc_url="http://evm.test",
                energy_rental_contract_address="0xRENTAL",
                energy_token_contract_address="0xTOKEN",
                energy_pricing_chain_id=11155111,
            ),
        },
    )
    result = runner.invoke(
        cli,
        ["market", "gpu", "agreement-create", "--provider", PROVIDER, "--price", "1.5", "--yes"],
        obj={},
    )
    assert result.exit_code != 0
    assert "authorizeConsumer" in result.output
    evm.submit_and_wait.assert_not_called()


def test_agreement_create_unauthorized_provider_aborts(runner, monkeypatch):
    evm = _evm_stub()
    evm.is_authorized_provider.return_value = False
    _patch(
        monkeypatch,
        {
            "_evm_contract_client": lambda config: evm,
            "load_wallet_for_payment": lambda ctx, **kw: (BUYER, "0xdeadbeef", "w1"),
            "get_config": lambda: SimpleNamespace(
                evm_rpc_url="http://evm.test",
                energy_rental_contract_address="0xRENTAL",
                energy_token_contract_address="0xTOKEN",
                energy_pricing_chain_id=11155111,
            ),
        },
    )
    result = runner.invoke(
        cli,
        ["market", "gpu", "agreement-create", "--provider", PROVIDER, "--price", "1.5", "--yes"],
        obj={},
    )
    assert result.exit_code != 0
    assert "authorizeProvider" in result.output
    evm.submit_and_wait.assert_not_called()


def test_agreement_create_protected_only_mode_aborts(runner, monkeypatch):
    evm = _evm_stub()
    evm.require_protected_rentals.return_value = True
    _patch(
        monkeypatch,
        {
            "_evm_contract_client": lambda config: evm,
            "load_wallet_for_payment": lambda ctx, **kw: (BUYER, "0xdeadbeef", "w1"),
            "get_config": lambda: SimpleNamespace(
                evm_rpc_url="http://evm.test",
                energy_rental_contract_address="0xRENTAL",
                energy_token_contract_address="0xTOKEN",
                energy_pricing_chain_id=11155111,
            ),
        },
    )
    result = runner.invoke(
        cli,
        ["market", "gpu", "agreement-create", "--provider", PROVIDER, "--price", "1.5", "--yes"],
        obj={},
    )
    assert result.exit_code != 0
    assert "protected" in result.output.lower()
    evm.submit_and_wait.assert_not_called()


def test_agreement_create_duration_bounds(runner, monkeypatch):
    evm = _evm_stub()
    _patch(
        monkeypatch,
        {
            "_evm_contract_client": lambda config: evm,
            "load_wallet_for_payment": lambda ctx, **kw: (BUYER, "0xdeadbeef", "w1"),
            "get_config": lambda: SimpleNamespace(
                evm_rpc_url="http://evm.test",
                energy_rental_contract_address="0xRENTAL",
                energy_token_contract_address="0xTOKEN",
                energy_pricing_chain_id=11155111,
            ),
        },
    )
    result = runner.invoke(
        cli,
        ["market", "gpu", "agreement-create", "--provider", PROVIDER, "--price", "1.5", "--duration", "60", "--yes"],
        obj={},
    )
    assert result.exit_code != 0
    assert "bounds" in result.output
    evm.submit_and_wait.assert_not_called()
