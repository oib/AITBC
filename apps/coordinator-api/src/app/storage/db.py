"""
Database storage module for AITBC Coordinator API

Provides unified database session management with connection pooling.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Annotated, Generator

from fastapi import Depends
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool
from sqlmodel import Session, SQLModel, create_engine

from ..config import settings
from ..domain import Job, Miner, MarketplaceOffer, MarketplaceBid, JobPayment, PaymentEscrow, GPURegistry, GPUBooking, GPUReview
from .models_governance import GovernanceProposal, ProposalVote, TreasuryTransaction, GovernanceParameter

_engine: Engine | None = None


def get_engine() -> Engine:
    """Get or create the database engine with connection pooling."""
    global _engine

    if _engine is None:
        db_config = settings.database
        connect_args = {"check_same_thread": False} if "sqlite" in db_config.effective_url else {}
        
        _engine = create_engine(
            db_config.effective_url,
            echo=False,
            connect_args=connect_args,
            poolclass=QueuePool if "postgresql" in db_config.effective_url else None,
            pool_size=db_config.pool_size,
            max_overflow=db_config.max_overflow,
            pool_pre_ping=db_config.pool_pre_ping,
        )
    return _engine


def init_db() -> None:
    """Initialize database tables."""
    engine = get_engine()
    SQLModel.metadata.create_all(engine)


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager for database sessions."""
    engine = get_engine()
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Generator[Session, None, None]:
    """Get a database session (for FastAPI dependency)."""
    with session_scope() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
