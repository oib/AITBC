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

    def load_all(self) -> list[EscrowEntry]:
        """Return every persisted escrow as an ``EscrowEntry``."""
        with get_db_session() as session:
            rows = session.query(TaskEscrow).all()
            return [self._to_entry(row) for row in rows]

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
