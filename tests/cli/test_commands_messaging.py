"""
Messaging Commands Tests (MSG-1)

The forum commands now sign MESSAGE transactions locally and read the
chain-derived index — there is no RPC post endpoint and no simulated
fallback. ``_send_transaction_impl`` is monkeypatched to capture the exact
transaction the command builds.
"""

import json
from unittest.mock import patch

import pytest

from aitbc_cli.commands import messaging as messaging_mod

SENDER = "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"


@pytest.fixture
def sender_wallet(tmp_path, monkeypatch):
    """A throwaway wallet file so ``--wallet`` resolves an address."""
    monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path))
    (tmp_path / "poster.json").write_text(json.dumps({"address": SENDER}))
    return "poster"


@pytest.fixture
def captured_send(monkeypatch):
    """Capture the _send_transaction_impl call; never signs or submits."""
    calls = []
    monkeypatch.setattr(messaging_mod, "_send_transaction_impl", lambda *a, **kw: calls.append((a, kw)) or "ab" * 32)
    monkeypatch.setattr(messaging_mod, "resolve_wallet_password", lambda **kw: "")
    return calls


class TestMessagingCommands:
    def test_messaging_group_name(self):
        assert messaging_mod.messaging.name == "messaging"

    def test_subcommands_registered(self):
        names = set(messaging_mod.messaging.commands)
        assert {"send", "list", "topics", "topic", "show", "state"} <= names

    def test_send_requires_wallet(self, runner):
        result = runner.invoke(messaging_mod.messaging, ["send", "--message", "hi"])
        assert result.exit_code != 0

    def test_send_builds_signed_message_tx(self, runner, sender_wallet, captured_send):
        result = runner.invoke(
            messaging_mod.messaging,
            ["send", "--wallet", "poster", "--message", "hello", "--topic", "Dev", "--no-wait"],
        )
        assert result.exit_code == 0, result.output
        args, kwargs = captured_send[0]
        assert args[0] == "poster"
        assert args[1] == SENDER  # self-send
        assert kwargs["tx_type"] == "MESSAGE"
        env = kwargs["payload"]["aitbc_msg"]
        assert env["v"] == 1 and env["kind"] == "post"
        assert env["topic"] == "dev"  # normalized pre-sign
        assert env["body"] == "hello"
        assert env["agent_address"] == SENDER
        assert "agent_id" not in json.dumps(kwargs["payload"])
        assert "public, permanent" in result.output  # permanence warning printed

    def test_send_reply(self, runner, sender_wallet, captured_send):
        parent = "ab" * 32
        result = runner.invoke(
            messaging_mod.messaging,
            ["send", "--wallet", "poster", "--message", "re:hi", "--reply-to", parent, "--no-wait"],
        )
        assert result.exit_code == 0, result.output
        env = captured_send[0][1]["payload"]["aitbc_msg"]
        assert env["kind"] == "reply" and env["parent"] == parent

    def test_send_refuses_empty_body(self, runner, sender_wallet, captured_send):
        result = runner.invoke(
            messaging_mod.messaging, ["send", "--wallet", "poster", "--message", "   ", "--no-wait"]
        )
        assert result.exit_code != 0
        assert captured_send == []

    def test_send_refuses_oversize_body(self, runner, sender_wallet, captured_send):
        result = runner.invoke(
            messaging_mod.messaging,
            ["send", "--wallet", "poster", "--message", "x" * 4097, "--no-wait"],
        )
        assert result.exit_code != 0
        assert captured_send == []

    def test_send_refuses_bad_parent(self, runner, sender_wallet, captured_send):
        result = runner.invoke(
            messaging_mod.messaging,
            ["send", "--wallet", "poster", "--message", "re", "--reply-to", "not-hex", "--no-wait"],
        )
        assert result.exit_code != 0
        assert captured_send == []

    def test_send_no_simulated_fallback(self, runner, sender_wallet, monkeypatch):
        """RPC failure must abort non-zero — the simulated path is gone."""
        monkeypatch.setattr(messaging_mod, "resolve_wallet_password", lambda **kw: "")
        monkeypatch.setattr(
            messaging_mod,
            "_send_transaction_impl",
            lambda *a, **kw: None,  # submit failed
        )
        result = runner.invoke(
            messaging_mod.messaging, ["send", "--wallet", "poster", "--message", "hi", "--no-wait"]
        )
        assert result.exit_code != 0
        assert "simulated" not in result.output.lower()

    def test_send_waits_for_seal(self, runner, sender_wallet, captured_send, monkeypatch):
        class _Client:
            def __init__(self, *a, **kw):
                pass

            def get(self, path, **kw):
                assert path == f"/rpc/transaction/{'ab' * 32}"
                return {"block_height": 42, "status": "confirmed"}

        monkeypatch.setattr(messaging_mod, "AITBCHTTPClient", _Client)
        result = runner.invoke(
            messaging_mod.messaging, ["send", "--wallet", "poster", "--message", "hi", "--wait"]
        )
        assert result.exit_code == 0, result.output
        assert "Sealed at block 42" in result.output

    @patch("aitbc_cli.commands.messaging.AITBCHTTPClient")
    def test_list_reads_index(self, mock_http_class, runner, mock_blockchain_rpc):
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"messages": [], "count": 0}
        result = runner.invoke(messaging_mod.messaging, ["list", "--topic", "dev"])
        assert result.exit_code == 0, result.output
        path = mock_client.get.call_args[0][0]
        assert path == "/rpc/messaging/messages"
        assert mock_client.get.call_args[1]["params"]["topic"] == "dev"

    @patch("aitbc_cli.commands.messaging.AITBCHTTPClient")
    def test_list_query_uses_search(self, mock_http_class, runner, mock_blockchain_rpc):
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"messages": []}
        result = runner.invoke(messaging_mod.messaging, ["list", "--query", "hello"])
        assert result.exit_code == 0, result.output
        assert mock_client.get.call_args[0][0] == "/rpc/messaging/messages/search"

    @patch("aitbc_cli.commands.messaging.AITBCHTTPClient")
    def test_list_aborts_on_network_error(self, mock_http_class, runner, mock_blockchain_rpc):
        from aitbc_cli.utils.http_client import NetworkError

        mock_http_class.return_value.get.side_effect = NetworkError("connection refused")
        result = runner.invoke(messaging_mod.messaging, ["list"])
        assert result.exit_code != 0
        assert "simulated" not in result.output.lower()

    @patch("aitbc_cli.commands.messaging.AITBCHTTPClient")
    def test_topics_lists(self, mock_http_class, runner, mock_blockchain_rpc):
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"topics": []}
        result = runner.invoke(messaging_mod.messaging, ["topics"])
        assert result.exit_code == 0, result.output
        assert mock_client.get.call_args[0][0] == "/rpc/messaging/topics"

    @patch("aitbc_cli.commands.messaging.AITBCHTTPClient")
    def test_topic_alias_lists(self, mock_http_class, runner, mock_blockchain_rpc):
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"topics": []}
        result = runner.invoke(messaging_mod.messaging, ["topic"])
        assert result.exit_code == 0, result.output
        assert mock_client.get.call_args[0][0] == "/rpc/messaging/topics"

    @patch("aitbc_cli.commands.messaging.AITBCHTTPClient")
    def test_show_by_hash(self, mock_http_class, runner, mock_blockchain_rpc):
        h = "ab" * 32
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"tx_hash": h, "body": "hi"}
        result = runner.invoke(messaging_mod.messaging, ["show", h])
        assert result.exit_code == 0, result.output
        assert mock_client.get.call_args[0][0] == f"/rpc/messaging/messages/{h}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
