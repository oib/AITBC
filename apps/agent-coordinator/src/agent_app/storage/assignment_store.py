"""Durable store for load-balancer task assignments.

Persists ``agent_app.routing.load_balancer.TaskAssignment`` records to the
shared agent SQLite database (``aitbc.db``, same machinery the coin requests
and task escrows use) so the task -> agent mapping survives coordinator
restarts. ``LoadBalancer`` keeps the rows hot in memory as a write-through
cache and reloads them at construction — a pending row restored on boot is
picked up by ``expire_stale_assignments`` and the ``/tasks/{id}/complete``
endpoints exactly like one the running process created itself.
"""

from __future__ import annotations

from datetime import UTC, datetime

from aitbc.aitbc_logging import get_logger
from aitbc.db import get_db_session, init_db
from aitbc.models import TaskAssignmentRow

from ..routing.load_balancer import TaskAssignment

logger = get_logger(__name__)


class TaskAssignmentStore:
    """Write-through backend for ``LoadBalancer.task_assignments``."""

    def __init__(self) -> None:
        # create_all is idempotent; guaranteeing the table here keeps the
        # store usable regardless of lifespan ordering.
        init_db()

    def save(self, assignment: TaskAssignment) -> None:
        """Upsert the durable row for ``assignment``."""
        with get_db_session() as session:
            row = session.get(TaskAssignmentRow, assignment.task_id)
            if row is None:
                row = TaskAssignmentRow()
                row.task_id = assignment.task_id
                session.add(row)
            row.agent_id = assignment.agent_id
            row.status = assignment.status
            row.assigned_at = assignment.assigned_at.timestamp()
            row.completed_at = assignment.completed_at.timestamp() if assignment.completed_at else None
            row.response_time = assignment.response_time
            row.success = assignment.success
            row.error_message = assignment.error_message

    def delete(self, task_id: str) -> None:
        """Drop the durable row for ``task_id`` (terminal-map eviction)."""
        with get_db_session() as session:
            row = session.get(TaskAssignmentRow, task_id)
            if row is not None:
                session.delete(row)

    def load_all(self) -> list[TaskAssignment]:
        """Return every persisted assignment as a ``TaskAssignment``.

        Terminal rows are rehydrated too: ``get_assignment`` serves them to
        the completion endpoints and stats, and the in-memory map is already
        bounded by ``LoadBalancer._max_assignments`` so the reload stays
        bounded with it (evicted rows are deleted, not left behind).
        """
        with get_db_session() as session:
            rows = session.query(TaskAssignmentRow).all()
            return [self._to_assignment(row) for row in rows]

    @staticmethod
    def _to_assignment(row: TaskAssignmentRow) -> TaskAssignment:
        return TaskAssignment(
            task_id=row.task_id,
            agent_id=row.agent_id,
            assigned_at=datetime.fromtimestamp(row.assigned_at, UTC),
            completed_at=datetime.fromtimestamp(row.completed_at, UTC) if row.completed_at else None,
            status=row.status,
            response_time=row.response_time,
            success=bool(row.success),
            error_message=row.error_message,
        )
