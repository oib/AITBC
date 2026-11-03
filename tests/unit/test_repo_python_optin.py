"""CI-REPOPYTHON-OPTIN-REFUSES-PYTHON3-1 — PYTHON=python3 is the documented
system-interpreter opt-in but _runs required an executable *path*, so a
bare name always fell through to the repo-venv search / exit 1."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "repo-python.sh"


def test_python3_optin_resolves():
    env = dict(os.environ, PYTHON="python3", PATH="/usr/bin:/bin")
    r = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "python3"


def test_bogus_name_still_fails():
    env = dict(os.environ, PYTHON="not-a-real-interpreter", PATH="/usr/bin:/bin")
    r = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=env)
    assert r.returncode == 1
