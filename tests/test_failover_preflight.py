"""Tests for scripts/ops/failover-preflight.sh with stubbed ssh/curl.

The ssh stub dispatches on the remote command string so each check gets
its own canned answer; values come from env knobs per test.
"""

import os
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/ops/failover-preflight.sh"

SSH_STUB = """#!/bin/sh
eval "cmd=\\${$#}"   # remote command is the last argument
case "$cmd" in
  *"max(height)"*) echo "${STUB_HEAD:-5666|0xabcdef123456}" ;;
  *"--EVENTS--"*)
    echo "NODE_TS=${STUB_TS:-Sun 2026-10-25 21:30:23 CET}"
    echo "FAILED=${STUB_FAILED:-0}"
    echo "--EVENTS--"
    echo "low 0"
    echo "high 0"
    echo "max 0"
    echo "oom 0"
    echo "oom_kill ${STUB_OOM:-0}"
    echo "oom_group_kill 0"
    echo "--MEM--"
    echo "${STUB_CUR:-2800000000}"
    echo "${STUB_MAX:-3221225472}"
    echo "--ACT--"
    echo "${STUB_ACT:-8}"
    echo "${STUB_KEE:-2}" ;;
  *swapon*) echo "${STUB_SWAP:-1000000}" ;;
  *sha256sum*) echo "${STUB_SHA:-deadbeef}" ;;
  *bridge_deposits*) echo "${STUB_BD:-139264}" ;;
  *) echo unknown ;;
esac
"""


def _run(tmp_path, env_over=None, args=(), curl_code="200"):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("ssh", SSH_STUB), ("curl", f"#!/bin/sh\nprintf '%s' '{curl_code}'\n")):
        f = bin_dir / name
        f.write_text(body)
        f.chmod(f.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
    env.update(env_over or {})
    return subprocess.run(["sh", str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=90)


def test_all_green(tmp_path):
    res = _run(tmp_path, args=("--expected-sha256", "deadbeef"))
    assert res.returncode == 0, res.stdout + res.stderr
    assert "PREFLIGHT PASS" in res.stdout


def test_fail_on_failed_unit(tmp_path):
    res = _run(tmp_path, {"STUB_FAILED": "1"})
    assert res.returncode == 1
    assert "hub1-failed-units" in res.stdout


def test_fail_on_swap_flag(tmp_path):
    res = _run(tmp_path, {"STUB_SWAP": "500000000"})
    assert res.returncode == 1
    assert "ns3-swap" in res.stdout


def test_fail_on_oom(tmp_path):
    res = _run(tmp_path, {"STUB_OOM": "1"})
    assert res.returncode == 1


def test_fail_on_wrong_sha(tmp_path):
    res = _run(tmp_path, args=("--expected-sha256", "0000ffff"))
    assert res.returncode == 1
    assert "hub-nginx-sha" in res.stdout


def test_no_mutating_commands_in_script():
    text = SCRIPT.read_text()
    for bad in (
        "systemctl start ",
        "systemctl stop ",
        "systemctl restart",
        "systemctl enable",
        "systemctl disable",
        "rm -f",
        "rm /",
        "tee /",
        "daemon-reload",
    ):
        assert bad not in text, f"mutating token {bad!r} found in script"
