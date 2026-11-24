"""Pin for AUDIT-EDGE-CLI-COINREQ-EXECUTE-NOCONFIRM (#2884).

``coin-requests execute`` signs+posts a genesis-faucet transfer (or
forwards it to the hub) with no confirmation — any process that can run
the CLI moves real funds. ``execute`` and ``request`` (auto-execute path)
now require ``--yes`` or an interactive confirm naming amount+recipient.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from aitbc.models import CoinRequest, CoinRequestStatus


def _approved_req():
    req = MagicMock(spec=CoinRequest)
    req.id = "req-test-1"
    req.status = CoinRequestStatus.APPROVED
    req.expires_at = None
    req.transaction_hash = None
    req.wallet_address = "0xRecipientAddr"
    req.amount = 3 * 10**18
    req.sender = "sender-1"
    req.audit_log = ""
    return req


def _session_returning(req):
    session = MagicMock()
    query = MagicMock()
    query.filter.return_value.first.return_value = req
    session.query.return_value = query
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=session)
    cm.__exit__ = MagicMock(return_value=None)
    return cm


def _invoke_execute(runner, monkeypatch, req, *extra, input_text=""):
    from aitbc_cli.commands import coin_requests as cr

    monkeypatch.setattr(cr, "init_db", lambda *a, **k: None)
    monkeypatch.setattr(cr, "get_db_session", lambda: _session_returning(req))
    with patch.object(cr, "TransactionService") as tx_cls:
        result = runner.invoke(
            cr.coin_requests, ["execute", "--request-id", req.id, *extra], input=input_text, catch_exceptions=False
        )
    return result, tx_cls


def test_execute_requires_confirmation(runner, monkeypatch):
    """No --yes + non-interactive stdin: aborts at the prompt, never builds TransactionService."""
    result, tx_cls = _invoke_execute(runner, monkeypatch, _approved_req())
    assert result.exit_code != 0
    tx_cls.assert_not_called()


def test_execute_confirm_no_aborts(runner, monkeypatch):
    result, tx_cls = _invoke_execute(runner, monkeypatch, _approved_req(), input_text="n\n")
    assert result.exit_code != 0
    tx_cls.assert_not_called()


def test_execute_yes_reaches_execution(runner, monkeypatch):
    """--yes passes the gate; execution then proceeds (and fails later on
    missing hub config here — proving the prompt was skipped, not the flow)."""
    from aitbc_cli.commands import coin_requests as cr

    monkeypatch.setattr(cr, "init_db", lambda *a, **k: None)
    monkeypatch.setattr(cr, "get_db_session", lambda: _session_returning(_approved_req()))
    with (
        patch.object(cr, "TransactionService") as tx_cls,
        patch("aitbc.config.hub.hub_agent_url", return_value=None),
    ):
        tx_cls.return_value.genesis_private_key = None
        result = runner.invoke(cr.coin_requests, ["execute", "--request-id", "req-test-1", "--yes"])
    tx_cls.assert_called_once()
    assert result.exit_code != 0
    assert "hub" in result.output.lower()


def test_execute_prompt_names_amount_and_recipient(runner, monkeypatch):
    result, _ = _invoke_execute(runner, monkeypatch, _approved_req(), input_text="\n")
    # click.confirm renders the prompt text before reading the (empty) answer.
    assert "0xRecipientAddr" in result.output
