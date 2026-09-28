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

import hashlib
import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, event, func, inspect, text
from sqlalchemy.orm.attributes import NEVER_SET
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

# The prune DELETE only runs every Nth persist — it scans the same index each
# time and the window is huge, so per-block pruning is wasted work.
_DELTA_PRUNE_EVERY = 64
_last_pruned_height: dict[str, int] = {}

# The journal table must never journal itself.
_SKIP_TABLES = frozenset({BlockStateDelta.__tablename__})

# Raw-SQL account writes in state_transition.py / pure_state_transition.py /
# liquidity_transition.py all address the row by its (chain_id, address) PK:
#   UPDATE account SET ... WHERE chain_id = :chain_id AND address = :<name>
_ACCOUNT_PK_RE = re.compile(
    r"chain_id\s*=\s*:([A-Za-z_]\w*)\s+and\s+address\s*=\s*:([A-Za-z_]\w*)",
    re.IGNORECASE,
)
# Any DML verb + target table — used to fail closed: a write to a chain table
# outside a flush that the journal cannot capture marks the journal
# "incomplete" rather than silently missing it.
_DML_TABLE_RE = re.compile(
    r"\b(update|insert(?:\s+or\s+\w+)?\s+into|replace\s+into|delete\s+from)\s+[\"'`]?([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)?)",
    re.IGNORECASE,
)

# Sentinel row op persisted when the journal could not capture everything it
# saw — revert refuses such blocks outright.
_OP_INCOMPLETE = "incomplete"
_INCOMPLETE_TABLE = "__journal__"

# Meta row carrying the pre-apply digest of every side table the block
# touched. The account table is verified at revert by the state root; this
# extends the same proof to escrow/bridge/bond/etc. — a capture gap inside an
# observed table, or a replay that restored wrong values, produces a digest
# mismatch and fails closed.
_OP_META = "meta"
_DIGEST_TABLE = "__digest__"

# Structural/ephemeral tables excluded from the digest: account is covered by
# the ancestor state root; transaction/block are handled by ins-undo and grow
# unboundedly; mempool is node-local. Everything else is digested at first
# touch, capped at _DIGEST_ROW_LIMIT rows. ``bridge_block_header`` is NOT in
# the exclude set: it is written only by the bridge finalizer in its own
# session, so it can never appear in a block journal — should a future apply
# path ever write it, an over-cap table is deliberately fail-closed (recorded
# in digest_skipped → revert escalates) rather than silently unproven.
_DIGEST_EXCLUDE = frozenset({"account", "transaction", "block", "mempool", "block_state_delta"})
_DIGEST_ROW_LIMIT = 100_000


