from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlmodel import SQLModel, Session, create_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from aitbc_chain.models import Block, Transaction, Receipt  # noqa: F401 - ensure models imported for metadata


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
