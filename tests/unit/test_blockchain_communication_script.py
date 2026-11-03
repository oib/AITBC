"""#875/#876: blockchain-communication-test.sh must not abort or mutate.

#875 — log_error appended "[${timestamp}] [ERROR] ..." to the error log, but
``timestamp`` is a local of ``log()`` and out of scope there; under
``set -u`` the first logged error killed the whole suite instead of being
counted. The script also probed the stale RPC port 8006 (the node serves
8202). These tests run log_error and the suite in scratch dirs and assert
failures are *counted* and reported, and that the configured port is 8202.

#876 — test_sync ran ``git pull origin main`` on three hosts on every cycle:
a *test* was mutating node checkouts. It now fetches and compares rev-list
counts, never pulls. Pinned statically: the script must contain no ``git
pull`` and must fetch + rev-list instead.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "deployment" / "blockchain-communication-test.sh"


def _env(tmp_path: Path, port: str = "1") -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "AITBC_NODE0_HOST": "127.0.0.1",
            "AITBC_NODE1_HOST": "127.0.0.1",
            "AITBC_NODE3_HOST": "127.0.0.1",
            "AITBC_NODE3_SSH": "127.0.0.1",
            "AITBC_LOG_DIR": str(tmp_path),
            "AITBC_RPC_PORT": port,
            "CLI_PATH": "true",
        }
    )
    return env


def test_script_probes_port_8202_not_the_stale_8006():
    text = SCRIPT.read_text()
    assert "8006" not in text, "script still references the stale RPC port 8006"
    assert re.search(r"PORT=.*8202", text), "script does not probe RPC port 8202"


def test_log_error_captures_its_own_timestamp(tmp_path):
    """#875: under set -u an out-of-scope $timestamp aborted the whole suite."""
    proc = subprocess.run(
        ["bash", "-u", "-c", f'source "{SCRIPT}"; log_error "boom"'],
        capture_output=True,
        text=True,
        env=_env(tmp_path),
    )
    assert proc.returncode == 0, f"log_error aborted under set -u: {proc.stderr}"
    error_log = tmp_path / "blockchain-test-errors.log"
    assert error_log.exists(), "log_error did not write the error log"
    assert re.search(
        r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] \[ERROR\] boom",
        error_log.read_text(),
    )


def test_suite_counts_a_failure_instead_of_aborting(tmp_path):
    """A failing check must end in a counted FAILED, not a set -u abort."""
    proc = subprocess.run(
        ["bash", str(SCRIPT), "--type", "connectivity"],
        capture_output=True,
        text=True,
        env=_env(tmp_path),
    )
    assert proc.returncode != 0
    assert "FAILED" in proc.stdout + proc.stderr, "suite aborted before run_test could count the failure"
    error_log = tmp_path / "blockchain-test-errors.log"
    assert error_log.exists() and "[ERROR]" in error_log.read_text()


def test_sync_never_pulls():
    """#876: a test must not mutate node checkouts — fetch + compare only."""
    text = SCRIPT.read_text()
    assert "git pull" not in text, "test_sync still runs git pull on the nodes"
    assert "git fetch" in text
    assert "rev-list" in text
