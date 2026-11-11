"""SECURITY-AUDIT-ROOT-TAUTOLOGY-AND-PERMISSION-SEVERITY-INVERTED-1 —
a unit with User=aitbc must not flag as root; a file more permissive
than expected is critical, not a stricter one."""

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("security_audit", REPO / "scripts" / "security" / "security_audit.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _issues(root: Path, check: str) -> list[dict]:
    a = mod.SecurityAudit(str(root))
    _, issues = getattr(a, check)()
    return issues


def test_user_equals_non_root_does_not_flag(tmp_path):
    (tmp_path / "a.service").write_text("[Service]\nUser=aitbc\n")
    (tmp_path / "b.service").write_text("[Service]\nExecStart=/bin/x\n")
    issues = _issues(tmp_path, "check_infrastructure_security")
    flagged = {i["file"] for i in issues if i["type"] == "service_running_as_root"}
    assert "a.service" not in flagged
    assert "b.service" in flagged  # no User= runs as root


def test_more_permissive_is_critical_not_stricter(tmp_path):
    (tmp_path / "k.key").write_text("x")
    (tmp_path / "k.key").chmod(0o644)  # too open -> critical
    (tmp_path / "k2.pem").write_text("x")
    (tmp_path / "k2.pem").chmod(0o400)  # stricter than expected -> warning at most
    issues = _issues(tmp_path, "check_file_permissions")
    sev = {i["file"]: i["severity"] for i in issues if i["type"] == "file_permission"}
    assert sev["k.key"] == "critical"
    assert sev["k2.pem"] == "warning"


def test_root_by_design_covers_exactly_the_documented_exceptions():
    """#1729: every repo unit without User= must be a documented exception.

    Units that ship no User= run as root — the audit allow-list must name
    each one, and each allow-listed path must exist and still lack
    User=aitbc (a unit that gained User=aitbc must leave the list).
    """
    missing_user = set()
    for f in REPO.rglob("*.service"):
        if any(part in {".git", "node_modules", "venv"} for part in f.parts):
            continue
        rel = f.relative_to(REPO).as_posix()
        users = [line.split("=", 1)[1].strip() for line in f.read_text().splitlines() if line.startswith("User=")]
        if not users or all(u == "root" for u in users):
            missing_user.add(rel)
    no_user_line = {
        p for p in missing_user if not any(line.startswith("User=") for line in (REPO / p).read_text().splitlines())
    }
    # scripts/ units with an explicit User=root (backup, load-secrets, …)
    # are deliberate and self-documenting; the #1729 allow-list covers the
    # units that ship NO User= line at all.
    assert no_user_line == set(mod.ROOT_BY_DESIGN), (
        f"undocumented root units: {no_user_line - set(mod.ROOT_BY_DESIGN)}; "
        f"stale allow-list entries: {set(mod.ROOT_BY_DESIGN) - no_user_line}"
    )


def test_deferred_1729_pins_run_as_aitbc():
    """#1819: the three #1729 follow-up pins, unblocked by operator chmods.

    backup-metrics reads /var/backups/aitbc (root:aitbc g+rX on node2);
    bridge-set and island-swarm-probe load root:aitbc 640 env files via
    EnvironmentFile=-. All three must pin User=/Group=aitbc — dropping
    either silently breaks the unit (env file skipped or backup dir
    unreadable). island-subscription-check deliberately stays root: its
    env holds a live AITBC_API_KEY."""
    pinned = {
        "scripts/monitoring/aitbc-backup-metrics.service",
        "scripts/monitoring/aitbc-bridge-set.service",
        "scripts/monitoring/aitbc-island-swarm-probe.service",
    }
    for rel in pinned:
        lines = (REPO / rel).read_text().splitlines()
        users = [line.split("=", 1)[1].strip() for line in lines if line.startswith("User=")]
        groups = [line.split("=", 1)[1].strip() for line in lines if line.startswith("Group=")]
        assert users == ["aitbc"], f"{rel}: User= must be aitbc, got {users}"
        assert groups == ["aitbc"], f"{rel}: Group= must be aitbc, got {groups}"

    sub = REPO / "scripts/monitoring/aitbc-island-subscription-check.service"
    assert not any(line.startswith("User=") for line in sub.read_text().splitlines()), (
        "island-subscription-check must stay root (live AITBC_API_KEY in env)"
    )
