"""Tests for scripts/monitoring/env-watch-textfile.py.

The exporter runs as root under systemd against /etc/aitbc, so tests drive
it as a subprocess with AITBC_ENV_WATCH and AITBC_TEXTFILE_DIR pointed at
tmp dirs. Assertions cover OR-across-files presence, per-file scrape
success, the names-only guarantee (values must never appear in output),
and the failure-file path for an empty spec.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "monitoring" / "env-watch-textfile.py"


def run_exporter(tmp_path: Path, spec: str) -> tuple[int, str]:
    textfile_dir = tmp_path / "textfile"
    textfile_dir.mkdir(exist_ok=True)
    env = dict(os.environ, AITBC_ENV_WATCH=spec, AITBC_TEXTFILE_DIR=str(textfile_dir))
    result = subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True)
    out = textfile_dir / "aitbc_env_watch.prom"
    return result.returncode, out.read_text() if out.exists() else ""


def test_present_in_base_file(tmp_path):
    env_file = tmp_path / "svc.env"
    env_file.write_text("FOO=1\nBAR=2\n")
    rc, prom = run_exporter(tmp_path, f"mysvc=BAR:{env_file}")
    assert rc == 0
    assert 'aitbc_env_var_present{service="mysvc",var="BAR"} 1' in prom
    assert 'aitbc_env_watch_scrape_success{file="svc.env"} 1' in prom
    assert "aitbc_env_watch_timestamp_seconds" in prom


def test_present_in_any_file_or_semantics(tmp_path):
    """systemd EnvironmentFile= stacking: the var in ANY listed file counts."""
    base = tmp_path / "base.env"
    base.write_text("UNRELATED=1\n")
    override = tmp_path / "override.env"
    override.write_text("RECEIPT_SIGNING_KEY_HEX=deadbeef\n")
    spec = f"aitbc-coordinator-api=RECEIPT_SIGNING_KEY_HEX:{base},{override}"
    rc, prom = run_exporter(tmp_path, spec)
    assert rc == 0
    assert 'aitbc_env_var_present{service="aitbc-coordinator-api",var="RECEIPT_SIGNING_KEY_HEX"} 1' in prom


def test_absent_from_all_files(tmp_path):
    base = tmp_path / "base.env"
    base.write_text("OTHER=1\nRECEIPT_SIGNING_KEY_HEX_OLD=still-not-it\n")
    override = tmp_path / "override.env"
    override.write_text("# comment only\n")
    spec = f"aitbc-coordinator-api=RECEIPT_SIGNING_KEY_HEX:{base},{override}"
    rc, prom = run_exporter(tmp_path, spec)
    assert rc == 0
    assert 'aitbc_env_var_present{service="aitbc-coordinator-api",var="RECEIPT_SIGNING_KEY_HEX"} 0' in prom


def test_values_never_leak(tmp_path):
    env_file = tmp_path / "svc.env"
    env_file.write_text("SECRET_KEY=s3cr3t-value-that-must-not-leak\n")
    rc, prom = run_exporter(tmp_path, f"mysvc=SECRET_KEY:{env_file}")
    assert rc == 0
    assert "s3cr3t-value-that-must-not-leak" not in prom


def test_unreadable_file_marks_scrape_failure(tmp_path):
    missing = tmp_path / "missing.env"
    rc, prom = run_exporter(tmp_path, f"mysvc=VAR:{missing}")
    assert rc == 0
    assert 'aitbc_env_var_present{service="mysvc",var="VAR"} 0' in prom
    assert 'aitbc_env_watch_scrape_success{file="missing.env"} 0' in prom


def test_empty_spec_writes_failure_file(tmp_path):
    rc, prom = run_exporter(tmp_path, "")
    assert rc == 0
    assert 'aitbc_env_watch_scrape_success{file="exporter"} 0' in prom
    assert "aitbc_env_watch_timestamp_seconds" in prom


def test_malformed_tokens_are_skipped_not_fatal(tmp_path):
    env_file = tmp_path / "svc.env"
    env_file.write_text("OK=1\n")
    rc, prom = run_exporter(tmp_path, f"garbage-token no-colon mysvc=OK:{env_file}")
    assert rc == 0
    assert 'aitbc_env_var_present{service="mysvc",var="OK"} 1' in prom
