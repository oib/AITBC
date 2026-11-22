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


class _HttpCause(Exception):
    """Exception carrying a ``.response`` like requests.HTTPError."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"{status_code} Error")
        self.response = mock.Mock(status_code=status_code)


def _http_error(status_code: int) -> NetworkError:
    """NetworkError shaped like the real client's wrap of a requests.HTTPError."""
    err = NetworkError(f"{status_code} Error")
    err.__cause__ = _HttpCause(status_code)
    return err


def test_account_404_reports_not_found_and_zero(runner):
    client_mod = mock.Mock()
    client_mod.get.side_effect = _http_error(404)
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
