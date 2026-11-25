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


# Keys the /mempool read path adds on top of the admitted tx body. They are
# response decoration, never sealed content — hashing them yields a phantom
# tx_hash that can never confirm (#2741).
_MEMPOOL_RESPONSE_ONLY_KEYS = frozenset({"state"})


def compute_mempool_entry_hash(tx: dict[str, Any]) -> str:
    """Canonical tx_hash for a ``/mempool`` response entry.

    ``get_mempool`` tags survivors with ``state: "pending"`` (#2457); the tag
    is not part of the admitted body, so strip response-only keys before the
    canonical hash or every lookup returns a hash that never seals.
    """
    return compute_tx_hash({key: value for key, value in tx.items() if key not in _MEMPOOL_RESPONSE_ONLY_KEYS})


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


def _contiguous_nonce_run(slotted: list[_DrainCand]) -> list[_DrainCand]:
    """The prefix of ``slotted`` (sorted by nonce) with no nonce gaps."""
    run: list[_DrainCand] = []
    prev = None
    for c in slotted:
        if prev is not None and c.nonce != prev + 1:
            break
        run.append(c)
        prev = c.nonce
    return run


def _sender_drain_runs(by_sender: dict[str, list[_DrainCand]]) -> dict[str, list[_DrainCand]]:
    """Truncate each sender's list to its contiguous nonce run in place and
    return the sender's unsigned (nonce-exempt) candidates (#2944)."""
    unsigned_by_sender: dict[str, list[_DrainCand]] = {}
    for sender, lst in by_sender.items():
        slotted = sorted(
            (c for c in lst if c.nonce is not None),
            key=lambda c: c.nonce if c.nonce is not None else 0,
        )
        unsigned = [c for c in lst if c.nonce is None]
        lst[:] = _contiguous_nonce_run(slotted)
        if unsigned:
            unsigned_by_sender[sender] = unsigned
    return unsigned_by_sender


def _heap_entry(c: _DrainCand) -> tuple[int, str, _DrainCand]:
    return (-c.fee, c.tx_hash, c)


def _seed_ready(
    by_sender: dict[str, list[_DrainCand]],
    unsigned_by_sender: dict[str, list[_DrainCand]],
    independent: list[_DrainCand],
) -> tuple[list[tuple[int, str, _DrainCand]], dict[str, int]]:
    """Initial drain heap: independents plus each sender's head — or its
    unsigned writes when the sender has no slotted run at all."""
    import heapq

    ready = [_heap_entry(c) for c in independent]
    heapq.heapify(ready)
    next_idx = dict.fromkeys(by_sender, 0)
    for sender, lst in by_sender.items():
        if lst:
            heapq.heappush(ready, _heap_entry(lst[0]))
        else:
            for c in unsigned_by_sender.pop(sender, []):
                heapq.heappush(ready, _heap_entry(c))
    return ready, next_idx


def _order_for_drain(cands: Iterable[_DrainCand]) -> list[_DrainCand]:
    """Order drain candidates so a sender's tx never precedes its own lower nonce.

    Global fee order lets a high-fee later nonce drain before its predecessor
    and get rejected as a nonce gap (#1068). Instead each sender contributes
    only the contiguous run from its lowest pooled nonce — a gapped nonce
    stays in the pool — and the ready heads merge by fee.

    Unsigned protocol-internal writes (``nonce=None``) carry a sender but no
    slot: they are nonce-exempt at apply, so any of them that drains while
    the sender's signed txs are still pooled takes the live account nonce
    and kills every pending signed tx behind it (#2944 — a queued
    STAKE_LOCK sealed ahead of a pending LIQUIDITY_DEPOSIT and the deposit
    died ``nonce_below_confirmed``). They therefore drain only after the
    sender's contiguous slotted run is exhausted; senders with no slotted
    entries keep them ready immediately. Entries without a sender at all
    are independent and always ready.
    """
    import heapq

    by_sender: dict[str, list[_DrainCand]] = {}
    independent: list[_DrainCand] = []
    for c in cands:
        if c.sender:
            by_sender.setdefault(c.sender, []).append(c)
        else:
            independent.append(c)

    unsigned_by_sender = _sender_drain_runs(by_sender)
    ready, next_idx = _seed_ready(by_sender, unsigned_by_sender, independent)

    ordered: list[_DrainCand] = []
    while ready:
        _, _, c = heapq.heappop(ready)
        ordered.append(c)
        if c.sender is None:
            continue
        i = next_idx[c.sender] + 1
        next_idx[c.sender] = i
        lst = by_sender[c.sender]
        if i < len(lst):
            heapq.heappush(ready, _heap_entry(lst[i]))
        else:
            for u in unsigned_by_sender.pop(c.sender, []):
                heapq.heappush(ready, _heap_entry(u))
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
