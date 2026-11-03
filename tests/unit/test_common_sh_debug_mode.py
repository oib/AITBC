"""UTILS-COMMON-SH-UNBOUND-DEBUG-MODE-IN-ERROR-TRAP-1 — common.sh enables
set -u without defining DEBUG_MODE, so log_debug/handle_error die on the
unbound variable instead of logging."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "utils" / "common.sh"


def test_debug_mode_is_defined_or_defaulted():
    body = SCRIPT.read_text()
    assert "DEBUG_MODE:=false" in body or "${DEBUG_MODE:-false}" in body


def test_source_and_log_debug_do_not_die(tmp_path):
    bash = f"source {SCRIPT}; log_debug hi; true"
    result = subprocess.run(
        ["bash", "-c", bash],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "AITBC_ROOT": str(tmp_path)},
    )
    assert "unbound variable" not in result.stderr
