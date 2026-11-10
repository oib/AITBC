"""Property-based tests for pure bound/clamp helpers landed in recent waves.

Three targets, all small pure (or sqlite-local) functions:

* ``aitbc_chain.rpc.blocks._clamp_block_range`` — the ``blocks_range_max_span``
  window clamp used by ``get_blocks_range`` (public /rpc/blocks-range input).
* ``blockchain-explorer`` ``validation.clamp_page_limit`` /
  ``check_page_offset`` / ``clamp_analytics_days`` — the PI-EX-001 (#1176)
  pagination bounds every explorer endpoint funnels through. The module is
  loaded by path: the explorer is a flat-layout app with no ``src/`` on
  ``pythonpath``.
* ``bridge_monitor.storage._apply_pragmas`` / ``_connect_db`` — the shared
  WAL + busy_timeout connect path for ``bridge_deposits.db`` (#1559).

hypothesis is already a dev dependency (pyproject.toml).
"""

import importlib.util
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi import HTTPException
from hypothesis import given, settings
from hypothesis import strategies as st

from aitbc_chain.rpc.blocks import _clamp_block_range
from bridge_monitor import storage as bridge_storage

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXPLORER_VALIDATION = _REPO_ROOT / "apps" / "blockchain-explorer" / "validation.py"


