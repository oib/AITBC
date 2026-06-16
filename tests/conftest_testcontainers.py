#!/usr/bin/env python3
"""
Test database setup using Testcontainers for integration tests.
"""

import os

import pytest

# Add testcontainers to test requirements
try:
    from testcontainers.mongodb import MongoDbContainer
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer

    TESTCONTAINERS_AVAILABLE = True
except ImportError:
    TESTCONTAINERS_AVAILABLE = False


@pytest.fixture(scope="session")
def postgres_container():
    """PostgreSQL test container fixture."""
    if not TESTCONTAINERS_AVAILABLE:
        pytest.skip("testcontainers not installed")

    container = PostgresContainer("postgres:16-alpine")
    container.start()
    yield container.get_connection_url()
    container.stop()


@pytest.fixture(scope="session")
def redis_container():
    """Redis test container fixture."""
    if not TESTCONTAINERS_AVAILABLE:
        pytest.skip("testcontainers not installed")

    container = RedisContainer("redis:7-alpine")
    container.start()
    yield container.get_connection_url()
    container.stop()


@pytest.fixture(scope="session")
def mongodb_container():
    """MongoDB test container fixture."""
    if not TESTCONTAINERS_AVAILABLE:
        pytest.skip("testcontainers not installed")

    container = MongoDbContainer("mongo:7-jammy")
    container.start()
    yield container.get_connection_url()
    container.stop()


@pytest.fixture(scope="function")
def test_db_url(postgres_container):
    """Override DATABASE_URL for tests."""
    original = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = postgres_container
    yield postgres_container
    if original:
        os.environ["DATABASE_URL"] = original


@pytest.fixture(scope="function")
def test_redis_url(redis_container):
    """Override REDIS_URL for tests."""
    original = os.environ.get("REDIS_URL")
    os.environ["REDIS_URL"] = redis_container
    yield redis_container
    if original:
        os.environ["REDIS_URL"] = original


class TestDatabaseSetup:
    """Test database container setup."""

    def test_postgres_available(self, postgres_container):
        """Test PostgreSQL container is running."""
        import psycopg2

        conn = psycopg2.connect(postgres_container)
        conn.close()

    def test_redis_available(self, redis_container):
        """Test Redis container is running."""
        import redis

        r = redis.from_url(redis_container)
        assert r.ping()

    def test_mongodb_available(self, mongodb_container):
        """Test MongoDB container is running."""
        from pymongo import MongoClient

        client = MongoClient(mongodb_container)
        assert client.admin.command("ping")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-x"])
