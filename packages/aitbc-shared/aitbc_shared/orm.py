"""
Shared ORM Configuration
Provides shared declarative_base and session handling for AITBC applications
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

DEFAULT_DATABASE_URL = "sqlite:///aitbc.db"

# Engines are cached per URL. A single module-level `_engine` meant the first caller won:
# every later call returned that engine regardless of the database_url passed, so a
# consumer asking for a different database silently read and wrote the first one.
_engines: dict[str, object] = {}


def get_engine(database_url: str | None = None):
    """Get or create the engine for ``database_url``.

    Caching is keyed by URL, so asking for a different database gets a different engine.
    """
    url = database_url or DEFAULT_DATABASE_URL
    if url not in _engines:
        _engines[url] = create_engine(url, echo=False)
    return _engines[url]


def dispose_engines() -> None:
    """Dispose every cached engine and clear the cache.

    Mainly for tests, which would otherwise leak a connection pool per database URL.
    """
    for engine in _engines.values():
        engine.dispose()  # type: ignore[attr-defined]
    _engines.clear()


def get_session(database_url: str | None = None) -> Iterator[Session]:
    """Yield a database session. Intended for FastAPI's ``Depends()``.

    This is a bare generator, which FastAPI's dependency system drives correctly but which
    cannot be used as ``with get_session() as s:`` -- that raises AttributeError. Use
    ``session_scope()`` outside FastAPI.
    """
    engine = get_engine(database_url)
    with Session(engine) as session:
        yield session


@contextmanager
def session_scope(database_url: str | None = None) -> Iterator[Session]:
    """Session as a context manager, for use outside FastAPI.

    ``get_session`` is a plain generator and only works through ``Depends()``; this
    package is described as generic utilities, so calling it directly was an easy and
    silent mistake.
    """
    engine = get_engine(database_url)
    with Session(engine) as session:
        yield session


def init_db(database_url: str | None = None):
    """Initialize the database with all shared models"""

    engine = get_engine(database_url)
    SQLModel.metadata.create_all(engine)
