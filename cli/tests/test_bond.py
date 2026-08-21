"""Unit tests for the aitbc bond command group."""
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
        "id": "pb_1234567890",
        "provider_id": "aitbc-miner-1",
        "bond_id": "bond-aitbc-miner-1",
        "status": "active",
        "amount": "10.0",
        "required_amount": "10.0",
        "meta": {},
        "created_at": "",
        "updated_at": "",
    }
    client.get.return_value = {
        "provider_id": "aitbc-miner-1",
        "eligible": True,
        "status": "active",
        "amount": "10.0",
        "required_amount": "10.0",
        "bond_id": "bond-aitbc-miner-1",
    }
    with patch("aitbc_cli.commands.bond.AITBCHTTPClient", return_value=client):
        config = MagicMock()
        config.coordinator_api_url = "http://localhost:8203"
        config.api_key = "test-key"
        config.timeout = 10
        with patch("aitbc_cli.commands.bond.get_config", return_value=config):
            yield client


def test_bond_group_help(runner):
    from aitbc_cli.commands.bond import bond

    result = runner.invoke(bond, ["--help"], obj={"output_format": "table"})
    assert result.exit_code == 0
    for cmd in ["create", "status", "top-up", "lock", "release", "slash"]:
        assert cmd in result.output, f"Missing {cmd} in help output"


def test_bond_create_posts_bonds(runner, mock_client):
    from aitbc_cli.commands.bond import bond

    result = runner.invoke(
        bond,
        ["create", "aitbc-miner-1", "--amount", "10.0", "--required-amount", "10.0"],
        obj={"output_format": "table", "api_key": "test-key"},
    )
    assert result.exit_code == 0, result.output
    call = mock_client.post.call_args
    assert call[0][0] == "/v1/marketplace/providers/aitbc-miner-1/bonds"
    assert call.kwargs["json"]["amount"] == "10.0"
    assert call.kwargs["json"]["required_amount"] == "10.0"


def test_bond_status_gets_eligibility(runner, mock_client):
    from aitbc_cli.commands.bond import bond

    result = runner.invoke(bond, ["status", "aitbc-miner-1"], obj={"output_format": "table", "api_key": "test-key"})
    assert result.exit_code == 0, result.output
    mock_client.get.assert_called_once_with("/v1/marketplace/providers/aitbc-miner-1/eligibility")


def test_bond_slash_posts_slash(runner, mock_client):
    from aitbc_cli.commands.bond import bond

    result = runner.invoke(
        bond,
        ["slash", "aitbc-miner-1", "--reason", "failed high-value job"],
        obj={"output_format": "table", "api_key": "test-key"},
    )
    assert result.exit_code == 0, result.output
    call = mock_client.post.call_args
    assert call[0][0] == "/v1/marketplace/providers/aitbc-miner-1/bonds/slash"
    assert call.kwargs["json"]["reason"] == "failed high-value job"


def test_bond_lock_and_release(runner, mock_client):
    from aitbc_cli.commands.bond import bond

    result = runner.invoke(bond, ["lock", "aitbc-miner-1"], obj={"output_format": "table", "api_key": "test-key"})
    assert result.exit_code == 0, result.output
    assert mock_client.post.call_args[0][0] == "/v1/marketplace/providers/aitbc-miner-1/bonds/lock"

    result = runner.invoke(bond, ["release", "aitbc-miner-1"], obj={"output_format": "table", "api_key": "test-key"})
    assert result.exit_code == 0, result.output
    assert mock_client.post.call_args[0][0] == "/v1/marketplace/providers/aitbc-miner-1/bonds/release"
