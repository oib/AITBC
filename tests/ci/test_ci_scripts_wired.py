"""CI-GATES-DOCUMENTED-AS-ENFORCING-BUT-WIRED-NOWHERE-1 — every executable
script in scripts/ci must be reachable from a gate (Makefile target,
pre-commit hook, workflow, or the manual pre-push driver), or explicitly
listed as a manual-only tool. Anything else is a script that claims to
enforce while nothing runs it.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_DIR = REPO_ROOT / "scripts" / "ci"

# Release-time/manual tools that are deliberately not in any gate.
MANUAL_ONLY = {
    "check_phase4_gates.py",  # v0.11 release checklist checker; run by hand at release time
}

# Files that are data, not runnable gates.
NON_SCRIPTS = {".txt", ".pyc", ".md"}


def _gate_files() -> list[Path]:
    files = [REPO_ROOT / "Makefile", REPO_ROOT / ".pre-commit-config.yaml", CI_DIR / "run-suite-manual.sh"]
    files += list((REPO_ROOT / ".gitea").rglob("*.yml")) + list((REPO_ROOT / ".gitea").rglob("*.yaml"))
    # A script a test executes (e.g. tests/test_requirements_tiers.py runs
    # export-requirements.sh and diffs the output) is gated through pytest.
    files += list((REPO_ROOT / "tests").rglob("*.py"))
    return [f for f in files if f.is_file()]


def test_every_ci_script_is_wired_or_documented():
    # Reachable set: names mentioned by a gate file, then names mentioned by
    # any reachable scripts/ci file (sourced helpers, sub-invocations).
    reachable: set[str] = set()
    for f in _gate_files():
        reachable |= {p.name for p in CI_DIR.iterdir() if p.name in f.read_text()}
    changed = True
    while changed:
        changed = False
        for p in CI_DIR.iterdir():
            if p.name not in reachable or not p.is_file():
                continue
            for q in CI_DIR.iterdir():
                if q.name not in reachable and q.name in p.read_text():
                    reachable.add(q.name)
                    changed = True

    unwired = [
        p.name
        for p in CI_DIR.iterdir()
        if p.is_file() and p.suffix in (".sh", ".py") and p.name not in reachable and p.name not in MANUAL_ONLY
    ]
    assert unwired == [], f"gate scripts wired nowhere and not marked manual: {unwired}"