def _table_digest(session: Session, table_name: str, chain_id: str) -> str | None:
    """Canonical SHA-256 over a table's current rows, chain-scoped when the
    table carries a chain_id column. Returns None when the table exceeds the
    row cap — the caller records that as skipped coverage, not a match."""
    table = chain_metadata.tables.get(table_name)
    if table is None:
        return None
    stmt = table.select()
    if "chain_id" in table.c:
        stmt = stmt.where(table.c.chain_id == chain_id)
    rows = session.connection().execute(stmt).mappings().all()
    if len(rows) > _DIGEST_ROW_LIMIT:
        return None
    digest = hashlib.sha256()
    for encoded in sorted(_encode_row(dict(row)) for row in rows):
        digest.update(encoded.encode())
        digest.update(b"\x00")
    return digest.hexdigest()


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
        # First-touch wins per attribute: a row mutated across two flushes
        # yields two 'upd' events whose before-images must merge (earliest
        # value per attribute), or the second flush's changes undo to nothing.
        self._upd_rows: dict[tuple[str, tuple[tuple[str, Any], ...], str], BlockStateDelta] = {}
        self._suppress = False
        # Fail-closed bookkeeping: any capture problem stamps an
        # ``incomplete`` sentinel row at persist time, and the resolver
        # refuses to revert that block. The state-root check only proves the
        # account table, so silent side-table gaps are worse than escalation.
        self._incomplete = False
        self._persisted = False
        # True between before_flush and after_flush — DML reaching
        # before_execute while a flush runs is ORM-managed (already captured
        # via the flush events); DML outside a flush is a raw/Core write that
        # must be captured explicitly or the journal is incomplete.
        self._in_flush = False
        # Pre-state digest of each side table this block touches, taken at the
        # before_flush that first touches it (still pre-write there). Verified
        # at revert — the non-account counterpart of the state-root check.
        self._pre_digest: dict[str, str] = {}
        self._digest_skipped: list[str] = []

    # ------------------------------------------------------------------ API

    @classmethod
    def attach(cls, session: Session, chain_id: str, height: int) -> BlockDeltaJournal:
        journal = cls(chain_id, height)
        session.info[_JOURNAL_KEY] = journal
        event.listen(session, "before_flush", journal._on_flush)
        event.listen(session, "after_flush", journal._on_after_flush)
        event.listen(session, "after_flush_postexec", journal._on_flush_postexec)
        # A transaction boundary mid-apply (commit or rollback) detaches the
        # listeners that live on the checked-out connection — capture cannot
        # be trusted past it, so the journal is marked incomplete.
        event.listen(session, "after_commit", journal._on_txn_end)
        event.listen(session, "after_rollback", journal._on_txn_end)
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
        if self._incomplete:
            session.add(
                BlockStateDelta(
                    chain_id=self.chain_id,
                    height=self.height,
                    table_name=_INCOMPLETE_TABLE,
                    op=_OP_INCOMPLETE,
                    pk_json="{}",
                    before_json=None,
                )
            )
        last = _last_pruned_height.get(self.chain_id, -1)
        if self.height - last >= _DELTA_PRUNE_EVERY:
            session.execute(
                text("DELETE FROM block_state_delta WHERE chain_id = :c AND height < :h"),
                {"c": self.chain_id, "h": self.height - _DELTA_KEEP_BLOCKS},
            )
            _last_pruned_height[self.chain_id] = self.height
        if self._rows or self._incomplete:
            # The digest anchors the segment-level revert check. Truly empty
            # blocks write no rows at all, keeping journal_status "absent".
            session.add(
                BlockStateDelta(
                    chain_id=self.chain_id,
                    height=self.height,
                    table_name=_DIGEST_TABLE,
                    op=_OP_META,
                    pk_json="{}",
                    before_json=_encode_row({"pre_digest": self._pre_digest, "digest_skipped": self._digest_skipped}),
                )
            )
        self._persisted = True

    # ------------------------------------------------------------ capture

    def _key(self, table: str, pk: dict[str, Any], kind: str) -> tuple[str, tuple[tuple[str, Any], ...], str]:
        return (table, tuple(sorted(pk.items())), kind)

    def _record(self, table: str, op: str, pk: dict[str, Any], before: dict[str, Any] | None) -> None:
        key = self._key(table, pk, op)
        if op == "upd":
            existing = self._upd_rows.get(key)
            if existing is not None:
                # Merge missing attributes — the first-captured value is the
                # pre-block state; a before=None delta (row born in-block)
                # keeps its delete-undo semantics untouched.
                if before is not None and existing.before_json is not None:
                    merged = _decode_row(existing.before_json) or {}
                    for name, value in before.items():
                        merged.setdefault(name, value)
                    existing.before_json = _encode_row(merged)
                return
            row = BlockStateDelta(
                chain_id=self.chain_id,
                height=self.height,
                table_name=table,
                op=op,
                pk_json=_encode_row(pk),
                before_json=_encode_row(before) if before is not None else None,
            )
            self._upd_rows[key] = row
            self._rows.append(row)
            return
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

    def _on_after_flush(self, session: Session, flush_context: Any) -> None:
        self._in_flush = False

    def _on_txn_end(self, session: Session) -> None:
        # A commit or rollback before persist means subsequent work runs on a
        # different transaction/connection the listeners do not cover.
        if not self._persisted:
            self._incomplete = True

    def _digest_touched_tables(self, session: Session) -> None:
        """Digest every newly-touched side table while it still holds pre-flush
        state. ``session.dirty`` is over-inclusive (objects can be dirty without
        emitting SQL), which is harmless: a digested-but-unwritten table still
        compares equal at revert."""
        touched = {
            obj.__table__.name
            for obj in (*session.new, *session.dirty, *session.deleted)
            if getattr(obj, "__table__", None) is not None
        }
        for name in touched - self._pre_digest.keys() - set(self._digest_skipped) - _DIGEST_EXCLUDE:
            digest = _table_digest(session, name, self.chain_id)
            if digest is None:
                self._digest_skipped.append(name)
                # A table too big to prove is a table we cannot undo with
                # proof — the block escalates rather than reverting journal-
                # only (operator decision: fail closed on digest skips).
                self._incomplete = True
                logger.warning(
                    "Delta journal: side-table %r exceeds the %s-row digest cap at height %s — marked incomplete",
                    name,
                    _DIGEST_ROW_LIMIT,
                    self.height,
                )
            else:
                self._pre_digest[name] = digest

    def _on_flush(self, session: Session, flush_context: Any, instances: Any) -> None:
        self._in_flush = True
        self._digest_touched_tables(session)
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
                self._incomplete = True
                logger.warning(
                    "Delta journal: dirty %s row with unresolvable pk at height %s — marked incomplete",
                    table,
                    self.height,
                )
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
                self._incomplete = True
                logger.warning(
                    "Delta journal: deleted %s row with unresolvable pk at height %s — marked incomplete",
                    table,
                    self.height,
                )
                continue
            # Before-image = the committed (pre-block) values, not the current
            # attributes: a row modified and deleted in one block must
            # re-insert with its pre-modification state. ``history.deleted``
            # holds it for changed columns, ``loaded_value`` for the rest —
            # neither triggers a mid-flush SELECT. An unloaded column means
            # the before-image cannot be proven: fail closed.
            state = inspect(obj)
            before = {}
            for attr in mapper.column_attrs:
                hist = state.attrs[attr.key].history
                if hist.deleted:
                    before[attr.columns[0].name] = hist.deleted[0]
                    continue
                value = state.attrs[attr.key].loaded_value
                if value is NEVER_SET:
                    self._incomplete = True
                    logger.warning(
                        "Delta journal: deleted %s row has unloaded column %r at height %s — marked incomplete",
                        table,
                        attr.key,
                        self.height,
                    )
                before[attr.columns[0].name] = None if value is NEVER_SET else value
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
                self._incomplete = True
                logger.warning(
                    "Delta journal: insert on %s with unresolved pk %r at height %s — marked incomplete",
                    table,
                    pk,
                    self.height,
                )
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
        if self._suppress or self._in_flush:
            return
        statement = clauseelement if isinstance(clauseelement, str) else str(clauseelement)
        m = _DML_TABLE_RE.search(statement)
        if m is None:
            return
        table_name = m.group(2).lower().rsplit(".", 1)[-1]  # strip schema qualifier (main.account)
        if table_name in _SKIP_TABLES or table_name not in chain_metadata.tables:
            return
        verb = m.group(1).lower()
        if table_name != "account":
            # A raw/Core write on a chain table the journal does not model —
            # e.g. session.execute(update(X)…), query().update(), bulk_* —
            # which bypasses the flush events. Fail closed.
            self._incomplete = True
            logger.warning(
                "Delta journal: unhandled %s on chain table %r at height %s — marked incomplete",
                verb,
                table_name,
                self.height,
            )
            return

        bound: dict[str, Any] = {}
        for p in multiparams or []:
            if isinstance(p, dict):
                bound.update(p)
        if isinstance(params, dict):
            bound.update(params)
        if not bound:
            self._incomplete = True
            return

        if verb.startswith("insert"):
            if verb != "insert into":
                # INSERT OR IGNORE/REPLACE and REPLACE INTO have conditional or
                # upsert semantics — the before-image depends on whether the row
                # already existed, which the journal cannot know cheaply.
                self._incomplete = True
                return
            cid = bound.get("chain_id")
            addr = bound.get("address")
        else:
            where = _ACCOUNT_PK_RE.search(statement)
            if where is None:
                # Unresolvable account write (e.g. qualified/positional bulk
                # form) — the journal cannot prove the before-image.
                self._incomplete = True
                logger.warning(
                    "Delta journal: account %s with unresolvable WHERE at height %s — marked incomplete",
                    verb,
                    self.height,
                )
                return
            cid = bound.get(where.group(1))
            addr = bound.get(where.group(2))
        if not cid or not addr:
            self._incomplete = True
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