def _load_explorer_validation():
    """Import the flat-layout explorer's validation.py without sys.path edits."""
    spec = importlib.util.spec_from_file_location("explorer_validation", _EXPLORER_VALIDATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclasses/annotations inside the module that
    # look themselves up via sys.modules resolve correctly.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


explorer_validation = _load_explorer_validation()


class TestClampBlockRange:
    """_clamp_block_range bounds the served window without moving the floor."""

    _height = st.integers(min_value=-(2**40), max_value=2**40)
    _span = st.integers(min_value=-(2**20), max_value=2**20)

    @given(start=_height, end=_height, max_span=_span)
    @settings(max_examples=300, deadline=None)
    def test_none_iff_inverted(self, start, end, max_span):
        result = _clamp_block_range(start, end, max_span)
        if end < start:
            assert result is None
        else:
            assert result is not None
            s, e = result
            assert s == start
            assert start <= e <= end

    @given(start=_height, end=_height, max_span=_span)
    @settings(max_examples=300, deadline=None)
    def test_width_within_span_budget(self, start, end, max_span):
        result = _clamp_block_range(start, end, max_span)
        if result is None:
            return
        s, e = result
        span = max(1, max_span)
        assert 1 <= e - s + 1 <= span
        # The clamp only ever shrinks the window from the top.
        assert e == min(end, start + span - 1)

    @given(start=_height, end=_height, max_span=_span)
    @settings(max_examples=200, deadline=None)
    def test_idempotent(self, start, end, max_span):
        once = _clamp_block_range(start, end, max_span)
        if once is None:
            assert _clamp_block_range(start, end, max_span) is None
            return
        twice = _clamp_block_range(*once, max_span)
        assert twice == once

    @given(start=_height, width=st.integers(min_value=0, max_value=2**30), max_span=_span)
    @settings(max_examples=200, deadline=None)
    def test_requested_width_preserved_when_within_budget(self, start, width, max_span):
        end = start + width
        result = _clamp_block_range(start, end, max_span)
        assert result is not None
        s, e = result
        span = max(1, max_span)
        expected_width = min(width + 1, span)
        assert e - s + 1 == expected_width

    @given(max_span=st.integers(min_value=-(2**20), max_value=0))
    @settings(max_examples=50, deadline=None)
    def test_nonpositive_span_still_serves_one_block(self, max_span):
        # max(1, max_span): a misconfigured 0/negative span must not invert
        # or empty every range — it degrades to a single-height window.
        assert _clamp_block_range(5, 100, max_span) == (5, 5)
        assert _clamp_block_range(5, 5, max_span) == (5, 5)


class TestExplorerPaginationClamps:
    """PI-EX-001 clamps: every client limit/offset/days stays in range."""

    _int = st.integers(min_value=-(2**62), max_value=2**62)

    @given(limit=_int)
    @settings(max_examples=200, deadline=None)
    def test_clamp_page_limit_in_range_and_monotone(self, limit):
        v = explorer_validation.clamp_page_limit(limit)
        assert 1 <= v <= explorer_validation.MAX_PAGE_LIMIT
        # Monotone non-decreasing in the input.
        assert explorer_validation.clamp_page_limit(limit + 1) >= v
        # Idempotent: a clamped value is a fixed point.
        assert explorer_validation.clamp_page_limit(v) == v

    @given(limit=_int)
    @settings(max_examples=200, deadline=None)
    def test_clamp_page_limit_exact_inside_window(self, limit):
        if 1 <= limit <= explorer_validation.MAX_PAGE_LIMIT:
            assert explorer_validation.clamp_page_limit(limit) == limit

    @given(offset=_int)
    @settings(max_examples=200, deadline=None)
    def test_check_page_offset_accepts_iff_in_window(self, offset):
        if 0 <= offset <= explorer_validation.MAX_PAGE_OFFSET:
            assert explorer_validation.check_page_offset(offset) == offset
        else:
            with pytest.raises(HTTPException) as exc_info:
                explorer_validation.check_page_offset(offset)
            assert exc_info.value.status_code == 400

    @given(days=_int)
    @settings(max_examples=200, deadline=None)
    def test_clamp_analytics_days_bounded_and_fixed_point(self, days):
        v = explorer_validation.clamp_analytics_days(days)
        assert 1 <= v <= explorer_validation.MAX_ANALYTICS_DAYS
        assert explorer_validation.clamp_analytics_days(v) == v


class TestBridgeDepositsPragmas:
    """_apply_pragmas forces WAL + NORMAL sync + 30s busy_timeout (#1559).

    journal_mode is persistent per database file while busy_timeout and
    synchronous are per-connection, so the interesting inputs are the
    *pre-existing* pragma state of the file/connection — hypothesis varies
    exactly that.
    """

    _pre_journal = st.sampled_from(["delete", "truncate", "persist", "wal", "memory"])
    _pre_sync = st.integers(min_value=0, max_value=3)
    _pre_busy = st.integers(min_value=0, max_value=120_000)

    def _seed_db(self, path: Path, journal: str, sync: int, busy: int) -> None:
        conn = sqlite3.connect(path)
        try:
            conn.execute(f"PRAGMA journal_mode={journal}")
            conn.execute(f"PRAGMA synchronous={sync}")
            conn.execute(f"PRAGMA busy_timeout={busy}")
            conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY)")
            conn.commit()
        finally:
            conn.close()

    @given(journal=_pre_journal, sync=_pre_sync, busy=_pre_busy)
    @settings(max_examples=60, deadline=None)
    def test_apply_pragmas_normalizes_any_prior_state(self, journal, sync, busy):
        # tempfile per example: function-scoped fixtures are not reset
        # between @given inputs (hypothesis health check).
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "bridge_deposits.db"
            self._seed_db(db, journal, sync, busy)

            conn = sqlite3.connect(db, timeout=30)
            try:
                bridge_storage._apply_pragmas(conn)
                assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
                assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
                assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
            finally:
                conn.close()

    @given(journal=_pre_journal, sync=_pre_sync, busy=_pre_busy)
    @settings(max_examples=40, deadline=None)
    def test_connect_db_returns_pragmad_connection(self, journal, sync, busy):
        original_db_path = bridge_storage.DB_PATH
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "bridge_deposits.db"
            self._seed_db(db, journal, sync, busy)
            # monkeypatch is function-scoped and unsafe under @given; swap the
            # module global by hand and restore it.
            bridge_storage.DB_PATH = str(db)
            try:
                conn = bridge_storage._connect_db()
            finally:
                bridge_storage.DB_PATH = original_db_path
            try:
                assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
                assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1
                assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
            finally:
                conn.close()

    def test_apply_pragmas_idempotent_on_fresh_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "fresh.db"
            conn = sqlite3.connect(db)
            try:
                bridge_storage._apply_pragmas(conn)
                bridge_storage._apply_pragmas(conn)
                assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
                assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
            finally:
                conn.close()
