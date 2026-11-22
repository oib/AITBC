"""#2395: CLI-signed transactions must skip nonce slots already held by the
sender's own pending mempool transactions."""

import pytest

from aitbc_cli.utils.nonce import next_send_nonce, pending_nonce_floor


class _StubClient:
    def __init__(self, account=None, mempool=None, account_exc=None, mempool_exc=None):
        self._account = account if account is not None else {"nonce": 5}
        self._mempool = mempool if mempool is not None else {"transactions": []}
        self._account_exc = account_exc
        self._mempool_exc = mempool_exc

    def get(self, path: str):
        if path.startswith("/rpc/account/"):
            if self._account_exc:
                raise self._account_exc
            return self._account
        if path.startswith("/rpc/mempool"):
            if self._mempool_exc:
                raise self._mempool_exc
            return self._mempool
        raise AssertionError(f"unexpected path {path}")


def _tx(sender: str, n) -> dict:
    return {"from": sender, "nonce": n}


ADDR = "0x" + "ab" * 20
OTHER = "0x" + "cd" * 20


def test_pending_nonce_floor_skips_own_pending_slots():
    client = _StubClient(mempool={"transactions": [_tx(ADDR, 5), _tx(ADDR, 6), _tx(OTHER, 5)]})
    # sealed 5, pending occupy 5 and 6 -> next is 7
    assert pending_nonce_floor(client, ADDR, 5) == 7


def test_pending_nonce_floor_ignores_stale_and_foreign_nonces():
    client = _StubClient(
        mempool={
            "transactions": [
                _tx(OTHER, 99),  # foreign sender
                _tx(ADDR, "9"),  # non-int nonce
                {"from": ADDR},  # nonce missing
                _tx(ADDR, 3),  # below sealed nonce
            ]
        }
    )
    assert pending_nonce_floor(client, ADDR, 5) == 5


def test_pending_nonce_floor_probe_failure_reports_none():
    """#2479: probe failure is now distinguishable from a readable empty
    mempool — None, not sealed, so offset callers can tell them apart."""
    from aitbc.exceptions import NetworkError

    client = _StubClient(mempool_exc=NetworkError("down"))
    assert pending_nonce_floor(client, ADDR, 5) is None


def test_pending_nonce_floor_malformed_mempool_degrades():
    client = _StubClient(mempool=["not", "a", "dict"])
    assert pending_nonce_floor(client, ADDR, 5) == 5


def test_next_send_nonce_combines_sealed_and_mempool():
    client = _StubClient(
        account={"nonce": 10},
        mempool={"transactions": [_tx(ADDR, 10), _tx(ADDR, 11)]},
    )
    assert next_send_nonce(client, ADDR, "bc-2") == 12


def test_next_send_nonce_raises_when_sealed_lookup_fails():
    from aitbc.exceptions import NetworkError

    client = _StubClient(account_exc=NetworkError("down"))
    with pytest.raises(NetworkError):
        next_send_nonce(client, ADDR)
