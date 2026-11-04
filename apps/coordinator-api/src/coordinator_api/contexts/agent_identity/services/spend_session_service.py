"""Spend session lifecycle (AGENT-SPEND-A-1 Phase A)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import desc, update
from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger

from ..domain.agent_identity import AgentSpendSession, WalletAuditLog
from ..domain.spend_policy import ALLOWED_PERMISSIONS

logger = get_logger(__name__)


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

    def consume(
        self,
        session_id: str,
        agent_id: str,
        chain_id: int,
        amount: Decimal,
        operation: str,
        ref: str | None = None,
    ) -> None:
        """Atomic cap check and used_ait increment."""
        if operation not in ALLOWED_PERMISSIONS:
            raise ValueError(f"unsupported spend operation: {operation}")
        # lock row
        stmt = (
            select(AgentSpendSession)
            .where(AgentSpendSession.id == session_id, AgentSpendSession.agent_id == agent_id)
            .with_for_update()
        )
        row = self.session.exec(stmt).first()
        if row is None:
            raise ValueError("spend session not found")
        if row.revoked_at is not None:
            raise ValueError("spend session revoked")
        if row.chain_id != chain_id:
            raise ValueError("spend session chain mismatch")
        now = datetime.now(UTC)
        if row.expires_at is not None and row.expires_at <= now:
            raise ValueError("spend session expired")
        if operation not in row.allowed_ops:
            raise ValueError("operation not allowed for session")
        if amount <= 0:
            raise ValueError("amount must be positive")
        new_used = row.used_ait + amount
        if new_used > row.cap_ait:
            raise ValueError("session spend cap exceeded")
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
        self.session.commit()