def journal_status(session: Session, chain_id: str, height: int) -> str:
    """``complete`` (revertible), ``incomplete`` (sentinel — never revert) or
    ``absent`` (no journal — only the provably-empty path may apply)."""
    ops = session.exec(
        select(BlockStateDelta.op).where(BlockStateDelta.chain_id == chain_id).where(BlockStateDelta.height == height)
    ).all()
    if not ops:
        return "absent"
    if _OP_INCOMPLETE in ops:
        return "incomplete"
    return "complete"


def has_journal(session: Session, chain_id: str, height: int) -> bool:
    """True when block `height` has at least one journaled delta row."""
    return journal_status(session, chain_id, height) != "absent"


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
    """Transactions to requeue — the stored signed envelope when present,
    else a best-effort reconstruction (older rows predate ``envelope``)."""
    rows = session.exec(
        select(ChainTransaction).where(ChainTransaction.chain_id == chain_id).where(ChainTransaction.block_height == height)
    ).all()
    out: list[dict[str, Any]] = []
    for tx in rows:
        if isinstance(tx.envelope, dict) and tx.envelope:
            payload = dict(tx.envelope)
            payload.setdefault("tx_hash", tx.tx_hash)
            out.append(payload)
            continue
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
    reverted_accounts: set[str] | None = None,
) -> list[dict[str, Any]] | None:
    """Undo a losing segment inside the caller's open transaction.

    ``blocks`` are the local blocks to drop (any order), ``ancestor`` the
    common ancestor whose recorded state_root anchors the verification, and
    ``provably_empty`` a callable ``(session, [blocks]) -> bool`` for the
    pre-journal fallback. Returns the orphaned transaction payloads for the
    caller to requeue into the mempool after commit — or None when undo is
    impossible (a non-empty block without a journal, or a state root that
    refuses to match the ancestor's). On None the caller must NOT commit.

    When ``reverted_accounts`` is a set, every account address the journal
    touched is added to it before the delta rows are consumed — the caller
    uses it to invalidate balance/detail caches once the revert commits.
    """
    # ``incomplete`` counts as not journaled: the provably-empty path is still
    # allowed (nothing to undo), anything else escalates — never a partial
    # revert from a journal that flagged itself unreliable.
    journaled = {b.height: journal_status(session, chain_id, b.height) == "complete" for b in blocks}
    for blk in blocks:
        if not journaled.get(blk.height) and not provably_empty(session, [blk]):
            return None

    # Collect each block's side-table pre-state digests before _revert_block
    # deletes its delta rows. Blocks journaled before the digest feature carry
    # no meta row — they simply contribute no entries.
    pre_digests: dict[int, dict[str, str]] = {}
    for blk in blocks:
        meta = session.exec(
            select(BlockStateDelta)
            .where(BlockStateDelta.chain_id == chain_id)
            .where(BlockStateDelta.height == blk.height)
            .where(BlockStateDelta.table_name == _DIGEST_TABLE)
        ).first()
        if meta is not None:
            meta_row = _decode_row(meta.before_json) or {}
            pre_digests[blk.height] = {
                str(k): str(v) for k, v in (meta_row.get("pre_digest") or {}).items() if isinstance(v, str)
            }

    # Account addresses whose rows the revert restores/creates/deletes —
    # captured before _revert_block consumes the delta rows so the caller can
    # drop their balance/detail cache keys once the revert commits.
    if reverted_accounts is not None:
        reverted_heights = [b.height for b in blocks]
        for pk_json in session.exec(
            select(BlockStateDelta.pk_json)
            .where(BlockStateDelta.chain_id == chain_id)
            .where(col(BlockStateDelta.height).in_(reverted_heights))
            .where(BlockStateDelta.table_name == "account")
        ).all():
            pk = _decode_row(pk_json) or {}
            addr = pk.get("address")
            if addr:
                reverted_accounts.add(str(addr))

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

    # Structural check: nothing may remain at the reverted heights — the
    # digest excludes transaction/block (the Sep-02 incident was exactly
    # orphan rows in those tables), so prove they are empty directly.
    reverted_heights = [b.height for b in blocks]
    leftover = (
        session.exec(
            select(func.count())
            .select_from(ChainTransaction)
            .where(ChainTransaction.chain_id == chain_id)
            .where(col(ChainTransaction.block_height).in_(reverted_heights))
        ).one()
        + session.exec(
            select(func.count())
            .select_from(Block)
            .where(Block.chain_id == chain_id)
            .where(col(Block.height).in_(reverted_heights))
        ).one()
    )
    if leftover:
        logger.error(
            "Fork undo left %s block/transaction rows at heights %s — refusing revert",
            leftover,
            reverted_heights,
        )
        return None

    # Side-table digest: for every table any reverted block digested, the
    # post-revert contents must equal the earliest reverted block's recorded
    # pre-state. Earlier-in-segment pre-state is the segment's pre-state for
    # tables untouched by still-earlier reverted blocks.
    expected_digest: dict[str, str] = {}
    for height in sorted(pre_digests):
        for table_name, digest in pre_digests[height].items():
            expected_digest.setdefault(table_name, digest)
    for table_name, want in sorted(expected_digest.items()):
        got = _table_digest(session, table_name, chain_id)
        if got != want:
            logger.error(
                "Fork undo side-table digest mismatch on %r: recorded=%s reverted=%s — refusing revert",
                table_name,
                want[:16],
                (got or "skipped")[:16],
            )
            return None

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


