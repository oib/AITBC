"""Mempool shared model and pure transaction helpers (mempool split, #1860).

Facade module: ``aitbc_chain.mempool`` re-exports every name defined here;
this module is not meant to be imported directly."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from collections.abc import Iterable

from sqlalchemy import BigInteger, Boolean, Column, Float, Index, Integer, MetaData, Text
from sqlalchemy.dialects.postgresql import DOUBLE_PRECISION
from sqlmodel import Field, Session, select

from .metadata import ChainBase

mempool_metadata = MetaData()


class MempoolEntry(ChainBase, table=True):
    __tablename__ = "mempool"
    __table_args__: Any = (
        Index("idx_mempool_fee", "fee", postgresql_ops={"fee": "DESC"}),
        Index("idx_mempool_chain_fee", "chain_id", "fee"),
        Index("idx_mempool_sender_nonce", "chain_id", "sender", "nonce"),
    )

    chain_id: str = Field(primary_key=True)
    tx_hash: str = Field(primary_key=True)
    content: str = Field(sa_column=Column(Text, nullable=False))
    fee: int = Field(default=0, sa_column=Column(BigInteger, nullable=False))
    size_bytes: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    # DOUBLE PRECISION on Postgres — 32-bit REAL rounds epoch timestamps to a
    # 128 s granularity, which is the eviction tie-break input (#797).
    received_at: float = Field(sa_column=Column(Float().with_variant(DOUBLE_PRECISION(), "postgresql"), nullable=False))
    sender: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    nonce: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    # Whether the entry holds a signed (sender, nonce) slot — i.e.
    # _tx_slot_key(content) is not None. Unsigned protocol-internal writes
    # (escrow, bond, bridge) carry no signature and must never be
    # supersede-swept by a sealed tx of the same sender (#796). NULL marks a
    # row written before the column existed; it is treated as unsigned —
    # sweeping it could drop a protocol write, never the reverse.
    signed: bool | None = Field(default=None, sa_column=Column(Boolean, nullable=True))


@dataclass(frozen=True)
class PendingTransaction:
    tx_hash: str
    content: dict[str, Any]
    received_at: float
    fee: int = 0
    size_bytes: int = 0


def compute_tx_hash(tx: dict[str, Any]) -> str:
    canonical = json.dumps(tx, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    return f"0x{digest}"


def _estimate_size(tx: dict[str, Any]) -> int:
    return len(json.dumps(tx, separators=(",", ":")).encode())


def _tx_slot_key(tx: dict[str, Any]) -> tuple[str, int] | None:
    """(sender, nonce) slot key for externally submitted transactions.

    Only signed transactions compete for a slot: everything reaching a public
    intake (REST or gossip) must be signed, while protocol-internal writes —
    escrow movements, bridge locks and credits — carry no top-level signature
    and a placeholder nonce the proposer rewrites at seal time. Slot
    bookkeeping on those would only collide protocol writes with each other.
    """
    if not (tx.get("signature") or tx.get("sig")):
        return None
    sender = tx.get("from") or tx.get("sender")
    nonce = tx.get("nonce")
    if not isinstance(sender, str) or not sender:
        return None
    if not isinstance(nonce, int) or isinstance(nonce, bool) or nonce < 0:
        return None
    return sender.lower(), nonce


def _tx_sender(tx: dict[str, Any]) -> str:
    return str(tx.get("from") or tx.get("sender") or "").lower()


def _tx_nonce(tx: dict[str, Any]) -> int | None:
    nonce = tx.get("nonce")
    if isinstance(nonce, int) and not isinstance(nonce, bool):
        return nonce
    return None


@dataclass
class _DrainCand:
    """One drain candidate. ``payload`` is caller-owned (the PendingTransaction
    for the in-memory pool, the slim row tuple for the database pool)."""

    fee: int
    tx_hash: str
    size_bytes: int
    sender: str | None
    nonce: int | None
    payload: Any


def _order_for_drain(cands: Iterable[_DrainCand]) -> list[_DrainCand]:
    """Order drain candidates so a sender's tx never precedes its own lower nonce.

    Global fee order lets a high-fee later nonce drain before its predecessor
    and get rejected as a nonce gap (#1068). Instead each sender contributes
    only the contiguous run from its lowest pooled nonce — a gapped nonce
    stays in the pool — and the ready heads merge by fee. Entries without a
    sender/nonce slot are independent and always ready.
    """
    import heapq

    by_sender: dict[str, list[_DrainCand]] = {}
    independent: list[_DrainCand] = []
    for c in cands:
        if c.sender and c.nonce is not None:
            by_sender.setdefault(c.sender, []).append(c)
        else:
            independent.append(c)

    for lst in by_sender.values():
        lst.sort(key=lambda c: c.nonce if c.nonce is not None else 0)
        run: list[_DrainCand] = []
        prev = None
        for c in lst:
            if prev is not None and c.nonce != prev + 1:
                break
            run.append(c)
            prev = c.nonce
        lst[:] = run

    ready: list[tuple[int, str, _DrainCand]] = [(-c.fee, c.tx_hash, c) for c in independent]
    heapq.heapify(ready)
    next_idx: dict[str, int] = {}
    for sender, lst in by_sender.items():
        next_idx[sender] = 0
        heapq.heappush(ready, (-lst[0].fee, lst[0].tx_hash, lst[0]))

    ordered: list[_DrainCand] = []
    while ready:
        _, _, c = heapq.heappop(ready)
        ordered.append(c)
        if c.sender is not None:
            i = next_idx[c.sender] + 1
            next_idx[c.sender] = i
            lst = by_sender[c.sender]
            if i < len(lst):
                heapq.heappush(ready, (-lst[i].fee, lst[i].tx_hash, lst[i]))
    return ordered


def _tx_cost(tx: dict[str, Any]) -> int:
    try:
        return int(tx.get("amount") or 0) + int(tx.get("fee") or 0)
    except (TypeError, ValueError):
        return 0


def _claimed_lock_hashes(tx: dict[str, Any]) -> set[str]:
    if str(tx.get("type", "")).upper() != "STAKE_RELEASE":
        return set()
    return {str(h).lower() for h in (tx.get("payload") or {}).get("lock_tx_hashes") or []}


def _reject_conflicting_stake_release(tx: dict[str, Any], pending: Iterable[tuple[str, dict[str, Any]]]) -> None:
    """Same-block double-release guard: two STAKE_RELEASEs claiming the same
    lock may coexist in the mempool because neither is in confirmed history
    yet — the proposer would drain both and the second would pass the in-block
    check too (block tx records are flushed only at commit). Keep the first,
    drop the rest; the owner can re-queue after the block seals."""
    claimed = _claimed_lock_hashes(tx)
    if not claimed:
        return
    for pending_hash, pending_tx in pending:
        if claimed & _claimed_lock_hashes(pending_tx):
            raise ValueError(f"A pending release already claims one of these locks (tx {pending_hash})")


def _pending_tx_rows(session: Session, chain_id: str) -> Iterable[tuple[str, dict[str, Any]]]:
    for entry in session.exec(select(MempoolEntry).where(MempoolEntry.chain_id == chain_id)).all():
        try:
            content = json.loads(entry.content)
        except (TypeError, ValueError):
            continue
        if isinstance(content, dict):
            yield entry.tx_hash, content
