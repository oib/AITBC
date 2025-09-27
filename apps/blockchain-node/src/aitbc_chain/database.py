from __future__ import annotations

from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

from .config import settings

_engine = create_engine(f"sqlite:///{settings.db_path}", echo=False)


def init_db() -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(_engine)


@contextmanager
def session_scope() -> Session:
    with Session(_engine) as session:
        yield session