def _mark_domain_row_orphaned(session_factory: Any, chain_id: str, tx: dict[str, Any]) -> int:
    """Orphan-mark the RPC-side domain row a lost lock transaction funded.

    ``stake``, ``agent_stake`` and ``bounty_contract`` rows are written by the
    RPC handlers at queue time — outside block apply, so the delta journal
    can never capture them. When the confirming lock tx disappears in a reorg
    (failed requeue AND absent from the winning branch), the row would stay
    ``active`` forever with no on-chain backing. Marking it ``orphaned`` keeps
    it out of every status-filtered query (``confirmed_lock_txs``/payout paths
    already resolve against confirmed tx rows, never the domain row alone).
    """
    if session_factory is None:
        return 0
    raw_payload = tx.get("payload")
    payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
    tx_type = tx.get("type")
    # (lock tx type, payload key, model, model field naming the key)
    from ..base_models import AgentStakeRecord, BountyContract, Stake
    from ..protocol_escrow import confirmed_lock_txs

    targets: list[tuple[type[Any], str, str]] = []
    if tx_type == "STAKE_LOCK":
        if payload.get("stake_id"):
            targets.append((Stake, "id", "stake_id"))
        if payload.get("agent_stake_id"):
            targets.append((AgentStakeRecord, "stake_id", "agent_stake_id"))
    elif tx_type == "BOUNTY_LOCK" and payload.get("bounty_id"):
        targets.append((BountyContract, "bounty_id", "bounty_id"))
    if not targets:
        return 0
    marked = 0
    try:
        with session_factory() as session:
            for model, field, payload_key in targets:
                value = str(payload[payload_key])
                # Multiple locks can fund one record (agent-stake top-ups) —
                # only orphan it when no confirmed lock references it anymore.
                if confirmed_lock_txs(session, chain_id, str(tx_type), payload_key, value):
                    continue
                row = session.exec(
                    select(model).where(
                        col(model.chain_id) == chain_id,
                        col(getattr(model, field)) == (int(value) if field == "id" else value),
                    )
                ).first()
                if row is None or row.status == "orphaned":
                    continue
                row.status = "orphaned"
                row.updated_at = datetime.now(UTC)
                session.add(row)
                marked += 1
                logger.warning(
                    "Orphaned %s row %s=%s: confirming %s tx %s lost in fork",
                    model.__tablename__,
                    field,
                    value,
                    tx_type,
                    str(tx.get("tx_hash") or "")[:18],
                )
            session.commit()
    except Exception:
        logger.exception("Failed to orphan-mark domain rows for lost tx %s", tx.get("tx_hash"))
        return marked
    return marked


