"""Regression tests: /rpc/blocks-range span budget.

The route is public and feeds peer bulk sync; an unbounded start/end used to
serialize the entire chain (plus every transaction envelope) in one response.
The served window is now clamped to ``settings.blocks_range_max_span``.
"""

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from aitbc_chain.config import settings
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Block
from aitbc_chain.rpc import blocks as rpc_blocks
from sqlmodel import Session, create_engine


@pytest.fixture
def isolated_engine(tmp_path, monkeypatch):
    db_path = tmp_path / "test_blocks_range.db"
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    chain_metadata.create_all(engine)

    @contextmanager
    def _session_scope(*args, **kwargs):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(rpc_blocks, "session_scope", _session_scope)
    try:
        yield engine
    finally:
        engine.dispose()


def _insert_blocks(engine, chain_id: str, count: int, start: int = 0) -> None:
    with Session(engine) as session:
        for h in range(start, start + count):
            session.add(
                Block(
                    chain_id=chain_id,
                    height=h,
                    hash=f"0x{h:064x}",
                    parent_hash=f"0x{h - 1:064x}" if h else "0x00",
                    proposer="tester",
                    timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                    tx_count=0,
                )
            )
        session.commit()


def test_blocks_range_clamps_wide_window(isolated_engine, monkeypatch):
    monkeypatch.setattr(settings, "blocks_range_max_span", 5)
    _insert_blocks(isolated_engine, "chain-a", 20)
    result = rpc_blocks.get_blocks_range(Mock(), start=0, end=10**9, include_tx=False, chain_id="chain-a")
    assert result["success"] is True
    assert result["count"] == 5
    assert [b["height"] for b in result["blocks"]] == [0, 1, 2, 3, 4]


def test_blocks_range_inverted_range_is_empty(isolated_engine, monkeypatch):
    monkeypatch.setattr(settings, "blocks_range_max_span", 5)
    _insert_blocks(isolated_engine, "chain-a", 3)
    result = rpc_blocks.get_blocks_range(Mock(), start=10, end=2, include_tx=False, chain_id="chain-a")
    assert result == {"success": True, "blocks": [], "count": 0}


def test_blocks_range_small_window_untouched(isolated_engine, monkeypatch):
    monkeypatch.setattr(settings, "blocks_range_max_span", 5)
    _insert_blocks(isolated_engine, "chain-a", 10)
    result = rpc_blocks.get_blocks_range(Mock(), start=2, end=4, include_tx=False, chain_id="chain-a")
    assert result["count"] == 3
    assert [b["height"] for b in result["blocks"]] == [2, 3, 4]
