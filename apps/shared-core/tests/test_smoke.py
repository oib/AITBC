"""Smoke tests for shared-core: the re-export shims must stay in sync with aitbc_shared."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[1] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


def test_config_shim_reexports_aitbc_shared() -> None:
    import aitbc_shared
    from shared_core.core import config

    assert config.DatabaseConfig is aitbc_shared.DatabaseConfig
    assert config.ServiceSettings is aitbc_shared.ServiceSettings


def test_package_importable() -> None:
    import shared_core

    assert shared_core is not None


def test_database_module_importable() -> None:
    from shared_core.core import database

    assert database is not None


def test_security_package_importable() -> None:
    from shared_core.core import security

    assert security is not None


def test_get_async_engine_does_not_double_prefix_async_urls(monkeypatch) -> None:
    """SHARED-DB-ASYNCURL-1 (#1447): get_async_engine must not rewrite an
    already dialect-qualified URL — "sqlite:///" is a substring of
    "sqlite+aiosqlite:///" and produced "sqlite+aiosqlite+aiosqlite:///"."""
    from shared_core.core import database
    from shared_core.core.config import DatabaseConfig

    calls: list[str] = []
    monkeypatch.setattr(database, "create_async_engine", lambda url, **kw: calls.append(url) or url)

    database.get_async_engine(DatabaseConfig(adapter="sqlite", url="sqlite+aiosqlite:////tmp/x.db"))
    database.get_async_engine(DatabaseConfig(adapter="sqlite", url="sqlite:////tmp/x.db"))
    database.get_async_engine(DatabaseConfig(adapter="postgresql", url="postgresql+asyncpg://h/db"))
    database.get_async_engine(DatabaseConfig(adapter="postgresql", url="postgresql://h/db"))

    assert calls == [
        "sqlite+aiosqlite:////tmp/x.db",
        "sqlite+aiosqlite:////tmp/x.db",
        "postgresql+asyncpg://h/db",
        "postgresql+asyncpg://h/db",
    ]
