"""#2396: protocol-queued transfers must relay to mesh peers.

``queue_protocol_transfer`` wrote only the serving host's local mempool, so
a stake/unstake/bounty request handled by a non-proposing node returned a tx
hash for a transaction no proposer ever saw — the phantom leg the player hit
on node0. The helper now schedules the same ``_queue_peer_fanout`` the REST
submit path uses (#2361).
"""

from aitbc_chain import protocol_escrow


class _FakeMempool:
    def __init__(self):
        self.added: list[dict] = []

    def add(self, tx, chain_id=None, tx_hash=None):
        self.added.append(tx)
        return "0x" + "ab" * 32


def test_queue_protocol_transfer_schedules_peer_fanout(monkeypatch):
    mempool = _FakeMempool()
    monkeypatch.setattr("aitbc_chain.mempool.get_mempool", lambda: mempool)

    relayed: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "aitbc_chain.rpc.transactions._queue_peer_fanout",
        lambda chain_id, tx_data: relayed.append((chain_id, tx_data)),
    )

    tx_hash = protocol_escrow.queue_protocol_transfer(
        sender="0x" + "11" * 20,
        recipient="0x" + "22" * 20,
        amount=100,
        chain_id="bc-2",
        tx_type="STAKE_LOCK",
        payload={"stake_id": "1"},
    )

    assert tx_hash == "0x" + "ab" * 32
    assert len(mempool.added) == 1
    assert len(relayed) == 1
    chain_id, tx_data = relayed[0]
    assert chain_id == "bc-2"
    assert tx_data is mempool.added[0]
    assert tx_data["type"] == "STAKE_LOCK"


def test_queue_protocol_transfer_survives_fanout_failure(monkeypatch):
    mempool = _FakeMempool()
    monkeypatch.setattr("aitbc_chain.mempool.get_mempool", lambda: mempool)

    def _boom(chain_id, tx_data):
        raise RuntimeError("no event loop")

    monkeypatch.setattr("aitbc_chain.rpc.transactions._queue_peer_fanout", _boom)

    tx_hash = protocol_escrow.queue_protocol_transfer(
        sender="0x" + "11" * 20,
        recipient="0x" + "22" * 20,
        amount=100,
        chain_id="bc-2",
        tx_type="STAKE_RELEASE",
    )

    # The local mempool entry still stands — this host may be the proposer.
    assert tx_hash == "0x" + "ab" * 32
    assert len(mempool.added) == 1
