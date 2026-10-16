"""Tests for the MSG-2/MSG-2c signed action commands — dry-run by default,
--confirm signs once, and the dry run reports current effectiveness."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

MOD = "aitbc_cli.commands.messaging"
ALICE = "0x1111111111111111111111111111111111111111"
BOB = "0x2222222222222222222222222222222222222222"
TARGET = "ab" * 32


@pytest.fixture
def runner():
    return CliRunner()


def _http_for(moderators=None, topic="dev"):
    """HTTP mock answering message resolution and the moderation read."""
    client = MagicMock()

    def _get(url):
        if url.startswith("/rpc/messaging/messages/"):
            return {"tx_hash": TARGET, "topic": topic, "author": ALICE}
        if url == f"/rpc/messaging/topics/{topic}/moderation":
            return {
                "topic": topic,
                "founder": ALICE,
                "moderators": moderators or [],
                "authority_unresolved": False,
                "actions": [],
            }
        raise AssertionError(f"unexpected GET {url}")

    client.get.side_effect = _get
    return client


@pytest.fixture
def patched():
    client = _http_for(moderators=[BOB])
    with (
        patch(f"{MOD}._wallet_address", return_value=ALICE),
        patch(f"{MOD}._resolve_transaction_rpc_url", return_value="http://rpc"),
        patch(f"{MOD}._rpc_client", return_value=client),
        patch(f"{MOD}.resolve_wallet_password", return_value="pw"),
        patch(f"{MOD}._send_transaction_impl", return_value=TARGET) as send_impl,
        patch(f"{MOD}._wait_for_seal"),
    ):
        yield send_impl, client


def _invoke(runner, args):
    from aitbc_cli.commands.messaging import messaging

    return runner.invoke(messaging, args, obj={"output_format": "json"})


def _payload(result):
    """The JSON output body (the DRY RUN banner goes to stderr, not output)."""
    start = result.output.find("{")
    assert start >= 0, result.output
    return json.loads(result.output[start:])


def test_vote_dry_run_signs_nothing(runner, patched):
    send_impl, _client = patched
    result = _invoke(runner, ["vote", TARGET, "up", "--wallet", "w"])
    assert result.exit_code == 0, result.output
    assert "DRY RUN" in (result.stderr or "") or "DRY RUN" in result.output
    body = _payload(result)
    assert body["kind"] == "vote"
    assert body["envelope"]["kind"] == "vote" and body["envelope"]["value"] == 1
    assert body["fee_ait"]
    send_impl.assert_not_called()


def test_vote_confirm_signs_once(runner, patched):
    send_impl, _client = patched
    result = _invoke(runner, ["vote", TARGET, "down", "--wallet", "w", "--confirm"])
    assert result.exit_code == 0, result.output
    send_impl.assert_called_once()
    payload = send_impl.call_args.kwargs.get("payload") or send_impl.call_args[1].get("payload")
    assert payload["aitbc_msg"]["kind"] == "vote"
    assert payload["aitbc_msg"]["value"] == -1


def test_hide_dry_run_reports_not_moderator(runner, patched):
    send_impl, _client = patched
    result = _invoke(runner, ["hide", TARGET, "--wallet", "w"])
    assert result.exit_code == 0, result.output
    body = _payload(result)
    # ALICE signs, but only BOB moderates 'dev'.
    assert body["would_be_effective_now"] is False
    send_impl.assert_not_called()


def test_hide_dry_run_reports_moderator(runner):
    client = _http_for(moderators=[ALICE])
    with (
        patch(f"{MOD}._wallet_address", return_value=ALICE),
        patch(f"{MOD}._resolve_transaction_rpc_url", return_value="http://rpc"),
        patch(f"{MOD}._rpc_client", return_value=client),
        patch(f"{MOD}._send_transaction_impl") as send_impl,
    ):
        result = _invoke(runner, ["hide", TARGET, "--wallet", "w"])
    assert result.exit_code == 0, result.output
    assert _payload(result)["would_be_effective_now"] is True
    send_impl.assert_not_called()


def test_lock_requires_exactly_one_scope(runner, patched):
    result = _invoke(runner, ["lock", "--wallet", "w"])
    assert result.exit_code != 0
    assert "exactly one" in result.output or "exactly one" in (result.stderr or "")


def test_lock_topic_dry_run(runner, patched):
    send_impl, _client = patched
    result = _invoke(runner, ["lock", "--topic", "dev", "--wallet", "w"])
    assert result.exit_code == 0, result.output
    body = _payload(result)
    assert body["kind"] == "lock" and body["target"] is None
    send_impl.assert_not_called()


def test_mod_grant_dry_run(runner, patched):
    send_impl, _client = patched
    result = _invoke(runner, ["mod-grant", BOB, "--topic", "dev", "--wallet", "w"])
    assert result.exit_code == 0, result.output
    body = _payload(result)
    assert body["kind"] == "mod_grant" and body["grantee"] == BOB
    assert body["envelope"]["grantee"] == BOB
    send_impl.assert_not_called()
