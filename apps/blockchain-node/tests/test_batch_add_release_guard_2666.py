"""AUDIT-BN-MEMPOOL-BATCH-ADD-SKIPS-STAKE-RELEASE-GUARD-1 (#2666):

``DatabaseMempool.batch_add`` admitted each transaction through
``_batch_admit_one`` without the ``_reject_conflicting_stake_release`` guard
that ``add`` enforces — so a batch (or a batch member against the pool) could
pool two STAKE_RELEASEs claiming the same lock, the double-payout the guard
exists to stop. The guard now runs per member against the pool rows (the
replaced slot occupant excluded, matching ``add``'s post-delete view) plus
earlier members of the same batch via session autoflush.
"""

from __future__ import annotations

from aitbc_chain.mempool import DatabaseMempool

CHAIN = "c2666"
LOCK = "0x" + "cc" * 32
OTHER_LOCK = "0x" + "dd" * 32


def _release(sender: str, nonce: int, fee: int, lock: str = LOCK) -> dict:
    return {
        "from": sender,
        "to": "0xescrow",
        "amount": 0,
        "fee": fee,
        "nonce": nonce,
        "type": "STAKE_RELEASE",
        "payload": {"lock_tx_hashes": [lock]},
        "signature": "0xsig",
    }


def _pool(tmp_path) -> DatabaseMempool:
    return DatabaseMempool(f"sqlite:///{tmp_path / 'mempool.db'}")


def _pending_release_hashes(pool: DatabaseMempool) -> set[str]:
    return {
        t.tx_hash
        for t in pool.list_transactions(chain_id=CHAIN)
        if str(t.content.get("type", "")).upper() == "STAKE_RELEASE"
        and LOCK in (t.content.get("payload") or {}).get("lock_tx_hashes", [])
    }


def test_batch_member_conflicting_with_pool_is_refused(tmp_path) -> None:
    pool = _pool(tmp_path)
    pool.add(_release("0xb", 0, 1), chain_id=CHAIN)

    recorded = pool.batch_add([_release("0xa", 0, 9)], chain_id=CHAIN)

    assert recorded == []
    assert len(_pending_release_hashes(pool)) == 1


def test_batch_internal_conflict_admits_only_first(tmp_path) -> None:
    pool = _pool(tmp_path)

    recorded = pool.batch_add(
        [_release("0xa", 0, 5), _release("0xb", 0, 5), _release("0xc", 0, 5, OTHER_LOCK)],
        chain_id=CHAIN,
    )

    assert len(recorded) == 2
    assert len(_pending_release_hashes(pool)) == 1
    # The unrelated-lock release in the same batch is admitted.
    assert pool.size(chain_id=CHAIN) == 2


def test_batch_release_replacing_own_slot_still_works(tmp_path) -> None:
    """A same-slot release replacement must not refuse against its own
    occupant — add() sees the post-delete pool; batch excludes the occupant."""
    pool = _pool(tmp_path)
    occupant_hash = pool.add(_release("0xa", 0, 5), chain_id=CHAIN)

    recorded = pool.batch_add([_release("0xa", 0, 9)], chain_id=CHAIN)

    assert recorded != []
    hashes = {t.tx_hash for t in pool.list_transactions(chain_id=CHAIN)}
    assert occupant_hash not in hashes
    assert len(hashes) == 1
