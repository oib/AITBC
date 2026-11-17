"""``DatabaseMempool`` removal, reservation and lifecycle paths (mempool split, #1860).

Mixin methods for ``DatabaseMempool``: remove/batch_remove/remove_superseded,
the #1300 owner/epoch reservation lifecycle (peek_reserve, release,
live_reservations, reconcile_sealed) and the remaining read/gauge paths.
Import ``aitbc_chain.mempool`` first (it wires these mixins into the class);
this module is not meant to be imported directly."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterable
from typing import Any, cast

from sqlalchemy import bindparam, delete, func, select as sa_select, text
from sqlmodel import Session, select

from .mempool_common import MempoolEntry, PendingTransaction, _DrainCand, _order_for_drain
from .metrics import (
    mempool_pending_count,
    mempool_pending_size_bytes,
    mempool_reservation_release_total,
    metrics_registry,
)

logger = logging.getLogger("aitbc_chain.mempool")


class _DbReservationMixin:
    """``DatabaseMempool`` removal, reservation and lifecycle paths."""

    # Attributes supplied by ``DatabaseMempool`` at runtime; declared here so
    # mypy can check the mixin standalone (same convention as the poa split).
    _engine: Any
    _lock: Any

    def _live_reserved_set(self, session: Session, chain_id: str, now: float | None = None) -> set[str]:
        """tx_hashes holding a live reservation on this chain (any owner)."""
        now = now if now is not None else time.time()
        try:
            rows = session.execute(
                text(
                    "SELECT tx_hash FROM mempool_reservation WHERE chain_id=:chain_id AND state='reserved' AND expires_at>:now"
                ),
                {"chain_id": chain_id, "now": now},
            ).all()
        except Exception as e:  # noqa: BLE001 - pre-migration DB has no reservation table
            logger.debug("mempool reservation probe failed: %s", type(e).__name__)
            # Pre-migration database without the reservation table — nothing
            # is reserved, so every deleter keeps baseline behavior.
            return set()
        return {r[0] for r in rows}

    def remove(self, tx_hash: str, chain_id: str | None = None, commit: bool = True) -> bool:
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            with Session(self._engine) as session:
                # #1300: a live-reserved row is mid-attempt — generic removes
                # (dead-occupant sweeps, import-path deletes) must not take it.
                # Sealed reconciliation goes through reconcile_sealed, which
                # releases the marker in the same transaction.
                if tx_hash in self._live_reserved_set(session, chain_id):
                    return False
                entry = session.exec(
                    select(MempoolEntry).where(MempoolEntry.chain_id == chain_id, MempoolEntry.tx_hash == tx_hash)
                ).first()
                if entry:
                    session.delete(entry)
                    if commit:
                        session.commit()
                    removed = True
                else:
                    removed = False
            if removed:
                self._update_gauge(chain_id)
            return removed

    def remove_superseded(self, chain_id: str | None, sender: str, nonce: int, commit: bool = True) -> int:
        """Drop rows whose (sender, nonce) slot a sealed block consumed —
        they can never seal and otherwise refuse resubmits until TTL
        expiry (Refs #717)."""
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            with Session(self._engine) as session:
                rows = session.exec(
                    select(MempoolEntry).where(
                        MempoolEntry.chain_id == chain_id,
                        MempoolEntry.sender == sender.lower(),
                        cast(Any, MempoolEntry.nonce) <= nonce,
                        # Only slot-holding (signed) rows may be swept —
                        # unsigned protocol-internal writes survive (#796).
                        # NULL reads as not-signed for rows that predate the
                        # backfill.
                        MempoolEntry.signed.is_(True),  # type: ignore[union-attr]
                    )
                ).all()
                # #1300: never sweep a row mid-attempt.
                reserved = self._live_reserved_set(session, chain_id)
                rows = [r for r in rows if r.tx_hash not in reserved]
                for row in rows:
                    session.delete(row)
                if commit:
                    session.commit()
            if rows:
                self._update_gauge(chain_id)
            return len(rows)

    def batch_remove(self, hashes: list[str], chain_id: str | None = None) -> int:
        """Remove multiple transactions in a single session with a single commit."""
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        if not hashes:
            return 0

        with self._lock:
            with Session(self._engine) as session:
                # #1300: reserved rows are mid-attempt — batch_remove is not
                # the sealed-reconcile path (that is reconcile_sealed).
                reserved = self._live_reserved_set(session, chain_id)
                removable = [h for h in hashes if h not in reserved]
                if not removable:
                    return 0
                result = session.exec(
                    delete(MempoolEntry).where(
                        MempoolEntry.chain_id == chain_id,  # type: ignore[arg-type]
                        MempoolEntry.tx_hash.in_(removable),  # type: ignore[attr-defined]
                    )
                )
                session.commit()
                removed = result.rowcount if result.rowcount is not None else 0
            self._update_gauge(chain_id)
        return removed

    # ------------------------------------------------------------------
    # #1300 P2-v2.4: owner/epoch reservations (peek_reserve lifecycle)
    # ------------------------------------------------------------------

    _RESERVATION_ADVISORY_KEY = "mempool-peek-reserve"

    def _sweep_expired_reservations(self, session: Session, chain_id: str, now: float) -> int:
        """Release reservations whose TTL lapsed. Caller holds the txn."""
        result = session.execute(
            text(
                "UPDATE mempool_reservation SET state = 'released', release_reason = 'expired', "
                "released_at = :now WHERE chain_id = :chain_id AND state = 'reserved' AND expires_at <= :now"
            ),
            {"now": now, "chain_id": chain_id},
        )
        return cast(Any, result).rowcount or 0

    def peek_reserve(
        self,
        chain_id: str,
        *,
        owner_id: str,
        proposer: str = "",
        height: int | None = None,
        round: int | None = None,
        attempt_seq: int = 0,
        ttl_seconds: float | None = None,
        max_count: int = 0,
        max_bytes: int = 0,
    ) -> list[PendingTransaction]:
        """Atomically select drain candidates and mark them reserved — no delete.

        P2-v2.4 §2: one backend transaction sweeps expired reservations,
        orders candidates with the unchanged ``_order_for_drain`` over slim
        columns, excludes rows under a live reservation owned by someone
        else, then writes reservation markers and commits. The caller gets
        the tx contents; the rows stay pooled until release or reconcile.

        SQLite takes ``BEGIN IMMEDIATE`` on a dedicated connection so a
        concurrent admission's write serializes behind the peek; PostgreSQL
        serializes reservers on a transaction-scoped advisory lock (slot
        advisory locks already bound the admission side).
        """
        from .config import settings

        if ttl_seconds is None:
            ttl_seconds = float(settings.mempool_reservation_ttl_seconds)
        now = time.time()
        expires = now + ttl_seconds

        with self._lock:
            if self._engine.dialect.name == "sqlite":
                return self._peek_reserve_sqlite(
                    chain_id,
                    owner_id=owner_id,
                    proposer=proposer,
                    height=height,
                    round=round,
                    attempt_seq=attempt_seq,
                    now=now,
                    expires=expires,
                    max_count=max_count,
                    max_bytes=max_bytes,
                )
            return self._peek_reserve_session(
                chain_id,
                owner_id=owner_id,
                proposer=proposer,
                height=height,
                round=round,
                attempt_seq=attempt_seq,
                now=now,
                expires=expires,
                max_count=max_count,
                max_bytes=max_bytes,
            )

    def _live_reserved_hashes(self, session: Session, chain_id: str, now: float, exclude_owner: str) -> set[str]:
        rows = session.execute(
            text(
                "SELECT tx_hash FROM mempool_reservation WHERE chain_id = :chain_id "
                "AND state = 'reserved' AND expires_at > :now AND owner_id != :owner"
            ),
            {"chain_id": chain_id, "now": now, "owner": exclude_owner},
        ).all()
        return {r[0] for r in rows}

    def _ordered_candidates(self, session: Session, chain_id: str) -> list[_DrainCand]:
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
        return list(
            _order_for_drain(
                _DrainCand(fee=f, tx_hash=h, size_bytes=s, sender=snd or None, nonce=n, payload=r)
                for h, f, s, r, snd, n in entries
            )
        )

    def _pick_within_bounds(
        self, cands: list[_DrainCand], reserved: set[str], max_count: int, max_bytes: int
    ) -> list[_DrainCand]:
        """First-fit within count/byte bounds, skipping other-owner rows and
        byte-blocked senders — mirrors drain()'s selection rules."""
        picked: list[_DrainCand] = []
        total_bytes = 0
        blocked: set[str] = set()
        for c in cands:
            if c.tx_hash in reserved:
                continue
            if max_count and len(picked) >= max_count:
                break
            if c.sender is not None and c.sender in blocked:
                continue
            if max_bytes and total_bytes + c.size_bytes > max_bytes:
                if c.sender is not None:
                    blocked.add(c.sender)
                continue
            picked.append(c)
            total_bytes += c.size_bytes
        return picked

    def _reserve_rows(
        self,
        session: Session,
        chain_id: str,
        picked: list[_DrainCand],
        *,
        owner_id: str,
        proposer: str,
        height: int | None,
        round: int | None,
        attempt_seq: int,
        now: float,
        expires: float,
    ) -> None:
        for c in picked:
            session.execute(
                text(
                    "INSERT INTO mempool_reservation (chain_id, tx_hash, owner_id, attempt_seq, height, round, "
                    "proposer, reserved_at, expires_at, state) VALUES (:chain_id, :tx_hash, :owner_id, :attempt_seq, "
                    ":height, :round, :proposer, :now, :expires, 'reserved') "
                    "ON CONFLICT (chain_id, tx_hash) DO UPDATE SET owner_id = :owner_id, attempt_seq = :attempt_seq, "
                    "height = :height, round = :round, proposer = :proposer, reserved_at = :now, expires_at = :expires, "
                    "state = 'reserved', release_reason = NULL, released_at = NULL "
                    "WHERE mempool_reservation.state = 'released' OR mempool_reservation.owner_id = :owner_id"
                ),
                {
                    "chain_id": chain_id,
                    "tx_hash": c.tx_hash,
                    "owner_id": owner_id,
                    "attempt_seq": attempt_seq,
                    "height": height,
                    "round": round,
                    "proposer": proposer,
                    "now": now,
                    "expires": expires,
                },
            )

    def _contents_for(self, session: Session, chain_id: str, picked: list[_DrainCand]) -> list[PendingTransaction]:
        if not picked:
            return []
        hashes = [c.tx_hash for c in picked]
        content_by_hash = {
            row[0]: row[1]
            for row in session.exec(
                select(MempoolEntry.tx_hash, MempoolEntry.content).where(
                    MempoolEntry.chain_id == chain_id,
                    MempoolEntry.tx_hash.in_(hashes),  # type: ignore[attr-defined]
                )
            ).all()
        }
        return [
            PendingTransaction(
                tx_hash=c.tx_hash,
                content=json.loads(content_by_hash[c.tx_hash]),
                fee=c.fee,
                size_bytes=c.size_bytes,
                received_at=c.payload,
            )
            for c in picked
            if c.tx_hash in content_by_hash
        ]

    def _peek_reserve_session(self, chain_id: str, **kw: Any) -> list[PendingTransaction]:
        owner_id = kw["owner_id"]
        with Session(self._engine) as session:
            if session.get_bind().dialect.name == "postgresql":
                # Serialize reservers; admissions don't take this lock —
                # they only add rows, which a later peek simply won't see.
                session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:key))").bindparams(key=self._RESERVATION_ADVISORY_KEY)
                )
            self._sweep_expired_reservations(session, chain_id, kw["now"])
            reserved = self._live_reserved_hashes(session, chain_id, kw["now"], owner_id)
            picked = self._pick_within_bounds(
                self._ordered_candidates(session, chain_id), reserved, kw["max_count"], kw["max_bytes"]
            )
            self._reserve_rows(
                session,
                chain_id,
                picked,
                now=kw["now"],
                expires=kw["expires"],
                **{k: kw[k] for k in ("owner_id", "proposer", "height", "round", "attempt_seq")},
            )
            result = self._contents_for(session, chain_id, picked)
            session.commit()
        self._update_gauge(chain_id)
        return result

    def _peek_reserve_sqlite(self, chain_id: str, **kw: Any) -> list[PendingTransaction]:
        """BEGIN IMMEDIATE path: the write lock is taken up front so a
        concurrent admission's write transaction serializes behind the peek
        instead of observing pre-reservation state (P2-v2.4 §2/F5)."""
        raw = self._engine.raw_connection()
        try:
            cur = raw.cursor()
            cur.execute("BEGIN IMMEDIATE")
            try:
                now = kw["now"]
                cur.execute(
                    "UPDATE mempool_reservation SET state='released', release_reason='expired', released_at=? "
                    "WHERE chain_id=? AND state='reserved' AND expires_at<=?",
                    (now, chain_id, now),
                )
                cur.execute(
                    "SELECT tx_hash FROM mempool_reservation WHERE chain_id=? AND state='reserved' "
                    "AND expires_at>? AND owner_id!=?",
                    (chain_id, now, kw["owner_id"]),
                )
                reserved = {r[0] for r in cur.fetchall()}
                cur.execute(
                    "SELECT tx_hash, fee, size_bytes, received_at, sender, nonce FROM mempool WHERE chain_id=?",
                    (chain_id,),
                )
                rows = cur.fetchall()
                # Reuse the ORM-free candidate ordering: build _DrainCand list.
                cands = list(
                    _order_for_drain(
                        _DrainCand(fee=int(f), tx_hash=h, size_bytes=int(s), sender=snd or None, nonce=n, payload=r)
                        for h, f, s, r, snd, n in rows
                    )
                )
                picked = self._pick_within_bounds(cands, reserved, kw["max_count"], kw["max_bytes"])
                for c in picked:
                    cur.execute(
                        "INSERT INTO mempool_reservation (chain_id, tx_hash, owner_id, attempt_seq, height, round, "
                        "proposer, reserved_at, expires_at, state) VALUES (?,?,?,?,?,?,?,?,?,'reserved') "
                        "ON CONFLICT (chain_id, tx_hash) DO UPDATE SET owner_id=excluded.owner_id, "
                        "attempt_seq=excluded.attempt_seq, height=excluded.height, round=excluded.round, "
                        "proposer=excluded.proposer, reserved_at=excluded.reserved_at, "
                        "expires_at=excluded.expires_at, state='reserved', release_reason=NULL, released_at=NULL "
                        "WHERE mempool_reservation.state='released' OR mempool_reservation.owner_id=excluded.owner_id",
                        (
                            chain_id,
                            c.tx_hash,
                            kw["owner_id"],
                            kw["attempt_seq"],
                            kw["height"],
                            kw["round"],
                            kw["proposer"],
                            now,
                            kw["expires"],
                        ),
                    )
                hashes = [c.tx_hash for c in picked]
                content_by_hash: dict[str, str] = {}
                if hashes:
                    marks = ",".join("?" for _ in hashes)
                    cur.execute(
                        f"SELECT tx_hash, content FROM mempool WHERE chain_id=? AND tx_hash IN ({marks})",  # nosec # marks is only '?' placeholders
                        (chain_id, *hashes),
                    )
                    content_by_hash = {r[0]: r[1] for r in cur.fetchall()}
                cur.execute("COMMIT")
            except BaseException:
                cur.execute("ROLLBACK")
                raise
            finally:
                cur.close()
        finally:
            raw.close()
        self._update_gauge(chain_id)
        return [
            PendingTransaction(
                tx_hash=c.tx_hash,
                content=json.loads(content_by_hash[c.tx_hash]),
                fee=c.fee,
                size_bytes=c.size_bytes,
                received_at=c.payload,
            )
            for c in picked
            if c.tx_hash in content_by_hash
        ]

    def _release_update(
        self,
        session: Session,
        chain_id: str,
        reason: str,
        *,
        tx_hashes: Iterable[str] | None = None,
        owner_id: str | None = None,
        now: float | None = None,
    ) -> int:
        now = now if now is not None else time.time()
        clauses = ["chain_id = :chain_id", "state = 'reserved'"]
        params: dict[str, Any] = {"chain_id": chain_id, "reason": reason, "now": now}
        if tx_hashes is not None:
            hashes = list(tx_hashes)
            if not hashes:
                return 0
            clauses.append("tx_hash IN :hashes")
            params["hashes"] = tuple(hashes)
        if owner_id is not None:
            clauses.append("owner_id = :owner_id")
            params["owner_id"] = owner_id
        stmt = text(
            "UPDATE mempool_reservation SET state='released', release_reason=:reason, released_at=:now "
            f"WHERE {' AND '.join(clauses)}"  # nosec # clauses are static literals, values are bound params
        )
        if tx_hashes is not None:
            stmt = stmt.bindparams(bindparam("hashes", expanding=True))
        result = session.execute(stmt, params)
        count = cast(Any, result).rowcount or 0
        if count:
            mempool_reservation_release_total.labels(chain_id=chain_id, reason=reason).inc(count)
        return count

    def release_reservations(self, chain_id: str, tx_hashes: Iterable[str], reason: str, owner_id: str | None = None) -> int:
        """Release specific reservations (owner release, outbid, sealed…)."""
        with self._lock:
            with Session(self._engine) as session:
                count = self._release_update(session, chain_id, reason, tx_hashes=tx_hashes, owner_id=owner_id)
                session.commit()
        return count

    def release_owner_reservations(self, chain_id: str, owner_id: str, reason: str) -> int:
        """Release every live reservation held by one owner (abort/rotate)."""
        with self._lock:
            with Session(self._engine) as session:
                count = self._release_update(session, chain_id, reason, owner_id=owner_id)
                session.commit()
        return count

    def live_reservations(self, chain_id: str, *, now: float | None = None) -> dict[str, str]:
        """tx_hash -> owner_id for live reservations on a chain."""
        now = now if now is not None else time.time()
        with self._lock:
            with Session(self._engine) as session:
                rows = session.execute(
                    text(
                        "SELECT tx_hash, owner_id FROM mempool_reservation WHERE chain_id=:chain_id "
                        "AND state='reserved' AND expires_at>:now"
                    ),
                    {"chain_id": chain_id, "now": now},
                ).all()
        return {r[0]: r[1] for r in rows}

    def reconcile_sealed(self, chain_id: str, sealed_tx_hashes: Iterable[str]) -> int:
        """Evict pooled rows the chain has sealed and release their markers.

        ``sealed_tx_hashes`` must come from the caller's chain-side check —
        the mempool database is separate from chain.db, so the
        ``status='confirmed' AND block_height IS NOT NULL`` predicate is
        enforced by whoever supplies the set (import path, sweeper). A
        NULL-height row is NOT sealed and must never appear in the set —
        that is the height_recorded edge: pending writeback rows keep
        their pool entry until a real seal.
        """
        hashes = list(dict.fromkeys(sealed_tx_hashes))
        if not hashes:
            return 0
        with self._lock:
            with Session(self._engine) as session:
                removed = session.exec(
                    delete(MempoolEntry).where(
                        MempoolEntry.chain_id == chain_id,  # type: ignore[arg-type]
                        MempoolEntry.tx_hash.in_(hashes),  # type: ignore[attr-defined]
                    )
                )
                released = self._release_update(session, chain_id, "sealed_reconciled", tx_hashes=hashes)
                session.commit()
                count = removed.rowcount if removed.rowcount is not None else 0
            if count or released:
                self._update_gauge(chain_id)
        return count

    def evict_expired(self, max_age: float) -> int:
        """Delete entries older than ``max_age`` seconds, across every chain.

        Entries here outlive the process, so a strand that a restart would have
        cleared in the in-memory backend persists until something removes it.
        """
        if max_age <= 0:
            return 0
        cutoff = time.time() - max_age
        with self._lock:
            with Session(self._engine) as session:
                # #1300: age eviction must not take a row mid-attempt —
                # reserved entries re-enter eligibility only via owner
                # release or TTL expiry (P2-v2.4 §2 deleter map).
                now = time.time()
                stale_chains = session.exec(select(MempoolEntry.chain_id).where(MempoolEntry.received_at < cutoff)).all()
                if not stale_chains:
                    return 0
                reserved_by_chain: dict[str, set[str]] = {}
                for cid in set(stale_chains):
                    reserved_by_chain[cid] = self._live_reserved_set(session, cid, now)
                # Delete per-chain with the reserved exclusion applied.
                total_removed = 0
                removed_by_chain: dict[str, int] = {}
                for cid in set(stale_chains):
                    keep = reserved_by_chain.get(cid, set())
                    cid_rows = session.exec(
                        select(MempoolEntry.tx_hash).where(
                            MempoolEntry.chain_id == cid,
                            MempoolEntry.received_at < cutoff,
                        )
                    ).all()
                    cid_hashes = [r[0] for r in cid_rows if r[0] not in keep]
                    if not cid_hashes:
                        continue
                    res = session.exec(
                        delete(MempoolEntry).where(
                            MempoolEntry.chain_id == cid,  # type: ignore[arg-type]
                            MempoolEntry.tx_hash.in_(cid_hashes),  # type: ignore[attr-defined]
                        )
                    )
                    n = res.rowcount if res.rowcount is not None else len(cid_hashes)
                    total_removed += n
                    removed_by_chain[cid] = n
                session.commit()
                removed = total_removed
            for chain_id in removed_by_chain:
                metrics_registry.increment(f"mempool_evictions_total_{chain_id}", float(removed_by_chain[chain_id]))
                self._update_gauge(chain_id)
        return removed

    def size(self, chain_id: str | None = None) -> int:
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            with Session(self._engine) as session:
                count = session.exec(
                    select(func.count()).select_from(MempoolEntry).where(MempoolEntry.chain_id == chain_id)
                ).one()
                return count

    def pending_tx_hashes(self, chain_id: str | None = None) -> set[str]:
        """Hashes of pending entries on a chain — cheap, content-free."""
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            with Session(self._engine) as session:
                return set(session.exec(select(MempoolEntry.tx_hash).where(MempoolEntry.chain_id == chain_id)).all())

    def get_pending_transactions(self, chain_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Get pending transactions for RPC endpoint"""
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id

        with self._lock:
            with Session(self._engine) as session:
                entries = session.exec(
                    select(MempoolEntry)
                    .where(MempoolEntry.chain_id == chain_id)
                    .order_by(cast(Any, MempoolEntry.fee).desc(), cast(Any, MempoolEntry.tx_hash).asc())
                    .limit(limit)
                ).all()

        return [json.loads(e.content) for e in entries]

    def _update_gauge(self, chain_id: str | None = None) -> None:
        """Refresh both metric surfaces for a chain after a mutation.

        The legacy registry gauge is kept for continuity; the prometheus
        gauges back the MempoolFull alert.
        """
        from .config import settings

        if chain_id is None:
            chain_id = settings.chain_id
        with self._lock:
            with Session(self._engine) as session:
                count, total_bytes = session.exec(
                    select(func.count(), func.coalesce(func.sum(MempoolEntry.size_bytes), 0))
                    .select_from(MempoolEntry)
                    .where(MempoolEntry.chain_id == chain_id)
                ).one()
        metrics_registry.set_gauge(f"mempool_size_{chain_id}", float(count))
        mempool_pending_count.labels(chain_id=chain_id).set(float(count))
        mempool_pending_size_bytes.labels(chain_id=chain_id).set(float(total_bytes))
