"""#992 pin: refusal_class only accepts the node's real refusal vocabulary."""

import subprocess

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB = "scripts/stress/lib.sh"


def classify(outcome: str) -> str:
    rc = subprocess.run(
        ["bash", "-c", f'out="$1"; source {LIB} >/dev/null 2>&1; refusal_class "$out"', "_", outcome],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return rc.stdout.strip()


def test_known_refusals_classify_expected():
    assert classify("Error: Mempool full") == "expected"  # case-insensitive
    assert classify("nonce too low") == "expected"
    assert classify("insufficient funds") == "expected"
    assert classify("rate limit exceeded") == "expected"


def test_phantom_and_admit():
    assert classify("nonce slot occupied") == "phantom"
    assert classify("0x" + "ab" * 32) == "ok"


def test_unknown_outcome_is_not_expected():
    assert classify("connection refused") == "unknown"
    assert classify("Internal server error") == "unknown"
    assert classify("status: broken") == "unknown"
