"""Unit tests for the aitbc tee command group."""

from __future__ import annotations

import os
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
    for cmd in ["attest", "keygen", "launch", "register", "status", "verify"]:
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
        ["register", "enc-test", "--public-key", "cGt0ZXN0", "--agent-id", "agent-1"],
        obj={"output_format": "table"},
    )

    assert result.exit_code == 0
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "/v1/tee/enclaves"
    payload = call_args.kwargs["json"]
    assert payload["enclave_id"] == "enc-test"
    assert payload["agent_id"] == "agent-1"
    assert payload["public_key"] == "cGt0ZXN0"
    assert payload["status"] == "active"


def test_tee_register_requires_public_key(runner, mock_client):
    """Security fix (2026-08-24): register must refuse to fabricate a placeholder key.

    A fabricated key with no matching private half would permanently lock
    out real attestations for that enclave_id once pinning is enforced.
    """
    from aitbc_cli.commands.tee import tee

    result = runner.invoke(
        tee,
        ["register", "enc-test", "--agent-id", "agent-1"],
        obj={"output_format": "table"},
    )

    assert result.exit_code != 0
    assert "--public-key" in (result.output + str(result.exception))
    mock_client.post.assert_not_called()


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


def test_tee_attest_with_key_file_is_stable_across_calls(tmp_path, runner, mock_client):
    """Part 4 (2026-08-24): --key-file gives attest a signing identity that
    survives across separate invocations, unlike the default fresh-per-call key.
    """
    from aitbc.tee import AttestationQuote
    from aitbc_cli.commands.tee import tee

    key_file = str(tmp_path / "enc.key")
    for _ in range(2):
        result = runner.invoke(
            tee,
            ["attest", "enc-test", "--measurement", "m1", "--key-file", key_file],
            obj={"output_format": "table"},
        )
        assert result.exit_code == 0

    quotes = [
        AttestationQuote.from_base64(call.kwargs["json"]["quote"]) for call in mock_client.post.call_args_list
    ]
    assert quotes[0].public_key == quotes[1].public_key


def test_tee_keygen_creates_a_key_file_and_prints_its_public_key(tmp_path, runner):
    from aitbc_cli.commands.tee import tee

    key_file = str(tmp_path / "new.key")
    result = runner.invoke(tee, ["keygen", "--key-file", key_file], obj={"output_format": "table"})

    assert result.exit_code == 0
    assert os.path.exists(key_file)
    assert "public_key" in result.output.lower() or "public key" in result.output.lower()


def test_tee_keygen_is_idempotent(tmp_path, runner):
    """Re-running keygen against an existing file must not regenerate the key."""
    from aitbc_cli.commands.tee import tee

    key_file = str(tmp_path / "existing.key")
    with open(key_file, "wb") as f:
        f.write(b"0" * 32)

    result = runner.invoke(tee, ["keygen", "--key-file", key_file], obj={"output_format": "table"})

    assert result.exit_code == 0
    with open(key_file, "rb") as f:
        assert f.read() == b"0" * 32


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
