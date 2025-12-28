from __future__ import annotations

from contextlib import contextmanager
from typing import Annotated, Generator

from fastapi import Depends
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from ..config import settings
from ..domain import Job, Miner, MarketplaceOffer, MarketplaceBid
from .models_governance import GovernanceProposal, ProposalVote, TreasuryTransaction, GovernanceParameter

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine

    if _engine is None:
        connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
        _engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)
    return _engine


def init_db() -> None:
    engine = get_engine()
    SQLModel.metadata.create_all(engine)


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    engine = get_engine()
    with Session(engine) as session:
        yield session


def get_session() -> Generator[Session, None, None]:
    with session_scope() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
