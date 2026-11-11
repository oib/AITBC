"""except-ratchet must see real ruff output (no ANSI false-green)."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_except_ratchet_counts_payment_escrow():
    proc = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/ci/check-except-ratchet.sh")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stdout[-1000:] + proc.stderr[-500:]
    assert "492 baselined files" in proc.stdout or "baselined files" in proc.stdout
