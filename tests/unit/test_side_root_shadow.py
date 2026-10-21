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
    COMMITTED_TABLES_V15,
    committed_fingerprint,
    committed_tables_for_version,
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


def test_v15_set_is_committed_set_minus_edge_registration() -> None:
    """EDGE-REG-CONSENSUS-1 (operator card B, 21 Oct): the only delta at v15 is
    edge_node_registration leaving the set — everything else stays, ordering
    is preserved, and the v14 set is untouched."""
    assert len(COMMITTED_TABLES_V15) == 12
    assert "edge_node_registration" not in COMMITTED_TABLES_V15
    assert COMMITTED_TABLES_V15 == tuple(t for t in COMMITTED_TABLES if t != "edge_node_registration")
    assert len(COMMITTED_TABLES) == 13  # the v14 set is frozen


def test_committed_tables_for_version_selects_set() -> None:
    assert committed_tables_for_version(None) == COMMITTED_TABLES
    assert committed_tables_for_version(14) == COMMITTED_TABLES
    assert committed_tables_for_version(13) == COMMITTED_TABLES
    assert committed_tables_for_version(15) == COMMITTED_TABLES_V15
    assert committed_tables_for_version(16) == COMMITTED_TABLES_V15


def test_v15_block_version_gate_setting_default_unarmed() -> None:
    """The committed-set change only matters where the version boundary
    exists: state_transition_v15_height defaults to None so nothing switches
    until the operator pins a fleet activation height."""
    from aitbc_chain.config import settings

    assert settings.state_transition_v15_height is None


def _register_edge_row(conn: sqlite3.Connection, node_id: str) -> None:
    """Reproduce the POST /rpc/edge/register write (gpu_resources.py) — a raw
    insert on exactly one node, outside any apply."""
    conn.execute(
        "INSERT INTO edge_node_registration (id, chain_id, node_id, registered_at) VALUES (1, 'c1', ?, '2026-10-21 12:14:00')",
        (node_id,),
    )
    conn.commit()


def test_edge_register_rpc_write_diverges_v14_but_not_v15(tmp_path: Path) -> None:
    """Two simulated nodes, one local register call — the 21 Oct node2
    incident. At v14 the committed fingerprints diverge (this is the failure
    the aux root caught at block 119); at v15 they stay equal because the
    service-local table is no longer in the set. This test fails without the
    v15 set."""
    node_a = _mk_db(tmp_path / "node_a.db")  # the node that served the RPC
    node_b = _mk_db(tmp_path / "node_b.db")  # a peer that never saw it
    _register_edge_row(node_a, "node2-edge")

    assert committed_fingerprint(node_a, 14)["fingerprint"] != committed_fingerprint(node_b, 14)["fingerprint"]
    assert committed_fingerprint(node_a, 15)["fingerprint"] == committed_fingerprint(node_b, 15)["fingerprint"]
    assert set(committed_fingerprint(node_a, 15)["tables"]) == set(COMMITTED_TABLES_V15)


def test_direct_write_to_still_committed_table_is_detected(tmp_path: Path) -> None:
    """Regression: the shadow compare still catches a non-apply local write to
    a table that remains committed at v15 — the guard that fired on 21 Oct
    keeps working for the remaining 12 tables."""
    node_a = _mk_db(tmp_path / "node_a.db")
    node_b = _mk_db(tmp_path / "node_b.db")
    node_a.execute(
        "INSERT INTO stake (id, chain_id, address, amount, locked_until, created_at)"
        " VALUES (99, 'c1', '0xLocal', 1, '2027-01-01', 'x')"
    )
    node_a.commit()
    assert committed_fingerprint(node_a, 15)["fingerprint"] != committed_fingerprint(node_b, 15)["fingerprint"]
    # and the local same-height recompute flags it on the diverged node
    first = record_shadow(node_a, "c1", 7, block_version=15)
    node_a.execute("UPDATE account SET balance = balance + 1 WHERE id = 1")
    node_a.commit()
    second = record_shadow(node_a, "c1", 7, block_version=15)
    assert first["recomputed_differed"] is False
    assert second["recomputed_differed"] is True


