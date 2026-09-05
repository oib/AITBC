"""Unit tests for aitbc ai submit TEE/confidential flags."""

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
        "job_id": "job-cli-tee-1",
        "payment_id": "pay-1",
        "state": "QUEUED",
    }
    with patch("aitbc_cli.commands.ai.AITBCHTTPClient", return_value=client):
        config = MagicMock()
        config.coordinator_api_url = "http://localhost:8203"
        config.blockchain_rpc_url = "http://localhost:8202"
        config.api_key = "test-key"
        config.timeout = 10
        wallet = ("0x6dB6EBAda5ab0d00041FDCa3a409EE0aA15B5F2f", None, "default")
        with (
            patch("aitbc_cli.commands.ai.get_config", return_value=config),
            patch("aitbc_cli.commands.ai.load_wallet_for_payment", return_value=wallet),
        ):
            yield client


def test_ai_submit_tee_attestation_flags(runner, mock_client):
    from aitbc_cli.commands.ai import ai

    result = runner.invoke(
        ai,
        [
            "submit",
            "--tee-attestation-required",
            "--tee-enclave-id",
            "enc-test",
            "--prompt",
            "hello",
            "--payment",
            "5",
            "--provider-address",
            "0x17B9ED0c7b8b0d0B30Fa3d4BbE2F6a0Abb679d",
        ],
        obj={"output_format": "table", "api_key": "test-key"},
    )

    assert result.exit_code == 0, result.output
    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["constraints"]["tee_attestation_required"] is True
    assert payload["constraints"]["tee_enclave_id"] == "enc-test"


def test_ai_submit_confidential_and_measurement(runner, mock_client):
    from aitbc_cli.commands.ai import ai

    result = runner.invoke(
        ai,
        [
            "submit",
            "--confidential",
            "--enclave-measurement",
            "m1",
            "--prompt",
            "hello",
            "--payment",
            "5",
            "--provider-address",
            "0x17B9ED0c7b8b0d0B30Fa3d4BbE2F6a0Abb679d",
        ],
        obj={"output_format": "table", "api_key": "test-key"},
    )

    assert result.exit_code == 0, result.output
    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["constraints"]["confidential"] is True
    assert payload["constraints"]["tee_attestation_required"] is True
    assert payload["constraints"]["required_enclave_measurement"] == "m1"
    assert payload["constraints"]["tee_enclave_id"] == "m1"


def test_ai_submit_paid_job_without_provider_aborts(runner, mock_client):
    """A paid job with no resolvable provider must fail loudly at submit
    time rather than queue forever (the 3df89318 artifact)."""
    from aitbc_cli.commands.ai import ai

    result = runner.invoke(
        ai,
        [
            "submit",
            "--prompt",
            "hello",
            "--payment",
            "5",
        ],
        obj={"output_format": "table", "api_key": "test-key"},
        env={"SHOP_WALLET_ADDRESS": ""},
    )

    assert result.exit_code != 0
    assert "provider_address is required" in result.output
    mock_client.post.assert_not_called()
