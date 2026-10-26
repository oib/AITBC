"""mining commands must abort non-zero on RPC refusals (CLI-SWALLOW-SWEEP-1, #566)."""

from __future__ import annotations

import json
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from aitbc.exceptions import NetworkError


@pytest.fixture
def runner():
    return CliRunner()


def _network_error(message: str, status_code: int | None = None) -> NetworkError:
    """Build a NetworkError shaped like the real client's wrap of an HTTPError."""
    exc = NetworkError(message)
    if status_code is not None:
        cause = cast(Any, Exception(f"{status_code} Client Error"))
        cause.response = MagicMock(status_code=status_code)
        exc.__cause__ = cause
    return exc


def _invoke(runner, argv, fmt="table", get_exc=None, post_exc=None, result=None):
    from aitbc_cli.commands.mining import mining

    client = MagicMock()
    if get_exc is not None:
        client.get.side_effect = get_exc
    if post_exc is not None:
        client.post.side_effect = post_exc
    if result is not None:
        client.get.return_value = result
        client.post.return_value = result
    with (
        patch("aitbc_cli.commands.mining._client", return_value=client),
        patch("aitbc_cli.commands.mining._load_wallet_address", return_value="0x" + "ab" * 20),
        patch("aitbc_cli.commands.mining._default_wallet_name", return_value="wallet-1"),
    ):
        return runner.invoke(mining, argv, obj={"output_format": fmt})


# --- status -----------------------------------------------------------------


def test_status_401_aborts_table(runner):
    """A 401 from the RPC must not exit 0 (old code printed an error and returned)."""
    result = _invoke(runner, ["status"], get_exc=_network_error("GET request failed: 401", 401))
    assert result.exit_code != 0
    assert "Authentication failed" in result.output


def test_status_401_aborts_json(runner):
    """JSON mode emits exactly one error document and exits non-zero."""
    result = _invoke(runner, ["status"], fmt="json", get_exc=_network_error("GET request failed: 401", 401))
    assert result.exit_code != 0
    doc = json.loads(result.output)
    assert doc.get("error") or doc.get("message"), result.output
    assert "Authentication failed" in doc["message"]


def test_status_other_network_error_aborts(runner):
    """A non-401 refusal (e.g. 503) must also abort rather than print-and-return."""
    result = _invoke(runner, ["status"], get_exc=_network_error("GET request failed: 503", 503))
    assert result.exit_code != 0
    assert "Error getting mining status" in result.output


def test_status_success_rc0(runner):
    result = _invoke(runner, ["status"], result={"status": "mining", "height": 7})
    assert result.exit_code == 0


# --- stop -------------------------------------------------------------------


def test_stop_401_aborts(runner):
    result = _invoke(runner, ["stop"], post_exc=_network_error("POST request failed: 401", 401))
    assert result.exit_code != 0
    assert "Authentication failed" in result.output


def test_stop_other_network_error_aborts(runner):
    result = _invoke(runner, ["stop"], post_exc=_network_error("POST request failed: 503"))
    assert result.exit_code != 0
    assert "Error stopping mining" in result.output


def test_stop_success_rc0(runner):
    result = _invoke(runner, ["stop"], result={"status": "stopped"})
    assert result.exit_code == 0


# --- list -------------------------------------------------------------------


def test_list_401_aborts(runner):
    result = _invoke(runner, ["list"], get_exc=_network_error("GET request failed: 401", 401))
    assert result.exit_code != 0
    assert "Authentication failed" in result.output


def test_list_other_network_error_aborts(runner):
    result = _invoke(runner, ["list"], get_exc=_network_error("GET request failed: 503"))
    assert result.exit_code != 0
    assert "Error listing miners" in result.output


def test_list_success_rc0(runner):
    result = _invoke(runner, ["list"], result={"miners": []})
    assert result.exit_code == 0


# --- start ------------------------------------------------------------------


def test_start_401_aborts_json(runner):
    result = _invoke(
        runner,
        ["start", "--wallet-name", "wallet-1"],
        fmt="json",
        post_exc=_network_error("POST request failed: 401", 401),
    )
    assert result.exit_code != 0
    doc = json.loads(result.output)
    assert "Authentication failed" in doc["message"]


def test_start_404_aborts(runner):
    """A missing mining RPC endpoint is an error, not a successful exit."""
    result = _invoke(
        runner,
        ["start", "--wallet-name", "wallet-1"],
        post_exc=_network_error("POST request failed: 404"),
    )
    assert result.exit_code != 0
    assert "endpoint not found" in result.output


def test_start_success_rc0(runner):
    result = _invoke(runner, ["start", "--wallet-name", "wallet-1"], result={"status": "started"})
    assert result.exit_code == 0


# --- wallet refusal ---------------------------------------------------------


def test_missing_wallet_aborts(runner):
    """A wallet-name refusal already aborted; keep it non-zero."""
    from aitbc_cli.commands.mining import mining

    with (
        patch("aitbc_cli.commands.mining._client", return_value=MagicMock()),
        patch(
            "aitbc_cli.commands.mining._load_wallet_address",
            side_effect=FileNotFoundError("Wallet 'nosuch' not found"),
        ),
    ):
        result = runner.invoke(mining, ["start", "--wallet-name", "nosuch"], obj={"output_format": "table"})
    assert result.exit_code != 0
    assert "not found" in result.output
