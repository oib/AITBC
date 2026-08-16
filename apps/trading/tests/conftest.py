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
    """Build the schema this suite needs, the way a deployment builds it.

    Alembic and nothing else, because this service's ``init_db()`` deliberately creates
    nothing ("Schema management is Alembic's job") — a database nobody has migrated has no
    tables at all, which is why the suite used to run against the deployed file.

    This used to run ``trading_metadata.create_all`` afterwards as well, because
    ``alembic upgrade head`` built two of the nine tables and stopped. Migration 003 builds
    the other seven, so the stopgap is gone — and its absence is the test. If a model is
    added without a migration, this suite fails on ``no such table`` rather than papering
    over the gap, which is the failure a deployment would have hit instead.
    """
    from alembic import command
    from alembic.config import Config

    app_dir = Path(__file__).resolve().parent.parent
    config = Config(str(app_dir / "alembic.ini"))
    config.set_main_option("script_location", str(app_dir / "alembic"))
    command.upgrade(config, "head")


@pytest.fixture
def client():
    """Authenticated TestClient for the Trading service."""
    from trading_service.main import app

    return TestClient(app, headers={"X-Trading-Api-Key": "test-trading-key"})
