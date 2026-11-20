"""`transactions send --key-env NAME` sends signed by an env-held key (#2328).

Env-held keys (FAUCET_PRIVATE_KEY / GENESIS_PRIVATE_KEY in service env files,
ops-signer keys) have no wallet-service keystore, so `--from` could never see
them. `--key-env` takes the env-var NAME only — never key material — derives
the sender address from the key, gates the send behind a confirmation (or
--yes), and shares the wallet path's chain-id/nonce/sign/submit code.
"""

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from eth_keys import keys
from eth_utils import keccak

import aitbc_cli.utils.chain_id as chain_id_mod
from aitbc_cli.commands import transactions as tx_cmd

RECIPIENT = "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B"
# 32 bytes of 0x11 — a valid secp256k1 scalar, deterministic across runs.
TEST_KEY_HEX = "11" * 32
TEST_ENV_NAME = "AITBC_TEST_SEND_KEY"


def _derived_address() -> str:
    return keys.PrivateKey(bytes.fromhex(TEST_KEY_HEX)).public_key.to_checksum_address()


class _FakeHTTP:
    """Minimal AITBCHTTPClient stand-in: nonce lookup + tx submit capture."""

    posted: list[dict] = []

    def __init__(self, base_url="", **kw):
        self.base_url = base_url

    def get(self, endpoint, **kw):
        if "/rpc/account/" in endpoint:
            return {"nonce": 5, "balance": 0}
        raise AssertionError(f"unexpected GET {endpoint}")

    def post(self, endpoint, json=None, **kw):
        assert endpoint == "/rpc/transaction"
        _FakeHTTP.posted.append(json)
        return {"transaction_hash": "0xtesthash"}


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def rpc_mocks(monkeypatch):
    _FakeHTTP.posted = []
    monkeypatch.setenv(TEST_ENV_NAME, TEST_KEY_HEX)
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with (
        patch.object(chain_id_mod, "get_chain_id", return_value="ait-test"),
        patch("aitbc_cli.commands.transactions.AITBCHTTPClient", _FakeHTTP),
    ):
        yield


def _invoke(runner, *extra):
    return runner.invoke(
        tx_cmd.transactions,
        [
            "send",
            "--key-env",
            TEST_ENV_NAME,
            "--to",
            RECIPIENT,
            "--amount",
            "1",
            "--rpc-url",
            "http://node:1",
            *extra,
        ],
        obj={},
    )


def test_env_key_send_submits_signed_tx(runner, rpc_mocks):
    result = _invoke(runner, "--yes")
    assert result.exit_code == 0, result.output
    assert "0xtesthash" in result.output
    # The derived sender address is printed so the operator sees who paid.
    assert _derived_address() in result.output

    assert len(_FakeHTTP.posted) == 1
    tx = _FakeHTTP.posted[0]
    assert tx["from"] == _derived_address()
    assert tx["to"] == RECIPIENT
    assert tx["type"] == "TRANSFER"
    assert tx["nonce"] == 5
    assert tx["chain_id"] == "ait-test"
    assert tx["signature"]

    # The signature must verify against the canonical signed fields — the
    # same message shape the node verifier reconstructs.
    from aitbc.crypto.signature_recovery import recover_address

    signed = {k: tx[k] for k in ("chain_id", "from", "to", "amount", "fee", "nonce", "payload", "type")}
    msg = keccak(json.dumps(signed, sort_keys=True, separators=(",", ":")).encode())
    assert recover_address(msg, tx["signature"]) == _derived_address()


def test_env_key_send_prompts_without_yes(runner, rpc_mocks):
    result = runner.invoke(
        tx_cmd.transactions,
        [
            "send",
            "--key-env",
            TEST_ENV_NAME,
            "--to",
            RECIPIENT,
            "--amount",
            "1",
            "--rpc-url",
            "http://node:1",
        ],
        input="n\n",
        obj={},
    )
    assert result.exit_code != 0
    assert _FakeHTTP.posted == []


def test_env_key_send_confirm_prompt_accepts(runner, rpc_mocks):
    result = runner.invoke(
        tx_cmd.transactions,
        [
            "send",
            "--key-env",
            TEST_ENV_NAME,
            "--to",
            RECIPIENT,
            "--amount",
            "1",
            "--rpc-url",
            "http://node:1",
        ],
        input="y\n",
        obj={},
    )
    assert result.exit_code == 0, result.output
    assert len(_FakeHTTP.posted) == 1


