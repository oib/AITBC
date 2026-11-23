"""#2755: ``market exchange deposit-eth`` estimates gas for the contract deposit.

The deposit transaction carries ``data`` (the AIT recipient address) so it
is a contract interaction, not a plain 21k transfer. With no ``--gas`` the
command now calls ``eth_estimateGas`` and applies a 25% headroom; an
explicit ``--gas`` is still honored verbatim and skips the estimate.
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner
from web3 import Web3

from aitbc_cli.commands.market import exchange as ex

# Lowercase hex: Web3.is_address's eth_utils regex accepts [0-9a-f] only,
# so the mixed-case checksummed spelling used elsewhere is refused here.
BRIDGE = "0x310dce00270d0ac10caccfbd636ff07bd5648781"
RECIPIENT = "0x" + "44" * 20
SENDER = "0x" + "55" * 20
ESTIMATE = 100_000
EXPECTED_GAS = math.ceil(ESTIMATE * 5 / 4)


@pytest.fixture
def w3():
    w3 = MagicMock(name="web3")
    w3.to_wei.side_effect = lambda value, unit: 123_000_000_000_000_000
    w3.eth.gas_price = 1_000_000_000
    w3.eth.get_transaction_count.return_value = 3
    w3.eth.estimate_gas.return_value = ESTIMATE
    signed = MagicMock()
    signed.raw_transaction = b"\x01\x02\x03"
    w3.eth.account.sign_transaction.return_value = signed
    tx_hash = MagicMock()
    tx_hash.hex.return_value = "0xdeadbeef"
    w3.eth.send_raw_transaction.return_value = tx_hash
    receipt = MagicMock()
    receipt.status = 1
    w3.eth.wait_for_transaction_receipt.return_value = receipt
    return w3


@pytest.fixture
def harness(monkeypatch, w3):
    rpc = MagicMock(name="EthereumRPCClient")
    rpc._get_web3.return_value = w3
    monkeypatch.setattr(ex, "EthereumRPCClient", lambda: rpc)
    monkeypatch.setattr(
        ex,
        "load_wallet_for_payment",
        lambda *a, **k: (SENDER, "0x" + "ab" * 32, None),
    )
    monkeypatch.delenv("BRIDGE_ETH_ADDRESS", raising=False)
    return w3


def _run(*args):
    return CliRunner().invoke(ex.deposit_eth, list(args), obj={})


BASE_ARGS = [
    "--amount",
    "0.1",
    "--bridge-address",
    BRIDGE,
    "--ait-address",
    RECIPIENT,
]


def test_gas_omitted_estimates_with_headroom(harness):
    result = _run(*BASE_ARGS)
    assert result.exit_code == 0, result.output
    harness.eth.estimate_gas.assert_called_once()
    est_tx = harness.eth.estimate_gas.call_args[0][0]
    assert est_tx["from"] == SENDER
    assert est_tx["to"] == Web3.to_checksum_address(BRIDGE)
    assert est_tx["data"] == Web3.to_checksum_address(RECIPIENT)
    assert est_tx["value"] == 123_000_000_000_000_000
    tx = harness.eth.account.sign_transaction.call_args[0][0]
    assert tx["gas"] == EXPECTED_GAS
    assert tx["gas"] != 30_000  # not the old default


def test_explicit_gas_skips_estimate(harness):
    result = _run(*BASE_ARGS, "--gas", "99999")
    assert result.exit_code == 0, result.output
    harness.eth.estimate_gas.assert_not_called()
    tx = harness.eth.account.sign_transaction.call_args[0][0]
    assert tx["gas"] == 99999
