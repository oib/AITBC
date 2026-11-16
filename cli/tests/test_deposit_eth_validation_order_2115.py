"""#2115: `market exchange deposit-eth` validates its arguments before it loads the wallet.

On hub a bad --bridge-address died on the default wallet's missing private
key first; node2 (which has the key) refused at the address. The refusal must
not depend on which wallet the host happens to hold.
"""

from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.market import exchange as ex

GOOD = "0x310dcE00270D0aC10CAccfBD636Ff07BD5648781"


@pytest.fixture
def harness(monkeypatch):
    wallet = MagicMock(side_effect=AssertionError("wallet loaded before argument validation"))
    monkeypatch.setattr(ex, "load_wallet_for_payment", wallet)
    monkeypatch.setattr(ex, "EthereumRPCClient", lambda: MagicMock())
    monkeypatch.delenv("BRIDGE_ETH_ADDRESS", raising=False)
    return wallet


def _run(*args):
    return CliRunner().invoke(ex.deposit_eth, list(args), obj={})


def test_invalid_bridge_address_is_refused_without_touching_the_wallet(harness):
    res = _run("--amount", "0.1", "--bridge-address", "notanaddress")
    assert res.exit_code != 0
    assert "Invalid bridge deposit address: notanaddress" in res.output
    harness.assert_not_called()


def test_missing_bridge_address_is_refused_without_touching_the_wallet(harness):
    res = _run("--amount", "0.1")
    assert res.exit_code != 0
    assert "Bridge deposit address is required" in res.output
    harness.assert_not_called()


def test_env_bridge_address_is_validated_too(harness, monkeypatch):
    monkeypatch.setenv("BRIDGE_ETH_ADDRESS", "nope")
    res = _run("--amount", "0.1")
    assert "Invalid bridge deposit address: nope" in res.output
    harness.assert_not_called()


def test_invalid_explicit_recipient_is_refused_without_touching_the_wallet(harness):
    res = _run("--amount", "0.1", "--bridge-address", GOOD, "--ait-address", "bad")
    assert "Invalid AIT recipient address: bad" in res.output
    harness.assert_not_called()


def test_non_positive_amount_is_refused_without_touching_the_wallet(harness):
    res = _run("--amount", "0", "--bridge-address", GOOD)
    assert "Amount must be greater than 0" in res.output
    harness.assert_not_called()


def test_valid_arguments_still_reach_the_wallet(harness):
    harness.side_effect = RuntimeError("wallet reached")
    res = _run("--amount", "0.1", "--bridge-address", GOOD)
    assert "wallet reached" in res.output
    harness.assert_called_once()
