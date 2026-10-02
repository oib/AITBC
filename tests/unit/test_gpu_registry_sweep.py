"""Tests for scripts/ops/gpu-registry-sweep.py — the repair step for a database that re-applied
history created before the 2 Oct 2026 GPU cleanup.

The script is stdlib-only and works on bare sqlite tables, so the tests build the two tables
with just the columns it reads.
"""

import importlib.util
import os
import sqlite3
import stat
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "gpu-registry-sweep.py"

CHAIN = "sweep-test"
KEPT = "node0-rtx4060ti"


@pytest.fixture(scope="module")
def sweep_mod():
    spec = importlib.util.spec_from_file_location("gpu_registry_sweep", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["gpu_registry_sweep"] = module
    spec.loader.exec_module(module)
    return module


def _make_db(path: Path, registrations: list[tuple], allocations: list[tuple]) -> Path:
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE gpu_registration (id INTEGER PRIMARY KEY, chain_id TEXT, gpu_id TEXT, status TEXT, registered_by TEXT)"
    )
    db.execute(
        "CREATE TABLE gpu_allocation (id INTEGER PRIMARY KEY, chain_id TEXT, allocation_id TEXT, gpu_id TEXT, status TEXT)"
    )
    db.executemany("INSERT INTO gpu_registration (chain_id, gpu_id, status, registered_by) VALUES (?, ?, ?, ?)", registrations)
    db.executemany("INSERT INTO gpu_allocation (chain_id, allocation_id, gpu_id, status) VALUES (?, ?, ?, ?)", allocations)
    db.commit()
    db.close()
    return path


@pytest.fixture()
def replayed_db(tmp_path):
    """What a replay of pre-cleanup history leaves behind: retired rows next to the kept one."""
    registrations = [
        (CHAIN, KEPT, "active", "0x08aB8011"),
        (CHAIN, "gpu-live-05", "active", "0x08aB8011"),
        (CHAIN, "canary9-gpu-001", "active", "0xF4924759"),
        ("", "test-rtx4060ti", "active", "0x08aB8011"),  # never sealed: empty chain_id
        ("other-chain", "gpu-live-05", "active", "0x08aB8011"),  # same id on another chain
        (CHAIN, "gpu-keep-me", "active", "0x08aB8011"),
    ]
    allocations = [
        (CHAIN, "alloc_keep", KEPT, "active"),
        (CHAIN, "alloc_a", "canary9-gpu-001", "active"),
        (CHAIN, "alloc_b", "canary9-gpu-001", "active"),
    ]
    return _make_db(tmp_path / "chain.db", registrations, allocations)


def _gpu_ids(db_path: Path, table: str = "gpu_registration") -> list[tuple[str, str]]:
    db = sqlite3.connect(db_path)
    try:
        return db.execute(f"SELECT chain_id, gpu_id FROM {table} ORDER BY chain_id, gpu_id").fetchall()  # noqa: S608
    finally:
        db.close()


