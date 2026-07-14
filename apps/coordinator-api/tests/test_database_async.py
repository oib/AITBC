import pytest

from coordinator_api.database_async import _build_async_url


def test_build_async_url_sqlite():
    assert _build_async_url("sqlite:///path.db") == "sqlite+aiosqlite:///path.db"
    assert _build_async_url("sqlite:///path.db?mode=ro") == "sqlite+aiosqlite:///path.db?mode=ro"


def test_build_async_url_postgresql():
    assert _build_async_url("postgresql://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
    assert _build_async_url("postgresql://u:p@h/db?sslmode=require") == "postgresql+asyncpg://u:p@h/db?sslmode=require"


def test_build_async_url_already_async():
    assert _build_async_url("sqlite+aiosqlite:///path.db") == "sqlite+aiosqlite:///path.db"
    assert _build_async_url("postgresql+asyncpg://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"


def test_build_async_url_unsupported():
    with pytest.raises(ValueError, match="Unsupported async database URL"):
        _build_async_url("mysql://u:p@h/db")
