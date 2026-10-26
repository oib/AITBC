"""agent-msg / agent-task commands must abort non-zero on failure paths
(CLI-SWALLOW-SWEEP-2, #570).

Each test below fails if the fix is reverted to ``error(...) + return``
because the command would then exit 0.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

pytest.importorskip("eth_account", reason="hire path needs eth-account for envelope signing")

from eth_account import Account  # noqa: E402

_TEST_KEY = "0x" + "42" * 32


@pytest.fixture
def runner():
    return CliRunner()


# --- WebSocket fakes ---------------------------------------------------------


class _FakeWS:
    """Minimal stand-in for a websockets connection: canned recv frames."""

    def __init__(self, frames):
        self._frames = [json.dumps(f) for f in frames]

    async def recv(self):
        if not self._frames:
            raise asyncio.TimeoutError()
        return self._frames.pop(0)

    async def send(self, _data):
        return None


class _FakeConnect:
    """``websockets.connect(...)`` replacement usable with ``async with``."""

    def __init__(self, ws):
        self._ws = ws

    async def __aenter__(self):
        return self._ws

    async def __aexit__(self, *exc):
        return False


def _invoke_request_coins(runner, frames, fmt="table", argv_extra=None):
    from aitbc_cli.commands.agent import messaging

    ws = _FakeWS(frames)
    argv = ["request-coins", "--wallet", "w1", "--sender", "follower"] + (argv_extra or [])
    with (
        patch("aitbc_cli.commands.agent._resolve_wallet_address", return_value="0x" + "ab" * 20),
        patch("aitbc_cli.commands.agent._ws_auth_token", return_value=None),
        patch(
            "aitbc_cli.commands.agent.get_config",
            return_value=MagicMock(agent_coordinator_url="http://coord.local", api_key=None),
        ),
        patch("websockets.connect", lambda *a, **k: _FakeConnect(ws)),
    ):
        return runner.invoke(messaging, argv, obj={"output_format": fmt})


def _json_error_docs(output: str):
    docs = []
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("{"):
            docs.append(json.loads(output[output.index(line) :]))
            break
    return docs


# --- _resolve_wallet_address -------------------------------------------------


def test_request_coins_missing_wallet_aborts(runner, tmp_path):
    """--wallet naming a non-existent wallet must not exit 0."""
    from aitbc_cli.commands.agent import messaging

    with (
        patch("aitbc_cli.commands.agent.wallet_search_dirs", return_value=[tmp_path]),
        patch("aitbc_cli.commands.agent.find_wallet_file", return_value=None),
    ):
        result = runner.invoke(messaging, ["request-coins", "--wallet", "ghost"], obj={"output_format": "table"})
    assert result.exit_code != 0
    assert "Wallet 'ghost' not found" in result.output


def test_request_coins_missing_wallet_aborts_json(runner, tmp_path):
    """JSON mode: exactly one error document on stdout."""
    from aitbc_cli.commands.agent import messaging

    with (
        patch("aitbc_cli.commands.agent.wallet_search_dirs", return_value=[tmp_path]),
        patch("aitbc_cli.commands.agent.find_wallet_file", return_value=None),
    ):
        result = runner.invoke(messaging, ["request-coins", "--wallet", "ghost"], obj={"output_format": "json"})
    assert result.exit_code != 0
    doc = json.loads(result.stdout)
    assert "Wallet 'ghost' not found" in doc["message"]


def test_request_coins_no_wallets_aborts(runner, tmp_path):
    """Auto-detect with an empty wallet dir must not exit 0."""
    from aitbc_cli.commands.agent import messaging

    with (
        patch("aitbc_cli.commands.agent.wallet_search_dirs", return_value=[tmp_path]),
        patch("aitbc_cli.commands.agent._default_wallet_name", return_value=None),
    ):
        result = runner.invoke(messaging, ["request-coins"], obj={"output_format": "table"})
    assert result.exit_code != 0
    assert "No wallets found" in result.output


def test_request_coins_wallet_without_address_aborts(runner, tmp_path):
    """A wallet file lacking the address field must not exit 0."""
    from aitbc_cli.commands.agent import messaging

    wallet_file = tmp_path / "w1.json"
    wallet_file.write_text(json.dumps({"encrypted": True}))
    with (
        patch("aitbc_cli.commands.agent.wallet_search_dirs", return_value=[tmp_path]),
        patch("aitbc_cli.commands.agent.find_wallet_file", return_value=wallet_file),
    ):
        result = runner.invoke(messaging, ["request-coins", "--wallet", "w1"], obj={"output_format": "table"})
    assert result.exit_code != 0
    assert "No address field in wallet file" in result.output


# --- _consume_connection_frame ------------------------------------------------


def test_request_coins_unexpected_first_frame_aborts(runner):
    """A non-connection_established first frame must not exit 0."""
    result = _invoke_request_coins(runner, [{"type": "bogus_frame"}])
    assert result.exit_code != 0
    assert "Unexpected first message" in result.output


def test_request_coins_unexpected_first_frame_aborts_json(runner):
    result = _invoke_request_coins(runner, [{"type": "bogus_frame"}], fmt="json")
    assert result.exit_code != 0
    doc = json.loads(result.stdout)
    assert "Unexpected first message" in doc["message"]


# --- request_coins frame loop -------------------------------------------------


def _ack(result_action: dict):
    return {"type": "handler_acknowledgment", "handler_results": {"results": [{"result": result_action}]}}


def test_request_coins_failed_action_aborts(runner):
    """coin_request_failed in the ack must abort, not print-and-exit-0."""
    frames = [
        {"type": "connection_established"},
        _ack({"action": "coin_request_failed", "error": "quota exhausted"}),
    ]
    result = _invoke_request_coins(runner, frames)
    assert result.exit_code != 0
    assert "Coin request failed: quota exhausted" in result.output


def test_request_coins_failed_action_aborts_json(runner):
    frames = [
        {"type": "connection_established"},
        _ack({"action": "coin_request_failed", "error": "quota exhausted"}),
    ]
    result = _invoke_request_coins(runner, frames, fmt="json")
    assert result.exit_code != 0
    doc = json.loads(result.stdout)
    assert "Coin request failed: quota exhausted" in doc["message"]


def test_request_coins_pending_approval_rc0(runner):
    """BY-DESIGN: pending_approval is a success path and stays exit 0."""
    frames = [
        {"type": "connection_established"},
        _ack(
            {
                "action": "coin_request_received",
                "status": "pending_approval",
                "request_id": "req-1",
                "message": "awaiting approval",
            }
        ),
    ]
    result = _invoke_request_coins(runner, frames)
    assert result.exit_code == 0
    assert "pending manual approval" in result.output


def test_request_coins_transferred_rc0(runner):
    """Happy path: COINS_TRANSFERRED stays exit 0."""
    frames = [
        {"type": "connection_established"},
        {"type": "COINS_TRANSFERRED", "transaction_hash": "0xtx", "amount": 3},
    ]
    result = _invoke_request_coins(runner, frames)
    assert result.exit_code == 0
    assert "Received 3 AIT" in result.output


# --- agent-task hire: task_reject --------------------------------------------


def test_hire_provider_reject_aborts(runner, tmp_path):
    """A task_reject inbox message must abort hire, not print-and-exit-0."""
    from aitbc_cli.commands.agent_task import agent_task

    wallet = Account.from_key(_TEST_KEY)
    captured: dict[str, str] = {}

    def fake_get(path, params=None, headers=None):
        if path.startswith("/v1/agents/"):
            return {"agent": {"metadata": {"wallet": "0xProvider"}}}
        if path == "/v1/tasks/escrow-config":
            return {"status": "success", "settlement_wallet": "0xSettleNode"}
        if path == "/api/v1/agent/messages/inbox":
            return {
                "messages": [
                    {
                        "message_type": "task_reject",
                        "content": {"task_id": captured["task_id"], "reason": "provider busy"},
                    }
                ]
            }
        return {"messages": []}

    def fake_post(path, json=None, headers=None):
        if path == "/v1/tasks/submit":
            captured["task_id"] = json["task_data"]["task_id"]
            return {"status": "success", "escrow_id": "esc-9", "task_id": json["task_data"]["task_id"]}
        return {"status": "success", "message_id": "m-1"}

    client = MagicMock()
    client.get.side_effect = fake_get
    client.post.side_effect = fake_post

    with (
        patch("aitbc_cli.commands.agent_task.AITBCHTTPClient", return_value=client),
        patch(
            "aitbc_cli.commands.agent_task.get_config",
            return_value=MagicMock(agent_coordinator_url="http://coord.local", blockchain_rpc_url="http://rpc.local:8202"),
        ),
        patch("aitbc_cli.commands.agent_task._resolve_payload_ref", return_value="QmCID"),
        patch(
            "aitbc_cli.commands.agent_task.load_wallet_for_payment",
            return_value=(wallet.address, wallet.key.hex(), "w1"),
        ),
        patch("aitbc_cli.utils.escrow.create_signed_escrow_lock", return_value=({"type": "ESCROW_LOCK"}, "sig")),
        patch("aitbc_cli.commands.agent_task._get_blockchain_rpc_url", return_value="http://rpc.local:8202"),
        patch("aitbc_cli.commands.agent_task.check_registry_binding", return_value=None),
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
                "--coordinator-url",
                "http://coord.local",
            ],
            obj={"output_format": "table"},
        )
    assert result.exit_code != 0
    assert "Provider rejected the task" in result.output


def test_hire_provider_reject_aborts_json(runner, tmp_path):
    """JSON mode: exactly one error document on stdout."""
    from aitbc_cli.commands.agent_task import agent_task

    wallet = Account.from_key(_TEST_KEY)
    captured: dict[str, str] = {}

    def fake_get(path, params=None, headers=None):
        if path.startswith("/v1/agents/"):
            return {"agent": {"metadata": {"wallet": "0xProvider"}}}
        if path == "/v1/tasks/escrow-config":
            return {"status": "success", "settlement_wallet": "0xSettleNode"}
        if path == "/api/v1/agent/messages/inbox":
            return {
                "messages": [
                    {
                        "message_type": "task_reject",
                        "content": {"task_id": captured["task_id"], "reason": "provider busy"},
                    }
                ]
            }
        return {"messages": []}

    def fake_post(path, json=None, headers=None):
        if path == "/v1/tasks/submit":
            captured["task_id"] = json["task_data"]["task_id"]
            return {"status": "success", "escrow_id": "esc-9", "task_id": json["task_data"]["task_id"]}
        return {"status": "success", "message_id": "m-1"}

    client = MagicMock()
    client.get.side_effect = fake_get
    client.post.side_effect = fake_post

    with (
        patch("aitbc_cli.commands.agent_task.AITBCHTTPClient", return_value=client),
        patch(
            "aitbc_cli.commands.agent_task.get_config",
            return_value=MagicMock(agent_coordinator_url="http://coord.local", blockchain_rpc_url="http://rpc.local:8202"),
        ),
        patch("aitbc_cli.commands.agent_task._resolve_payload_ref", return_value="QmCID"),
        patch(
            "aitbc_cli.commands.agent_task.load_wallet_for_payment",
            return_value=(wallet.address, wallet.key.hex(), "w1"),
        ),
        patch("aitbc_cli.utils.escrow.create_signed_escrow_lock", return_value=({"type": "ESCROW_LOCK"}, "sig")),
        patch("aitbc_cli.commands.agent_task._get_blockchain_rpc_url", return_value="http://rpc.local:8202"),
        patch("aitbc_cli.commands.agent_task.check_registry_binding", return_value=None),
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
                "--coordinator-url",
                "http://coord.local",
            ],
            obj={"output_format": "json"},
        )
    assert result.exit_code != 0
    doc = json.loads(result.stdout)
    assert "Provider rejected the task" in doc["message"]
