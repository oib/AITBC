"""Trading service test configuration.

trading_service.main reads TRADING_API_KEY into a module constant at import time, so the
test key must be set before the app is first imported. The client fixtures below also set
the matching header by default so authenticated route tests can run unchanged.

The database is already a throwaway: the repo-root conftest points ``AITBC_DATA_DIR`` at a
temporary directory, so ``trading_service.storage`` resolves to a file under it rather than to
``/var/lib/aitbc/data/trading_service.db``, which is what the suite ran against until V23-73.
"""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("TRADING_API_KEY", "test-trading-key")


def _model_tables():
    """The tables declared by this service's own domain modules.

    Named explicitly rather than calling ``create_all`` over the whole registry: in a full
    repo run that registry holds every other service's tables too, and building them into this
    service's database is how a schema ends up with tables nobody can account for.
    """
    from sqlmodel import SQLModel

    from trading_service.domain import inter_chain, trading

    tables = []
    for module in (inter_chain, trading):
        for value in vars(module).values():
            if isinstance(value, type) and issubclass(value, SQLModel):
                table = getattr(value, "__table__", None)
                if table is not None:
                    tables.append(table)
    return tables


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    """Build the schema this suite needs.

    Alembic first, because this service's ``init_db()`` deliberately creates nothing ("Schema
    management is Alembic's job") — a database nobody has migrated has no tables at all, which
    is why the suite had to run against the deployed file. Running the migrations here also
    puts them under test.

    Then the models, because the migrations do not cover them. ``alembic upgrade head`` builds
    ``inter_chain_trades`` and ``island_registry`` and stops; the seven tables in
    ``domain/trading.py`` — ``trade_requests``, ``trade_matches``, ``trade_negotiations``,
    ``trade_agreements``, ``trade_settlements``, ``trade_feedback``, ``trading_analytics`` —
    have never had a migration. The deployed database has them because something ran
    ``create_all`` before that comment was written, so a fresh deployment would come up with
    two of this service's nine tables. Recorded as a finding; ``checkfirst`` leaves anything
    Alembic already built alone.
    """
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    app_dir = Path(__file__).resolve().parent.parent
    config = Config(str(app_dir / "alembic.ini"))
    config.set_main_option("script_location", str(app_dir / "alembic"))
    command.upgrade(config, "head")

    from trading_service.storage import DATABASE_URL

    engine = create_engine(DATABASE_URL.replace("+aiosqlite", ""))
    for table in _model_tables():
        table.create(engine, checkfirst=True)
    engine.dispose()


@pytest.fixture
def client():
    """Authenticated TestClient for the Trading service."""
    from trading_service.main import app

    return TestClient(app, headers={"X-Trading-Api-Key": "test-trading-key"})
