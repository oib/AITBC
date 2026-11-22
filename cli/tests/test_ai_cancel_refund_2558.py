"""#2558: ``aitbc ai cancel --refund`` must not relabel a landed cancel as a
cancel failure when only the refund aborts, and the dead ``--wallet`` /
``--password*`` options are gone."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from aitbc_cli.utils.error_handling import NetworkError


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def coord_client():
    """Coordinator client: cancel POST succeeds with an escrowed payment;
    the refund POST raises (the fallback then runs)."""
    client = MagicMock()
    client.post.side_effect = [
        {"job_id": "j1", "state": "CANCELLED", "payment_status": "escrowed", "payment_id": "pay-1"},
        NetworkError("refund endpoint 500"),
    ]
    return client


def _invoke(runner, args, client):
    from aitbc_cli.commands.ai import ai

    config = MagicMock()
    config.coordinator_api_url = "http://localhost:8203"
    config.api_key = "k"
    with (
        patch("aitbc_cli.commands.ai.get_config", return_value=config),
        patch("aitbc_cli.commands.ai.AITBCHTTPClient", return_value=client),
    ):
        return runner.invoke(ai, args, obj={"output_format": "table", "api_key": "k"})


def _text(result) -> str:
    return str(result.output) + str(result.exception or "")


def test_refund_abort_after_cancel_reports_cancel_done(runner, coord_client):
    """Auditor repro: cancel landed, coordinator refund failed, the chain
    fallback aborted — the output must say the job IS cancelled and name the
    refund failure plus the manual command, not 'Error cancelling job: '."""
    with patch(
        "aitbc_cli.commands.market.escrow.refund_escrow",
        side_effect=click.Abort(),
    ):
        result = _invoke(runner, ["cancel", "--job-id", "j1", "--refund"], coord_client)
    text = _text(result)
    assert result.exit_code != 0
    assert "Job j1 cancelled" in text
    assert "cancelled but the refund failed" in text
    assert "aitbc market escrow refund --job-id j1" in text
    assert "Error cancelling job" not in text


def test_refund_success_still_exits_zero(runner):
    client = MagicMock()
    client.post.side_effect = [
        {"job_id": "j1", "state": "CANCELLED", "payment_status": "escrowed", "payment_id": "pay-1"},
        {"refund": "accepted"},
    ]
    result = _invoke(runner, ["cancel", "--job-id", "j1", "--refund"], client)
    assert result.exit_code == 0, _text(result)
    assert "Job j1 cancelled" in result.output


def test_cancel_failure_still_reports_cancel_error(runner):
    client = MagicMock()
    client.post.side_effect = NetworkError("connection refused")
    result = _invoke(runner, ["cancel", "--job-id", "j1"], client)
    assert result.exit_code != 0
    text = _text(result)
    assert "Network error" in text or "cancel" in text.lower()


def test_dead_wallet_options_rejected(runner, coord_client):
    """--wallet/--password* were accepted but never used; they are removed."""
    result = _invoke(runner, ["cancel", "--job-id", "j1", "--wallet", "w1"], coord_client)
    assert result.exit_code != 0
    assert "No such option" in _text(result)
