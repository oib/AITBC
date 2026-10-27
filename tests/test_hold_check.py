"""Tests for scripts/ops/hold-check.sh against a synthetic holds file."""

import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/ops/hold-check.sh"

HOLDS = """# holds

## Binding now

| hold | scope | until | source |
|---|---|---|---|
| **HUB1 HOLD** | no restart, pull or deploy on hub1 (node, rpc, coordinator-api) | drill ends | #601 |
| Coin request | must not be executed | expiry | operator |

## Windows

| what | when |
|---|---|
| Drill (#392) | today 11:00 CET |
"""


def run(tmp_path: Path, *args: str, holds: str = HOLDS) -> subprocess.CompletedProcess:
    f = tmp_path / "HOLDS.md"
    f.write_text(holds)
    return subprocess.run(
        ["sh", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env={"HOLDS_FILE": str(f), "PATH": "/usr/bin:/bin"},
    )


def test_active_hold_blocks(tmp_path):
    r = run(tmp_path, "hub1")
    assert r.returncode == 1
    assert "HOLD ACTIVE" in r.stderr


def test_other_host_passes(tmp_path):
    r = run(tmp_path, "node2")
    assert r.returncode == 0


def test_hub_does_not_match_hub1(tmp_path):
    # "hub" must not match the "hub1" hold row
    r = run(tmp_path, "hub")
    assert r.returncode == 0


def test_missing_file_fails_closed(tmp_path):
    r = subprocess.run(
        ["sh", str(SCRIPT), "hub1", str(tmp_path / "nope.md")],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 2


def test_non_restart_hold_does_not_block_restart_gate(tmp_path):
    holds = HOLDS.replace("no restart, pull or deploy on hub1", "no env edits on hub1")
    r = run(tmp_path, "hub1", holds=holds)
    assert r.returncode == 0


def test_script_is_executable():
    assert SCRIPT.stat().st_mode & stat.S_IXUSR
