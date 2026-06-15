from __future__ import annotations

import pytest
from aitbc_chain.models import Block, Receipt, Transaction  # noqa: F401 - ensure models imported for metadata
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    try:
        yield engine
    finally:
        SQLModel.metadata.drop_all(engine)


@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session
        session.rollback()
