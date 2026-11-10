"""Merge-regression pin: ``expire_on_commit=False`` convergence (#1585)
protecting the #1411-class post-commit read.

Before the convergence commit the fleet's session helpers diverged — some
built sessions with SQLAlchemy's ``expire_on_commit=True`` default, so an
ORM attribute read *after* ``commit()`` triggered a lazy refresh that
raised ``MissingGreenlet``/``DetachedInstanceError`` on the async paths
(#1411, residual-fixed in 85f4ea95e for trading). The merged state pins
``expire_on_commit=False`` as the default everywhere and proves the
post-commit attribute read — the exact pattern that 500'd — now returns
the in-memory value with no refresh and no IO.

Coder: C
"""

from __future__ import annotations

import pytest
from sqlalchemy import Integer, String, create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from aitbc.database.pooling import (
    create_async_pooled_sessionmaker,
    create_pooled_sessionmaker,
)


class _Base(DeclarativeBase):
    pass


class _ExpirePinRow(_Base):
    __tablename__ = "expire_on_commit_pin_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))


def _engine():
    engine = create_engine("sqlite:///:memory:")
    _Base.metadata.create_all(engine)
    return engine


class TestSessionmakerDefaults:
    """Every pooled factory must default expire_on_commit to False."""

    def test_create_pooled_sessionmaker_defaults_false(self):
        sm = create_pooled_sessionmaker(_engine())
        assert sm.kw["expire_on_commit"] is False

    def test_create_async_pooled_sessionmaker_defaults_false(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        sm = create_async_pooled_sessionmaker(engine)
        assert sm.kw["expire_on_commit"] is False

    def test_plain_sessionmaker_still_expire_true_by_default(self):
        """Contrast pin: the SQLAlchemy default IS expire-on-commit — the
        fleet helpers exist precisely to override it. If this ever flips,
        the convergence pins above are meaningless."""
        sm = sessionmaker(bind=_engine())
        assert sm.kw.get("expire_on_commit", True) is True


class TestPostCommitRead:
    """The #1411-class read: attribute access after commit() must not
    trigger a refresh/IO under the merged session configuration."""

    def test_attribute_read_after_commit_returns_value(self):
        engine = _engine()
        sm = create_pooled_sessionmaker(engine)
        with sm() as session:
            row = _ExpirePinRow(name="post-commit-value")
            session.add(row)
            session.commit()
            # expire_on_commit=False: the attribute is still populated
            # in-memory — this is the read match_trade/get_chain_health
            # perform when building their response dicts.
            assert row.name == "post-commit-value"
            assert row.id is not None

    def test_attribute_read_after_commit_with_explicit_session(self):
        """Same guarantee for a hand-built Session(engine, expire_on_commit=False)
        — the shape coordinator-api storage/db.py uses for get_session."""
        engine = _engine()
        with Session(engine, expire_on_commit=False) as session:
            row = _ExpirePinRow(name="explicit-session")
            session.add(row)
            session.commit()
            assert session.expire_on_commit is False
            assert row.name == "explicit-session"

    @pytest.mark.asyncio
    async def test_async_session_post_commit_read(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(_Base.metadata.create_all)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        async with sm() as session:
            row = _ExpirePinRow(name="async-post-commit")
            session.add(row)
            await session.commit()
            # Under expire_on_commit=True this read would raise
            # MissingGreenlet on the async path — the #1411 failure mode.
            assert row.name == "async-post-commit"

    def test_coordinator_storage_sessions_use_no_expire(self):
        """Pin the consumer side: coordinator-api's session_scope/get_session
        and async_session_scope/get_async_session all build with
        expire_on_commit=False (storage/db.py)."""
        import inspect

        from coordinator_api.storage import db as coord_db

        for fn in (coord_db.session_scope, coord_db.get_session, coord_db.async_session_scope, coord_db.get_async_session):
            src = inspect.getsource(fn)
            assert "expire_on_commit=False" in src, f"{fn.__name__} lost its expire_on_commit=False pin"
