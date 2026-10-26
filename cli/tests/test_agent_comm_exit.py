"""agent-comm receive must abort non-zero on a refusal (CLI-AGENTCOMM-RC0-1)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


def _invoke(runner, fmt, exc=None, bypass_wallet=False):
    from aitbc_cli.commands.agent_comm import agent_comm

    client = MagicMock()
    if exc is not None:
        client.get.side_effect = exc
    patches = [patch("aitbc_cli.commands.agent_comm._agent_client", return_value=client)]
    if bypass_wallet:
        patches.append(
            patch(
                "aitbc_cli.commands.agent_comm.load_signing_wallet",
                return_value=("addr", "key"),
            )
        )
    with patches[0]:
        if bypass_wallet:
            with patches[1]:
                result = runner.invoke(
                    agent_comm,
                    ["receive", "--receiver-id", "agent-x", "--format", fmt],
                    obj={"output_format": fmt},
                )
        else:
            result = runner.invoke(
                agent_comm,
                [
                    "receive",
                    "--receiver-id",
                    "agent-x",
                    "--wallet",
                    "nosuch-cli565",
                    "--password-file",
                    "/nonexistent-cli565.pw",
                    "--format",
                    fmt,
                ],
                obj={"output_format": fmt},
            )
    return result


def test_receive_wallet_refusal_aborts(runner):
    """A wallet/password refusal exits non-zero (old code swallowed to rc 0)."""
    result = _invoke(runner, "table")
    assert result.exit_code != 0
    assert "not found" in result.output or "Cannot read" in result.output


def test_receive_error_aborts_table(runner):
    """A broad exception in the try block aborts instead of printing a table."""
    result = _invoke(runner, "table", exc=ConnectionError("boom"), bypass_wallet=True)
    assert result.exit_code != 0
    assert "Error receiving messages" in result.output


def test_receive_error_aborts_json(runner):
    """JSON mode emits exactly one error document and aborts."""
    result = _invoke(runner, "json", exc=ConnectionError("boom"), bypass_wallet=True)
    assert result.exit_code != 0
    doc = json.loads(result.output)
    assert doc.get("error") or doc.get("message"), result.output
