"""#2735: a pending peer-relay summary surfaces as ``info``, not ``warning``.

The node reports ``peer_relay.status == "pending"`` when the bounded
fan-out wait timed out — the tx is already in the local mempool and peer
delivery is unknown, not failed. The CLI must pass ``info`` through to the
JSON document and print it via the stderr-routed status helpers so
``--output json`` stdout stays a single clean document.
"""

import json
from decimal import Decimal
from unittest.mock import Mock

import click

from aitbc_cli.commands import transactions as tx_cmd

INFO_TEXT = (
    "transaction accepted into the local mempool; peer relay is still pending "
    "(summary wait timed out), so peer delivery is unknown; "
    "not confirmed - check transaction status for sealing"
)

PENDING_RESPONSE = {
    "success": True,
    "transaction_hash": "0xabc",
    "message": "Transaction submitted to mempool",
    "peer_relay": {"status": "pending", "attempted": None, "accepted": None},
    "info": INFO_TEXT,
}


class _PendingHTTP:
    """AITBCHTTPClient stand-in: /rpc/transaction returns the pending relay doc."""

    def __init__(self, base_url="", timeout=None, **kw):
        self.base_url = base_url

    def post(self, endpoint, json=None, **kw):
        assert endpoint == "/rpc/transaction"
        return dict(PENDING_RESPONSE)


def test_submit_signed_transaction_returns_response_and_emits_info_once(monkeypatch):
    monkeypatch.setattr(tx_cmd, "AITBCHTTPClient", _PendingHTTP)
    info_spy = Mock()
    success_spy = Mock()
    monkeypatch.setattr(tx_cmd, "info", info_spy)
    monkeypatch.setattr(tx_cmd, "success", success_spy)

    result = tx_cmd._submit_signed_transaction(
        "http://node:1",
        {"from": "0xsender", "to": "0xdef", "amount": 1},
        "sender",
        "0xdef",
    )

    assert result == PENDING_RESPONSE
    info_spy.assert_called_once_with(INFO_TEXT)
    success_spy.assert_called_once()


def test_emit_send_json_document_pending_fields(capsys):
    send_out = {"transaction": {}, "submit": dict(PENDING_RESPONSE)}
    tx_cmd._emit_send_json_document(
        send_out,
        tx_hash="0xabc",
        tx_type="TRANSFER",
        from_wallet="sender",
        key_env=None,
        to_address="0xdef",
        amount=Decimal("1"),
        fee=Decimal("0"),
        explorer_result=None,
    )
    doc = json.loads(capsys.readouterr().out)
    assert doc["transaction_hash"] == "0xabc"
    assert doc["status"] == "submitted"
    assert doc["type"] == "TRANSFER"
    assert doc["peer_relay"] == PENDING_RESPONSE["peer_relay"]
    assert doc["info"] == INFO_TEXT
    assert "warning" not in doc


def test_emit_send_json_document_warning_passthrough_still_works(capsys):
    """Known-failure warnings keep flowing next to peer_relay (#2361 pin)."""
    warning_text = "transaction relay reached no mesh peers; on this non-proposing host it cannot reach a block"
    submit = {
        "transaction_hash": "0xabc",
        "peer_relay": {"status": "failed", "attempted": 2, "accepted": 0},
        "warning": warning_text,
    }
    send_out = {"transaction": {}, "submit": submit}
    tx_cmd._emit_send_json_document(
        send_out,
        tx_hash="0xabc",
        tx_type="TRANSFER",
        from_wallet="sender",
        key_env=None,
        to_address="0xdef",
        amount=Decimal("1"),
        fee=Decimal("0"),
        explorer_result=None,
    )
    doc = json.loads(capsys.readouterr().out)
    assert doc["peer_relay"] == submit["peer_relay"]
    assert doc["warning"] == warning_text
    assert "info" not in doc
    assert doc["status"] == "submitted"


def test_status_helpers_stay_off_stdout_in_json_mode(capsys):
    """info/success route to stderr under an active json format so the single
    stdout document contract (#2416) is not polluted by status lines."""
    ctx = click.Context(click.Command("probe"), obj={"output_format": "json"})
    with ctx:
        tx_cmd.info("relay info line")
        tx_cmd.success("submitted line")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "relay info line" in captured.err
    assert "submitted line" in captured.err
