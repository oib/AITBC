"""Unit tests for the aitbc ai submit --auto-reinvest-pct wiring."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.post.return_value = {
        "job_id": "j_reinvest_1",
        "payment_id": "p_reinvest_1",
        "payment_status": "escrowed",
    }
    with patch("aitbc_cli.commands.ai.AITBCHTTPClient", return_value=client):
        config = MagicMock()
        config.coordinator_api_url = "http://localhost:8203"
        config.api_key = "test-key"
        config.timeout = 10
        wallet = ("0x6dB6EBAda5ab0d00041FDCa3a409EE0aA15B5F2f", None, "genesis")
        with (
            patch("aitbc_cli.commands.ai.get_config", return_value=config),
            patch("aitbc_cli.commands.ai.load_wallet_for_payment", return_value=wallet),
        ):
            yield client


def test_ai_submit_with_auto_reinvest_pct(runner, mock_client):
    from aitbc_cli.commands.ai import submit

    result = runner.invoke(
        submit,
        [
            "--prompt",
            "auto reinvest",
            "--payment",
            "5",
            "--auto-reinvest-pct",
            "50",
            "--wallet",
            "genesis",
            "--buyer-address",
            "0x6dB6EBAda5ab0d00041FDCa3a409EE0aA15B5F2f",
            "--provider-address",
            "0xb8A506Cd711eb63630081cCfD907Fa0545B3BE9E",
        ],
        obj={"output_format": "table", "api_key": "test-key"},
    )
    assert result.exit_code == 0, result.output
    call = mock_client.post.call_args
    assert call[0][0] == "/v1/jobs"
    assert call.kwargs["json"]["constraints"]["auto_reinvest_pct"] == 50.0
