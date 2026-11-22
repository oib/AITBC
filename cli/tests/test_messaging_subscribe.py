"""`aitbc messaging subscribe` — cursor-polling subscribe command (MSG-15)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from click.testing import CliRunner

MOD = "aitbc_cli.commands.messaging"
MC = "aitbc.messaging_client"


def _resp(status: int, body: Any):
    import requests

    r = requests.models.Response()
    r.status_code = status
    r._content = json.dumps(body).encode()
    return r


def _msg(height: int, n: int, body: str = "x"):
    return {"tx_hash": f"{n:064x}", "block_height": height, "body": body, "kind": "post", "topic": "dev"}


def _run(args, pages, expected_exit=0):
    from aitbc_cli.commands.messaging import messaging

    it = iter(pages)

    def fake_fetch(rpc, *, topic=None, cursor=None, limit=50, timeout=10.0):
        try:
            return next(it)
        except StopIteration:
            return {"messages": []}

    runner = CliRunner()
    with (
        patch(f"{MC}.fetch_messages", side_effect=fake_fetch),
        patch(f"{MOD}._resolve_transaction_rpc_url", return_value="http://rpc"),
        patch("time.sleep"),
    ):
        result = runner.invoke(messaging, args)
    assert result.exit_code == expected_exit, result.output
    return result


class TestSubscribeCommand:
    def test_one_shot_no_backlog_prints_head_cursor(self):
        out = _run(["subscribe", "dev"], [{"messages": [_msg(10, 5)]}])
        assert "next_cursor: 10:" + "0" * 63 + "5" in out.output

    def test_from_cursor_prints_newer_rows(self):
        rows = [_msg(10, 3, "BODY_NEWER"), _msg(9, 1, "BODY_OLDER")]
        out = _run(["subscribe", "dev", "--from-cursor", "9:" + "01" * 32], [{"messages": rows}])
        assert "BODY_NEWER" in out.output and "BODY_OLDER" not in out.output
        assert "next_cursor: 10:" in out.output

    def test_bad_cursor_rejected(self):
        _run(["subscribe", "dev", "--from-cursor", "junk"], [], expected_exit=1)

    def test_unreachable_aborts(self):
        import aitbc.messaging_client as mc

        runner = CliRunner()
        with (
            patch(f"{MC}.fetch_messages", return_value=mc.UNREACHABLE),
            patch(f"{MOD}._resolve_transaction_rpc_url", return_value="http://rpc"),
        ):
            from aitbc_cli.commands.messaging import messaging

            result = runner.invoke(messaging, ["subscribe", "dev"])
        assert result.exit_code == 1
        assert "unavailable" in result.output.lower()

    def test_empty_topic(self):
        out = _run(["subscribe", "emptytopic"], [{"messages": []}])
        assert "no messages" in out.output


def _msg0x(height: int, n: int, body: str = "x"):
    return {"tx_hash": "0x" + f"{n:064x}", "block_height": height, "body": body, "kind": "post", "topic": "dev"}


class TestSubscribeAuditFixes:
    def test_from_cursor_pages_back_over_gap(self):
        """#2575: rows older than one page but newer than the cursor are
        delivered — the CLI resume path pages back via next_cursor."""
        from aitbc_cli.commands.messaging import messaging

        head = {"messages": [_msg(30, 30, "H30"), _msg(29, 29, "H29")], "next_cursor": "28:" + f"{28:064x}"}
        middle = {"messages": [_msg(28, 28, "M28"), _msg(27, 27, "M27")], "next_cursor": "26:" + f"{26:064x}"}
        tail = {
            "messages": [_msg(26, 26, "T26"), _msg(20, 20, "CURSOR"), _msg(19, 19, "OLD")],
            "next_cursor": None,
        }

        def fake_fetch(rpc, *, topic=None, cursor=None, limit=50, timeout=10.0):
            if cursor is None:
                return head
            if cursor.startswith("28:"):
                return middle
            return tail

        runner = CliRunner()
        with (
            patch(f"{MC}.fetch_messages", side_effect=fake_fetch),
            patch(f"{MOD}._resolve_transaction_rpc_url", return_value="http://rpc"),
            patch("time.sleep"),
        ):
            result = runner.invoke(messaging, ["subscribe", "dev", "--from-cursor", "20:" + f"{20:064x}"])
        assert result.exit_code == 0, result.output
        for body in ("T26", "M27", "M28", "H29", "H30"):
            assert body in result.output
        assert "CURSOR" not in result.output and "OLD" not in result.output

    def test_empty_topic_follow_delivers_first_message(self):
        """#2573: --follow on a topic that starts empty delivers the first post."""
        from aitbc_cli.commands.messaging import messaging

        pages = iter(
            [
                {"messages": []},  # first batch: topic empty
                {"messages": [_msg(11, 7, "FIRST_POST")]},  # kernel poll 1
                {"messages": [_msg(11, 7, "FIRST_POST")]},  # kernel poll 2 (max-polls bound)
            ]
        )

        def fake_fetch(rpc, *, topic=None, cursor=None, limit=50, timeout=10.0):
            return next(pages, {"messages": [_msg(11, 7, "FIRST_POST")]})

        runner = CliRunner()
        with (
            patch(f"{MC}.fetch_messages", side_effect=fake_fetch),
            patch(f"{MOD}._resolve_transaction_rpc_url", return_value="http://rpc"),
            patch("time.sleep"),
        ):
            result = runner.invoke(messaging, ["subscribe", "dev", "--follow", "--max-polls", "2", "--interval", "0"])
        assert result.exit_code == 0, result.output
        assert "FIRST_POST" in result.output

    def test_0x_row_hashes_resume_same_block(self):
        """#2574: 0x-prefixed row hashes compare correctly against a bare cursor."""

        rows = [_msg0x(10, 9, "NEWER"), _msg0x(10, 7, "ALSO"), _msg0x(10, 5, "CURSOR_ROW"), _msg0x(10, 3, "OLDER")]
        out = _run(["subscribe", "dev", "--from-cursor", "10:" + f"{5:064x}"], [{"messages": rows}])
        assert "NEWER" in out.output and "ALSO" in out.output
        assert "CURSOR_ROW" not in out.output and "OLDER" not in out.output


class TestListQueryFilters:
    def test_query_sends_topic_author_include_hidden(self):
        """#2576: --query no longer drops --topic/--author/--include-hidden."""
        from aitbc_cli.commands.messaging import messaging

        calls = []

        class FakeClient:
            def get(self, path, params=None):
                calls.append((path, params))
                return {"messages": [], "success": True}

        runner = CliRunner()
        with (
            patch(f"{MOD}._rpc_client", return_value=FakeClient()),
            patch(f"{MOD}._resolve_transaction_rpc_url", return_value="http://rpc"),
        ):
            result = runner.invoke(
                messaging,
                [
                    "list",
                    "--query",
                    "hello",
                    "--topic",
                    "dev",
                    "--author",
                    "0xabc",
                    "--include-hidden",
                ],
            )
        assert result.exit_code == 0, result.output
        assert calls and calls[0][0] == "/rpc/messaging/messages/search"
        params = calls[0][1]
        assert params["topic"] == "dev" and params["author"] == "0xabc"
        assert params["include_hidden"] == "true" and params["query"] == "hello"
