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
        ["create", "--provider-id", "aitbc-miner-1", "--amount", "10.0", "--required-amount", "10.0"],
        obj={"output_format": "table", "api_key": "test-key"},
    )
    assert result.exit_code == 0, result.output
    call = mock_client.post.call_args
    assert call[0][0] == "/v1/market/providers/aitbc-miner-1/bonds"
    assert call.kwargs["json"]["amount"] == "10.0"
    assert call.kwargs["json"]["required_amount"] == "10.0"


def test_bond_create_with_key_signs_challenge(runner):
    """#1967: --private-key fetches the challenge and posts nonce+signature."""
    from aitbc_cli.commands.bond import bond

    client = MagicMock()
    client.post.side_effect = [
        {"nonce": "n1", "message": "sign-me", "wallet_address": "0xabc", "expires_in": 300},
        {"id": "pb_1", "provider_id": "p1", "status": "active"},
    ]
    config = MagicMock()
    config.coordinator_api_url = "http://localhost:8203"
    config.api_key = "test-key"
    config.timeout = 10
    with (
        patch("aitbc_cli.commands.bond.AITBCHTTPClient", return_value=client),
        patch("aitbc_cli.commands.bond.get_config", return_value=config),
    ):
        result = runner.invoke(
            bond,
            ["create", "--provider-id", "p1", "--bond-id", "cb1", "--private-key", "0x" + "42" * 32],
            obj={"output_format": "table", "api_key": "test-key"},
        )
    assert result.exit_code == 0, result.output
    calls = client.post.call_args_list
    assert calls[0][0][0] == "/v1/market/providers/p1/bonds/challenge"
    body = calls[1].kwargs["json"]
    assert body["bond_id"] == "cb1"
    assert body["challenge_nonce"] == "n1"
    assert body["wallet_signature"].startswith("0x")


def test_bond_status_gets_eligibility(runner, mock_client):
    from aitbc_cli.commands.bond import bond

    result = runner.invoke(
        bond, ["status", "--provider-id", "aitbc-miner-1"], obj={"output_format": "table", "api_key": "test-key"}
    )
    assert result.exit_code == 0, result.output
    mock_client.get.assert_called_once_with("/v1/market/providers/aitbc-miner-1/eligibility")


def test_bond_slash_posts_slash(runner, mock_client):
    from aitbc_cli.commands.bond import bond

    result = runner.invoke(
        bond,
        ["slash", "--provider-id", "aitbc-miner-1", "--reason", "failed high-value job"],
        obj={"output_format": "table", "api_key": "test-key"},
    )
    assert result.exit_code == 0, result.output
    call = mock_client.post.call_args
    assert call[0][0] == "/v1/market/providers/aitbc-miner-1/bonds/slash"
    assert call.kwargs["json"]["reason"] == "failed high-value job"


def test_bond_lock_and_release(runner, mock_client):
    from aitbc_cli.commands.bond import bond

    result = runner.invoke(
        bond, ["lock", "--provider-id", "aitbc-miner-1"], obj={"output_format": "table", "api_key": "test-key"}
    )
    assert result.exit_code == 0, result.output
    assert mock_client.post.call_args[0][0] == "/v1/market/providers/aitbc-miner-1/bonds/lock"

    result = runner.invoke(
        bond, ["release", "--provider-id", "aitbc-miner-1"], obj={"output_format": "table", "api_key": "test-key"}
    )
    assert result.exit_code == 0, result.output
    assert mock_client.post.call_args[0][0] == "/v1/market/providers/aitbc-miner-1/bonds/release"


def test_bond_lock_onchain_submits_bond_lock(runner, tmp_path):
    """lock-onchain wraps transactions send with the BOND_LOCK payload schema."""
    import json

    wallet = tmp_path / "provider-1.json"
    wallet.write_text(json.dumps({"address": "0xProvider", "type": "private"}))

    from aitbc_cli.commands.bond import bond

    with patch("aitbc_cli.utils.wallet_paths.wallet_search_dirs", return_value=[tmp_path]):
        with patch("aitbc_cli.commands.bond.resolve_wallet_password", return_value=""):
            with patch("aitbc_cli.commands.transactions._send_transaction_impl", return_value="0xTxHash") as m:
                result = runner.invoke(
                    bond,
                    [
                        "lock-onchain",
                        "--bond-id",
                        "bond-1",
                        "--escrow-address",
                        "0xEscrow",
                        "--amount",
                        "10",
                        "--lock-days",
                        "90",
                        "--wallet",
                        "provider-1",
                        "--rpc-url",
                        "http://rpc:8202",
                    ],
                    obj={"output_format": "json"},
                )
    assert result.exit_code == 0, result.output
    kwargs = m.call_args.kwargs
    assert kwargs["tx_type"] == "BOND_LOCK"
    assert kwargs["to_address"] if "to_address" in kwargs else m.call_args.args[1] == "0xEscrow"
    payload = kwargs["payload"]
    assert payload == {"bond_id": "bond-1", "provider": "0xProvider", "lock_days": 90}
    assert '"0xTxHash"' in result.output


def test_bond_lock_onchain_missing_wallet_aborts(runner):
    from aitbc_cli.commands.bond import bond

    with patch("aitbc_cli.utils.wallet_paths.wallet_search_dirs", return_value=[]):
        result = runner.invoke(
            bond,
            [
                "lock-onchain",
                "--bond-id",
                "bond-1",
                "--escrow-address",
                "0xEscrow",
                "--amount",
                "10",
                "--wallet",
                "no-such-wallet",
            ],
            obj={"output_format": "table"},
        )
    assert result.exit_code != 0
    assert "not found" in result.output
