"""PG-TARGET-1 stream 1: shared DB-target resolver tests.

All URLs are fake. The resolver, the sync conversion, the redaction and the
fail-closed check are exercised without a live database.
"""

import pytest

from aitbc.database.target import (
    assert_same_target,
    redacted_url,
    resolve_service_database_url,
    to_sync_url,
)


def test_redacted_url_drops_userinfo_and_query():
    assert redacted_url("postgresql+asyncpg://u:p%40ss@db.internal:5433/mydb?ssl=1") == (
        "postgresql+asyncpg://db.internal:5433/mydb"
    )
    assert redacted_url("sqlite:////var/lib/aitbc/x.db") == "sqlite:////var/lib/aitbc/x.db"
    assert "p%40ss" not in redacted_url("postgresql://u:p%40ss@h/d")
    assert "u" not in redacted_url("postgresql://secretuser:x@h/d").split("://")[1].split("/")[0]


def test_to_sync_url():
    assert to_sync_url("postgresql+asyncpg://u:p@h/d") == "postgresql+psycopg2://u:p@h/d"
    assert to_sync_url("sqlite+aiosqlite:////x.db") == "sqlite:////x.db"
    assert to_sync_url("postgresql://u:p@h/d") == "postgresql://u:p@h/d"


def test_resolve_pg_env_quotes_credentials():
    env = {"DB_TYPE": "postgresql", "DB_HOST": "pg1", "DB_PORT": "5433", "DB_NAME": "x", "DB_USER": "a@b", "DB_PASS": "p/w:d"}
    url = resolve_service_database_url(env, default_url="sqlite+aiosqlite:///x.db", default_db_name="x")
    assert url.startswith("postgresql+asyncpg://a%40b:p%2Fw%3Ad@pg1:5433/x")
    url_sync = resolve_service_database_url(env, default_url="x", default_db_name="x", async_=False)
    assert url_sync.startswith("postgresql+psycopg2://a%40b")


def test_resolve_falls_back_to_database_url_then_default():
    env = {"DATABASE_URL": "postgresql+asyncpg://u:p@h/d"}
    assert resolve_service_database_url(env, default_url="sqlite+aiosqlite:///x", default_db_name="x").startswith(
        "postgresql+asyncpg"
    )
    assert (
        resolve_service_database_url({}, default_url="sqlite+aiosqlite:///x", default_db_name="x") == "sqlite+aiosqlite:///x"
    )


def test_resolve_db_type_wins_over_database_url():
    env = {"DB_TYPE": "postgresql", "DATABASE_URL": "sqlite+aiosqlite:///other.db"}
    url = resolve_service_database_url(env, default_url="sqlite+aiosqlite:///x", default_db_name="d", async_=False)
    assert url.startswith("postgresql+psycopg2://")


def test_assert_same_target_pass_and_fail():
    assert_same_target("postgresql+asyncpg://u:p@h/d", "postgresql+psycopg2://u:p@h/d")
    assert_same_target("sqlite+aiosqlite:////x.db", "sqlite:////x.db")
    with pytest.raises(RuntimeError) as exc:
        assert_same_target("sqlite+aiosqlite:////x.db", "postgresql+psycopg2://u:p@h/d")
    assert "postgresql+psycopg2://h/d" in str(exc.value)
    assert "u:p" not in str(exc.value)
