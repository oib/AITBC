"""``DatabaseMempool`` admission and read paths (mempool split, #1860).

Mixin methods for ``DatabaseMempool``: ``add``/``batch_add`` admission,
``list_transactions``/``drain`` reads, ``pending_cost``/``slot_occupant``.
Import ``aitbc_chain.mempool`` first (it wires these mixins into the class);
this module is not meant to be imported directly."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import delete, func, select as sa_select
from sqlmodel import Session, select

from .mempool_common import (
    MempoolEntry,
    PendingTransaction,
    _DrainCand,
    _order_for_drain,
    _pending_tx_rows,
    _reject_conflicting_stake_release,
    _tx_cost,
    _tx_nonce,
    _tx_sender,
    _tx_slot_key,
    compute_tx_hash,
)
from .mempool_db_helpers import _slot_advisory_lock, _slot_advisory_lock_by_key, _slot_lock_key_str
from .metrics import metrics_registry

logger = logging.getLogger("aitbc_chain.mempool")


class _DbAdmissionMixin:
    """``DatabaseMempool`` admission (add/batch_add) and read paths."""

    # Attributes supplied by ``DatabaseMempool`` at runtime; declared here so
    # mypy can check the mixin standalone (same convention as the poa split).
    _engine: Any
    _lock: Any
    _max_size: int
    _min_fee: int

    if TYPE_CHECKING:

        def _release_update(self, *args: Any, **kwargs: Any) -> Any: ...
        def _sealed_on_chain_tx_hashes(self, *args: Any, **kwargs: Any) -> Any: ...
        def _update_gauge(self, *args: Any, **kwargs: Any) -> Any: ...

    def add(
        self,
        tx: dict[str, Any],
        chain_id: str | None = None,
        tx_hash: str | None = None,
        commit: bool = True,
    ) -> str:
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        fee = tx.get("fee", 0)
        if fee < self._min_fee:
            raise ValueError(f"Fee {fee} below minimum {self._min_fee}")

        if tx_hash is None:
            tx_hash = compute_tx_hash(tx)
        entry_content = json.dumps(tx, sort_keys=True, separators=(",", ":"))
        size_bytes = len(entry_content.encode())
        if size_bytes > settings.mempool_max_tx_size_bytes:
            metrics_registry.increment(f"mempool_tx_rejected_total_{chain_id}")
            raise ValueError(f"transaction size {size_bytes} exceeds limit {settings.mempool_max_tx_size_bytes}")

        with self._lock:
            with Session(self._engine) as session:
                self._add_tx_session(session, chain_id, tx, tx_hash, entry_content, size_bytes, fee, commit)
            self._update_gauge(chain_id)
        return tx_hash

    def _evict_lowest_for_admission(self, session: Session, chain_id: str, fee: int) -> None:
        """Make room in a full pool — only for a strictly better bid.

        Raises ValueError when the pool is full and the newcomer does not
        outbid the floor (a fee-floor flood must not evict real transactions).
        """
        to_evict = session.exec(
            select(MempoolEntry)
            .where(MempoolEntry.chain_id == chain_id)
            .order_by(
                cast(Any, MempoolEntry.fee).asc(),
                cast(Any, MempoolEntry.received_at).asc(),
                cast(Any, MempoolEntry.tx_hash).asc(),
            )
            .limit(1)
        ).first()
        if to_evict is None or fee <= to_evict.fee:
            metrics_registry.increment(f"mempool_tx_rejected_total_{chain_id}")
            raise ValueError(
                f"mempool full ({self._max_size}): fee {fee} does not beat lowest pending fee "
                f"{to_evict.fee if to_evict is not None else 0}"
            )
        session.delete(to_evict)
        metrics_registry.increment(f"mempool_evictions_total_{chain_id}")

    def _add_tx_session(
        self,
        session: Session,
        chain_id: str,
        tx: dict[str, Any],
        tx_hash: str,
        content: str,
        size_bytes: int,
        fee: int,
        commit: bool,
    ) -> None:
        """Admission critical section for ``add`` — runs inside ``self._lock``."""
        # Check duplicate
        existing = session.exec(
            select(MempoolEntry).where(MempoolEntry.chain_id == chain_id, MempoolEntry.tx_hash == tx_hash)
        ).first()
        if existing:
            if commit:
                session.commit()
            return

        # #1300 P2-v2.4 §4/F8: never re-pool a sealed tx — the
        # on-chain check lives inside the admission critical
        # section so every entry path (RPC, p2p, requeue, orphan)
        # inherits it.
        if self._sealed_on_chain_tx_hashes(chain_id, [tx_hash]):
            metrics_registry.increment(f"mempool_tx_rejected_total_{chain_id}")
            raise ValueError(f"transaction {tx_hash} is already sealed on chain {chain_id}")

        # Signed transactions compete for their (sender, nonce) slot:
        # a second occupant is admitted only as a strictly better bid,
        # replacing the first.
        slot = _tx_slot_key(tx)
        if slot is not None:
            _slot_advisory_lock(session, chain_id, slot)
            occupant = session.exec(
                select(MempoolEntry).where(
                    MempoolEntry.chain_id == chain_id,
                    MempoolEntry.sender == slot[0],
                    MempoolEntry.nonce == slot[1],
                )
            ).first()
            if occupant is not None and occupant.tx_hash != tx_hash:
                if fee <= occupant.fee:
                    metrics_registry.increment(f"mempool_tx_rejected_total_{chain_id}")
                    raise ValueError(
                        f"nonce slot ({slot[0]}, {slot[1]}) already occupied by "
                        f"{occupant.tx_hash} with fee {occupant.fee} >= {fee}"
                    )
                session.delete(occupant)
                # #1300: the ONLY mid-flight release besides owner
                # release/TTL/sealed — recorded atomically here.
                self._release_update(session, chain_id, "outbid", tx_hashes=[occupant.tx_hash])
                metrics_registry.increment(f"mempool_tx_replaced_total_{chain_id}")

        _reject_conflicting_stake_release(tx, _pending_tx_rows(session, chain_id))

        # Evict if full — but only for a newcomer that outbids the
        # floor, or a fee-floor flood could evict real transactions.
        count = session.exec(select(func.count()).select_from(MempoolEntry).where(MempoolEntry.chain_id == chain_id)).one()
        if count >= self._max_size:
            self._evict_lowest_for_admission(session, chain_id, fee)

        entry = MempoolEntry(
            chain_id=chain_id,
            tx_hash=tx_hash,
            content=content,
            fee=fee,
            size_bytes=size_bytes,
            received_at=time.time(),
            sender=_tx_sender(tx) or None,
            nonce=_tx_nonce(tx),
            signed=_tx_slot_key(tx) is not None,
        )
        session.add(entry)
        if commit:
            session.commit()
        metrics_registry.increment(f"mempool_tx_added_total_{chain_id}")

    def batch_add(self, transactions: list[dict[str, Any]], chain_id: str | None = None) -> list[str]:
        """Add multiple transactions in a single session with a single commit."""
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id

        # Pre-compute all tx hashes and validate fees and sizes upfront
        tx_hashes: list[str] = []
        for tx in transactions:
            fee = tx.get("fee", 0)
            if fee < self._min_fee:
                raise ValueError(f"Fee {fee} below minimum {self._min_fee}")
            size = len(json.dumps(tx, sort_keys=True, separators=(",", ":")).encode())
            if size > settings.mempool_max_tx_size_bytes:
                raise ValueError(f"transaction size {size} exceeds limit {settings.mempool_max_tx_size_bytes}")
            tx_hashes.append(compute_tx_hash(tx))

        hashes: list[str] = []
        with self._lock:
            with Session(self._engine) as session:
                # Batch query: fetch all existing hashes in one query (N+1 → 1)
                existing_hashes: set[str] = set()
                if tx_hashes:
                    existing_rows = session.exec(
                        select(MempoolEntry.tx_hash).where(
                            MempoolEntry.chain_id == chain_id,
                            MempoolEntry.tx_hash.in_(tx_hashes),  # type: ignore[attr-defined]
                        )
                    ).all()
                    existing_hashes = set(existing_rows)

                # #1300 P2-v2.4 §4/F8: sealed txs are never re-pooled —
                # same predicate as add(), applied per hash inside the
                # batch admission critical section.
                sealed_hashes = self._sealed_on_chain_tx_hashes(chain_id, tx_hashes)
                if sealed_hashes:
                    metrics_registry.increment(f"mempool_tx_rejected_total_{chain_id}", float(len(sealed_hashes)))
                    logger.warning(
                        "[MEMPOOL] refusing %d already-sealed transactions on %s",
                        len(sealed_hashes),
                        chain_id,
                    )

                # Fetch current count once before the loop (N+1 → 1)
                current_count = session.exec(
                    select(func.count()).select_from(MempoolEntry).where(MempoolEntry.chain_id == chain_id)
                ).one()

                # #1300 P2-v2.4: normalize -> sort -> acquire. The sort key is
                # the sanitized lock-key STRING (the same string
                # _slot_advisory_lock hashes), so every process acquires in
                # one total order and hashtext collisions cannot reorder it.
                for lock_key in sorted(
                    {_slot_lock_key_str(chain_id, s) for s in (_tx_slot_key(t) for t in transactions) if s is not None}
                ):
                    _slot_advisory_lock_by_key(session, lock_key)
                for tx, tx_hash in zip(transactions, tx_hashes, strict=True):
                    recorded, current_count = self._batch_admit_one(
                        session, chain_id, tx, tx_hash, existing_hashes, sealed_hashes, current_count
                    )
                    if recorded:
                        hashes.append(tx_hash)
                session.commit()
            self._update_gauge(chain_id)
        return hashes

    def _batch_evict_for_admission(self, session: Session, chain_id: str, fee: int, current_count: int) -> int | None:
        """Make room in a full pool for a batch newcomer — only on a strictly
        better bid. Returns the updated count, or None when refused."""
        if current_count < self._max_size:
            return current_count
        to_evict = session.exec(
            select(MempoolEntry)
            .where(MempoolEntry.chain_id == chain_id)
            .order_by(
                cast(Any, MempoolEntry.fee).asc(),
                cast(Any, MempoolEntry.received_at).asc(),
                cast(Any, MempoolEntry.tx_hash).asc(),
            )
            .limit(1)
        ).first()
        if to_evict is None or fee <= to_evict.fee:
            metrics_registry.increment(f"mempool_tx_rejected_total_{chain_id}")
            return None
        session.delete(to_evict)
        current_count -= 1
        metrics_registry.increment(f"mempool_evictions_total_{chain_id}")
        return current_count

    def _batch_admit_one(
        self,
        session: Session,
        chain_id: str,
        tx: dict[str, Any],
        tx_hash: str,
        existing_hashes: set[str],
        sealed_hashes: set[str],
        current_count: int,
    ) -> tuple[bool, int]:
        """Admit one transaction inside ``batch_add``'s session.

        Returns ``(recorded, current_count)`` — ``recorded`` is True when the
        hash belongs in the result list (duplicate/sealed passthrough or a
        successful insert), False when the tx was refused.
        """
        # O(1) duplicate check using the pre-fetched set
        if tx_hash in existing_hashes or tx_hash in sealed_hashes:
            return True, current_count

        content = json.dumps(tx, sort_keys=True, separators=(",", ":"))
        size_bytes = len(content.encode())
        fee = tx.get("fee", 0)

        # Same nonce-slot rule as add(): a same-slot occupant is
        # displaced only by a strictly higher fee.
        slot = _tx_slot_key(tx)
        if slot is not None:
            occupant = session.exec(
                select(MempoolEntry).where(
                    MempoolEntry.chain_id == chain_id,
                    MempoolEntry.sender == slot[0],
                    MempoolEntry.nonce == slot[1],
                )
            ).first()
            if occupant is not None and occupant.tx_hash != tx_hash:
                if fee <= occupant.fee:
                    metrics_registry.increment(f"mempool_tx_rejected_total_{chain_id}")
                    return False, current_count
                session.delete(occupant)
                self._release_update(session, chain_id, "outbid", tx_hashes=[occupant.tx_hash])
                current_count -= 1
                metrics_registry.increment(f"mempool_tx_replaced_total_{chain_id}")

        # Evict if full (use in-memory count, decrement on eviction)
        # — only when the newcomer outbids the floor.
        new_count = self._batch_evict_for_admission(session, chain_id, fee, current_count)
        if new_count is None:
            return False, current_count
        current_count = new_count

        entry = MempoolEntry(
            chain_id=chain_id,
            tx_hash=tx_hash,
            content=content,
            fee=fee,
            size_bytes=size_bytes,
            received_at=time.time(),
            sender=_tx_sender(tx) or None,
            nonce=_tx_nonce(tx),
            signed=_tx_slot_key(tx) is not None,
        )
        session.add(entry)
        current_count += 1
        existing_hashes.add(tx_hash)
        metrics_registry.increment(f"mempool_tx_added_total_{chain_id}")
        return True, current_count

    def list_transactions(self, chain_id: str | None = None) -> list[PendingTransaction]:
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            with Session(self._engine) as session:
                entries = session.exec(
                    select(MempoolEntry)
                    .where(MempoolEntry.chain_id == chain_id)
                    .order_by(cast(Any, MempoolEntry.fee).desc(), cast(Any, MempoolEntry.received_at).asc())
                ).all()
        return [
            PendingTransaction(
                tx_hash=e.tx_hash, content=json.loads(e.content), fee=e.fee, size_bytes=e.size_bytes, received_at=e.received_at
            )
            for e in entries
        ]

    def drain(self, max_count: int, max_bytes: int, chain_id: str | None = None) -> list[PendingTransaction]:
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            with Session(self._engine) as session:
                # Rank on the slim columns only: loading every pending row's
                # content per block is wasted memory when the pool holds
                # thousands of entries we will not include.
                entries = session.execute(
                    sa_select(
                        cast(Any, MempoolEntry.tx_hash),
                        cast(Any, MempoolEntry.fee),
                        cast(Any, MempoolEntry.size_bytes),
                        cast(Any, MempoolEntry.received_at),
                        cast(Any, MempoolEntry.sender),
                        cast(Any, MempoolEntry.nonce),
                    ).where(cast(Any, MempoolEntry.chain_id == chain_id))
                ).all()

                picked: list[tuple[str, int, int, float]] = []
                total_bytes = 0
                blocked: set[str] = set()
                for c in _order_for_drain(
                    _DrainCand(fee=f, tx_hash=h, size_bytes=s, sender=snd or None, nonce=n, payload=r)
                    for h, f, s, r, snd, n in entries
                ):
                    if len(picked) >= max_count:
                        break
                    if c.sender is not None and c.sender in blocked:
                        continue
                    if total_bytes + c.size_bytes > max_bytes:
                        if c.sender is not None:
                            blocked.add(c.sender)
                        continue
                    picked.append((c.tx_hash, c.fee, c.size_bytes, c.payload))
                    total_bytes += c.size_bytes

                result: list[PendingTransaction] = []
                if picked:
                    picked_hashes = [h for h, _, _, _ in picked]
                    content_by_hash = {
                        row[0]: row[1]
                        for row in session.exec(
                            select(MempoolEntry.tx_hash, MempoolEntry.content).where(
                                MempoolEntry.chain_id == chain_id,
                                MempoolEntry.tx_hash.in_(picked_hashes),  # type: ignore[attr-defined]
                            )
                        ).all()
                    }
                    result = [
                        PendingTransaction(
                            tx_hash=h,
                            content=json.loads(content_by_hash[h]),
                            fee=f,
                            size_bytes=s,
                            received_at=r,
                        )
                        for h, f, s, r in picked
                        if h in content_by_hash
                    ]
                    session.exec(
                        delete(MempoolEntry).where(
                            MempoolEntry.chain_id == chain_id,  # type: ignore[arg-type]
                            MempoolEntry.tx_hash.in_(picked_hashes),  # type: ignore[attr-defined]
                        )
                    )
                    session.commit()

                metrics_registry.increment(f"mempool_tx_drained_total_{chain_id}", float(len(result)))
            self._update_gauge(chain_id)
            return result

    def pending_cost(self, chain_id: str | None = None, sender: str = "", exclude_nonce: int | None = None) -> int:
        """Total amount+fee committed to the sender's signed pending transactions.

        Same contract as ``InMemoryMempool.pending_cost``: only signed entries
        count, so protocol-internal writes (escrow, bridge) are not charged to
        the sender's admission budget.

        #1300 P2-v2.4: this read opens its own session OUTSIDE any advisory
        lock — it is a best-effort fast-reject only. The authoritative gate
        is the locked re-check inside the admission transaction (slot
        occupancy under ``_slot_advisory_lock``); no correctness claim rests
        on this unlocked read.
        """
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            with Session(self._engine) as session:
                rows = session.exec(
                    select(MempoolEntry.nonce, MempoolEntry.content).where(
                        MempoolEntry.chain_id == chain_id,
                        MempoolEntry.sender == sender.lower(),
                    )
                ).all()
        total = 0
        for nonce_value, content in rows:
            if exclude_nonce is not None and nonce_value == exclude_nonce:
                continue
            try:
                tx = json.loads(content)
            except (TypeError, ValueError):
                continue
            if not isinstance(tx, dict) or not (tx.get("signature") or tx.get("sig")):
                continue
            total += _tx_cost(tx)
        return total

    def slot_occupant(self, chain_id: str | None, sender: str, nonce: int) -> str | None:
        """tx_hash currently holding the (sender, nonce) slot, if any."""
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            with Session(self._engine) as session:
                row = session.exec(
                    select(MempoolEntry.tx_hash).where(
                        MempoolEntry.chain_id == chain_id,
                        MempoolEntry.sender == (sender or "").lower(),
                        MempoolEntry.nonce == nonce,
                    )
                ).first()
        return row
