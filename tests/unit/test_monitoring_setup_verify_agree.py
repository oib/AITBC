"""VERIFY-MONITORING-SETUP-MISMATCH-1 — setup followed by verify must pass
on a clean tree and fail on a broken alertmanager.yml."""

import subprocess
from pathlib import Path

MON = Path(__file__).resolve().parents[2] / "scripts" / "monitoring"
SETUP = MON / "setup-contract-monitoring.sh"
VERIFY = MON / "verify-monitoring.sh"


def _run(script, scratch, network="mainnet"):
    # Both scripts resolve REPO_ROOT from their own location; copy them into a
    # scratch tree so setup writes there, never into the real checkout.
    target = scratch / "scripts" / "monitoring"
    target.mkdir(parents=True, exist_ok=True)
    import shutil

    shutil.copy(SETUP, target / "setup-contract-monitoring.sh")
    shutil.copy(VERIFY, target / "verify-monitoring.sh")
    return subprocess.run(
        ["bash", str(target / script.name), network],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
    )


def test_same_default_network():
    setup_net = [line for line in SETUP.read_text().splitlines() if line.startswith("NETWORK=")][0]
    verify_net = [line for line in VERIFY.read_text().splitlines() if line.startswith("NETWORK=")][0]
    assert setup_net == verify_net


def test_setup_then_verify_passes(tmp_path):
    s = _run(SETUP, tmp_path)
    assert s.returncode == 0, s.stderr
    v = _run(VERIFY, tmp_path)
    assert v.returncode == 0, v.stdout + v.stderr


def test_broken_alertmanager_fails_verify(tmp_path):
    _run(SETUP, tmp_path)
    am = tmp_path / "scripts" / "monitoring" / "config" / "alertmanager.yml"
    am.write_text("route: [unclosed")
    v = _run(VERIFY, tmp_path)
    assert v.returncode == 1
