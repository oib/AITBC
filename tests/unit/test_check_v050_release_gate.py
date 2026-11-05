"""Pins for scripts/release/check-v0.5.0.sh (RELEASE-CHECK-V0-5-0-FAILS-ON-ITS-OWN-SOURCE-AND-IS-UNWIRED-1, #1036).

The old gate could never pass: step 2's grep scanned the script's own source
(itself containing the pattern), and ``2>/dev/null`` turned grep errors
(missing dirs) into a false "no match" PASS. The rewrite takes ``--root`` /
``--tag`` / ``--with-services``, excludes itself and the known legit
placeholder carriers, and distinguishes grep rc>=2 (exit 2) from matches
(exit 1).
"""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "release" / "check-v0.5.0.sh"

SCAN_DIRS = ("apps", "scripts", "contracts", "cli")


def _scratch(tmp_path: Path, placeholder: str | None = None) -> Path:
    root = tmp_path / "tree"
    for d in SCAN_DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
    if placeholder is not None:
        target = root / "apps" / "svc" / "config.env"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"SECRET={placeholder}\n")
    return root


def _run(root: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), "--root", str(root), *extra],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_clean_tree_passes(tmp_path):
    proc = _run(_scratch(tmp_path))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "All checks passed" in proc.stdout


def test_placeholder_match_fails_and_prints_it(tmp_path):
    proc = _run(_scratch(tmp_path, "change-me-in-production"))
    assert proc.returncode == 1
    assert "change-me-in-production" in proc.stdout
    assert "FAILED" in proc.stdout


def test_your_here_placeholder_fails(tmp_path):
    proc = _run(_scratch(tmp_path, "your_api_key_here"))
    assert proc.returncode == 1
    assert "your_" in proc.stdout


def test_missing_scan_dir_is_error_not_pass(tmp_path):
    root = _scratch(tmp_path)
    import shutil

    shutil.rmtree(root / "contracts")
    proc = _run(root)
    assert proc.returncode == 2
    assert "grep failed" in proc.stderr or "No such file" in proc.stderr


def test_missing_dir_with_match_prints_match_and_exits_2(tmp_path):
    # verify spec: one match + one missing directory -> match printed, exit 2
    root = _scratch(tmp_path, "change-me-in-production")
    import shutil

    shutil.rmtree(root / "contracts")
    proc = _run(root)
    assert proc.returncode == 2
    assert "change-me-in-production" in proc.stderr + proc.stdout


def test_script_does_not_match_itself(tmp_path):
    # The gate's own source lives under scripts/release in the real tree; in a
    # scratch tree copy it there to prove self-exclusion.
    root = _scratch(tmp_path)
    rel = Path("scripts") / "release" / "check-v0.5.0.sh"
    dest = root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(SCRIPT.read_text())
    proc = _run(root)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_default_root_is_checkout_not_opt_aitbc(tmp_path):
    # --root omitted: ROOT derives from the script location (the worktree),
    # which is a valid tree here.
    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "/opt/aitbc" not in proc.stdout.split("root:", 1)[1].splitlines()[0]