def _tx_on_chain(session_factory: Any, chain_id: str, tx_hash: str) -> bool:
    """True when the hash already exists in the transaction table — i.e. the
    winning branch (or a prior import) carries it, so it is not lost."""
    if session_factory is None or not tx_hash:
        return False
    try:
        with session_factory() as session:
            row = session.exec(
                select(ChainTransaction.id)
                .where(ChainTransaction.chain_id == chain_id)
                .where(ChainTransaction.tx_hash == tx_hash)
                .limit(1)
            ).first()
            return row is not None
    except Exception:
        return False


def _admit_orphan(tx: dict[str, Any], mempool: Any, chain_id: str) -> str:
    """Re-admit one orphaned transaction under real admission rules.

    Bridge credit types (release/refund) have no sender-side admission by
    design — they enter the mempool only from consensus-verified issuance, so
    an orphaned one proved itself by having been in a block. Everything else
    goes through the same gate as public intake: signature verification first
    (a payload without a verifiable signature — e.g. a pre-``envelope``
    reconstruction — can never legitimately re-enter the mempool), then
    ``_validate_transaction_admission`` (sender, balance, nonce window,
    supported chain).
    """
    from ..rpc.transactions import _validate_transaction_admission
    from ..rpc.utils import PREREGISTERED_CREDIT_TX_TYPES, _resolved_tx_type, verify_transaction_signature

    if _resolved_tx_type(tx) not in PREREGISTERED_CREDIT_TX_TYPES:
        signature = str(tx.get("signature") or tx.get("sig") or "")
        sender = str(tx.get("from") or tx.get("sender") or "")
        if not verify_transaction_signature(tx, signature, sender):
            raise ValueError("orphaned payload fails signature verification")
        _validate_transaction_admission(tx, mempool)
    return str(mempool.add(tx, chain_id=chain_id, tx_hash=str(tx.get("tx_hash") or "") or None))


