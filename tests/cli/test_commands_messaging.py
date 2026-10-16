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


@pytest.fixture(autouse=True)
def _no_real_http(monkeypatch):
    """No test in this file may reach a real URL.

    ``--wait`` polls with plain ``requests``; without this guard a forgotten
    stub would hit the network for the whole ``--wait-timeout``. Tests that
    exercise the wait install their own ``requests.get`` stub on top.
    """
    import requests

    def _blocked(url, *a, **kw):
        raise AssertionError(f"real HTTP attempted in a unit test: {url}")

    for verb in ("get", "post", "put", "delete", "head", "request"):
        monkeypatch.setattr(requests, verb, _blocked)


class TestMessagingCommands:
    def test_messaging_group_name(self):
        assert messaging_mod.messaging.name == "messaging"

    def test_subcommands_registered(self):
        names = set(messaging_mod.messaging.commands)
        assert {"send", "list", "topics", "topic", "show", "state"} <= names

    def test_send_requires_wallet(self, runner):
        result = runner.invoke(messaging_mod.messaging, ["send", "--message", "hi"])
        assert result.exit_code != 0

    def test_send_dry_run_default_signs_nothing(self, runner, sender_wallet, captured_send):
        """Without --confirm nothing is signed or sent — the dry run prints
        wallet, sender, topic, byte length and fee."""
        result = runner.invoke(
            messaging_mod.messaging,
            ["send", "--wallet", "poster", "--message", "hello", "--topic", "dev"],
        )
        assert result.exit_code == 0, result.output
        assert captured_send == []
        assert "DRY RUN" in result.output
        assert "poster" in result.output
        assert SENDER in result.output
        assert "dev" in result.output
        assert "5" in result.output  # body bytes

    def test_send_builds_signed_message_tx(self, runner, sender_wallet, captured_send):
        result = runner.invoke(
            messaging_mod.messaging,
            ["send", "--wallet", "poster", "--message", "hello", "--topic", "Dev", "--no-wait", "--confirm"],
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
            ["send", "--wallet", "poster", "--message", "re:hi", "--reply-to", parent, "--no-wait", "--confirm"],
        )
        assert result.exit_code == 0, result.output
        env = captured_send[0][1]["payload"]["aitbc_msg"]
        assert env["kind"] == "reply" and env["parent"] == parent

    def test_send_reply_uppercase_parent_lowercased(self, runner, sender_wallet, captured_send):
        """--reply-to is lowercased before signing: stored tx_hash values are
        lowercase hex and an uppercase parent would never resolve."""
        parent = "AB" * 32
        result = runner.invoke(
            messaging_mod.messaging,
            ["send", "--wallet", "poster", "--message", "re:hi", "--reply-to", parent, "--no-wait", "--confirm"],
        )
        assert result.exit_code == 0, result.output
        env = captured_send[0][1]["payload"]["aitbc_msg"]
        assert env["kind"] == "reply" and env["parent"] == parent.lower()

    def test_send_refuses_empty_body(self, runner, sender_wallet, captured_send):
        result = runner.invoke(
            messaging_mod.messaging, ["send", "--wallet", "poster", "--message", "   ", "--no-wait", "--confirm"]
        )
        assert result.exit_code != 0
        assert captured_send == []

    def test_send_refuses_oversize_body(self, runner, sender_wallet, captured_send):
        result = runner.invoke(
            messaging_mod.messaging,
            ["send", "--wallet", "poster", "--message", "x" * 4097, "--no-wait", "--confirm"],
        )
        assert result.exit_code != 0
        assert captured_send == []

    def test_send_refuses_bad_parent(self, runner, sender_wallet, captured_send):
        result = runner.invoke(
            messaging_mod.messaging,
            ["send", "--wallet", "poster", "--message", "re", "--reply-to", "not-hex", "--no-wait", "--confirm"],
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
            messaging_mod.messaging, ["send", "--wallet", "poster", "--message", "hi", "--no-wait", "--confirm"]
        )
        assert result.exit_code != 0
        assert "simulated" not in result.output.lower()

    def test_send_waits_for_seal(self, runner, sender_wallet, captured_send):
        """MSG-CLI-WAIT moved the poll to plain ``requests`` against
        ``/rpc/messaging/messages/<hash>`` (the transaction route 404s for
        MESSAGE rows); a 200 body with a block height confirms the seal."""
        from unittest.mock import MagicMock

        class _Resp:
            status_code = 200

            def json(self):
                return {"block_height": 42}

        with patch("requests.get", MagicMock(return_value=_Resp())) as get:
            result = runner.invoke(
                messaging_mod.messaging,
                ["send", "--wallet", "poster", "--message", "hi", "--wait", "--wait-timeout", "5", "--confirm"],
            )
        assert result.exit_code == 0, result.output
        assert "Sealed at block 42" in result.output
        assert get.call_args[0][0].endswith(f"/rpc/messaging/messages/{'ab' * 32}")

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

    @patch("aitbc_cli.commands.messaging.AITBCHTTPClient")
    def test_list_sanitises_invisible_chars(self, mock_http_class, runner, mock_blockchain_rpc):
        """MSG-4b: chain text reaching the agent via CLI must show format
        characters (incl. the tag block) as visible [U+XXXX] placeholders."""
        tag = chr(0xE0001)
        body = f"hi{chr(0x200B)}there{tag}soft{chr(0x00AD)}hy"
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"messages": [{"body": body, "topic": "msg-fix"}], "count": 1}
        result = runner.invoke(messaging_mod.messaging, ["list"])
        assert result.exit_code == 0, result.output
        assert "[U+200B]" in result.output
        assert "[U+E0001]" in result.output
        assert "[U+00AD]" in result.output
        assert tag not in result.output
        assert chr(0x200B) not in result.output

    @patch("aitbc_cli.commands.messaging.AITBCHTTPClient")
    def test_topics_sanitises_invisible_chars(self, mock_http_class, runner, mock_blockchain_rpc):
        tag = chr(0xE0002)
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"topics": [{"topic": f"top{tag}ic"}], "count": 1}
        result = runner.invoke(messaging_mod.messaging, ["topics"])
        assert result.exit_code == 0, result.output
        assert "[U+E0002]" in result.output
        assert tag not in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
