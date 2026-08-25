"""Unit tests for the aitbc zk command group."""

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
    client.get.return_value = {
        "enabled": True,
        "available_circuits": ["receipt_public", "receipt_simple"],
    }
    client.post.return_value = {
        "verified": True,
        "computation_correct": True,
        "privacy_preserved": True,
        "reason": None,
    }
    with patch("aitbc_cli.commands.zk.AITBCHTTPClient", return_value=client):
        config = MagicMock()
        config.coordinator_api_url = "http://localhost:8203"
        config.api_key = "test-key"
        config.timeout = 10
        with patch("aitbc_cli.commands.zk.get_config", return_value=config):
            yield client


def test_zk_group_help(runner):
    from aitbc_cli.commands.zk import zk

    result = runner.invoke(zk, ["--help"], obj={"output_format": "table"})
    assert result.exit_code == 0
    for cmd in ["circuits", "health", "verify"]:
        assert cmd in result.output, f"Missing {cmd} in help output"


def test_zk_circuits_gets_info(runner, mock_client):
    from aitbc_cli.commands.zk import zk

    result = runner.invoke(zk, ["circuits"], obj={"output_format": "table", "api_key": "test-key"})
    assert result.exit_code == 0, result.output
    mock_client.get.assert_called_once_with("/v1/zk/info")


def test_zk_health_gets_health(runner, mock_client):
    from aitbc_cli.commands.zk import zk

    result = runner.invoke(zk, ["health"], obj={"output_format": "table", "api_key": "test-key"})
    assert result.exit_code == 0, result.output
    mock_client.get.assert_called_once_with("/v1/zk/health")


def test_zk_verify_from_job_receipt(runner, mock_client):
    from aitbc_cli.commands.zk import zk

    mock_client.get.return_value = {
        "receipt": {
            "zk_proof": {
                "proof": {"pi_a": ["1"]},
                "public_signals": ["sig1"],
                "circuit": "receipt_public",
            }
        }
    }
    result = runner.invoke(zk, ["verify", "--job-id", "job-1"], obj={"output_format": "table", "api_key": "test-key"})
    assert result.exit_code == 0, result.output
    mock_client.get.assert_called_once_with("/v1/jobs/job-1/result")
    call = mock_client.post.call_args
    assert call[0][0] == "/v1/zk/verify"
    payload = call.kwargs["json"]
    assert payload["circuit_name"] == "receipt_public"
    assert payload["proof"] == {"pi_a": ["1"]}
    assert payload["public_signals"] == ["sig1"]


def test_zk_verify_from_args(runner, mock_client):
    from aitbc_cli.commands.zk import zk

    result = runner.invoke(
        zk,
        [
            "verify",
            "--proof",
            '{"pi_a":["1"]}',
            "--public-signals",
            '["sig1"]',
            "--circuit",
            "receipt_public",
        ],
        obj={"output_format": "table", "api_key": "test-key"},
    )
    assert result.exit_code == 0, result.output
    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["circuit_name"] == "receipt_public"
    assert payload["proof"] == {"pi_a": ["1"]}
    assert payload["public_signals"] == ["sig1"]