def test_key_env_and_from_are_mutually_exclusive(runner, rpc_mocks, tmp_path):
    result = runner.invoke(
        tx_cmd.transactions,
        [
            "send",
            "--from",
            "w1",
            "--key-env",
            TEST_ENV_NAME,
            "--to",
            RECIPIENT,
            "--amount",
            "1",
            "--yes",
            "--rpc-url",
            "http://node:1",
        ],
        obj={},
    )
    assert result.exit_code != 0
    assert "Exactly one of --from" in result.output
    assert _FakeHTTP.posted == []


def test_send_requires_a_sender(runner, rpc_mocks):
    result = runner.invoke(
        tx_cmd.transactions,
        ["send", "--to", RECIPIENT, "--amount", "1", "--rpc-url", "http://node:1"],
        obj={},
    )
    assert result.exit_code != 0
    assert "Exactly one of --from" in result.output


def test_key_env_rejects_raw_key_material(runner, rpc_mocks):
    # A pasted 32-byte hex key is syntactically a valid env name, so it gets a
    # dedicated refusal — key material must never be accepted as an argument.
    result = runner.invoke(
        tx_cmd.transactions,
        [
            "send",
            "--key-env",
            TEST_KEY_HEX,
            "--to",
            RECIPIENT,
            "--amount",
            "1",
            "--yes",
            "--rpc-url",
            "http://node:1",
        ],
        obj={},
    )
    assert result.exit_code != 0
    assert "not a private key" in result.output
    assert _FakeHTTP.posted == []


def test_key_env_unset_variable_fails(runner, monkeypatch):
    monkeypatch.delenv(TEST_ENV_NAME, raising=False)
    result = runner.invoke(
        tx_cmd.transactions,
        [
            "send",
            "--key-env",
            TEST_ENV_NAME,
            "--to",
            RECIPIENT,
            "--amount",
            "1",
            "--yes",
            "--rpc-url",
            "http://node:1",
        ],
        obj={},
    )
    assert result.exit_code != 0
    assert "not set or is empty" in result.output


def test_key_env_rejects_wrong_length_key(runner, monkeypatch):
    monkeypatch.setenv(TEST_ENV_NAME, "11" * 31)
    result = runner.invoke(
        tx_cmd.transactions,
        [
            "send",
            "--key-env",
            TEST_ENV_NAME,
            "--to",
            RECIPIENT,
            "--amount",
            "1",
            "--yes",
            "--rpc-url",
            "http://node:1",
        ],
        obj={},
    )
    assert result.exit_code != 0
    assert "32 bytes" in result.output


def test_key_env_accepts_0x_prefix(runner, monkeypatch):
    monkeypatch.setenv(TEST_ENV_NAME, "0x" + TEST_KEY_HEX)
    monkeypatch.delenv("CHAIN_ID", raising=False)
    _FakeHTTP.posted = []
    with (
        patch.object(chain_id_mod, "get_chain_id", return_value="ait-test"),
        patch("aitbc_cli.commands.transactions.AITBCHTTPClient", _FakeHTTP),
    ):
        result = runner.invoke(
            tx_cmd.transactions,
            [
                "send",
                "--key-env",
                TEST_ENV_NAME,
                "--to",
                RECIPIENT,
                "--amount",
                "1",
                "--yes",
                "--rpc-url",
                "http://node:1",
            ],
            obj={},
        )
    assert result.exit_code == 0, result.output
    assert _FakeHTTP.posted[0]["from"] == _derived_address()


def test_env_key_impl_shares_nonce_offset(runner, rpc_mocks):
    """--nonce-offset applies to env-key sends exactly like wallet sends."""
    result = _invoke(runner, "--yes", "--nonce-offset", "3")
    assert result.exit_code == 0, result.output
    assert _FakeHTTP.posted[0]["nonce"] == 8


def test_env_key_zero_amount_transfer_rejected(runner, rpc_mocks):
    result = runner.invoke(
        tx_cmd.transactions,
        [
            "send",
            "--key-env",
            TEST_ENV_NAME,
            "--to",
            RECIPIENT,
            "--amount",
            "0",
            "--yes",
            "--rpc-url",
            "http://node:1",
        ],
        obj={},
    )
    assert result.exit_code != 0
    assert _FakeHTTP.posted == []
