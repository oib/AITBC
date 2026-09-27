"""Per-block state-delta journal — the undo log for fork-safe reverts.

Every block application (follower import and local production) runs under a
``BlockDeltaJournal`` attached to the apply ``Session``. Two channels record
the complete before-image set:

- ORM events capture inserts/updates/deletes for every journaled table (the
  journal table itself is excluded). Inserts are deferred to
  ``after_flush_postexec`` so autoincrement primary keys are populated.
- ``before_execute`` catches the raw ``text() UPDATE account ...``
  balance/nonce writes that bypass ORM dirty tracking
  (``state_transition.py`` applies value movement that way). Only writes
  whose ``WHERE chain_id = :.. AND address = :..`` clause can be resolved are
  captured; anything the journal misses shows up later as a state-root
  mismatch at revert time and escalates — the same behaviour as before the
  journal existed, never a wrong revert.

``revert_losing_segment`` replays a losing segment's deltas in reverse, then
verifies the recomputed state root against the common ancestor's recorded
root — the cryptographic proof that undo restored exactly the pre-fork
state. The caller requeues the returned payloads into the mempool after
committing.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, event, inspect, text
from sqlmodel import Session, col, select

from ..base_models import Block, BlockStateDelta
from ..base_models import Transaction as ChainTransaction
from ..logger import get_logger
from ..metadata import chain_metadata
from .state_root_utils import compute_state_root_full

logger = get_logger(__name__)

_JOURNAL_KEY = "aitbc_block_delta_journal"

# Delta rows older than this many blocks are pruned on persist — fork
# resolution never reaches past ``max_reorg_depth``, which is far smaller.
_DELTA_KEEP_BLOCKS = 10_000

# The journal table must never journal itself.
_SKIP_TABLES = frozenset({BlockStateDelta.__tablename__})

# Raw-SQL account writes in state_transition.py / pure_state_transition.py /
# liquidity_transition.py all address the row by its (chain_id, address) PK:
#   UPDATE account SET ... WHERE chain_id = :chain_id AND address = :<name>
_ACCOUNT_DML_RE = re.compile(r"\b(update|insert\s+into|delete\s+from)\s+account\b", re.IGNORECASE)
_ACCOUNT_PK_RE = re.compile(
    r"chain_id\s*=\s*:([A-Za-z_]\w*)\s+and\s+address\s*=\s*:([A-Za-z_]\w*)",
    re.IGNORECASE,
)


def _encode_value(value: Any) -> Any:
    """JSON-safe encoding preserving the types JSON alone would lose."""
    if isinstance(value, datetime):
        return {"__dt__": value.isoformat()}
    if isinstance(value, date):
        return {"__date__": value.isoformat()}
    if isinstance(value, Decimal):
        return {"__dec__": str(value)}
    if isinstance(value, (bytes, bytearray)):
        return {"__bytes__": bytes(value).hex()}
    if isinstance(value, dict):
        return {str(k): _encode_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode_value(v) for v in value]
    return value


def _decode_value(value: Any) -> Any:
    if isinstance(value, dict):
        if "__dt__" in value:
            return datetime.fromisoformat(value["__dt__"])
        if "__date__" in value:
            return date.fromisoformat(value["__date__"])
        if "__dec__" in value:
            return Decimal(value["__dec__"])
        if "__bytes__" in value:
            return bytes.fromhex(value["__bytes__"])
        return {k: _decode_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode_value(v) for v in value]
    return value


def _encode_row(row: dict[str, Any]) -> str:
    return json.dumps({k: _encode_value(v) for k, v in row.items()})


def _decode_row(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    data = json.loads(raw)
    if not isinstance(data, dict):
        return None
    return {k: _decode_value(v) for k, v in data.items()}


def _pk_of(obj: Any) -> dict[str, Any] | None:
    """Primary-key map (keyed by column name) for a mapped object."""
    try:
        mapper = inspect(type(obj))
    except Exception:
        return None
    cols = getattr(mapper, "primary_key", None)
    if not cols:
        return None
    return {c.name: getattr(obj, c.key, None) for c in cols}


class BlockDeltaJournal:
    """Captures the before-image of every row a block apply touches.

    ``attach`` installs the listeners on the apply session; ``persist`` writes
    the collected delta rows inside the same transaction as the block commit,
    so a rolled-back apply leaves no journal and a committed block always has
    one.
    """

    def __init__(self, chain_id: str, height: int) -> None:
        self.chain_id = chain_id
        self.height = height
        self._rows: list[BlockStateDelta] = []
        # Inserts are recorded post-flush: autoincrement PKs are only
        # populated once the INSERT executes.
        self._pending_ins: list[Any] = []
        # First-touch wins per (table, pk, op-kind): the earliest before-image
        # is the pre-block state, later mutations must not overwrite it.
        self._seen: set[tuple[str, tuple[tuple[str, Any], ...], str]] = set()
        self._suppress = False

    # ------------------------------------------------------------------ API

    @classmethod
    def attach(cls, session: Session, chain_id: str, height: int) -> BlockDeltaJournal:
        journal = cls(chain_id, height)
        session.info[_JOURNAL_KEY] = journal
        event.listen(session, "before_flush", journal._on_flush)
        event.listen(session, "after_flush_postexec", journal._on_flush_postexec)
        # Raw account writes reach the connection without touching ORM state.
        # ``before_execute`` sees SQLAlchemy-level multiparams, independent of
        # the driver's paramstyle.
        conn = session.connection()
        event.listen(conn, "before_execute", journal._on_execute)
        return journal

    @classmethod
    def get(cls, session: Session | None) -> BlockDeltaJournal | None:
        if session is None:
            return None
        return session.info.get(_JOURNAL_KEY)

    def persist(self, session: Session) -> None:
        """Write collected delta rows into the session's pending commit and
        prune deltas old enough that fork resolution can never reach them.

        Capture happens at flush time, so persist flushes first — otherwise
        rows still pending would be captured after persist and never added.
        """
        session.flush()
        for row in self._rows:
            session.add(row)
        session.execute(
            text("DELETE FROM block_state_delta WHERE chain_id = :c AND height < :h"),
            {"c": self.chain_id, "h": self.height - _DELTA_KEEP_BLOCKS},
        )

    # ------------------------------------------------------------ capture

    def _key(self, table: str, pk: dict[str, Any], kind: str) -> tuple[str, tuple[tuple[str, Any], ...], str]:
        return (table, tuple(sorted(pk.items())), kind)

    def _record(self, table: str, op: str, pk: dict[str, Any], before: dict[str, Any] | None) -> None:
        key = self._key(table, pk, op)
        if key in self._seen:
            return
        self._seen.add(key)
        self._rows.append(
            BlockStateDelta(
                chain_id=self.chain_id,
                height=self.height,
                table_name=table,
                op=op,
                pk_json=_encode_row(pk),
                before_json=_encode_row(before) if before is not None else None,
            )
        )

    def _on_flush(self, session: Session, flush_context: Any, instances: Any) -> None:
        for obj in session.new:
            self._pending_ins.append(obj)

        for obj in session.dirty:
            if not session.is_modified(obj, include_collections=False):
                continue
            try:
                mapper = inspect(type(obj))
                table = mapper.local_table.name
            except Exception:
                continue
            if table in _SKIP_TABLES:
                continue
            pk = _pk_of(obj)
            if not pk or any(v is None for v in pk.values()):
                continue
            state = inspect(obj)
            before: dict[str, Any] = {}
            for attr in mapper.column_attrs:
                hist = state.attrs[attr.key].history
                if hist.deleted:
                    before[attr.columns[0].name] = hist.deleted[0]
            if before:
                self._record(table, "upd", pk, before)

        for obj in session.deleted:
            try:
                mapper = inspect(type(obj))
                table = mapper.local_table.name
            except Exception:
                continue
            if table in _SKIP_TABLES:
                continue
            pk = _pk_of(obj)
            if not pk or any(v is None for v in pk.values()):
                continue
            before = {attr.columns[0].name: getattr(obj, attr.key, None) for attr in mapper.column_attrs}
            self._record(table, "del", pk, before)

    def _on_flush_postexec(self, session: Session, flush_context: Any) -> None:
        """Resolve deferred insert pks — populated once INSERTs execute."""
        if not self._pending_ins:
            return
        pending, self._pending_ins = self._pending_ins, []
        for obj in pending:
            try:
                mapper = inspect(type(obj))
                table = mapper.local_table.name
            except Exception:
                continue
            if table in _SKIP_TABLES:
                continue
            pk = _pk_of(obj)
            if not pk:
                continue
            if any(v is None for v in pk.values()):
                logger.warning("Delta journal: insert on %s with unresolved pk %r — undo may miss it", table, pk)
                continue
            self._record(table, "ins", pk, None)

    def _on_execute(
        self,
        conn: Any,
        clauseelement: Any,
        multiparams: Any,
        params: Any,
        execution_options: Any,
    ) -> None:
        if self._suppress:
            return
        statement = clauseelement if isinstance(clauseelement, str) else str(clauseelement)
        m = _ACCOUNT_DML_RE.search(statement)
        if m is None:
            return
        verb = m.group(1).lower()
        bound: dict[str, Any] = {}
        for p in multiparams or []:
            if isinstance(p, dict):
                bound.update(p)
        if isinstance(params, dict):
            bound.update(params)
        if not bound:
            return

        if verb.startswith("insert"):
            cid = bound.get("chain_id")
            addr = bound.get("address")
        else:
            where = _ACCOUNT_PK_RE.search(statement)
            if where is None:
                return  # unresolvable address — missed capture surfaces as a
                # state-root mismatch at revert time, which escalates
            cid = bound.get(where.group(1))
            addr = bound.get(where.group(2))
        if not cid or not addr:
            return
        pk = {"chain_id": cid, "address": addr}
        if verb.startswith("insert"):
            self._record("account", "ins", pk, None)
            return

        key = self._key("account", pk, "upd")
        if key in self._seen:
            return
        # Query via the typed table, not text(): a raw SELECT returns
        # untyped values (datetime columns come back as strings) which would
        # fail the revert-side bind.
        acct = chain_metadata.tables["account"]
        self._suppress = True
        try:
            row = conn.execute(acct.select().where(and_(acct.c.chain_id == cid, acct.c.address == addr))).mappings().first()
        finally:
            self._suppress = False
        if row is None:
            # UPDATE/DELETE against a row absent in the committed state — it
            # exists only because this very block inserted it pending flush.
            # Undo = the row must not exist: record an update whose before is
            # absent, which the reverter reads as "delete the row".
            self._record("account", "upd", pk, None)
        else:
            self._record("account", "upd", pk, dict(row))


def has_journal(session: Session, chain_id: str, height: int) -> bool:
    """True when block `height` has at least one journaled delta row."""
    row = session.exec(
        select(BlockStateDelta.id).where(BlockStateDelta.chain_id == chain_id).where(BlockStateDelta.height == height).limit(1)
    ).first()
    return row is not None


def _revert_block(session: Session, chain_id: str, height: int) -> None:
    """Replay one block's delta rows in reverse inside the open transaction."""
    deltas = session.exec(
        select(BlockStateDelta)
        .where(BlockStateDelta.chain_id == chain_id)
        .where(BlockStateDelta.height == height)
        .order_by(col(BlockStateDelta.id).desc())
    ).all()
    for d in deltas:
        table = chain_metadata.tables.get(d.table_name)
        pk = _decode_row(d.pk_json) or {}
        if table is None or not pk:
            continue
        clause = and_(*(table.c[name] == value for name, value in pk.items()))
        before = _decode_row(d.before_json)
        if d.op == "ins" or (d.op == "upd" and before is None):
            session.execute(table.delete().where(clause))
        elif d.op == "upd" and before is not None:
            session.execute(table.update().where(clause).values(**{k: v for k, v in before.items() if k in table.c}))
        elif d.op == "del" and before is not None:
            session.execute(table.insert().values(**{k: v for k, v in before.items() if k in table.c}))
    session.execute(
        text("DELETE FROM block_state_delta WHERE chain_id = :c AND height = :h"),
        {"c": chain_id, "h": height},
    )