def test_edge_write_no_longer_flags_v15_recompute(tmp_path: Path) -> None:
    """Inverse of the above at v15: a local edge-registration write between
    two same-height shadow records is legitimate divergence now and does not
    flag — while it still flags at v14 (the historical rule)."""
    conn = _mk_db(tmp_path / "a.db")
    record_shadow(conn, "c1", 7, block_version=15)
    _register_edge_row(conn, "edge-x")
    assert record_shadow(conn, "c1", 7, block_version=15)["recomputed_differed"] is False
    assert record_shadow(conn, "c1", 8, block_version=14)["recomputed_differed"] is False
    conn.execute("DELETE FROM edge_node_registration")
    conn.commit()
    assert record_shadow(conn, "c1", 8, block_version=14)["recomputed_differed"] is True


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


_CCT_DDL = (
    "CREATE TABLE cross_chain_transfer (id INTEGER PRIMARY KEY, chain_id TEXT,"
    " transfer_id TEXT, source_chain TEXT, target_chain TEXT, sender TEXT,"
    " recipient TEXT, amount INTEGER, asset TEXT, source_tx_hash TEXT,"
    " status TEXT, target_tx_hash TEXT, created_at TEXT)"
)


def _add_transfer_rows(conn: sqlite3.Connection, rows: int, *, tag: str) -> None:
    conn.execute(_CCT_DDL)
    for i in range(rows):
        conn.execute(
            "INSERT INTO cross_chain_transfer"
            " (id, chain_id, transfer_id, source_chain, target_chain, sender, recipient,"
            "  amount, asset, source_tx_hash, status, created_at)"
            " VALUES (?, 'c1', ?, 'src', 'dst', ?, ?, ?, 'AIT', ?, 'pending', ?)",
            (i + 1, f"tid-{tag}-{i}", f"0xSenDer-{i}", f"0xRecip-{i}", 100 + i, f"0xsrc{i}", f"2026-10-1{i}"),
        )
    conn.commit()


def test_cross_chain_transfer_is_not_in_committed_set() -> None:
    """The v14 aux root covers exactly COMMITTED_TABLES; service-local bridge
    bookkeeping must never be promoted into it without a new version rung."""
    assert "cross_chain_transfer" not in COMMITTED_TABLES


def test_different_cross_chain_transfer_rows_same_fingerprint(tmp_path: Path) -> None:
    """ACT-2 evidence: two databases carrying identical committed-table rows
    but different cross_chain_transfer content must produce the identical
    committed fingerprint (hence the same aux_state_root at >= v14). The fleet
    legitimately holds different per-node lock subsets (rows are born on the
    node that served the lock RPC — see block_deltas.CONSENSUS_SENSITIVE_WATCH),
    so this is the production shape, not a corner case."""
    a = _mk_db(tmp_path / "a.db")  # hub-like: more rows
    b = _mk_db(tmp_path / "b.db")  # follower-like: fewer rows
    _add_transfer_rows(a, 5, tag="a")
    _add_transfer_rows(b, 4, tag="b")
    assert committed_fingerprint(a)["fingerprint"] == committed_fingerprint(b)["fingerprint"]


def test_missing_cross_chain_transfer_table_same_fingerprint(tmp_path: Path) -> None:
    """A host with no cross_chain_transfer table at all (fresh node) still
    fingerprints identically — the digest never selects the table."""
    a = _mk_db(tmp_path / "a.db")
    b = _mk_db(tmp_path / "b.db")
    _add_transfer_rows(a, 5, tag="a")
    # b carries no cross_chain_transfer table at all
    assert committed_fingerprint(a)["fingerprint"] == committed_fingerprint(b)["fingerprint"]


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
