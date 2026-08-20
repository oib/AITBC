"""AITBC database session helpers."""

from contextlib import contextmanager
from typing import Generator


@contextmanager
def get_db_session() -> Generator[dict, None, None]:
    """Yield a stub database session."""
    yield {}


def init_db() -> None:
    """Stub database initialisation."""
    pass


__all__ = ["get_db_session", "init_db"]
