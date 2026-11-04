"""Spend session lifecycle (AGENT-SPEND-A-1 Phase A)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import desc, update
from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger

from ..domain.agent_identity import AgentSpendSession, WalletAuditLog
from ..domain.spend_policy import ALLOWED_PERMISSIONS, SpendSessionCapError

logger = get_logger(__name__)


def _validate_cap_ait(cap_ait: Decimal) -> None:
    if not cap_ait.is_finite() or cap_ait <= 0:
        raise ValueError("cap_ait must be a finite value greater than zero")


def _validate_expires_at(expires_at: datetime | None) -> None:
    if expires_at is None:
        return
    if expires_at.tzinfo is None:
        raise ValueError("expires_at must be timezone-aware")
    if expires_at <= datetime.now(UTC):
        raise ValueError("expires_at must be in the future")


class SpendSessionService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _audit(
        self,
        agent_id: str,
        event: str,
        *,
        session_id: str | None = None,
        amount_ait: Decimal | None = None,
        op: str | None = None,
        ref: str | None = None,
    ) -> None:
        row = WalletAuditLog(
            id=f"audit_{uuid4().hex[:8]}",
            agent_id=agent_id,
            session_id=session_id,
            event=event,
            amount_ait=amount_ait,
            op=op,
            ref=ref,
        )
        self.session.add(row)

    def create_session(
        self,
        agent_id: str,
        owner_address: str,
        chain_id: int,
        cap_ait: Decimal,
        allowed_ops: list[str],
        expires_at: datetime | None,
    ) -> AgentSpendSession:
        _validate_cap_ait(cap_ait)
        _validate_expires_at(expires_at)
        for op in allowed_ops:
            if op not in ALLOWED_PERMISSIONS:
                raise ValueError(f"unsupported spend operation: {op}")
        row = AgentSpendSession(
            agent_id=agent_id,
            owner_address=owner_address,
            chain_id=chain_id,
            cap_ait=cap_ait,
            allowed_ops=allowed_ops,
            expires_at=expires_at,
        )
        self.session.add(row)
        self._audit(agent_id, "session.create", session_id=row.id, amount_ait=cap_ait)
        self.session.commit()
        self.session.refresh(row)
        logger.info("Created spend session %s for agent %s", row.id, agent_id)
        return row

    def list_sessions(self, agent_id: str, include_revoked: bool = False) -> list[AgentSpendSession]:
        stmt = select(AgentSpendSession).where(AgentSpendSession.agent_id == agent_id)
        if not include_revoked:
            stmt = stmt.where(AgentSpendSession.revoked_at.is_(None))  # type: ignore[union-attr]
        return list(
            self.session.exec(stmt.order_by(desc(AgentSpendSession.created_at))).all()  # type: ignore[arg-type]
        )

    def revoke_session(self, agent_id: str, session_id: str) -> AgentSpendSession:
        row = self.session.get(AgentSpendSession, session_id)
        if row is None or row.agent_id != agent_id:
            raise ValueError("spend session not found")
        if row.revoked_at is not None:
            return row
        row.revoked_at = datetime.now(UTC)
        self._audit(agent_id, "session.revoke", session_id=session_id)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def _load_session_for_update(
        self,
        session_id: str,
        agent_id: str,
        chain_id: int,
        operation: str,
        amount: Decimal,
    ) -> AgentSpendSession:
        if operation not in ALLOWED_PERMISSIONS:
            raise ValueError(f"unsupported spend operation: {operation}")
        stmt = (
            select(AgentSpendSession)
            .where(AgentSpendSession.id == session_id, AgentSpendSession.agent_id == agent_id)
            .with_for_update()
        )
        row = self.session.exec(stmt).first()
        if row is None:
            raise SpendSessionCapError("spend session not found")
        if row.revoked_at is not None:
            raise SpendSessionCapError("spend session revoked")
        if row.chain_id != chain_id:
            raise SpendSessionCapError("spend session chain mismatch")
        now = datetime.now(UTC)
        if row.expires_at is not None and row.expires_at <= now:
            raise SpendSessionCapError("spend session expired")
        if operation not in row.allowed_ops:
            raise SpendSessionCapError("operation not allowed for session")
        if amount <= 0:
            raise SpendSessionCapError("amount must be positive")
        new_used = row.used_ait + amount
        if new_used > row.cap_ait:
            raise SpendSessionCapError("session spend cap exceeded")
        return row

    def validate_consume(
        self,
        session_id: str,
        agent_id: str,
        chain_id: int,
        amount: Decimal,
        operation: str,
    ) -> None:
        """Check session cap and state without mutating used_ait."""
        self._load_session_for_update(session_id, agent_id, chain_id, operation, amount)

    def apply_consume(
        self,
        session_id: str,
        agent_id: str,
        chain_id: int,
        amount: Decimal,
        operation: str,
        ref: str | None = None,
    ) -> None:
        """Increment used_ait and write spend.ok after a successful transfer (no commit)."""
        row = self._load_session_for_update(session_id, agent_id, chain_id, operation, amount)
        new_used = row.used_ait + amount
        self.session.exec(
            update(AgentSpendSession)
            .where(AgentSpendSession.id == session_id)  # type: ignore[arg-type]
            .values(used_ait=new_used)
        )
        self._audit(
            agent_id,
            "spend.ok",
            session_id=session_id,
            amount_ait=amount,
            op=operation,
            ref=ref,
        )

    def consume(
        self,
        session_id: str,
        agent_id: str,
        chain_id: int,
        amount: Decimal,
        operation: str,
        ref: str | None = None,
    ) -> None:
        """Validate, apply, and commit (unit tests and direct callers)."""
        self.validate_consume(session_id, agent_id, chain_id, amount, operation)
        self.apply_consume(session_id, agent_id, chain_id, amount, operation, ref=ref)
        self.session.commit()
