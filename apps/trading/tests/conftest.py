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
    two of this service's nine tables. Recorded as a finding; ``checkfirst`` leaves the two
    Alembic already built alone.

    ``trading_metadata`` holds exactly this service's tables and nothing else (V23-74), so
    ``create_all`` over it cannot build another service's schema into this database.
    """
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    from trading_service.domain.base import trading_metadata
    from trading_service.storage import DATABASE_URL

    app_dir = Path(__file__).resolve().parent.parent
    config = Config(str(app_dir / "alembic.ini"))
    config.set_main_option("script_location", str(app_dir / "alembic"))
    command.upgrade(config, "head")

    engine = create_engine(DATABASE_URL.replace("+aiosqlite", ""))
    trading_metadata.create_all(engine, checkfirst=True)
    engine.dispose()


@pytest.fixture
def client():
    """Authenticated TestClient for the Trading service."""
    from trading_service.main import app

    return TestClient(app, headers={"X-Trading-Api-Key": "test-trading-key"})
