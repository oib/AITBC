"""Database schema for task payment escrows.

Durable bookkeeping for the agent-coordinator's ``PaymentEscrow`` manager
(``aitbc.crypto.payment_escrow``): every escrow mutation is written through
to this table so a coordinator restart does not drop LOCKED escrows that
still hold on-chain funds.

Timestamps are stored as Unix epoch floats to match ``EscrowEntry`` exactly —
converting to ``DateTime`` would lose precision and invite timezone drift.
``status`` holds the ``EscrowStatus`` member name (``LOCKED``, ``RELEASED``,
``REFUNDED``, ``EXPIRED``, ``PENDING``); storing it as a plain string keeps
this module free of an ``aitbc.crypto`` import.
"""

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .coin_request import Base


class TaskEscrow(Base):
    """Persisted payment escrow entry for a coordinator task."""

    __tablename__ = "task_escrows"

    escrow_id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, index=True)
    chain_id: Mapped[str] = mapped_column(String)
    requester: Mapped[str] = mapped_column(String)  # buyer paying for the task
    agent: Mapped[str] = mapped_column(String)  # provider receiving payment
    amount: Mapped[int] = mapped_column(Integer)
    fee: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), index=True, default="PENDING")
    contract_id: Mapped[str | None] = mapped_column(String, index=True)
    tx_hash_lock: Mapped[str | None] = mapped_column(String)
    tx_hash_release: Mapped[str | None] = mapped_column(String)
    tx_hash_refund: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[float] = mapped_column(Float)
    locked_at: Mapped[float | None] = mapped_column(Float)
    released_at: Mapped[float | None] = mapped_column(Float)
    expires_at: Mapped[float | None] = mapped_column(Float, index=True)
    # 'metadata' is reserved by the declarative base; the DB column keeps the name.
    extra_metadata: Mapped[str | None] = mapped_column("metadata", Text)
