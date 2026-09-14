"""Unit tests for the `aitbc agent-task` command group (paid A2A delegation)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

pytest.importorskip("eth_account", reason="envelope signing tests need eth-account")

from eth_account import Account  # noqa: E402

_TEST_KEY = "0x" + "42" * 32


def _real_wallet():
    """A real secp256k1 account so hire's envelope signing genuinely runs."""
    return Account.from_key(_TEST_KEY)


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_client():
    """Mock AITBCHTTPClient for agent-task commands."""
    client = MagicMock()
    client.get.return_value = {
        "status": "success",
        "agent": {"agent_id": "aitbc-miner-1", "metadata": {"wallet": "0xProv"}},
    }
    client.post.return_value = {"status": "success", "message_id": "msg-1"}
    with patch("aitbc_cli.commands.agent_task.AITBCHTTPClient", return_value=client):
        with patch(
            "aitbc_cli.commands.agent_task.get_config",
            return_value=MagicMock(agent_coordinator_url="http://coord.local", blockchain_rpc_url="http://rpc.local:8202"),
        ):
            yield client


def test_agent_task_group_help(runner):
    from aitbc_cli.commands.agent_task import agent_task

    result = runner.invoke(agent_task, ["--help"], obj={"output_format": "table"})
    assert result.exit_code == 0
    for cmd in ["hire", "status", "result"]:
        assert cmd in result.output, f"Missing {cmd} in help output"


def test_hire_help(runner):
    from aitbc_cli.commands.agent_task import agent_task

    result = runner.invoke(agent_task, ["hire", "--help"], obj={"output_format": "table"})
    assert result.exit_code == 0
    for opt in ["--to-agent", "--service-type", "--payload", "--max-price", "--wallet"]:
        assert opt in result.output


def test_status_outputs_escrow_and_negotiation(runner, mock_client):
    from aitbc_cli.commands.agent_task import agent_task

    def fake_get(path, params=None, headers=None):
        if path == "/v1/tasks/t-1/escrow":
            return {"status": "success", "escrow": {"task_id": "t-1", "escrow_status": "locked"}}
        if path == "/api/v1/agent/messages/inbox":
            return {
                "messages": [
                    {
                        "message_id": "m1",
                        "message_type": "task_quote",
                        "content": '{"task_id": "t-1", "price": "0.02"}',
                    }
                ]
            }
        return {}

    mock_client.get.side_effect = fake_get
    result = runner.invoke(
        agent_task,
        ["status", "--task-id", "t-1", "--coordinator-url", "http://coord.local"],
        obj={"output_format": "json"},
    )
    assert result.exit_code == 0, result.output
    assert '"escrow_status": "locked"' in result.output
    assert "task_quote" in result.output


def test_result_fetches_cid(runner, mock_client, tmp_path):
    import hashlib

    payload = b'{"text": "hello world"}'
    result_ref = "bafyResult1234567890" + "a" * 45  # CIDv1-looking

    from aitbc_cli.commands.agent_task import agent_task

    def fake_get(path, params=None, headers=None):
        if path == "/api/v1/agent/messages/inbox":
            return {
                "messages": [
                    {
                        "message_id": "m9",
                        "message_type": "task_result",
                        "content": (
                            '{"task_id": "t-1", "status": "success", '
                            f'"result_ref": "{result_ref}", "result_hash": "{hashlib.sha256(payload).hexdigest()}"'
                            "}"
                        ),
                    }
                ]
            }
        return {}

    mock_client.get.side_effect = fake_get

    fake_resp = MagicMock()
    fake_resp.content = payload
    fake_resp.raise_for_status = MagicMock()

    out_file = tmp_path / "out.json"
    with patch("aitbc_cli.commands.agent_task._daemon_available", return_value=True):
        with patch("requests.post", return_value=fake_resp) as mock_post:
            result = runner.invoke(
                agent_task,
                [
                    "result",
                    "--task-id",
                    "t-1",
                    "--coordinator-url",
                    "http://coord.local",
                    "--out",
                    str(out_file),
                ],
                obj={"output_format": "json"},
            )
    assert result.exit_code == 0, result.output
    assert out_file.read_bytes() == payload
    # result CID went to the local daemon's cat endpoint
    assert mock_post.call_args.kwargs["params"]["arg"] == result_ref


