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
