"""AUDIT-CROSSCHAIN-ABORT-RELABEL-1 (#2555): abort() inside the ops try was
re-caught by ``except _OPS_ERRORS`` (CLIError is a member), so a swap's own
error surfaced as 'Network error: Error: …'. CLIError now passes through.
"""

from __future__ import annotations

from unittest import mock

from click.testing import CliRunner

import aitbc_cli.commands.cross_chain as cross_mod
from aitbc_cli.commands.cross_chain import confirm, status


def _client(get_result=None, get_side_effect=None):
    client = mock.Mock()
    client.get = mock.Mock(side_effect=get_side_effect, return_value=get_result)
    client.post = mock.Mock(return_value={})
    return client


def test_status_swap_error_not_relabelled_network():
    client = _client(get_result={"swap_id": "s1", "status": "failed", "error": "insufficient liquidity"})
    with mock.patch.object(cross_mod, "AITBCHTTPClient", return_value=client):
        r = CliRunner().invoke(status, ["--swap-id", "s1"], obj={"output_format": "table"})
    assert r.exit_code != 0
    assert "Error: insufficient liquidity" in r.output
    assert "Network error" not in r.output


def test_confirm_no_proof_not_relabelled():
    client = _client(get_result={"proof": None})
    with (
        mock.patch.object(cross_mod, "AITBCHTTPClient", return_value=client),
        mock.patch.object(cross_mod, "_load_signing_wallet", return_value=("0xabc", "0xkey")),
        mock.patch.object(cross_mod, "_sign_request", return_value="sig"),
    ):
        r = CliRunner().invoke(confirm, ["--transfer-id", "t1"], obj={"output_format": "table"})
    assert r.exit_code != 0
    assert "No proof returned" in r.output
    assert "Confirm failed" not in r.output


def test_status_network_failure_still_labelled():
    from aitbc_cli.utils.http_client import NetworkError

    client = _client(get_side_effect=NetworkError("connection refused"))
    with mock.patch.object(cross_mod, "AITBCHTTPClient", return_value=client):
        r = CliRunner().invoke(status, ["--swap-id", "s1"], obj={"output_format": "table"})
    assert r.exit_code != 0
    assert "Network error" in r.output
