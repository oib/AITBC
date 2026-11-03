"""Pin for OPS-BRIDGE-TRANSPLANT-IGNORES-CHAINS-1 (#909): the relay step used
to run with default chains regardless of --source-chain/--target-chain, and
leave a fixed /tmp/bridge-relay-trigger.py on the relayer."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "bridge-transplant.sh"

pytestmark = pytest.mark.skipif(not SCRIPT.exists(), reason="script missing")

SSH_STUB = """#!/bin/sh
printf 'SSH %s\\n' "$*" >> "$SSH_LOG"
case "$*" in
  *mktemp*) printf '/tmp/bridge-relay-trigger.AbC123.py\\n';;
esac
case "$*" in
  *"cat > "*) cat >/dev/null;;
  *PRAGMA*|*"SELECT "*|*"SELECT \\*"*) cat "$CANNED_ROW" 2>/dev/null || true;;
esac
"""

ROW = '{"transfer_id":"0xabc","status":"locked","source_chain":"foo","target_chain":"bar","amount":"5"}'


@pytest.fixture
def env(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh = bin_dir / "ssh"
    ssh.write_text(SSH_STUB)
    ssh.chmod(0o755)
    canned = tmp_path / "row.json"
    canned.write_text(ROW)
    log = tmp_path / "ssh.log"
    return SimpleNamespace(
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "SSH_LOG": str(log),
            "CANNED_ROW": str(canned),
            "HOME": str(tmp_path),
        },
        log=log,
    )


def test_relay_uses_the_flag_chains_and_a_mktemp_trigger(env):
    r = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--transfer-id",
            "0xabc",
            "--source-chain",
            "foo",
            "--target-chain",
            "bar",
        ],
        env=env.env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    log = env.log.read_text()
    assert r.returncode == 0, r.stderr
    relay_line = next(ln for ln in log.splitlines() if "bridge-relay-trigger" in ln and "python" in ln)
    assert "SOURCE_CHAIN='foo'" in relay_line
    assert "CHAIN_ID='bar'" in relay_line
    assert "/tmp/bridge-relay-trigger.py" not in log
    assert "mktemp" in log


def test_defaults_still_bc2(env):
    subprocess.run(
        ["bash", str(SCRIPT), "--transfer-id", "0xabc"],
        env=env.env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    log = env.log.read_text()
    assert "SOURCE_CHAIN='bc-2'" in log
    assert "CHAIN_ID='bc-2-island-1'" in log
