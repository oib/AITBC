"""#2937: ``aitbc agent verify-identity`` must sign the freshness-bound
``agent_verify`` message — ``/rpc/identity/verify`` has required it since
b2691ce92 (#2936) and the unsigned POST 403'd.

Pins:

* the posted body carries ``nonce``/``timestamp``/``signature`` and the
  signature verifies against ``--verifier-address`` over the exact
  ``sign_data`` the node rebuilds;
* the signer wallet must control ``--verifier-address``;
* no configured wallet aborts before any request.
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from eth_utils import keccak

pytest.importorskip("eth_account", reason="signature pins need eth-account")

from eth_account import Account  # noqa: E402

from aitbc.crypto.signature_recovery import verify_signature  # noqa: E402

PRIVATE_KEY = "0x" + "42" * 32
ACCOUNT = Account.from_key(PRIVATE_KEY)
VERIFIER = ACCOUNT.address
OTHER = "0x" + "43" * 32


@pytest.fixture
def runner():
    return CliRunner()


def _invoke(runner, args, monkeypatch, client):
    monkeypatch.setenv("CHAIN_ID", "env-chain")
    monkeypatch.delenv("AITBC_DEFAULT_WALLET", raising=False)
    config = MagicMock()
    config.blockchain_rpc_url = "http://rpc:8202"
    config.blockchain_rpc_api_key = None
    from aitbc_cli.commands.agent_sdk import agent

    with (
        patch("aitbc_cli.commands.agent_sdk.get_config", return_value=config),
        patch("aitbc_cli.commands.agent_sdk.AITBCHTTPClient", return_value=client),
        patch(
            "aitbc_cli.commands.agent_sdk.load_signing_wallet",
            return_value=(ACCOUNT.address, PRIVATE_KEY),
        ),
    ):
        return runner.invoke(agent, args, obj={"output_format": "table"})


def _client():
    client = MagicMock()
    client.get.return_value = {"nonce": 41, "balance": "0"}
    client.post.return_value = {"success": True, "is_verified": True}
    return client


def test_verify_identity_posts_verifier_signature(runner, monkeypatch):
    client = _client()
    result = _invoke(
        runner,
        ["verify-identity", "--agent-id", "a1", "--verifier-address", VERIFIER, "--wallet", "verifier"],
        monkeypatch,
        client,
    )
    assert result.exit_code == 0, result.output
    body = client.post.call_args.kwargs["json"]
    assert client.post.call_args.args[0] == "/rpc/identity/verify"
    assert body["agent_id"] == "a1"
    assert body["chain_id"] == "env-chain"
    assert body["nonce"] == 41
    assert isinstance(body["timestamp"], int)
    assert abs(time.time() - body["timestamp"]) < 60
    sign_data = {
        "action": "agent_verify",
        "agent_id": "a1",
        "chain_id": "env-chain",
        "nonce": body["nonce"],
        "timestamp": body["timestamp"],
        "verifier_address": VERIFIER.lower(),
    }
    message = json.dumps(sign_data, sort_keys=True, separators=(",", ":")).encode()
    assert verify_signature(keccak(message), body["signature"], VERIFIER) is True


def test_verify_identity_rejects_wallet_for_other_address(runner, monkeypatch):
    client = _client()
    result = _invoke(
        runner,
        ["verify-identity", "--agent-id", "a1", "--verifier-address", OTHER, "--wallet", "verifier"],
        monkeypatch,
        client,
    )
    assert result.exit_code != 0
    assert "does not match" in result.output
    client.post.assert_not_called()


def test_verify_identity_aborts_without_signing_wallet(runner, monkeypatch):
    client = _client()
    monkeypatch.setenv("CHAIN_ID", "env-chain")
    monkeypatch.delenv("AITBC_DEFAULT_WALLET", raising=False)
    config = MagicMock()
    config.blockchain_rpc_url = "http://rpc:8202"
    config.blockchain_rpc_api_key = None
    from aitbc_cli.commands.agent_sdk import agent

    with (
        patch("aitbc_cli.commands.agent_sdk.get_config", return_value=config),
        patch("aitbc_cli.commands.agent_sdk.AITBCHTTPClient", return_value=client),
    ):
        result = runner.invoke(
            agent,
            ["verify-identity", "--agent-id", "a1", "--verifier-address", VERIFIER],
            obj={"output_format": "table"},
        )
    assert result.exit_code != 0
    assert "--wallet" in result.output
    client.post.assert_not_called()
