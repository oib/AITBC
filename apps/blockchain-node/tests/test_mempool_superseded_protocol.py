"""Phase-0 test for MEMPOOL-SUPERSEDE-DROPS-PROTOCOL-TX-1 (#796).

``remove_superseded(chain, sender, nonce)`` runs for every tx of an imported
block and deletes every pending row of that sender with ``nonce <= sealed`` —
without checking for a signature. Protocol-internal writes (escrow, bond,
bridge: ``from=<user>``, placeholder nonce 0, no top-level signature) are
swept out by any imported tx from the same sender, silently: the RPC caller
was already told success and the write never seals.

Desired behaviour (pinned by these tests): only entries holding a signed
slot (``_tx_slot_key is not None``) may be dropped; unsigned protocol entries
survive. On current main the unsigned-survives tests FAIL on both backends —
that is the bug demonstration. The signed-drop and keep tests pass today.
"""

import pytest
from aitbc_chain.mempool import DatabaseMempool, InMemoryMempool
from aitbc_chain.metrics import metrics_registry

CHAIN = "bc-2.test"  # conftest pins settings.chain_id to this value
SENDER = "0xSender"
OTHER = "0xOther"


@pytest.fixture(autouse=True)
def reset_metrics():
    metrics_registry.reset()
    yield
    metrics_registry.reset()


def _protocol_tx(sender: str, nonce: int = 0) -> dict:
    """Unsigned protocol-internal write (escrow/bond/bridge shape)."""
    return {
        "type": "ESCROW_LOCK",
        "from": sender,
        "nonce": nonce,
        "payload": {"job_id": "job-1", "amount": 1000},
    }


def _signed_tx(sender: str, nonce: int, fee: int = 0) -> dict:
    return {
        "from": sender,
        "to": "0xRecipient",
        "amount": 10,
        "fee": fee,
        "nonce": nonce,
        "signature": "0xdeadbeef",
    }


def _pending_hashes(pool) -> set[str]:
    return {tx.get("_hash") or getattr(tx, "tx_hash", None) for tx in pool.get_pending_transactions(CHAIN)}


def _pending_contents(pool) -> list[dict]:
    return pool.get_pending_transactions(CHAIN)


@pytest.fixture(params=["memory", "db"])
def pool(request, tmp_path):
    if request.param == "memory":
        yield InMemoryMempool()
    else:
        yield DatabaseMempool(f"sqlite:///{tmp_path / 'mempool.db'}", max_size=100, min_fee=0)


class TestRemoveSupersededKeepsUnsignedProtocolEntries:
    def test_unsigned_protocol_entry_survives(self, pool):
        """An unsigned protocol-internal entry must NOT be dropped when a
        signed tx from the same sender seals at a higher nonce."""
        pool.add(_protocol_tx(SENDER, nonce=0), chain_id=CHAIN)
        removed = pool.remove_superseded(CHAIN, SENDER, 5)
        assert removed == 0, "unsigned protocol entry was swept by an unrelated sealed tx"
        remaining = _pending_contents(pool)
        assert any(tx.get("type") == "ESCROW_LOCK" for tx in remaining)

    def test_signed_entry_at_sealed_nonce_is_dropped(self, pool):
        pool.add(_signed_tx(SENDER, nonce=5), chain_id=CHAIN)
        removed = pool.remove_superseded(CHAIN, SENDER, 5)
        assert removed == 1
        assert all(tx.get("signature") != "0xdeadbeef" or tx.get("nonce") != 5 for tx in _pending_contents(pool))

    def test_signed_entry_below_sealed_nonce_is_dropped(self, pool):
        pool.add(_signed_tx(SENDER, nonce=3), chain_id=CHAIN)
        removed = pool.remove_superseded(CHAIN, SENDER, 5)
        assert removed == 1

    def test_higher_nonce_signed_entry_is_kept(self, pool):
        pool.add(_signed_tx(SENDER, nonce=9), chain_id=CHAIN)
        removed = pool.remove_superseded(CHAIN, SENDER, 5)
        assert removed == 0
        assert any(tx.get("nonce") == 9 for tx in _pending_contents(pool))

    def test_other_sender_untouched(self, pool):
        pool.add(_signed_tx(OTHER, nonce=2), chain_id=CHAIN)
        pool.add(_protocol_tx(OTHER, nonce=0), chain_id=CHAIN)
        removed = pool.remove_superseded(CHAIN, SENDER, 5)
        assert removed == 0
        assert len(_pending_contents(pool)) == 2

    def test_mixed_pool_only_signed_dropped(self, pool):
        """The realistic sweep: same sender holds a signed pending tx below the
        sealed nonce AND an unsigned protocol entry — only the signed row goes."""
        pool.add(_signed_tx(SENDER, nonce=4), chain_id=CHAIN)
        pool.add(_signed_tx(SENDER, nonce=8), chain_id=CHAIN)
        pool.add(_protocol_tx(SENDER, nonce=0), chain_id=CHAIN)
        pool.add(_signed_tx(OTHER, nonce=1), chain_id=CHAIN)
        removed = pool.remove_superseded(CHAIN, SENDER, 5)
        assert removed == 1
        remaining = _pending_contents(pool)
        kinds = {(tx.get("type"), tx.get("nonce")) for tx in remaining}
        assert ("ESCROW_LOCK", 0) in kinds  # protocol entry survived
        assert (None, 8) in kinds  # higher-nonce signed kept
        assert (None, 1) in kinds  # other sender kept
        assert (None, 4) not in kinds  # superseded signed row dropped
