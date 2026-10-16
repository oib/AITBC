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
