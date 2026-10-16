"""Tests for MSG-CLI-WAIT: the seal-wait must poll messaging read routes.

Regression context: ``_wait_for_seal`` used to poll the generic
``/rpc/transaction/{hash}`` route through the breakered HTTP client. That
route 404s for MESSAGE transactions even after sealing, so the default
``--wait`` path opened the circuit breaker on healthy submissions (seen
live in MSG-3d). Posts are detected at ``/rpc/messaging/messages/{hash}``;
actions via the topic moderation ``actions`` list.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

MOD = "aitbc_cli.commands.messaging"
TX = "0x" + "cd" * 32
TARGET = "ab" * 32
VOTER = "0xBdDF27912eDc786aaA566712075dA9E70EFd64F7"
GRANTEE = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"


def _resp(status: int, payload=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload if payload is not None else {}
    return r


def _forever(response):
    return lambda *a, **k: response


def _run(is_action: bool, side_effect, timeout: float = 1.0, **kw):
    """Invoke _wait_for_seal with stubbed requests/time; returns (calls, warns, succs)."""
    from aitbc_cli.commands.messaging import _wait_for_seal

    get = MagicMock(side_effect=side_effect)
    warnings: list[str] = []
    successes: list[str] = []
    with (
        patch("requests.get", get),
        patch(f"{MOD}._WAIT_POLL_SECONDS", 0),
        patch(f"{MOD}.warning", side_effect=warnings.append),
        patch(f"{MOD}.success", side_effect=successes.append),
    ):
        _wait_for_seal(None, "http://rpc", TX, timeout, topic="dev", is_action=is_action, **kw)
    urls = [c.args[0] for c in get.call_args_list]
    return urls, warnings, successes


def test_post_wait_polls_message_route_never_transaction_route():
    urls, warnings, successes = _run(
        is_action=False,
        side_effect=[_resp(404), _resp(200, {"block_height": 49312})],
    )
    assert urls == [f"http://rpc/rpc/messaging/messages/{TX}"] * 2
    assert not any("/rpc/transaction/" in u for u in urls)
    assert successes == ["Sealed at block 49312"]
    assert warnings == []


def test_action_wait_detects_tx_in_moderation_actions():
    mod = {"actions": [{"tx_hash": TX, "block_height": 49315, "kind": "hide", "effective": True}]}
    urls, warnings, successes = _run(
        is_action=True,
        kind="hide",
        side_effect=[_resp(404), _resp(200, mod)],
    )
    assert urls == ["http://rpc/rpc/messaging/topics/dev/moderation"] * 2
    assert successes == ["Sealed at block 49315"]
    assert warnings == []


def test_vote_wait_polls_target_votes_route_for_standing_value():
    votes = {"votes": [{"voter": VOTER.lower(), "value": 1, "self_vote": False}], "count": 1}
    urls, warnings, successes = _run(
        is_action=True,
        kind="vote",
        target=TARGET,
        sender=VOTER,
        value=1,
        side_effect=[_resp(404), _resp(200, votes)],
    )
    assert urls == [f"http://rpc/rpc/messaging/messages/0x{TARGET}/votes"] * 2
    assert successes == [f"'vote' reads as expected on topic 'dev' (tx {TX})"]
    assert warnings == []


def test_vote_wrong_value_keeps_polling():
    votes = {"votes": [{"voter": VOTER.lower(), "value": -1}], "count": 1}
    _, warnings, successes = _run(
        is_action=True,
        kind="vote",
        target=TARGET,
        sender=VOTER,
        value=1,
        side_effect=_forever(_resp(200, votes)),
        timeout=0.05,
    )
    assert successes == []
    assert len(warnings) == 1
    assert "/votes" in warnings[0]


def test_grant_wait_detects_grantee_in_moderators():
    mod = {"moderators": ["0xaaaa", GRANTEE], "actions": []}
    urls, warnings, successes = _run(
        is_action=True,
        kind="mod_grant",
        grantee=GRANTEE,
        side_effect=[_resp(404), _resp(200, mod)],
    )
    assert urls == ["http://rpc/rpc/messaging/topics/dev/moderation"] * 2
    assert successes == [f"'mod_grant' reads as expected on topic 'dev' (tx {TX})"]


def test_revoke_wait_detects_grantee_gone_from_moderators():
    mod = {"moderators": ["0xaaaa"], "actions": []}
    _, warnings, successes = _run(
        is_action=True,
        kind="mod_revoke",
        grantee=GRANTEE,
        side_effect=[_resp(200, mod)],
    )
    assert successes == [f"'mod_revoke' reads as expected on topic 'dev' (tx {TX})"]
    assert warnings == []


def test_revoke_still_present_keeps_polling():
    mod = {"moderators": [GRANTEE], "actions": []}
    _, warnings, successes = _run(
        is_action=True,
        kind="mod_revoke",
        grantee=GRANTEE,
        side_effect=_forever(_resp(200, mod)),
        timeout=0.05,
    )
    assert successes == []
    assert len(warnings) == 1
    assert "moderation" in warnings[0]


def test_unknown_action_kind_prints_hint_without_waiting():
    from aitbc_cli.commands.messaging import _wait_for_seal

    get = MagicMock()
    warnings: list[str] = []
    with (
        patch("requests.get", get),
        patch(f"{MOD}.warning", side_effect=warnings.append),
    ):
        _wait_for_seal(None, "http://rpc", TX, 60.0, topic="dev", is_action=True, kind="future_kind")
    get.assert_not_called()
    assert len(warnings) == 1
    assert "no read route" in warnings[0]


def test_action_state_probe_reports_pre_send_state():
    from aitbc_cli.commands.messaging import _action_state_probe

    votes = {"votes": [{"voter": VOTER.lower(), "value": 1}]}
    with patch("requests.get", MagicMock(return_value=_resp(200, votes))):
        assert _action_state_probe("http://rpc", "vote", "dev", TARGET, sender=VOTER, value=1, grantee=None) is True
        assert _action_state_probe("http://rpc", "vote", "dev", TARGET, sender=VOTER, value=-1, grantee=None) is False
    with patch("requests.get", MagicMock(side_effect=requests.ConnectionError("down"))):
        assert _action_state_probe("http://rpc", "vote", "dev", TARGET, sender=VOTER, value=1, grantee=None) is False


def test_confirm_with_pre_matched_state_says_so_and_skips_wait():
    """A vote whose state already matched before the send must not claim a seal."""
    from click.testing import CliRunner

    from aitbc_cli.commands.messaging import messaging

    client = MagicMock()
    client.get.side_effect = lambda url: {"tx_hash": TARGET, "topic": "dev", "author": "0xaaaa"}
    infos: list[str] = []
    with (
        patch(f"{MOD}._wallet_address", return_value=VOTER),
        patch(f"{MOD}._resolve_transaction_rpc_url", return_value="http://rpc"),
        patch(f"{MOD}._rpc_client", return_value=client),
        patch(f"{MOD}.resolve_wallet_password", return_value="pw"),
        patch(f"{MOD}._send_transaction_impl", return_value=TX),
        patch(f"{MOD}._action_state_probe", return_value=True) as probe,
        patch(f"{MOD}._wait_for_seal") as wait_mock,
        patch(f"{MOD}.info", side_effect=infos.append),
    ):
        result = CliRunner().invoke(messaging, ["vote", TARGET, "up", "--wallet", "w", "--confirm"])
    assert result.exit_code == 0, result.output
    probe.assert_called_once()
    wait_mock.assert_not_called()
    assert any("already reads as expected" in m for m in infos)


def test_never_appearing_tx_degrades_to_hint_not_breaker():
    urls, warnings, successes = _run(is_action=False, side_effect=_forever(_resp(404)))
    assert urls and all("/rpc/messaging/messages/" in u for u in urls)
    assert successes == []
    assert len(warnings) == 1
    assert "not confirmed" in warnings[0]
    assert "aitbc messaging show" in warnings[0]
    assert "circuit" not in warnings[0].lower()


def test_connection_error_is_distinct_from_404():
    urls, warnings, successes = _run(
        is_action=False,
        side_effect=requests.ConnectionError("refused"),
        timeout=0.05,
    )
    assert urls and all(u == f"http://rpc/rpc/messaging/messages/{TX}" for u in urls)
    assert successes == []
    assert len(warnings) == 1
    assert "no answer from RPC" in warnings[0]


def test_action_wait_timeout_hints_moderation_route():
    _, warnings, successes = _run(is_action=True, side_effect=_forever(_resp(404)))
    assert successes == []
    assert len(warnings) == 1
    assert "/rpc/messaging/topics/dev/moderation" in warnings[0]


def test_retract_wait_matches_when_signer_absent():
    """A retract removes the signer — absence from standing votes is the match."""
    with_voter = {"votes": [{"voter": VOTER.lower(), "value": 1}], "count": 1}
    without = {"votes": [], "count": 0}
    urls, warnings, successes = _run(
        is_action=True,
        kind="vote",
        target=TARGET,
        sender=VOTER,
        value=0,
        side_effect=[_resp(200, with_voter), _resp(200, without)],
    )
    assert urls == [f"http://rpc/rpc/messaging/messages/0x{TARGET}/votes"] * 2
    assert successes == [f"vote retracted — signer absent from standing votes on 'dev' (tx {TX})"]
    assert warnings == []


def test_retract_with_no_prior_vote_is_pre_matched():
    from aitbc_cli.commands.messaging import _action_state_probe

    empty = {"votes": [{"voter": "0x9999", "value": 1}]}
    with patch("requests.get", MagicMock(return_value=_resp(200, empty))):
        assert _action_state_probe("http://rpc", "vote", "dev", TARGET, sender=VOTER, value=0, grantee=None) is True


def test_nonmoderator_action_returns_immediately():
    from aitbc_cli.commands.messaging import _wait_for_seal

    get = MagicMock()
    warnings: list[str] = []
    with (
        patch("requests.get", get),
        patch(f"{MOD}.warning", side_effect=warnings.append),
    ):
        _wait_for_seal(None, "http://rpc", TX, 180.0, topic="dev", is_action=True, kind="hide", expect_listed=False)
    get.assert_not_called()
    assert len(warnings) == 1
    assert "not effective for a non-moderator" in warnings[0]


def test_full_actions_list_caps_wait_at_short_bound():
    """A 100-entry actions list caps the hash wait at the short bound, not the timeout."""
    import itertools

    full = {"actions": [{"tx_hash": f"0x{i:064x}", "block_height": 1} for i in range(100)]}
    clock = itertools.count(step=20)  # each monotonic() call jumps 20s
    from aitbc_cli.commands.messaging import _wait_for_seal

    get = MagicMock(side_effect=_forever(_resp(200, full)))
    warnings: list[str] = []
    successes: list[str] = []
    with (
        patch("requests.get", get),
        patch(f"{MOD}._WAIT_POLL_SECONDS", 0),
        patch("time.monotonic", side_effect=lambda: next(clock) * 1.0),
        patch(f"{MOD}.warning", side_effect=warnings.append),
        patch(f"{MOD}.success", side_effect=successes.append),
    ):
        _wait_for_seal(None, "http://rpc", TX, 180.0, topic="dev", is_action=True, kind="hide")
    assert successes == []
    # Stops at the 30s cap, not the 180s timeout: only a couple of polls.
    assert len(get.call_args_list) <= 3
    assert len(warnings) == 1
    assert "not confirmed" in warnings[0]


def test_retract_pre_matched_command_says_nothing_to_retract():
    from click.testing import CliRunner

    from aitbc_cli.commands.messaging import messaging

    client = MagicMock()
    client.get.side_effect = lambda url: {"tx_hash": TARGET, "topic": "dev", "author": "0xaaaa"}
    infos: list[str] = []
    with (
        patch(f"{MOD}._wallet_address", return_value=VOTER),
        patch(f"{MOD}._resolve_transaction_rpc_url", return_value="http://rpc"),
        patch(f"{MOD}._rpc_client", return_value=client),
        patch(f"{MOD}.resolve_wallet_password", return_value="pw"),
        patch(f"{MOD}._send_transaction_impl", return_value=TX),
        patch(f"{MOD}._action_state_probe", return_value=True),
        patch(f"{MOD}._wait_for_seal") as wait_mock,
        patch(f"{MOD}.info", side_effect=infos.append),
    ):
        result = CliRunner().invoke(messaging, ["vote", TARGET, "retract", "--wallet", "w", "--confirm"])
    assert result.exit_code == 0, result.output
    wait_mock.assert_not_called()
    assert any("nothing to retract" in m for m in infos)


def test_nonmoderator_hide_command_warns_not_waits():
    from click.testing import CliRunner

    from aitbc_cli.commands.messaging import messaging

    client = MagicMock()
    client.get.side_effect = lambda url: {"tx_hash": TARGET, "topic": "dev", "author": "0xaaaa"}
    warnings: list[str] = []
    with (
        patch(f"{MOD}._wallet_address", return_value=VOTER),
        patch(f"{MOD}._resolve_transaction_rpc_url", return_value="http://rpc"),
        patch(f"{MOD}._rpc_client", return_value=client),
        patch(f"{MOD}.resolve_wallet_password", return_value="pw"),
        patch(f"{MOD}._send_transaction_impl", return_value=TX),
        patch(f"{MOD}._topic_moderators_probe", return_value={"0xother"}),
        patch(f"{MOD}.warning", side_effect=warnings.append),
    ):
        result = CliRunner().invoke(messaging, ["hide", TARGET, "--wallet", "w", "--confirm"])
    assert result.exit_code == 0, result.output
    assert any("not effective for a non-moderator" in m for m in warnings)
