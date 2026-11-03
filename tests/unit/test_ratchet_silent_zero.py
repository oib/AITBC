"""CI-RATCHETS-EXIT-SILENTLY-AT-ZERO-1 — a ruff/tool failure must not read
as a clean scan."""

import subprocess
from pathlib import Path

CI = Path(__file__).resolve().parents[2] / "scripts" / "ci"


def test_c901_fails_loud_when_ruff_cannot_run(tmp_path):
    fake = tmp_path / "pypath"
    fake.write_text("#!/bin/sh\nexit 2\n")
    fake.chmod(0o755)
    r = subprocess.run(
        ["bash", str(CI / "check-c901-ratchet.sh")],
        capture_output=True,
        text=True,
        env={"PYTHON": str(fake), "PATH": "/usr/bin:/bin"},
    )
    # either repo-python refuses the interpreter or the gate names the scan
    assert r.returncode == 1


def test_no_bare_or_true_on_tool_output():
    for name in ("check-c901-ratchet.sh", "check-except-ratchet.sh"):
        body = (CI / name).read_text()
        for line in body.splitlines():
            if "ruff check" in line and "|| true" in line:
                raise AssertionError(f"{name}: tool output still swallowed: {line.strip()}")
