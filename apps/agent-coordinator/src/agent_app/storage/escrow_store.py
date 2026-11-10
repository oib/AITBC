"""Durable store for task payment escrows.

Persists ``aitbc.crypto.payment_escrow.EscrowEntry`` records to the shared
agent SQLite database (``aitbc.db``, same machinery the coin requests use)
so escrow bookkeeping survives coordinator restarts. ``PaymentEscrow`` keeps
the rows hot in memory as a write-through cache and reloads them here at
startup — a LOCKED row restored on boot is picked up by the expiry sweeper
exactly like one the running process locked itself.
"""

from __future__ import annotations

import json

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.payment_escrow import EscrowEntry, EscrowStatus
from aitbc.db import get_db_session, init_db
from aitbc.models import TaskEscrow

logger = get_logger(__name__)


class TaskEscrowStore:
    """``EscrowStore`` implementation backed by the ``task_escrows`` table."""

    def __init__(self) -> None:
        # create_all is idempotent; guaranteeing the table here keeps the
        # store usable regardless of lifespan ordering.
        init_db()

    def save(self, entry: EscrowEntry) -> None:
        """Upsert the durable row for ``entry``."""
        with get_db_session() as session:
            row = session.get(TaskEscrow, entry.escrow_id)
            if row is None:
                row = TaskEscrow()
                row.escrow_id = entry.escrow_id
                session.add(row)
            row.task_id = entry.task_id
            row.chain_id = entry.chain_id
            row.requester = entry.requester
            row.agent = entry.agent
            row.amount = entry.amount
            row.fee = entry.fee
            row.status = entry.status.name
            row.contract_id = entry.contract_id
            row.tx_hash_lock = entry.tx_hash_lock
            row.tx_hash_release = entry.tx_hash_release
            row.tx_hash_refund = entry.tx_hash_refund
            row.created_at = entry.created_at
            row.locked_at = entry.locked_at
            row.released_at = entry.released_at
            row.expires_at = entry.expires_at
            row.extra_metadata = json.dumps(entry.metadata) if entry.metadata else None

    # Statuses rehydrated at boot. Terminal rows (RELEASED/REFUNDED/EXPIRED)
    # can never transition again — the sweeper and state machine only ever
    # act on PENDING/LOCKED — so loading them made every restart pay for the
    # entire escrow history and grow memory monotonically (#1515). Terminal
    # rows remain reachable through the point lookups below.
    _ACTIVE_STATUSES = (EscrowStatus.PENDING.name, EscrowStatus.LOCKED.name)

    def load_all(self) -> list[EscrowEntry]:
        """Return persisted *active* escrows as ``EscrowEntry``s.

        Only PENDING/LOCKED rows are rehydrated into the in-memory cache;
        terminal rows are fetched on demand via :meth:`load` /
        :meth:`load_by_task`.
        """
        with get_db_session() as session:
            rows = session.query(TaskEscrow).filter(TaskEscrow.status.in_(self._ACTIVE_STATUSES)).all()
            return [self._to_entry(row) for row in rows]

    def load(self, escrow_id: str) -> EscrowEntry | None:
        """Point lookup by escrow id — covers terminal rows load_all skips."""
        with get_db_session() as session:
            row = session.get(TaskEscrow, escrow_id)
            return self._to_entry(row) if row is not None else None

    def load_by_task(self, task_id: str) -> EscrowEntry | None:
        """Point lookup by task id — same coverage as :meth:`load`.

        A reused ``task_id`` can have several rows; mirror
        ``PaymentEscrow.get_escrow_for_task`` and prefer the newest active
        (PENDING/LOCKED) entry so a terminal row cannot shadow the live
        escrow after a restart.
        """
        with get_db_session() as session:
            rows = session.query(TaskEscrow).filter(TaskEscrow.task_id == task_id).all()
            if not rows:
                return None
            entries = [self._to_entry(row) for row in rows]
            active = [e for e in entries if e.status in (EscrowStatus.PENDING, EscrowStatus.LOCKED)]
            return max(active or entries, key=lambda e: e.created_at)

    @staticmethod
    def _to_entry(row: TaskEscrow) -> EscrowEntry:
        try:
            status = EscrowStatus[row.status]
        except KeyError:
            logger.warning("Unknown escrow status %r on %s; treating as PENDING", row.status, row.escrow_id)
            status = EscrowStatus.PENDING
        metadata: dict = {}
        if row.extra_metadata:
            try:
                metadata = json.loads(row.extra_metadata)
            except (TypeError, ValueError):
                logger.warning("Unreadable escrow metadata on %s", row.escrow_id)
        return EscrowEntry(
            escrow_id=row.escrow_id,
            task_id=row.task_id,
            chain_id=row.chain_id,
            requester=row.requester,
            agent=row.agent,
            amount=row.amount,
            fee=row.fee,
            status=status,
            created_at=row.created_at,
            locked_at=row.locked_at,
            released_at=row.released_at,
            expires_at=row.expires_at,
            tx_hash_lock=row.tx_hash_lock,
            tx_hash_release=row.tx_hash_release,
            tx_hash_refund=row.tx_hash_refund,
            contract_id=row.contract_id,
            metadata=metadata,
        )
