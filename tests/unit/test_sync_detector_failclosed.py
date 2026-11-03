"""#901: sync_detector.sh fails closed on unreadable heights, the stray
EOF tail is gone, and the sync trigger path exists.

On base a failed curl|jq produced empty heights → integer-expression
errors → "difference is normal (0 <= 100)"; line 60's pasted heredoc
terminator made every run exit 127; the bulk_sync.sh call pointed at a
path that never existed.
"""

import os
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "sync" / "sync_detector.sh"


def _run(tmp_path, env_extra=None):
    env = dict(os.environ)
    env["AITBC_SYNC_LOG"] = str(tmp_path / "sync.log")
    env.update(env_extra or {})
    return subprocess.run(
        ["bash", "-c", f'source <(sed -n "/^check_sync_diff/,/^}}/p" "{SCRIPT}")\ncheck_sync_diff'],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_stray_eof_tail_is_gone_and_script_parses():
    src = SCRIPT.read_text()
    assert "EOF && chmod" not in src
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_heights_must_be_integers(tmp_path):
    r = _run(tmp_path, {"LOCAL_PORT": "1", "GENESIS_NODE": "127.0.0.1", "GENESIS_PORT": "1"})
    log = (tmp_path / "sync.log").read_text() if (tmp_path / "sync.log").exists() else ""
    assert "Cannot get blockchain heights" in log or r.returncode != 0
    assert "difference is normal" not in log.lower()


def test_trigger_path_no_longer_points_at_the_retired_script():
    src = SCRIPT.read_text()
    assert "/opt/aitbc/scripts/bulk_sync.sh" not in src
    assert "bulk_sync.sh" not in src
