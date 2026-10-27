"""``aitbc wallet balance`` must say when the account row is absent (#636).

A /rpc/account 404 used to print "0 AIT" with no hint, masking "not yet
synced" as "unfunded". The fix keeps exit 0 and balance 0 but prints
'account not found on chain <id> (unfunded or not yet synced)' and adds
account_found=false to the output. The 200 path is unchanged.
"""

import json
from unittest import mock

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.wallet.basic as basic_mod
from aitbc_cli.commands.wallet.basic import balance
from aitbc.exceptions import NetworkError  # the class AITBCHTTPClient raises

pytest.importorskip("yaml", reason="cli output helpers import yaml")

_ADDR = "0xce6c422fe31fc3bc0299cfad0070125ebc306dff"
_OBJ = {"wallet_name": "w1", "chain_id": "bc-2", "output_format": "json"}


@pytest.fixture
def runner():
    return CliRunner()


def test_account_404_reports_not_found_and_zero(runner):
    client_mod = mock.Mock()
    client_mod.get.side_effect = NetworkError("404 Not Found")
    with (
        mock.patch.object(basic_mod, "_resolve_wallet_address", return_value=_ADDR),
        mock.patch.object(basic_mod, "AITBCHTTPClient", return_value=client_mod),
    ):
        result = runner.invoke(balance, ["--name", "w1"], obj=_OBJ)
    assert result.exit_code == 0, result.output
    all_out = result.output + getattr(result, "stderr", "")
    assert "account not found on chain bc-2 (unfunded or not yet synced)" in all_out
    body = json.loads(result.output[result.output.index("{") :])
    assert body["balance"] == 0
    assert body["account_found"] is False


def test_account_200_unchanged(runner):
    client_mod = mock.Mock()
    client_mod.get.return_value = {"balance": 108000000, "nonce": 0, "chain_id": "bc-2"}
    with (
        mock.patch.object(basic_mod, "_resolve_wallet_address", return_value=_ADDR),
        mock.patch.object(basic_mod, "AITBCHTTPClient", return_value=client_mod),
    ):
        result = runner.invoke(balance, ["--name", "w1"], obj=_OBJ)
    assert result.exit_code == 0, result.output
    assert "account not found" not in result.output
    body = json.loads(result.output)
    assert body["balance"] == 108000000
    assert "account_found" not in body
