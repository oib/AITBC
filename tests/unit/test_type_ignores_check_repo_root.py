"""CI-TYPEIGNORES-CHECK-SCANS-OPT-AITBC-1 — the check must scan the repo it
lives in, not a hardcoded /opt/aitbc checkout."""

from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check-type-ignores.sh").read_text()


def test_no_hardcoded_opt_path():
    assert "/opt/aitbc" not in SCRIPT


def test_scans_repo_root():
    assert "REPO_ROOT" in SCRIPT
