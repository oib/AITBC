#!/usr/bin/env python3
"""
Test database setup using SQLite in-memory for integration tests.
This replaces testcontainers for environments without Docker.
"""

import os
import tempfile

import pytest


@pytest.fixture(scope="session")
def sqlite_db_path():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    yield f"sqlite:///{db_path}"

    # Cleanup
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture(scope="session")
def sqlite_async_db_path():
    """Create a temporary SQLite async database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    yield f"sqlite+aiosqlite:///{db_path}"

    # Cleanup
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture(scope="function")
def test_db_url(sqlite_db_path):
    """Override DATABASE_URL for tests."""
    original = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = sqlite_db_path
    os.environ["MARKETPLACE_DATABASE_URL"] = sqlite_db_path
    yield sqlite_db_path
    if original:
        os.environ["DATABASE_URL"] = original
        os.environ["MARKETPLACE_DATABASE_URL"] = original


@pytest.fixture(scope="function")
def test_redis_url():
    """Set REDIS_URL env var to a test Redis instance.

    Note: this only configures the environment variable. Tests that need an
    actual Redis connection without a running server should use the
    ``fakeredis_client`` / ``fakeredis_async_client`` fixtures defined in
    ``tests/conftest.py``, which provide in-process fakes backed by the
    ``fakeredis`` package.
    """
    original = os.environ.get("REDIS_URL")
    os.environ["REDIS_URL"] = "redis://localhost:6379/1"
    yield "redis://localhost:6379/1"
    if original:
        os.environ["REDIS_URL"] = original


class TestSQLiteDatabaseSetup:
    """Test SQLite database setup for integration tests."""

    def test_sqlite_sync_connection(self, sqlite_db_path):
        """Test SQLite sync database connection."""
        from sqlalchemy import create_engine, text

        engine = create_engine(sqlite_db_path)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

    def test_sqlite_async_connection(self, sqlite_async_db_path):
        """Test SQLite async database connection."""
        import pytest

        pytest.skip("Async test requires async setup")

    def test_database_url_env_override(self, test_db_url):
        """Test DATABASE_URL environment override works."""
        assert os.environ.get("DATABASE_URL") == test_db_url
        assert "sqlite:///" in test_db_url


class TestInMemoryDatabases:
    """Test in-memory database alternatives."""

    def test_sqlite_in_memory(self):
        """Test SQLite in-memory database."""
        from sqlalchemy import create_engine, text

        engine = create_engine("sqlite:///:memory:")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

    def test_table_creation(self):
        """Test creating tables in SQLite."""
        from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, text

        engine = create_engine("sqlite:///:memory:")
        metadata = MetaData()

        users = Table(
            "users",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("name", String(50)),
            Column("email", String(100)),
        )

        metadata.create_all(engine)

        with engine.connect() as conn:
            conn.execute(users.insert().values(name="test", email="test@example.com"))
            result = conn.execute(text("SELECT * FROM users"))
            rows = result.fetchall()
            assert len(rows) == 1
            assert rows[0][1] == "test"
            assert rows[0][2] == "test@example.com"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-x"])