def _tx_payloads_at(session: Session, chain_id: str, height: int) -> list[dict[str, Any]]:
    """Signed-transaction reconstructions for mempool requeue."""
    rows = session.exec(
        select(ChainTransaction).where(ChainTransaction.chain_id == chain_id).where(ChainTransaction.block_height == height)
    ).all()
    out: list[dict[str, Any]] = []
    for tx in rows:
        payload = dict(tx.payload) if isinstance(tx.payload, dict) else {}
        payload.setdefault("tx_hash", tx.tx_hash)
        payload.setdefault("from", tx.sender)
        payload.setdefault("to", tx.recipient)
        payload.setdefault("value", tx.value)
        payload.setdefault("amount", tx.value)
        payload.setdefault("fee", tx.fee)
        payload.setdefault("nonce", tx.nonce)
        payload.setdefault("type", tx.type or "TRANSFER")
        payload.setdefault("chain_id", tx.chain_id)
        out.append(payload)
    return out


def revert_losing_segment(
    session: Session,
    chain_id: str,
    blocks: list[Block],
    ancestor: Block | None,
    provably_empty: Any,
) -> list[dict[str, Any]] | None:
    """Undo a losing segment inside the caller's open transaction.

    ``blocks`` are the local blocks to drop (any order), ``ancestor`` the
    common ancestor whose recorded state_root anchors the verification, and
    ``provably_empty`` a callable ``(session, [blocks]) -> bool`` for the
    pre-journal fallback. Returns the orphaned transaction payloads for the
    caller to requeue into the mempool after commit — or None when undo is
    impossible (a non-empty block without a journal, or a state root that
    refuses to match the ancestor's). On None the caller must NOT commit.
    """
    journaled = {b.height: has_journal(session, chain_id, b.height) for b in blocks}
    for blk in blocks:
        if not journaled.get(blk.height) and not provably_empty(session, [blk]):
            return None

    payloads: list[dict[str, Any]] = []
    for blk in sorted(blocks, key=lambda b: -b.height):
        # Collect payloads before the 'ins' undos remove the tx rows.
        payloads.extend(_tx_payloads_at(session, chain_id, blk.height))
        if journaled.get(blk.height):
            _revert_block(session, chain_id, blk.height)
        else:
            # Pre-journal provably-empty block: nothing to restore, drop rows.
            for tx in session.exec(
                select(ChainTransaction)
                .where(ChainTransaction.chain_id == chain_id)
                .where(ChainTransaction.block_height == blk.height)
            ).all():
                session.delete(tx)
            session.delete(blk)
    session.flush()

    # Undo correctness is verified against the ancestor's recorded state
    # root — a journal gap can only ever produce a mismatch here, which is
    # rejected before commit, never a silently wrong revert.
    if ancestor is not None and ancestor.state_root:
        actual = compute_state_root_full(session, chain_id)
        recorded = str(ancestor.state_root).replace("0x", "").lower()
        if actual is None or actual.replace("0x", "").lower() != recorded:
            logger.error(
                "Fork undo state-root mismatch at ancestor %s: recorded=%s reverted=%s — refusing revert",
                ancestor.height,
                ancestor.state_root,
                actual,
            )
            return None
    return payloads


def requeue_orphaned_transactions(chain_id: str, payloads: list[dict[str, Any]]) -> int:
    """Push orphaned block transactions back into the mempool. Best-effort:
    a tx that fails admission (dup slot, low fee) is skipped — it was already
    confirmed once, and the winning branch may carry it anyway."""
    from ..mempool import get_mempool

    mempool = get_mempool()
    requeued = 0
    for tx in payloads:
        try:
            mempool.add(tx, chain_id=chain_id, tx_hash=tx.get("tx_hash"))
            requeued += 1
        except Exception as exc:
            logger.info("Requeue of orphaned tx %s skipped: %s", str(tx.get("tx_hash"))[:18], exc)
    return requeued