class TestSweep:
    def test_dry_run_reports_and_changes_nothing(self, sweep_mod, replayed_db, tmp_path):
        before = _gpu_ids(replayed_db)
        result = sweep_mod.sweep(replayed_db, CHAIN, backup_dir=tmp_path / "bk")
        assert {r[0] for r in result["found"]["registrations"]} == {"gpu-live-05", "canary9-gpu-001", "test-rtx4060ti"}
        assert [r[0] for r in result["found"]["allocations"]] == ["alloc_a", "alloc_b"]
        assert _gpu_ids(replayed_db) == before
        assert result["backup"] is None
        assert not (tmp_path / "bk").exists()

    def test_apply_removes_retired_rows_and_keeps_the_rest(self, sweep_mod, replayed_db, tmp_path):
        result = sweep_mod.sweep(replayed_db, CHAIN, apply=True, backup_dir=tmp_path / "bk")
        assert result["removed"] == {"registrations": 3, "allocations": 2}
        assert _gpu_ids(replayed_db) == [
            ("other-chain", "gpu-live-05"),
            (CHAIN, "gpu-keep-me"),
            (CHAIN, KEPT),
        ]
        assert _gpu_ids(replayed_db, "gpu_allocation") == [(CHAIN, KEPT)]

    def test_apply_takes_a_private_backup_of_the_state_before(self, sweep_mod, replayed_db, tmp_path):
        before = _gpu_ids(replayed_db)
        result = sweep_mod.sweep(replayed_db, CHAIN, apply=True, backup_dir=tmp_path / "bk")
        backup = Path(result["backup"])
        assert backup.parent == tmp_path / "bk"
        assert stat.S_IMODE(os.stat(backup).st_mode) == 0o600
        assert _gpu_ids(backup) == before

    def test_second_run_is_a_no_op(self, sweep_mod, replayed_db, tmp_path):
        sweep_mod.sweep(replayed_db, CHAIN, apply=True, backup_dir=tmp_path / "bk")
        after_first = _gpu_ids(replayed_db)
        backups = sorted((tmp_path / "bk").iterdir())
        again = sweep_mod.sweep(replayed_db, CHAIN, apply=True, backup_dir=tmp_path / "bk")
        assert again["found"] == {"registrations": [], "allocations": []}
        assert again["removed"] == {"registrations": 0, "allocations": 0}
        assert again["backup"] is None
        assert _gpu_ids(replayed_db) == after_first
        assert sorted((tmp_path / "bk").iterdir()) == backups

    def test_backup_can_be_skipped_for_a_scratch_database(self, sweep_mod, replayed_db, tmp_path):
        result = sweep_mod.sweep(replayed_db, CHAIN, apply=True, backup_dir=tmp_path / "bk", backup=False)
        assert result["removed"]["registrations"] == 3
        assert result["backup"] is None
        assert not (tmp_path / "bk").exists()

    def test_database_without_the_tables_is_refused(self, sweep_mod, tmp_path):
        path = tmp_path / "empty.db"
        sqlite3.connect(path).close()
        with pytest.raises(RuntimeError, match="no gpu_registration"):
            sweep_mod.sweep(path, CHAIN)

    def test_extra_ids_are_swept_too(self, sweep_mod, replayed_db, tmp_path):
        result = sweep_mod.sweep(
            replayed_db, CHAIN, (*sweep_mod.RETIRED_GPU_IDS, "gpu-keep-me"), apply=True, backup_dir=tmp_path / "bk"
        )
        assert result["removed"]["registrations"] == 4


class TestMain:
    def _run(self, sweep_mod, replayed_db, *flags):
        return sweep_mod.main(["--chain-id", CHAIN, "--db", str(replayed_db), *flags])

    def test_check_exits_3_when_retired_rows_are_present_and_changes_nothing(self, sweep_mod, replayed_db, capsys):
        before = _gpu_ids(replayed_db)
        assert self._run(sweep_mod, replayed_db, "--check") == 3
        assert _gpu_ids(replayed_db) == before
        assert "retired rows" in capsys.readouterr().out

    def test_check_exits_0_on_a_clean_database(self, sweep_mod, replayed_db, tmp_path, capsys):
        assert self._run(sweep_mod, replayed_db, "--apply", "--backup-dir", str(tmp_path / "bk")) == 0
        capsys.readouterr()
        assert self._run(sweep_mod, replayed_db, "--check") == 0
        assert "clean" in capsys.readouterr().out

    def test_plain_run_is_a_dry_run(self, sweep_mod, replayed_db):
        before = _gpu_ids(replayed_db)
        assert self._run(sweep_mod, replayed_db) == 0
        assert _gpu_ids(replayed_db) == before

    def test_apply_prints_the_backup_and_the_counts(self, sweep_mod, replayed_db, tmp_path, capsys):
        assert self._run(sweep_mod, replayed_db, "--apply", "--backup-dir", str(tmp_path / "bk")) == 0
        out = capsys.readouterr().out
        assert "removed 3 registrations and 2 allocations" in out
        assert "backup:" in out

    def test_apply_and_check_conflict(self, sweep_mod, replayed_db):
        with pytest.raises(SystemExit) as exc:
            self._run(sweep_mod, replayed_db, "--apply", "--check")
        assert exc.value.code == 2

    def test_missing_database_is_a_fatal_error(self, sweep_mod, tmp_path, capsys):
        assert sweep_mod.main(["--chain-id", CHAIN, "--db", str(tmp_path / "gone.db")]) == 2
        assert "not found" in capsys.readouterr().err

    def test_chain_id_is_required(self, sweep_mod, replayed_db, monkeypatch):
        monkeypatch.delenv("CHAIN_ID", raising=False)
        with pytest.raises(SystemExit) as exc:
            sweep_mod.main(["--db", str(replayed_db)])
        assert exc.value.code == 2
