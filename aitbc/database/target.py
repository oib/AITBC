"""Shared database-target resolution for services and their migrators (PG-TARGET-1).

A service's app code and its alembic ``env.py`` must resolve to the same
database. Today each side rebuilds the URL from env vars on its own, so a
``DB_TYPE``/``DB_*`` deployment can migrate Postgres while the app serves
SQLite — and reserved characters in credentials can parse differently on the
two paths. One resolver, used by both, removes the class of bug.

``redacted_url`` is the only form allowed near logs: scheme, host, port and
database name — never user, password or token.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import quote, urlsplit, urlunsplit

__all__ = [
    "assert_same_target",
    "redacted_url",
    "resolve_service_database_url",
    "to_sync_url",
]

_ASYNC_TO_SYNC_DRIVER = {
    "postgresql+asyncpg": "postgresql+psycopg2",
    "sqlite+aiosqlite": "sqlite",
}


def redacted_url(url: str) -> str:
    """``scheme://host:port/name`` — userinfo and query are dropped entirely."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<unparseable database url>"
    if not parts.scheme:
        return "<unparseable database url>"
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    return urlunsplit((parts.scheme, host + port, parts.path, "", ""))


def to_sync_url(url: str) -> str:
    """Map an async-driver URL to its sync equivalent for Alembic."""
    for async_driver, sync_driver in _ASYNC_TO_SYNC_DRIVER.items():
        if url.startswith(async_driver + "://"):
            return sync_driver + url[len(async_driver) :]
    return url


def resolve_service_database_url(
    env: Mapping[str, str] | None = None,
    *,
    default_url: str,
    default_db_name: str,
    async_: bool = True,
) -> str:
    """Resolve the database URL the service should use.

    Precedence: ``DB_TYPE=postgresql`` + ``DB_HOST``/``DB_PORT``/``DB_NAME``/
    ``DB_USER``/``DB_PASS`` (user and password are percent-encoded so
    reserved characters cannot corrupt the parsed URL), else
    ``DATABASE_URL``, else ``default_url``. With ``async_=False`` the result
    is the sync-driver form Alembic needs.
    """
    env_map: Mapping[str, str] = os.environ if env is None else env
    if env_map.get("DB_TYPE") == "postgresql":
        host = env_map.get("DB_HOST", "localhost")
        port = env_map.get("DB_PORT", "5432")
        name = env_map.get("DB_NAME", default_db_name)
        # Userinfo percent-encoded (safe=""): a reserved char in a credential
        # would silently corrupt the host/name the driver dials.
        user = quote(env_map.get("DB_USER", "aitbc"), safe="")
        password = quote(env_map.get("DB_PASS", ""), safe="")
        driver = "postgresql+asyncpg" if async_ else "postgresql+psycopg2"
        return f"{driver}://{user}:{password}@{host}:{port}/{name}"
    url = env_map.get("DATABASE_URL", default_url)
    return url if async_ else to_sync_url(url)


def assert_same_target(app_url: str, migrator_url: str) -> None:
    """Fail closed when the app and its migrator resolve to different targets.

    Raises ``RuntimeError`` naming both targets in redacted form — the error
    text must never carry credentials.
    """
    if to_sync_url(app_url) == to_sync_url(migrator_url):
        return
    raise RuntimeError(
        "database target mismatch: the app and the migrator resolve to different databases — "
        f"app reads {redacted_url(app_url)}, migrator targets {redacted_url(migrator_url)}. "
        "Refusing to start; align DB_TYPE/DB_*/DATABASE_URL."
    )
