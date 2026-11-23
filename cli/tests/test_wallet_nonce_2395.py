"""#2395: CLI-signed transactions must skip nonce slots already held by the
sender's own pending mempool transactions."""

import pytest

from aitbc_cli.utils.nonce import NonceClassificationError, next_send_nonce, pending_nonce_floor


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


def test_pending_nonce_floor_fills_the_lowest_gap():
    """#2745: a stranded/dead entry ahead of a hole must not push the next
    signature into future-nonce territory — apply seals nonces sequentially,
    so the hole is the only slot that can land."""
    client = _StubClient(mempool={"transactions": [_tx(ADDR, 189), _tx(ADDR, 191)]})
    # sealed 188, pending occupy 189 and 191 -> 188 is the lowest free slot
    assert pending_nonce_floor(client, ADDR, 188) == 188


def test_pending_nonce_floor_contiguous_still_advances():
    client = _StubClient(mempool={"transactions": [_tx(ADDR, 188), _tx(ADDR, 189)]})
    assert pending_nonce_floor(client, ADDR, 188) == 190


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


# --- #2745: opt-in rejection-aware nonce view -------------------------------


def test_nonce_view_negative_marker_fails_closed_for_all_callers():
    """``nonce_view_complete: false`` is a known "cannot classify" — it must
    bypass the legacy fallback for ordinary sends too, never read as an
    empty pool that would sign a still-held nonce."""
    client = _StubClient(mempool={"success": False, "nonce_view_complete": False, "transactions": [], "count": 0})
    with pytest.raises(NonceClassificationError, match="Could not classify"):
        pending_nonce_floor(client, ADDR, 5)
    with pytest.raises(NonceClassificationError, match="Could not classify"):
        pending_nonce_floor(client, ADDR, 5, require_nonce_view=True)


@pytest.mark.parametrize(
    "mempool_data",
    [
        {"success": True, "nonce_view_complete": True, "transactions": "nope"},
        {"success": True, "nonce_view_complete": True, "transactions": [{"from": ADDR, "nonce": "5"}]},
    ],
    ids=["non-list-transactions", "malformed-member"],
)
def test_nonce_view_malformed_classified_answer_fails_closed(mempool_data):
    """``complete: true`` promises a classified, well-formed list — a
    non-list ``transactions`` or a member that cannot name sender+nonce is
    malformed, not an empty pool."""
    client = _StubClient(mempool=mempool_data)
    with pytest.raises(NonceClassificationError, match="Could not classify"):
        pending_nonce_floor(client, ADDR, 5)
    with pytest.raises(NonceClassificationError, match="Could not classify"):
        pending_nonce_floor(client, ADDR, 5, require_nonce_view=True)


def test_require_nonce_view_rejects_legacy_unmarked_answer():
    """A normal listing without the marker is a legacy node: ordinary sends
    keep counting every occupant, but an explicit retry refuses to sign on
    an unclassified view."""
    client = _StubClient(mempool={"transactions": [_tx(ADDR, 5)]})
    with pytest.raises(NonceClassificationError, match="rejection-aware"):
        pending_nonce_floor(client, ADDR, 5, require_nonce_view=True)
    assert pending_nonce_floor(client, ADDR, 5) == 6


def test_require_nonce_view_probe_failure_raises_not_falls_back():
    """Transport failure under the opt-in must fail closed — the legacy
    ``None`` fallback would sign a nonce the node never classified."""
    from aitbc.exceptions import NetworkError

    client = _StubClient(mempool_exc=NetworkError("down"))
    with pytest.raises(NonceClassificationError, match="Could not read"):
        pending_nonce_floor(client, ADDR, 5, require_nonce_view=True)
    assert pending_nonce_floor(client, ADDR, 5) is None


def test_require_nonce_view_sends_opt_in_query_and_uses_classified_entries():
    paths: list[str] = []

    class _RecordingClient:
        def get(self, path: str):
            paths.append(path)
            return {
                "success": True,
                "nonce_view_complete": True,
                "transactions": [_tx(ADDR, 5), _tx(ADDR, 6), _tx(OTHER, 5)],
                "count": 3,
            }

    assert pending_nonce_floor(_RecordingClient(), ADDR, 5, "test-chain", require_nonce_view=True) == 7
    assert paths == ["/rpc/mempool?limit=500&nonce_view=true&chain_id=test-chain"]
