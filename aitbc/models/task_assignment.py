"""Database schema for load-balancer task assignments.

Durable bookkeeping for the agent-coordinator's ``LoadBalancer``
(``agent_app.routing.load_balancer``): every assignment mutation is written
through to this table so a coordinator restart does not drop the
task -> agent mapping that escrowed tasks still need for completion,
failure, and expiry accounting.

Timestamps are stored as Unix epoch floats — the same convention
``task_escrow`` uses — and converted back to tz-aware datetimes on load.
``task_data`` itself is not stored: the assignment record only needs the
ids and lifecycle fields; the task payload lives with the escrow/message
layers that own it.
"""

from sqlalchemy import Boolean, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .coin_request import Base


class TaskAssignmentRow(Base):
    """Persisted task -> agent assignment for the load balancer."""

    __tablename__ = "task_assignments"

    task_id: Mapped[str] = mapped_column(String, primary_key=True)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String(16), index=True, default="pending")
    assigned_at: Mapped[float] = mapped_column(Float)
    completed_at: Mapped[float | None] = mapped_column(Float)
    response_time: Mapped[float | None] = mapped_column(Float)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(Text)
