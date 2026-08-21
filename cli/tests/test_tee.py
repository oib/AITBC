"""Unit tests for the aitbc tee command group."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    """Create a Click CLI runner."""
    return CliRunner()


@pytest.fixture
def mock_client():
    """Mock AITBCHTTPClient for TEE coordinator calls."""
    client = MagicMock()
    client.post.return_value = {
        "id": "ta_cli_1",
        "enclave_id": "enc-test",
        "measurement": "m1",
        "status": "verified",
        "quote": "cXVvdGVibG9i",
        "created_at": "2026-08-21T12:00:00+00:00",
    }
    client.get.return_value = {
        "id": "ei_cli_1",
        "enclave_id": "enc-test",
        "public_key": "cGt0ZXN0",
        "agent_id": "agent-1",
        "status": "active",
    }
    with patch("aitbc_cli.commands.tee.AITBCHTTPClient", return_value=client):
        with patch(
            "aitbc_cli.commands.tee.get_config",
            return_value=MagicMock(coordinator_api_url="http://localhost:8203", api_key="test-key", timeout=10),
        ):
            with patch(
                "aitbc_cli.commands.tee.AuthManager", return_value=MagicMock(get_credential=MagicMock(return_value=""))
            ):
                yield client


def test_tee_group_help(runner):
    """The tee group should list all subcommands."""
    from aitbc_cli.commands.tee import tee

    result = runner.invoke(tee, ["--help"], obj={"output_format": "table"})
    assert result.exit_code == 0
    for cmd in ["attest", "launch", "register", "status", "verify"]:
        assert cmd in result.output, f"Missing {cmd} in help output"


def test_tee_attest_posts_quote(runner, mock_client):
    """attest should generate a quote and POST it to /v1/tee/attestations."""
    from aitbc_cli.commands.tee import tee

    result = runner.invoke(
        tee,
        ["attest", "enc-test", "--measurement", "m1"],
        obj={"output_format": "table"},
    )

    assert result.exit_code == 0
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "/v1/tee/attestations"
    payload = call_args.kwargs["json"]
    assert payload["enclave_id"] == "enc-test"
    assert payload["measurement"] == "m1"
    assert payload["quote"]


def test_tee_register_posts_enclave(runner, mock_client):
    """register should POST an enclave identity to /v1/tee/enclaves."""
    from aitbc_cli.commands.tee import tee

    result = runner.invoke(
        tee,
        ["register", "enc-test", "--agent-id", "agent-1"],
        obj={"output_format": "table"},
    )

    assert result.exit_code == 0
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "/v1/tee/enclaves"
    payload = call_args.kwargs["json"]
    assert payload["enclave_id"] == "enc-test"
    assert payload["agent_id"] == "agent-1"
    assert payload["public_key"]
    assert payload["status"] == "active"


def test_tee_register_uses_provided_public_key(runner, mock_client):
    """register should honor an explicitly provided public key."""
    from aitbc_cli.commands.tee import tee

    result = runner.invoke(
        tee,
        ["register", "enc-test", "--public-key", "mykey", "--agent-id", "agent-1"],
        obj={"output_format": "table"},
    )

    assert result.exit_code == 0
    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["public_key"] == "mykey"


def test_tee_status_fetches_enclave(runner, mock_client):
    """status should GET /v1/tee/enclaves/{enclave_id}."""
    from aitbc_cli.commands.tee import tee

    result = runner.invoke(
        tee,
        ["status", "enc-test"],
        obj={"output_format": "table"},
    )

    assert result.exit_code == 0
    mock_client.get.assert_called_once()
    assert mock_client.get.call_args[0][0] == "/v1/tee/enclaves/enc-test"


def test_tee_verify_local(runner):
    """verify should validate a quote locally without coordinator calls."""
    from aitbc.tee.attestation import QuoteGenerator
    from aitbc_cli.commands.tee import tee

    quote = QuoteGenerator("enc-test", signing_key=b"secret").generate(quote_id="q1", enclave_id="enc-test", measurement="m1")
    quote_b64 = quote.to_base64()

    result = runner.invoke(
        tee,
        ["verify", "--quote", quote_b64, "--measurement", "m1"],
        obj={"output_format": "table"},
    )

    assert result.exit_code == 0
    assert "valid" in result.output.lower()
