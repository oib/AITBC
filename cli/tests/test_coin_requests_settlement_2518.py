"""#2518: coin-requests reconcile/reopen must require a *settled* tx, not any 200.

``/rpc/transaction/{hash}`` answers 200 for rejected and still-pending
payouts too — counting those as paid is what let ``reopen`` refuse to undo
a payment that never happened, and let ``reconcile`` miss the discrepancy.
"""

from types import SimpleNamespace

import pytest
import requests
from click.testing import CliRunner

import aitbc_cli.commands.coin_requests as cr_mod


@pytest.fixture
def runner():
    return CliRunner()


class _Resp:
    def __init__(self, status_code, body=None, text=""):
        self.status_code = status_code
        self._body = body
        self.text = text

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def _get_returning(monkeypatch, resp=None, exc=None):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        if exc is not None:
            raise exc
        return resp

    monkeypatch.setattr(cr_mod.requests, "get", fake_get)
    return calls


H = "0x" + "ab" * 32


# ------------------------------------------------------------ helper tri-state


def test_sealed_confirmed_with_height_is_paid(monkeypatch):
    _get_returning(
        monkeypatch,
        _Resp(200, {"tx_hash": H, "status": "confirmed", "block_height": 1234}),
    )
    assert cr_mod._chain_tx_is_sealed("http://rpc", H) is True


def test_rejected_tx_is_absent(monkeypatch):
    """A 200 for a rejected payout must not count as paid."""
    _get_returning(monkeypatch, _Resp(200, {"tx_hash": H, "status": "rejected"}))
    assert cr_mod._chain_tx_is_sealed("http://rpc", H) is False


def test_failed_tx_is_absent(monkeypatch):
    _get_returning(monkeypatch, _Resp(200, {"tx_hash": H, "status": "failed"}))
    assert cr_mod._chain_tx_is_sealed("http://rpc", H) is False


def test_pending_mempool_view_is_unverifiable(monkeypatch):
    """The #2457 pending view carries state=pending and no status — the tx
    may still seal, so it must not read as paid OR absent."""
    _get_returning(monkeypatch, _Resp(200, {"tx_hash": H, "state": "pending"}))
    assert cr_mod._chain_tx_is_sealed("http://rpc", H) is None


def test_confirmed_without_height_is_unverifiable(monkeypatch):
    _get_returning(monkeypatch, _Resp(200, {"tx_hash": H, "status": "confirmed", "block_height": None}))
    assert cr_mod._chain_tx_is_sealed("http://rpc", H) is None


def test_404_is_absent(monkeypatch):
    _get_returning(monkeypatch, _Resp(404))
    assert cr_mod._chain_tx_is_sealed("http://rpc", H) is False


def test_server_error_is_unverifiable(monkeypatch):
    _get_returning(monkeypatch, _Resp(500, text="boom"))
    assert cr_mod._chain_tx_is_sealed("http://rpc", H) is None


def test_unreachable_is_unverifiable(monkeypatch):
    _get_returning(monkeypatch, exc=requests.ConnectionError("down"))
    assert cr_mod._chain_tx_is_sealed("http://rpc", H) is None


def test_unparseable_body_is_unverifiable(monkeypatch):
    _get_returning(monkeypatch, _Resp(200, body=ValueError("no json")))
    assert cr_mod._chain_tx_is_sealed("http://rpc", H) is None


# ------------------------------------------------------- reconcile / reopen


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *a, **kw):
        return self

    def order_by(self, *a, **kw):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def query(self, *a, **kw):
        return _FakeQuery(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _req(tid="req-1", tx_hash=H):
    return SimpleNamespace(
        id=tid,
        transaction_hash=tx_hash,
        wallet_address="0xw",
        amount=None,
        audit_log="",
    )


def _patch_db(monkeypatch, rows):
    monkeypatch.setattr(cr_mod, "init_db", lambda *a, **kw: None)
    monkeypatch.setattr(cr_mod, "get_db_session", lambda: _FakeSession(rows))


def test_reconcile_flags_rejected_payout(monkeypatch, runner):
    """A rejected payout must surface as a discrepancy, not read as paid."""
    _patch_db(monkeypatch, [_req()])
    _get_returning(monkeypatch, _Resp(200, {"status": "rejected"}))
    result = runner.invoke(
        cr_mod.coin_requests,
        obj={"output_format": "table"},
        args=["reconcile", "--rpc-url", "http://rpc"],
    )
    assert result.exit_code == 0
    assert "no settled" in result.output
    assert "1 not on chain" in result.output


def test_reconcile_skips_sealed_payout(monkeypatch, runner):
    _patch_db(monkeypatch, [_req()])
    _get_returning(monkeypatch, _Resp(200, {"status": "confirmed", "block_height": 99}))
    result = runner.invoke(
        cr_mod.coin_requests,
        obj={"output_format": "table"},
        args=["reconcile", "--rpc-url", "http://rpc"],
    )
    assert result.exit_code == 0
    assert "0 not on chain" in result.output


def test_reconcile_counts_pending_as_unverifiable(monkeypatch, runner):
    _patch_db(monkeypatch, [_req()])
    _get_returning(monkeypatch, _Resp(200, {"state": "pending"}))
    result = runner.invoke(
        cr_mod.coin_requests,
        obj={"output_format": "table"},
        args=["reconcile", "--rpc-url", "http://rpc"],
    )
    assert result.exit_code == 0
    assert "1 unverifiable" in result.output
    assert "0 not on chain" in result.output


def test_reopen_allows_rejected_payout(monkeypatch, runner):
    """The reported bug: a rejected payout used to refuse reopen forever."""
    req = _req()
    _patch_db(monkeypatch, [req])
    _get_returning(monkeypatch, _Resp(200, {"status": "rejected"}))
    result = runner.invoke(
        cr_mod.coin_requests,
        obj={"output_format": "table"},
        args=["reopen", "--request-id", "req-1", "--rpc-url", "http://rpc"],
    )
    assert result.exit_code == 0
    assert "Reopened req-1" in result.output
    assert req.transaction_hash is None


def test_reopen_still_refuses_sealed_payout(monkeypatch, runner):
    req = _req()
    _patch_db(monkeypatch, [req])
    _get_returning(monkeypatch, _Resp(200, {"status": "confirmed", "block_height": 7}))
    result = runner.invoke(
        cr_mod.coin_requests,
        obj={"output_format": "table"},
        args=["reopen", "--request-id", "req-1", "--rpc-url", "http://rpc"],
    )
    assert result.exit_code != 0
    assert "settled on chain" in result.output
    assert req.transaction_hash == H


def test_reopen_refuses_pending_payout(monkeypatch, runner):
    """Pending may still seal — reopening it risks a double pay."""
    req = _req()
    _patch_db(monkeypatch, [req])
    _get_returning(monkeypatch, _Resp(200, {"state": "pending"}))
    result = runner.invoke(
        cr_mod.coin_requests,
        obj={"output_format": "table"},
        args=["reopen", "--request-id", "req-1", "--rpc-url", "http://rpc"],
    )
    assert result.exit_code != 0
    assert "Refusing to reopen" in result.output
    assert req.transaction_hash == H
