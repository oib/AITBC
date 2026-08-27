"""Safe local integration tests for the ``aitbc transactions`` command.

These tests point at ``127.0.0.1:8202`` and exercise the full local
transaction-signing path using a deterministic, in-memory wallet.
"""

import json
import os
from decimal import Decimal

import pytest
from click.testing import CliRunner
from eth_account import Account
from eth_keys import keys
from eth_utils import keccak

os.environ["AITBC_SKIP_ENV_FILES"] = "1"

from aitbc_cli.commands.transactions import _send_transaction_impl, transactions


@pytest.fixture
def funded_wallet(tmp_path, monkeypatch):
    """Create a temporary unencrypted wallet and point transactions at it."""
    wallets_dir = tmp_path / "wallets"
    wallets_dir.mkdir(parents=True, exist_ok=True)

    # Deterministic test secp256k1 key so the signing test is reproducible.
    private_key_hex = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    acct = Account.from_key(private_key_hex)
    wallet = {
        "name": "test",
        "address": acct.address,
        "private_key": private_key_hex,
    }
    (wallets_dir / "test.json").write_text(json.dumps(wallet))

    # Make the CLI use this keystore directory.
    monkeypatch.setattr("aitbc_cli.commands.transactions.wallet_dir", lambda: wallets_dir)
    return wallet, private_key_hex, wallets_dir


@pytest.fixture
def mock_http_client(monkeypatch):
    """Replace AITBCHTTPClient with a fake that records calls."""
    calls = {"get": [], "post": []}
    responses = {
        "/health": {"supported_chains": ["ait-hub.aitbc.bubuit.net"]},
        "/rpc/account/": {"nonce": 7},
        "/rpc/transaction": {"transaction_hash": "0xabc123"},
        "/rpc/estimate-fee": {"fee_ait": "0.001"},
    }

    class FakeClient:
        def __init__(self, base_url=None, timeout=10):
            self.base_url = base_url or "http://127.0.0.1:8202"

        def get(self, path, **kwargs):
            calls["get"].append((self.base_url, path, kwargs))
            for key, value in responses.items():
                if path.startswith(key):
                    return value
            return {}

        def post(self, path, **kwargs):
            calls["post"].append((self.base_url, path, kwargs))
            for key, value in responses.items():
                if path.startswith(key):
                    return value
            return {}

    # Patch all the places that hold a local reference to AITBCHTTPClient.
    monkeypatch.setattr("aitbc_cli.commands.transactions.AITBCHTTPClient", FakeClient)
    monkeypatch.setattr("aitbc_cli.utils.chain_id.AITBCHTTPClient", FakeClient)
    return calls


def test_send_transaction_signs_with_secp256k1(mock_http_client, funded_wallet):
    """A transaction is canonically serialized, signed, and submitted locally."""
    calls = mock_http_client
    wallet, private_key_hex, keystore_dir = funded_wallet

    tx_hash = _send_transaction_impl(
        from_wallet="test",
        to_address="0x0000000000000000000000000000000000000000",
        amount=Decimal("1.0"),
        fee=Decimal("0.001"),
        password="",
        keystore_dir=keystore_dir,
        rpc_url="http://127.0.0.1:8202",
    )

    assert tx_hash == "0xabc123"

    # The signed payload was submitted to the local RPC node.
    assert len(calls["post"]) == 1
    _, path, kwargs = calls["post"][0]
    assert path == "/rpc/transaction"
    tx_payload = kwargs["json"]

    # Fields used by the verifier are present.
    assert tx_payload["from"] == wallet["address"]
    assert tx_payload["to"] == "0x0000000000000000000000000000000000000000"
    assert tx_payload["chain_id"] == "ait-hub.aitbc.bubuit.net"
    assert tx_payload["type"] == "TRANSFER"
    assert "signature" in tx_payload

    # The signature is recoverable from the canonical message.
    unsigned = {k: v for k, v in tx_payload.items() if k != "signature"}
    message = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    signature_bytes = bytes.fromhex(tx_payload["signature"])
    signature = keys.Signature(signature_bytes)
    public_key = signature.recover_public_key_from_msg_hash(keccak(message))
    expected_private = keys.PrivateKey(bytes.fromhex(private_key_hex))
    assert public_key.to_address() == expected_private.public_key.to_address()


def test_send_cli_invocation(mock_http_client, funded_wallet):
    """The ``transactions send`` CLI uses safe local defaults and succeeds."""
    calls = mock_http_client
    runner = CliRunner()
    result = runner.invoke(
        transactions,
        [
            "send",
            "--from",
            "test",
            "--to",
            "0x0000000000000000000000000000000000000000",
            "--amount",
            "1.0",
            "--fee",
            "0.001",
            "--rpc-url",
            "http://127.0.0.1:8202",
        ],
    )
    assert result.exit_code == 0, result.output
    assert any(path == "/rpc/transaction" for _, path, _ in calls["post"])
