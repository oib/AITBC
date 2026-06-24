from __future__ import annotations

import os

import pytest

# Disable rate limiting in tests to avoid 429s from tight loops
os.environ.setdefault("AITBC_ENABLE_RATE_LIMITING", "false")
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
