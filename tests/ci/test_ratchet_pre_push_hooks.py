"""Pre-push ratchet hooks must stay wired (#1517)."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _pre_commit_text() -> str:
    path = REPO_ROOT / ".pre-commit-config.yaml"
    if not path.is_file():
        import pytest

        pytest.skip("thin archive: .pre-commit-config.yaml not present")
    return path.read_text()


def test_ratchet_hooks_on_pre_push():
    text = _pre_commit_text()
    for hook_id, script in (
        ("c901-ratchet", "check-c901-ratchet.sh"),
        ("except-ratchet", "check-except-ratchet.sh"),
        ("module-size-ratchet", "check-module-size.py"),
        ("critical-path-tests", "check-critical-path-tests.sh"),
    ):
        assert f"id: {hook_id}" in text
        assert script in text