def test_hire_submits_signed_escrow(runner, mock_client):
    """hire: uploads payload, signs lock, submits task+payment, sends TaskRequest."""
    from aitbc_cli.commands.agent_task import agent_task

    wallet = _real_wallet()

    def fake_get(path, params=None, headers=None):
        if path.startswith("/v1/agents/"):
            return {"agent": {"metadata": {"wallet": "0xProvider"}}}
        if path == "/v1/tasks/escrow-config":
            return {"status": "success", "settlement_wallet": "0xSettleNode"}
        return {"messages": []}

    def fake_post(path, json=None, headers=None):
        if path == "/v1/tasks/submit":
            return {"status": "success", "escrow_id": "esc-9", "task_id": json["task_data"]["task_id"]}
        return {"status": "success", "message_id": "m-1"}

    mock_client.get.side_effect = fake_get
    mock_client.post.side_effect = fake_post

    with (
        patch("aitbc_cli.commands.agent_task._resolve_payload_ref", return_value="QmCID"),
        patch(
            "aitbc_cli.commands.agent_task.load_wallet_for_payment",
            return_value=(wallet.address, wallet.key.hex(), "w1"),
        ),
        patch("aitbc_cli.utils.escrow.create_signed_escrow_lock", return_value=({"type": "ESCROW_LOCK"}, "sig")) as mock_lock,
        patch("aitbc_cli.commands.agent_task._get_blockchain_rpc_url", return_value="http://rpc.local:8202"),
    ):
        result = runner.invoke(
            agent_task,
            [
                "hire",
                "--to-agent",
                "aitbc-miner-1",
                "--service-type",
                "whisper",
                "--payload",
                "QmCID",
                "--max-price",
                "0.05",
                "--no-wait",
                "--coordinator-url",
                "http://coord.local",
            ],
            obj={"output_format": "json"},
        )
    assert result.exit_code == 0, result.output

    # Task submit carried the signed lock tx + payment fields
    submit = next(c for c in mock_client.post.call_args_list if c.args[0] == "/v1/tasks/submit")
    body = submit.kwargs["json"]
    assert body["payment"]["lock_tx"] == {"type": "ESCROW_LOCK", "signature": "sig"}
    assert body["payment"]["lock_signature"] == "sig"
    assert body["payment"]["agent"] == "0xProvider"
    assert body["payment"]["requester"] == wallet.address
    assert body["payment"]["amount"] == 1_800_000  # 0.05 AIT

    # TaskRequest went to the provider agent as a signed envelope (Phase B2 §4)
    send = next(c for c in mock_client.post.call_args_list if c.args[0] == "/api/v1/agent/messages/send")
    msg = dict(send.kwargs["json"])
    assert msg["message_type"] == "task_request"
    assert msg["recipient"] == "aitbc-miner-1"
    assert msg["content"]["payload_ref"] == "QmCID"
    assert msg["content"]["escrow_id"] == "esc-9"
    assert msg["encrypt"] is False

    from aitbc.crypto.agent_envelope import AGENT_MSG_SIGNATURE_VERSION, verify_agent_envelope

    assert msg["signer"] == wallet.address
    assert msg["signature_version"] == AGENT_MSG_SIGNATURE_VERSION
    assert msg["timestamp"] and msg["nonce"]
    signature = msg.pop("signature")
    assert verify_agent_envelope(msg, signature, wallet.address)

    # The lock tx was signed to the coordinator's settlement wallet,
    # not the buyer's local node wallet.
    assert mock_lock.call_args.kwargs["node_wallet"] == "0xSettleNode"
