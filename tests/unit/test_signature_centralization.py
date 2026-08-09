import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
ALLOWED_FILES = {
    "aitbc/crypto/crypto.py",
    "tests/unit/test_signature_centralization.py",
}


def test_signature_verification_is_centralized():
    """Fail if keys.Signature( is used outside the canonical crypto module.

    V23-05: all secp256k1 signature recovery must go through a single helper.
    This grep assertion costs nothing and catches new regressions at commit time.
    """
    result = subprocess.run(
        ["git", "grep", "-l", r"keys\.Signature\(", "--", "*.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    hits = {line for line in result.stdout.splitlines() if line}
    bad = hits - ALLOWED_FILES
    assert not bad, f"keys.Signature( found outside canonical module: {sorted(bad)}"
