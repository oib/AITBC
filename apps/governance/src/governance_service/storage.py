"""
Database session management for Governance service
"""

import os
import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from aitbc.aitbc_logging import get_logger
from aitbc.constants import DATA_DIR

# Importing the models is what puts them on `governance_metadata`; create_all builds nothing
# otherwise. This service's tables live there rather than on the global SQLModel registry --
# see domain/base.py (V23-72).
from .domain import governance as _models  # noqa: F401
from .domain.base import governance_metadata

logger = get_logger(__name__)


# libpq sslmode values, in the order libpq defines them. Anything else is a
# configuration error rather than something to guess at.
_SSLMODES_WITHOUT_VERIFICATION = ("allow", "prefer", "require")
_SSLMODES_WITH_VERIFICATION = ("verify-ca", "verify-full")


def _resolve_sslmode() -> str:
    """Return the configured sslmode, defaulting to asyncpg's own default."""
    for var in ("DB_SSLMODE", "PGSSLMODE"):
        value = os.getenv(var)
        if value:
            return value.strip().lower().replace("_", "-")
    return "prefer"


def _build_ssl_arg() -> ssl.SSLContext | bool:
    """Resolve the `ssl` connect argument handed to asyncpg.

    `DB_SSLMODE` wins, then the libpq-standard `PGSSLMODE`, else `prefer` --
    asyncpg's own default, so a host that configures neither keeps the behaviour
    it has today.

    The reason this builds an `SSLContext` instead of just forwarding the mode
    *string* asyncpg would happily parse: for every mode above `disable`, asyncpg
    resolves `~/.postgresql/root.crl` and `~/.postgresql/postgresql.key` itself
    (`connect_utils._dot_postgresql_path`), and it guards those lookups against
    FileNotFoundError but not PermissionError. Units run under `ProtectHome=yes`,
    so wherever the service user's home sits under /home that lookup raises EACCES
    and the connection dies before it is ever attempted -- an outage whose only
    visible symptom is that the database is unreachable while the database is
    perfectly healthy. The workaround is `PGSSLMODE=disable` in the environment,
    which is a poor place for it: it is invisible to the repo, it silently costs
    the encryption, and any redeploy that loses the line re-arms the fault.
    Supplying the context here means the home directory is never consulted,
    whatever HOME happens to be, and the setting travels with the code.

    One deliberate behaviour change comes with that: asyncpg treats `prefer` as
    advisory and falls back to an unencrypted connection when the server refuses
    TLS. A caller-supplied context gets no such fallback, so `prefer` against a
    server with `ssl = off` now fails loudly instead of quietly downgrading. A
    deployment that really does want plaintext has to say `DB_SSLMODE=disable`
    and mean it, which is the right way round for a security default.
    """
    mode = _resolve_sslmode()
    if mode == "disable":
        return False
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if mode in _SSLMODES_WITHOUT_VERIFICATION:
        # Encrypt, but do not authenticate the server -- libpq's semantics for
        # these three, and what asyncpg does with them. check_hostname must go
        # first: CERT_NONE while it is still True raises ValueError.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    elif mode in _SSLMODES_WITH_VERIFICATION:
        context.check_hostname = mode == "verify-full"
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_default_certs(ssl.Purpose.SERVER_AUTH)
    else:
        supported = ("disable", *_SSLMODES_WITHOUT_VERIFICATION, *_SSLMODES_WITH_VERIFICATION)
        raise ValueError(f"Unsupported sslmode {mode!r}; expected one of: {', '.join(supported)}")
    return context


def _build_database_url() -> str:
    """Build database URL from environment variables at call time.

    TLS is not expressed here: an `SSLContext` cannot travel in a URL, so it is
    passed through `connect_args` in `_create_engine` instead. See `_build_ssl_arg`.
    """
    db_type = os.getenv("DB_TYPE", "sqlite")
    if db_type == "postgresql":
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        name = os.getenv("DB_NAME", "aitbc_governance")
        user = os.getenv("DB_USER", "aitbc")
        password = os.getenv("DB_PASS", "")
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"
    return os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DATA_DIR}/data/governance_service.db")


def _create_engine() -> AsyncEngine:
    """Create async engine based on current environment."""
    db_type = os.getenv("DB_TYPE", "sqlite")
    url = _build_database_url()
    kwargs: dict[str, int | bool] = {
        "echo": False,
        "pool_pre_ping": True,
    }
    if db_type == "postgresql":
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
        return create_async_engine(url, connect_args={"ssl": _build_ssl_arg()}, **kwargs)
    return create_async_engine(url, **kwargs)


engine = _create_engine()


async def init_db() -> None:
    """Initialize database tables.

    For PostgreSQL, Alembic manages schema migrations so we skip create_all.
    For SQLite (dev/test), create tables automatically.
    """
    if os.getenv("DB_TYPE", "sqlite") != "postgresql":
        async with engine.begin() as conn:
            await conn.run_sync(governance_metadata.create_all)

    logger.info("Governance service database initialized")


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Get database session"""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
