"""Tests for scripts/monitoring/backup-textfile.py (MON-2).

The exporter is exercised against a fake backup base dir plus a stub
``systemctl`` on PATH, the same convention as the other textfile tests.
"""

import os
import re
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MONITORING = REPO_ROOT / "scripts" / "monitoring"
sys.path.insert(0, str(MONITORING))

import importlib

exporter = importlib.import_module("backup-textfile")


@pytest.fixture()
def base(tmp_path: Path):
    d = tmp_path / "aitbc-backups"
    gen_old = d / "20261010_010100"
    gen_new = d / "20261013_010357"
    for g, payload in ((gen_old, b"a"), (gen_new, b"xy")):
        g.mkdir(parents=True)
        (g / "f1.gz").write_bytes(payload)
        (g / "f2.gz").write_bytes(payload * 3)
    os.utime(gen_new, (time.time() - 100,) * 2)
    os.utime(gen_old, (time.time() - 200,) * 2)
    return d


def test_scan_reports_newest_generation(base):
    ts, size, count = exporter.scan(base)
    assert ts == int((base / "20261013_010357").stat().st_mtime)
    assert size == 2 + 6  # 'xy' + 'xyxyxy'
    assert count == 2


def test_scan_ignores_foreign_dirs(base):
    (base / "untracked-20260909").mkdir()
    (base / "keep.me").mkdir()
    _, _, count = exporter.scan(base)
    assert count == 2


def test_last_run_success_parses_result(tmp_path, monkeypatch):
    stub = tmp_path / "systemctl"
    stub.write_text('#!/bin/sh\necho "success"\n')
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    assert exporter.last_run_success("aitbc-backup.service") == 1
    stub.write_text('#!/bin/sh\necho "failed"\n')
    assert exporter.last_run_success("aitbc-backup.service") == 0


def test_render_includes_all_metrics(base):
    ts, size, count = exporter.scan(base)
    text = exporter.render(ts, size, count, 1, now=1700000000.0, failed=[])
    for metric in (
        "aitbc_backup_last_generation_timestamp_seconds",
        "aitbc_backup_last_generation_bytes",
        "aitbc_backup_generations_count",
        "aitbc_backup_last_run_success",
        "aitbc_backup_scrape_success",
        "aitbc_backup_exporter_timestamp_seconds",
    ):
        assert metric in text


def test_failed_source_marks_scrape_success():
    text = exporter.render(None, None, None, None, now=1, failed=["backups_dir"])
    assert 'aitbc_backup_scrape_success{source="backups_dir"} 0' in text
    assert 'aitbc_backup_scrape_success{source="unit_result"} 1' in text
    assert "aitbc_backup_last_run_success" not in text.split("gauge")[2]


def test_every_metric_the_rules_use_is_emitted():
    """The rules file and the exporter must name the same aitbc_backup_* /
    aitbc_offsite_pull_* series."""
    rules = (MONITORING / "aitbc_rules.yml").read_text()
    used = set(re.findall(r"\baitbc_backup_[a-z_]+", rules))
    assert used, "the rules no longer read the backup series"
    emitted = set(
        re.findall(
            r"\baitbc_backup_[a-z_]+",
            exporter.render(1, 1, 1, 1, now=1, failed=["x"]),
        )
    )
    assert used <= emitted, f"rules use series the exporter never emits: {used - emitted}"
    # the offsite-pull metric is written by the pull script, not this
    # exporter -- assert the script names it, same discipline.
    script = (REPO_ROOT / "scripts" / "ops" / "offsite-pull-backups.sh").read_text()
    assert "aitbc_offsite_pull_last_success_timestamp_seconds" in script


def test_write_atomic_leaves_no_temp(tmp_path):
    exporter.write_atomic(str(tmp_path), "x\n")
    assert (tmp_path / exporter.OUTPUT_NAME).read_text() == "x\n"
    assert [p.name for p in tmp_path.iterdir()] == [exporter.OUTPUT_NAME]


def test_main_failure_render(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setenv("AITBC_BACKUP_BASE", str(tmp_path / "missing"))
    monkeypatch.setenv("AITBC_TEXTFILE_DIR", str(out))
    stub = tmp_path / "systemctl"
    stub.write_text("#!/bin/sh\nexit 1\n")
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    assert exporter.main() == 1
    text = (out / exporter.OUTPUT_NAME).read_text()
    assert 'aitbc_backup_scrape_success{source="backups_dir"} 0' in text
    assert 'aitbc_backup_scrape_success{source="unit_result"} 0' in text
