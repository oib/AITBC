"""REPO-2: signing commands' --fee defaults equal the chain standard fee.

`transactions send`, `transactions batch` per-entry fallback, and
`ipfs island subscribe` all sign and broadcast — their fee defaults must
track ``aitbc.utils.units.DEFAULT_TX_FEE_AIT``, not a frozen literal.
Explicit ``--fee`` (and a per-entry ``fee`` in a batch file) still wins.

Only the broadcast boundary is mocked; wallet password resolution is real
(an unencrypted throwaway wallet file short-circuits to ``""``).
"""

import json
from decimal import Decimal
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from aitbc.utils.units import DEFAULT_TX_FEE_AIT
from aitbc_cli.commands import ipfs as ipfs_cmd
from aitbc_cli.commands import transactions as tx_cmd

TO = "0x40c7181b639A2642294A802b1CD60C7a0d531a07"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def wallet_env(tmp_path):
    """An unencrypted wallet file + env pointing AITBC_WALLET_DIR at it."""
    (tmp_path / "w.json").write_text(
        json.dumps(
            {
                "address": "0xCf1719140054AB3fD52ce8aa3128dec9317426E3",
                "private_key": "0x" + "11" * 32,
            }
        )
    )
    return {"AITBC_WALLET_DIR": str(tmp_path)}


def _fees(mock_send):
    """`fee` is positional arg[3] in send/batch, a kwarg in subscribe."""
    return [c.kwargs["fee"] if "fee" in c.kwargs else c.args[3] for c in mock_send.call_args_list]


class TestTransactionsSendFee:
    def test_default_is_chain_standard(self, runner, wallet_env):
        with patch.object(tx_cmd, "_send_transaction_impl", return_value="0xhash") as m:
            result = runner.invoke(tx_cmd.send, ["--from", "w", "--to", TO, "--amount", "1"], env=wallet_env)
        assert result.exit_code == 0, result.output
        assert _fees(m) == [DEFAULT_TX_FEE_AIT]

    def test_explicit_fee_wins(self, runner, wallet_env):
        with patch.object(tx_cmd, "_send_transaction_impl", return_value="0xhash") as m:
            result = runner.invoke(
                tx_cmd.send,
                ["--from", "w", "--to", TO, "--amount", "1", "--fee", "0.5"],
                env=wallet_env,
            )
        assert result.exit_code == 0, result.output
        assert _fees(m) == [Decimal("0.5")]


class TestBatchEntryFee:
    def _run(self, runner, wallet_env, tmp_path, entry):
        batch_file = tmp_path / "batch.json"
        batch_file.write_text(json.dumps([entry]))
        with patch.object(tx_cmd, "_send_transaction_impl", return_value="0xhash") as m:
            result = runner.invoke(tx_cmd.batch, ["--transactions-file", str(batch_file)], env=wallet_env)
        assert result.exit_code == 0, result.output
        return m

    def test_default_is_chain_standard(self, runner, wallet_env, tmp_path):
        m = self._run(runner, wallet_env, tmp_path, {"from_wallet": "w", "to_address": TO, "amount": 1})
        assert _fees(m) == [DEFAULT_TX_FEE_AIT]

    def test_explicit_fee_wins(self, runner, wallet_env, tmp_path):
        m = self._run(
            runner,
            wallet_env,
            tmp_path,
            {"from_wallet": "w", "to_address": TO, "amount": 1, "fee": "0.5"},
        )
        assert _fees(m) == [Decimal("0.5")]


class TestIslandSubscribeFee:
    ARGS = ["--wallet", "w", "--to", TO, "--island-id", "isl", "--amount", "1"]

    def test_default_is_chain_standard(self, runner, wallet_env):
        with patch.object(ipfs_cmd, "_send_transaction_impl", return_value="0xhash") as m:
            result = runner.invoke(ipfs_cmd.subscribe, self.ARGS, obj={}, env=wallet_env)
        assert result.exit_code == 0, result.output
        assert _fees(m) == [DEFAULT_TX_FEE_AIT]

    def test_explicit_fee_wins(self, runner, wallet_env):
        with patch.object(ipfs_cmd, "_send_transaction_impl", return_value="0xhash") as m:
            result = runner.invoke(ipfs_cmd.subscribe, self.ARGS + ["--fee", "0.5"], obj={}, env=wallet_env)
        assert result.exit_code == 0, result.output
        assert _fees(m) == [Decimal("0.5")]