def requeue_orphaned_transactions(
    chain_id: str,
    payloads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Push orphaned block transactions back into the mempool under full
    admission. Returns the payloads admission REJECTED — the caller must run
    ``reconcile_orphaned_transactions`` on them only after the winning branch
    is imported, since whether a rejected tx is truly lost depends on whether
    that branch carries it."""
    from ..mempool import get_mempool

    mempool = get_mempool()
    failed: list[dict[str, Any]] = []
    for tx in payloads:
        try:
            _admit_orphan(tx, mempool, chain_id)
        except Exception as exc:
            tx["_requeue_error"] = str(exc)
            failed.append(tx)
            logger.info(
                "Orphaned tx %s failed re-admission (%s) — final classification after winning branch import",
                str(tx.get("tx_hash") or "")[:18],
                exc,
            )
    return failed


def reconcile_orphaned_transactions(
    chain_id: str,
    failed: list[dict[str, Any]],
    session_factory: Any,
) -> None:
    """Post-import pass over the payloads requeue could not re-admit.

    Runs after the winning branch is in the DB: a failed tx that appears
    there was never lost; one that does not is a confirmed user transaction
    disappearing — WARNING + ``sync_fork_orphaned_tx_lost_total`` (alert
    path) + orphan-marking of any domain row the lock funded. Also revives
    domain rows previously marked ``orphaned`` whose lock has since
    confirmed, so a stale mark cannot strand a valid stake.
    """
    from ..metrics import metrics_registry

    lost = 0
    for tx in failed:
        tx_hash = str(tx.get("tx_hash") or "")
        if _tx_on_chain(session_factory, chain_id, tx_hash):
            logger.info("Orphaned tx %s confirmed on the winning branch — not lost", tx_hash[:18])
            continue
        lost += 1
        logger.warning(
            "Orphaned tx %s (from %s) failed re-admission and is not on the winning branch — user transaction lost: %s",
            tx_hash[:18],
            tx.get("from"),
            tx.get("_requeue_error", "unknown"),
        )
        marked = _mark_domain_row_orphaned(session_factory, chain_id, tx)
        if marked:
            metrics_registry.increment("sync_fork_domain_rows_orphaned_total", float(marked))
    if lost:
        metrics_registry.increment("sync_fork_orphaned_tx_lost_total", float(lost))
    revived = _revive_confirmed_domain_rows(session_factory, chain_id)
    if revived:
        logger.warning("Revived %s domain rows marked orphaned whose lock tx is confirmed again", revived)


# (model, row key field, lock-tx payload key, lock tx type) for the queue-time
# domain rows RPC handlers create ahead of confirmation.
_DOMAIN_LOCK_MAP = (
    ("Stake", "id", "stake_id", "STAKE_LOCK"),
    ("AgentStakeRecord", "stake_id", "agent_stake_id", "STAKE_LOCK"),
    ("BountyContract", "bounty_id", "bounty_id", "BOUNTY_LOCK"),
)


def _revive_confirmed_domain_rows(session_factory: Any, chain_id: str) -> int:
    """Undo a stale ``orphaned`` mark: a domain row is reactivated when a
    confirmed lock tx referencing it exists (e.g. a false-orphan marked
    before the winning branch arrived, then carried by it)."""
    if session_factory is None:
        return 0
    from .. import base_models
    from ..protocol_escrow import confirmed_lock_txs

    revived = 0
    try:
        with session_factory() as session:
            for model_name, field, payload_key, lock_type in _DOMAIN_LOCK_MAP:
                model = getattr(base_models, model_name)
                rows = session.exec(
                    select(model).where(col(model.chain_id) == chain_id, col(model.status) == "orphaned")
                ).all()
                for row in rows:
                    value = str(getattr(row, field))
                    if confirmed_lock_txs(session, chain_id, lock_type, payload_key, value):
                        row.status = "active"
                        row.updated_at = datetime.now(UTC)
                        session.add(row)
                        revived += 1
                        logger.warning(
                            "Revived orphaned %s row %s=%s — a confirming %s tx is on chain",
                            model.__tablename__,
                            field,
                            value,
                            lock_type,
                        )
            if revived:
                session.commit()
    except Exception:
        logger.exception("Domain-row orphan revival failed")
        return 0
    return revived


def _account_cache() -> Any:
    """Lazily build the same Redis client the apply path uses; None when the
    caching package or a reachable server is unavailable — cache invalidation
    must never make a fork revert fail."""
    global _ACCOUNT_CACHE
    if _ACCOUNT_CACHE is not None:
        return _ACCOUNT_CACHE or None  # False = earlier init failure
    try:
        import os

        from aitbc.caching import RedisCache

        _ACCOUNT_CACHE = RedisCache(redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"), default_ttl=30)
    except Exception:
        _ACCOUNT_CACHE = False
    return _ACCOUNT_CACHE or None


_ACCOUNT_CACHE: Any = None


def invalidate_account_caches(chain_id: str, addresses: set[str]) -> int:
    """Drop ``account_balance``/``account_details`` keys for reverted accounts.

    Called after a fork undo commits: without it, RPC reads could serve the
    losing branch's balances for up to the cache TTL. Returns the number of
    keys deleted; 0 and silent when Redis is unavailable (the TTL bound then
    applies, same as for missed apply-time invalidations).
    """
    cache = _account_cache()
    if cache is None or not cache.is_available():
        return 0
    deleted = 0
    for addr in addresses:
        for prefix in ("account_balance", "account_details"):
            try:
                if cache.delete(f"{prefix}:{chain_id}:{addr.lower()}"):
                    deleted += 1
            except Exception:
                logger.warning("Failed to invalidate %s cache for %s", prefix, addr)
    return deleted
