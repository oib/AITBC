"""Fail-loud chain-id resolution for the operations.py paths.

vote/proposal POST the id to /rpc/governance/*; ai message signs it into a
TRANSFER; get_proposal's lookup was dead code and is removed. Resolution:
explicit > CHAIN_ID > strict probe of the submit URL.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

ACCOUNT = "0x6dB6EBAda5ab0d00041FDCa3a409EE0aA15B5F2f"
PROVIDER = "0x17B9ED0c7b8b0d0B30Fa3d4BbE2F6a0Abb679d"


@pytest.fixture
def runner():
    return CliRunner()


def _failing_probe():
    prober = MagicMock()
    prober.get.side_effect = RuntimeError("connection refused")
    return patch("aitbc_cli.utils.chain_id.AITBCHTTPClient", return_value=prober)


def _ok_probe(chain_id="ait-probed"):
    prober = MagicMock()
    prober.get.return_value = {"chain_id": chain_id}
    return patch("aitbc_cli.utils.chain_id.AITBCHTTPClient", return_value=prober)


# --- operations governance vote / proposal (mutating POSTs) ---


def _ops_patches(prober):
    config = MagicMock()
    config.blockchain_rpc_url = "http://rpc:8202"
    client = MagicMock()
    client.post.return_value = {}
    client.get.return_value = {"nonce": 7}
    return (
        patch("aitbc_cli.commands.operations.get_config", return_value=config),
        patch("aitbc_cli.commands.operations.AITBCHTTPClient", return_value=client),
        patch("aitbc_cli.commands.operations.find_wallet_file", return_value=Path("/tmp/w.json")),
        patch("aitbc_cli.commands.operations._load_wallet", return_value={"address": ACCOUNT}),
        prober,
        client,
    )


def _invoke_ops(runner, args, **obj):
    from aitbc_cli.commands.operations import operations

    return runner.invoke(operations, args, obj={"output_format": "table", **obj})


VOTE_ARGS = ["governance", "vote", "--proposal-id", "p1", "--vote", "for", "--wallet", "w"]
PROPOSAL_ARGS = [
    "governance",
    "proposal",
    "--proposal-id",
    "p1",
    "--title",
    "t",
    "--description",
    "d",
    "--wallet",
    "w",
]


def test_vote_aborts_when_chain_probe_fails(runner):
    *patches, probe, client = _ops_patches(_failing_probe())
    with patches[0], patches[1], patches[2], patches[3], probe:
        result = _invoke_ops(runner, VOTE_ARGS)
    assert result.exit_code != 0
    client.post.assert_not_called()


def test_vote_env_chain_id_wins(runner, monkeypatch):
    monkeypatch.setenv("CHAIN_ID", "env-chain")
    *patches, probe, client = _ops_patches(_failing_probe())
    with patches[0], patches[1], patches[2], patches[3], probe:
        result = _invoke_ops(runner, VOTE_ARGS)
    assert result.exit_code == 0, result.output
    assert client.post.call_args.kwargs["json"]["chain_id"] == "env-chain"


def test_vote_explicit_chain_id_wins(runner):
    *patches, probe, client = _ops_patches(_failing_probe())
    with patches[0], patches[1], patches[2], patches[3], probe as prober_cls:
        result = _invoke_ops(runner, VOTE_ARGS, chain_id_explicit="flag-chain")
    assert result.exit_code == 0, result.output
    prober_cls.assert_not_called()
    assert client.post.call_args.kwargs["json"]["chain_id"] == "flag-chain"


def test_proposal_aborts_when_chain_probe_fails(runner):
    *patches, probe, client = _ops_patches(_failing_probe())
    with patches[0], patches[1], patches[2], patches[3], probe:
        result = _invoke_ops(runner, PROPOSAL_ARGS)
    assert result.exit_code != 0
    client.post.assert_not_called()


def test_proposal_env_chain_id_wins(runner, monkeypatch):
    monkeypatch.setenv("CHAIN_ID", "env-chain")
    *patches, probe, client = _ops_patches(_failing_probe())
    with patches[0], patches[1], patches[2], patches[3], probe:
        result = _invoke_ops(runner, PROPOSAL_ARGS)
    assert result.exit_code == 0, result.output
    assert client.post.call_args.kwargs["json"]["chain_id"] == "env-chain"


# --- get-proposal: dead lookup removed, command still works (regression) ---


def test_get_proposal_still_reads(runner):
    *patches, probe, client = _ops_patches(_ok_probe())
    with patches[0], patches[1], patches[2], patches[3], probe:
        result = _invoke_ops(runner, ["governance", "get-proposal", "--proposal-id", "p1"])
    assert result.exit_code == 0, result.output
    assert client.get.call_args.args[0] == "/rpc/governance/proposal/p1"


# --- operations agent message (real signing path: chain id + nonce) ---


def _message_patches(tmp_path, prober, nonce=7):
    wallet = tmp_path / "w.json"
    wallet.write_text(json.dumps({"address": ACCOUNT}))
    client = MagicMock()
    client.get.return_value = {} if nonce is None else {"nonce": nonce}
    client.post.return_value = {"transaction_hash": "0xtx"}
    return (
        patch("aitbc_cli.commands.operations.wallet_dir", return_value=tmp_path),
        patch("aitbc_cli.commands.operations.decrypt_private_key", return_value="ab" * 32),
        patch("aitbc_cli.commands.operations.AITBCHTTPClient", return_value=client),
        prober,
        client,
    )


MESSAGE_ARGS = [
    "agent",
    "message",
    "--agent",
    PROVIDER,
    "--message",
    "hi",
    "--wallet",
    "w",
    "--password",
    "pw",
]


def test_message_aborts_when_chain_probe_fails(runner, tmp_path):
    *patches, probe, client = _message_patches(tmp_path, _failing_probe())
    with patches[0], patches[1], patches[2], probe:
        result = _invoke_ops(runner, MESSAGE_ARGS)
    assert result.exit_code != 0
    client.post.assert_not_called()


def test_message_env_chain_id_wins(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("CHAIN_ID", "env-chain")
    *patches, probe, client = _message_patches(tmp_path, _failing_probe())
    with patches[0], patches[1], patches[2], probe as prober_cls:
        result = _invoke_ops(runner, MESSAGE_ARGS)
    assert result.exit_code == 0, result.output
    prober_cls.assert_not_called()
    sent = client.post.call_args.kwargs["json"]
    assert sent["chain_id"] == "env-chain"
    assert sent["nonce"] == 7


def test_message_aborts_when_nonce_missing(runner, tmp_path):
    *patches, probe, client = _message_patches(tmp_path, _ok_probe(), nonce=None)
    with patches[0], patches[1], patches[2], probe:
        result = _invoke_ops(runner, MESSAGE_ARGS)
    assert result.exit_code != 0
    client.post.assert_not_called()
