"""V-3 side-table root shadow — fixture tests (branch-only, flag-gated feature).

Pins the shadow hook contract from docs/design/v3-side-table-root-shadow.md:
the committed fingerprint is deterministic over logical table content only
(order-independent, canonicalized), the feature flag defaults off and short-
circuits before any query, and a failing shadow computation can never raise
into the seal path.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aitbc_chain.metrics import metrics_registry
from aitbc_chain.state.side_root_shadow import (
    COMMITTED_TABLES,
    committed_fingerprint,
    on_block_sealed,
    record_shadow,
    table_digest,
)

_TABLES: dict[str, str] = {
    "account": "CREATE TABLE account (id INTEGER PRIMARY KEY, chain_id TEXT, address TEXT, balance INTEGER, created_at TEXT)",
    "bond": "CREATE TABLE bond (id INTEGER PRIMARY KEY, chain_id TEXT, bond_id TEXT, amount INTEGER, updated_at TEXT)",
    "chain_parameter": "CREATE TABLE chain_parameter (id INTEGER PRIMARY KEY, chain_id TEXT, name TEXT, value TEXT)",
    "chain_parameter_history": "CREATE TABLE chain_parameter_history (id INTEGER PRIMARY KEY, chain_id TEXT, name TEXT, value TEXT)",
    "edge_node_registration": "CREATE TABLE edge_node_registration (id INTEGER PRIMARY KEY, chain_id TEXT, node_id TEXT, registered_at TEXT)",
    "gpu_allocation": "CREATE TABLE gpu_allocation (id INTEGER PRIMARY KEY, chain_id TEXT, allocation_id TEXT, gpu_id TEXT, units INTEGER, allocated_at TEXT)",
    "gpu_registration": "CREATE TABLE gpu_registration (id INTEGER PRIMARY KEY, chain_id TEXT, gpu_id TEXT, owner TEXT, registered_at TEXT)",
    "ipfs_subscription": "CREATE TABLE ipfs_subscription (id INTEGER PRIMARY KEY, chain_id TEXT, sub_id TEXT, plan TEXT)",
    "liquidity_distribution": "CREATE TABLE liquidity_distribution (id INTEGER PRIMARY KEY, chain_id TEXT, dist_id TEXT, amount INTEGER)",
    "liquidity_pool": "CREATE TABLE liquidity_pool (id INTEGER PRIMARY KEY, chain_id TEXT, pool_id TEXT, reserve INTEGER)",
    "liquidity_stake": "CREATE TABLE liquidity_stake (id INTEGER PRIMARY KEY, chain_id TEXT, staker TEXT, amount INTEGER)",
    "receipt": "CREATE TABLE receipt (id INTEGER PRIMARY KEY, chain_id TEXT, receipt_id TEXT, job_id TEXT)",
    "stake": "CREATE TABLE stake (id INTEGER PRIMARY KEY, chain_id TEXT, address TEXT, amount INTEGER, locked_until TEXT, created_at TEXT)",
}


def _mk_db(path: Path, *, seed: int = 0) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    for ddl in _TABLES.values():
        conn.execute(ddl)
    _seed_rows(conn, seed)
    conn.commit()
    return conn


def _seed_rows(conn: sqlite3.Connection, seed: int) -> None:
    conn.execute(
        "INSERT INTO account (id, chain_id, address, balance, created_at) VALUES (1, ?, ?, ?, ?)",
        ("c1", "0xABCDEF" + str(seed), 1000 + seed, "2026-01-01 00:00:00"),
    )
    conn.execute(
        "INSERT INTO stake (id, chain_id, address, amount, locked_until, created_at) VALUES (1, ?, ?, ?, ?, ?)",
        ("c1", "0xDeAdBeEf" + str(seed), 500, "2026-02-01 10:00:00.000000", "x"),
    )
    conn.execute(
        "INSERT INTO gpu_allocation (id, chain_id, allocation_id, gpu_id, units, allocated_at) VALUES (1, ?, ?, ?, ?, ?)",
        ("c1", "alloc-local-" + str(seed), "gpu0", 4, "y"),
    )
    conn.execute(
        "INSERT INTO gpu_registration (id, chain_id, gpu_id, owner, registered_at) VALUES (1, ?, ?, ?, ?)",
        ("c1", "gpu0", "0xOwner" + str(seed), "z"),
    )


def test_committed_set_is_thirteen_tables() -> None:
    assert len(COMMITTED_TABLES) == 13
    assert COMMITTED_TABLES[0] == "account"


def test_deterministic_fingerprint(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path / "a.db")
    first = committed_fingerprint(conn)
    second = committed_fingerprint(conn)
    assert first["fingerprint"] == second["fingerprint"]
    assert set(first["tables"]) == set(COMMITTED_TABLES)


def test_row_reorder_same_fingerprint(tmp_path: Path) -> None:
    a = _mk_db(tmp_path / "a.db")
    b = sqlite3.connect(tmp_path / "b.db")
    for ddl in _TABLES.values():
        b.execute(ddl)
    # same logical rows with the same ids, written in a different order
    b.execute(
        "INSERT INTO gpu_registration (id, chain_id, gpu_id, owner, registered_at) VALUES (1, 'c1', 'gpu0', '0xOwner0', 'z')"
    )
    b.execute(
        "INSERT INTO gpu_allocation (id, chain_id, allocation_id, gpu_id, units, allocated_at) VALUES (1, 'c1', 'alloc-local-0', 'gpu0', 4, 'y')"
    )
    b.execute(
        "INSERT INTO stake (id, chain_id, address, amount, locked_until, created_at) VALUES (1, 'c1', '0xDeAdBeEf0', 500, '2026-02-01 10:00:00.000000', 'x')"
    )
    b.execute(
        "INSERT INTO account (id, chain_id, address, balance, created_at) VALUES (1, 'c1', '0xABCDEF0', 1000, '2026-01-01 00:00:00')"
    )
    b.commit()
    assert committed_fingerprint(a)["fingerprint"] == committed_fingerprint(b)["fingerprint"]


def test_changed_row_different_fingerprint(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path / "a.db")
    before = committed_fingerprint(conn)["fingerprint"]
    conn.execute("UPDATE account SET balance = balance + 1")
    conn.commit()
    assert committed_fingerprint(conn)["fingerprint"] != before


def test_canonical_rules_exclude_local_only_differences(tmp_path: Path) -> None:
    a = _mk_db(tmp_path / "a.db")
    b = _mk_db(tmp_path / "b.db")
    # locally-stamped *_at columns differ — must not change the digest
    b.execute("UPDATE account SET created_at = '2999-12-31 23:59:59'")
    b.execute("UPDATE stake SET created_at = '2999-12-31'")
    b.execute("UPDATE gpu_allocation SET allocated_at = 'other'")
    # node-local handle column — must not change the digest
    b.execute("UPDATE gpu_allocation SET allocation_id = 'alloc-local-OTHER'")
    # address case is an encoding artifact — must not change the digest
    b.execute("UPDATE stake SET address = '0xdeadbeef0'")
    # zero-fraction timestamp text normalization
    b.execute("UPDATE stake SET locked_until = '2026-02-01 10:00:00'")
    b.commit()
    assert committed_fingerprint(a)["fingerprint"] == committed_fingerprint(b)["fingerprint"]


def test_nonzero_fraction_timestamp_is_real_divergence(tmp_path: Path) -> None:
    a = _mk_db(tmp_path / "a.db")
    b = _mk_db(tmp_path / "b.db")
    b.execute("UPDATE stake SET locked_until = '2026-02-01 10:00:00.500000'")
    b.commit()
    assert committed_fingerprint(a)["fingerprint"] != committed_fingerprint(b)["fingerprint"]


def test_flag_off_issues_no_query(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aitbc_chain.config import settings

    monkeypatch.setattr(settings, "side_root_shadow_enabled", False)
    _mk_db(tmp_path / "a.db")

    class ExplodingSession:
        def connection(self) -> object:
            raise AssertionError("flag off must not touch the session")

    on_block_sealed(ExplodingSession(), "c1", 1)  # type: ignore[arg-type]


def test_flag_on_writes_shadow_row_and_metrics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aitbc_chain.config import settings

    monkeypatch.setattr(settings, "side_root_shadow_enabled", True)
    conn = _mk_db(tmp_path / "a.db")

    class FakeConn:
        def __init__(self, raw: sqlite3.Connection) -> None:
            self.connection = raw

    class FakeSession:
        def __init__(self, raw: sqlite3.Connection) -> None:
            self._raw = raw

        def connection(self) -> FakeConn:
            return FakeConn(self._raw)

    metrics_registry.reset()
    on_block_sealed(FakeSession(conn), "c1", 10)  # type: ignore[arg-type]
    row = conn.execute("SELECT block_height, fingerprint FROM shadow_side_root WHERE chain_id = 'c1'").fetchone()
    assert row is not None
    assert row[0] == 10
    assert row[1] == committed_fingerprint(conn)["fingerprint"]
    assert metrics_registry._counters["side_root_shadow_blocks_total"] == 1.0
    assert metrics_registry._gauges["side_root_shadow_last_height"] == 10.0


def test_recomputed_same_height_different_fingerprint_flags_divergence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = _mk_db(tmp_path / "a.db")
    first = record_shadow(conn, "c1", 5)
    assert first["recomputed_differed"] is False
    conn.execute("UPDATE account SET balance = balance + 1")
    conn.commit()
    second = record_shadow(conn, "c1", 5)
    assert second["recomputed_differed"] is True


def test_failing_shadow_never_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from aitbc_chain.config import settings

    monkeypatch.setattr(settings, "side_root_shadow_enabled", True)

    class BrokenSession:
        def connection(self) -> object:
            raise RuntimeError("db gone")

    metrics_registry.reset()
    on_block_sealed(BrokenSession(), "c1", 1)  # type: ignore[arg-type] — must not raise
    assert metrics_registry._counters.get("side_root_shadow_errors_total") == 1.0


def test_table_digest_absent_table(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "empty.db")
    assert table_digest(conn, "account") == {"status": "absent"}


class _FakeSession:
    """Minimal stand-in for the SQLModel session the hook unwraps:
    ``session.connection().connection`` must be a DBAPI conn."""

    def __init__(self, raw: sqlite3.Connection) -> None:
        self._raw = raw

    class _Conn:
        def __init__(self, raw: sqlite3.Connection) -> None:
            self.connection = raw

    def connection(self) -> _FakeSession._Conn:
        return _FakeSession._Conn(self._raw)


def test_interval_and_retention_settings_defaults() -> None:
    from aitbc_chain.config import settings

    assert settings.side_root_shadow_interval == 1  # every block — today's behaviour
    assert settings.side_root_shadow_retention == 10_000


def test_interval_skip_issues_no_query(monkeypatch: pytest.MonkeyPatch) -> None:
    from aitbc_chain.config import settings

    monkeypatch.setattr(settings, "side_root_shadow_enabled", True)
    monkeypatch.setattr(settings, "side_root_shadow_interval", 10)

    class ExplodingSession:
        def connection(self) -> object:
            raise AssertionError("a skipped height must not touch the session")

    on_block_sealed(ExplodingSession(), "c1", 7)  # type: ignore[arg-type] — 7 % 10, skipped


def test_interval_matching_height_writes_shadow_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aitbc_chain.config import settings

    monkeypatch.setattr(settings, "side_root_shadow_enabled", True)
    monkeypatch.setattr(settings, "side_root_shadow_interval", 10)
    conn = _mk_db(tmp_path / "a.db")
    metrics_registry.reset()
    on_block_sealed(_FakeSession(conn), "c1", 20)  # type: ignore[arg-type] — 20 % 10 == 0
    rows = conn.execute("SELECT block_height FROM shadow_side_root WHERE chain_id = 'c1'").fetchall()
    assert [r[0] for r in rows] == [20]
    assert metrics_registry._counters["side_root_shadow_blocks_total"] == 1.0


def test_retention_keeps_only_newest_n_rows(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path / "a.db")
    for height in range(1, 8):
        record_shadow(conn, "c1", height, retention=4)
    rows = conn.execute("SELECT block_height FROM shadow_side_root WHERE chain_id = 'c1' ORDER BY block_height").fetchall()
    assert [r[0] for r in rows] == [4, 5, 6, 7]


def test_retention_disabled_keeps_all_rows(tmp_path: Path) -> None:
    conn = _mk_db(tmp_path / "a.db")
    for height in range(1, 8):
        record_shadow(conn, "c1", height, retention=0)
    count = conn.execute("SELECT COUNT(*) FROM shadow_side_root WHERE chain_id = 'c1'").fetchone()[0]
    assert count == 7
