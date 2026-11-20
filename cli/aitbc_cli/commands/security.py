"""Security commands for AITBC CLI.

Real local checks only — no simulated backend:

* ``audit`` verifies the tamper-evident audit log
  (:class:`aitbc_cli.utils.secure_audit.SecureAuditLogger`) and checks
  filesystem permissions on wallet, credential and audit files under the
  aitbc home/data directories, then derives a letter grade.
* ``scan`` enumerates the same checks as issue rows.
* ``patch`` applies the safe subset of fixes — ``chmod 0600`` on sensitive
  files and ``chmod 0700`` on aitbc directories — and reports a per-target
  applied/skipped/failed result.  It never touches repo files, env files,
  or anything outside the aitbc home/data directories (a configured
  ``AITBC_WALLET_DIR`` outside those roots is reported but left alone).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import click

from ..utils import output
from ..utils.error_handling import abort
from ..utils.wallet_paths import wallet_dir

# Service wallet directories checked in addition to the configured wallet
# dir.  Mirrors wallet_paths._SERVICE_WALLET_DIRS (kept as a module-level
# name so tests can isolate the scan from the host's real service dir).
_SERVICE_WALLET_DIRS = (Path("/var/lib/aitbc/wallets"),)

_FILE_MODE = 0o600
_DIR_MODE = 0o0700
# Any group/other permission bit is a finding; owner bits may be stricter
# than the nominal mode (a 0400 wallet file is fine).
_FORBIDDEN_BITS = 0o077

_SEVERITY_DEDUCTION = {"critical": 40, "high": 15, "medium": 8, "low": 4}


def _aitbc_home() -> Path:
    return Path.home() / ".aitbc"


def _patch_roots() -> list[Path]:
    return [_aitbc_home(), Path("/var/lib/aitbc")]


def _wallet_dirs() -> list[Path]:
    """Wallet directories to inspect: configured dir plus service dirs."""
    dirs = [wallet_dir()]
    for candidate in _SERVICE_WALLET_DIRS:
        if candidate not in dirs:
            dirs.append(candidate)
    return dirs


def _dir_targets() -> list[Path]:
    """aitbc directories that must not grant group/other access."""
    dirs = [_aitbc_home(), _aitbc_home() / "wallets", _aitbc_home() / "audit"]
    for candidate in _wallet_dirs():
        if candidate not in dirs:
            dirs.append(candidate)
    return dirs


def _file_targets() -> list[tuple[Path, str, str]]:
    """(path, check, severity) candidates for the 0600 rule.

    Missing paths are skipped at evaluation time; symlinks are followed for
    the mode check (a broken symlink simply does not exist).
    """
    targets: list[tuple[Path, str, str]] = [
        (_aitbc_home() / "credentials.json", "credentials_file_perms", "high"),
    ]
    for directory in _wallet_dirs():
        if directory.is_dir():
            for path in sorted(directory.glob("*.json")):
                targets.append((path, "wallet_file_perms", "high"))
    audit_dir = _aitbc_home() / "audit"
    if audit_dir.is_dir():
        for path in sorted(audit_dir.iterdir()):
            if path.is_file():
                targets.append((path, "audit_file_perms", "medium"))
    return targets


def _mode_of(path: Path) -> int | None:
    """Permission bits of *path* (symlinks resolved), or None on error."""
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return None


def _perm_row(path: Path, check: str, severity: str, expected: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Evaluate one permission target.

    Returns ``(check_row, finding_or_None)``.  Missing paths return
    ``(None, None)`` — absence is not a failure.
    """
    if not path.exists() and not path.is_symlink():
        return None, None
    mode = _mode_of(path)
    if mode is None:
        check_row = {
            "check": check,
            "target": str(path),
            "passed": False,
            "expected": expected,
            "actual": "unreadable",
        }
        finding: dict[str, Any] | None = {
            "check": check,
            "target": str(path),
            "expected": expected,
            "actual": "unreadable",
            "severity": severity,
        }
        return check_row, finding
    actual = f"{mode:04o}"
    passed = not (mode & _FORBIDDEN_BITS)
    check_row = {
        "check": check,
        "target": str(path),
        "passed": passed,
        "expected": expected,
        "actual": actual,
    }
    finding = None
    if not passed:
        finding = {
            "check": check,
            "target": str(path),
            "expected": expected,
            "actual": actual,
            "severity": severity,
        }
    return check_row, finding


def _audit_integrity() -> tuple[bool, list[str], str]:
    """Verify the secure audit log.  Returns (ok, issues, target)."""
    target = str(_aitbc_home() / "audit" / "audit_secure.jsonl")
    try:
        # Imported lazily: the module creates its default logger (and the
        # ~/.aitbc/audit directory) at import time, which ``audit`` wants,
        # but unrelated CLI commands should not pay that cost.
        from ..utils.secure_audit import SecureAuditLogger

        ok, issues = SecureAuditLogger().verify_integrity()
        return ok, list(issues), target
    except Exception as e:  # noqa: BLE001 - audit must report, never crash
        return False, [f"integrity check failed: {e}"], target


def _evaluate() -> dict[str, Any]:
    """Run every local security check and derive score, grade, findings."""
    checks: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    # 1. Audit-log integrity (tamper-evident hash chain).
    integrity_ok, integrity_issues, integrity_target = _audit_integrity()
    checks.append(
        {
            "check": "audit_log_integrity",
            "target": integrity_target,
            "passed": integrity_ok,
            "expected": "intact hash chain",
            "actual": "verified" if integrity_ok else "; ".join(integrity_issues[:3]),
        }
    )
    if not integrity_ok:
        findings.append(
            {
                "check": "audit_log_integrity",
                "target": integrity_target,
                "expected": "intact hash chain",
                "actual": "; ".join(integrity_issues[:3]),
                "severity": "critical",
            }
        )

    # 2. File permissions (0600 or stricter).
    for path, check, severity in _file_targets():
        row, finding = _perm_row(path, check, severity, f"{_FILE_MODE:04o}")
        if row is not None:
            checks.append(row)
        if finding is not None:
            findings.append(finding)

    # 3. Directory permissions (0700 or stricter).
    for path in _dir_targets():
        row, finding = _perm_row(path, "aitbc_dir_perms", "medium", f"{_DIR_MODE:04o}")
        if row is not None:
            checks.append(row)
        if finding is not None:
            findings.append(finding)

    score = 100
    for finding in findings:
        score -= _SEVERITY_DEDUCTION.get(str(finding["severity"]), 8)
    score = max(score, 0)
    grade = _grade(score)

    recommendations = _recommendations(findings, integrity_ok)

    return {
        "status": "live",
        "security_score": grade,
        "score": score,
        "checks": checks,
        "checks_run": len(checks),
        "vulnerabilities": len(findings),
        "findings": findings,
        "recommendations": recommendations,
        "audit_log": {"verified": integrity_ok, "issues": integrity_issues},
    }


def _grade(score: int) -> str:
    if score >= 95:
        return "A+"
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _recommendations(findings: list[dict[str, Any]], integrity_ok: bool) -> list[str]:
    recommendations: list[str] = []
    if not integrity_ok:
        recommendations.append(
            "Audit log integrity check failed — investigate possible tampering before trusting the audit trail."
        )
    seen: set[str] = set()
    for finding in findings:
        target = str(finding["target"])
        if finding["check"] == "audit_log_integrity":
            continue
        mode = _FILE_MODE if "file_perms" in str(finding["check"]) else _DIR_MODE
        text = f"chmod {mode:o} {target}"
        if text not in seen:
            seen.add(text)
            recommendations.append(text)
    return recommendations


def _chmod_result(path: Path, mode: int) -> tuple[str, str, str, str]:
    """chmod *path* if it resolves inside the patch roots.

    Returns ``(action, before, after, detail)`` where action is
    ``applied`` / ``skipped`` / ``failed``.
    """
    before_mode = _mode_of(path)
    before = f"{before_mode:04o}" if before_mode is not None else "unreadable"
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path.absolute()
    roots = [_aitbc_home().resolve(), Path("/var/lib/aitbc").resolve()]
    if not any(resolved == root or root in resolved.parents for root in roots):
        return "skipped", before, before, "outside aitbc data dirs"
    try:
        os.chmod(path, mode)
    except OSError as e:
        return "failed", before, before, str(e)
    after_mode = _mode_of(path)
    after = f"{after_mode:04o}" if after_mode is not None else "unreadable"
    if after_mode is not None and not (after_mode & _FORBIDDEN_BITS):
        return "applied", before, after, ""
    return "failed", before, after, "chmod did not clear group/other bits"


@click.group(
    epilog="""Examples:

  aitbc security audit

  aitbc security scan

  aitbc security patch"""
)
def security():
    """Run security audits, scans, and apply safe permission patches."""
    pass


@security.command(
    epilog="""Examples:

  aitbc security audit

  aitbc security audit --output json"""
)
@click.pass_context
def audit(ctx):
    """Run a live local security audit and report a letter-grade score.

    Checks the tamper-evident audit log integrity and filesystem
    permissions on wallet, credential and audit files; missing files are
    skipped, not failures.
    """
    try:
        result = _evaluate()
        output(result, ctx.obj.get("output_format", "table"), title="Security Audit")
    except (OSError, ValueError, TypeError, AttributeError, RuntimeError) as e:
        abort(ctx, f"Error running security audit: {e}", from_exception=e)


@security.command(
    epilog="""Examples:

  aitbc security scan

  aitbc security scan --output json"""
)
@click.pass_context
def scan(ctx):
    """Run a live local security scan and list issues.

    Each finding is reported as a row with the check name, target,
    expected and actual permission/integrity state, and severity.
    """
    try:
        result = _evaluate()
        output(
            {
                "action": "security_scan",
                "status": "live",
                "checks_run": result["checks_run"],
                "issues_found": result["vulnerabilities"],
                "issues": result["findings"],
                "security_score": result["security_score"],
            },
            ctx.obj.get("output_format", "table"),
            title="Security Scan",
        )
    except (OSError, ValueError, TypeError, AttributeError, RuntimeError) as e:
        abort(ctx, f"Error running security scan: {e}", from_exception=e)


@security.command(
    epilog="""Examples:

  aitbc security patch

  aitbc security patch --output json"""
)
@click.pass_context
def patch(ctx):
    """Apply safe permission fixes under the aitbc data directories.

    chmod 0600 on wallet/credential/audit files and chmod 0700 on aitbc
    directories that grant group/other access.  Missing targets are
    skipped, chmod failures are reported per-target (never fatal), and
    nothing outside ``~/.aitbc`` / ``/var/lib/aitbc`` is modified.
    """
    try:
        results: list[dict[str, Any]] = []
        counts = {"applied": 0, "skipped": 0, "failed": 0}

        for path, check, _severity in _file_targets():
            if not path.exists() and not path.is_symlink():
                results.append(
                    {
                        "check": check,
                        "target": str(path),
                        "action": "skipped",
                        "detail": "not present",
                        "before": "-",
                        "after": "-",
                    }
                )
                counts["skipped"] += 1
                continue
            mode = _mode_of(path)
            if mode is not None and not (mode & _FORBIDDEN_BITS):
                results.append(
                    {
                        "check": check,
                        "target": str(path),
                        "action": "skipped",
                        "detail": "already compliant",
                        "before": f"{mode:04o}",
                        "after": f"{mode:04o}",
                    }
                )
                counts["skipped"] += 1
                continue
            action, before, after, detail = _chmod_result(path, _FILE_MODE)
            counts[action] += 1
            results.append(
                {"check": check, "target": str(path), "action": action, "detail": detail, "before": before, "after": after}
            )

        for path in _dir_targets():
            check = "aitbc_dir_perms"
            if not path.exists() and not path.is_symlink():
                results.append(
                    {
                        "check": check,
                        "target": str(path),
                        "action": "skipped",
                        "detail": "not present",
                        "before": "-",
                        "after": "-",
                    }
                )
                counts["skipped"] += 1
                continue
            mode = _mode_of(path)
            if mode is not None and not (mode & _FORBIDDEN_BITS):
                results.append(
                    {
                        "check": check,
                        "target": str(path),
                        "action": "skipped",
                        "detail": "already compliant",
                        "before": f"{mode:04o}",
                        "after": f"{mode:04o}",
                    }
                )
                counts["skipped"] += 1
                continue
            action, before, after, detail = _chmod_result(path, _DIR_MODE)
            counts[action] += 1
            results.append(
                {"check": check, "target": str(path), "action": action, "detail": detail, "before": before, "after": after}
            )

        output(
            {
                "action": "security_patch",
                "status": "live",
                "applied": counts["applied"],
                "skipped": counts["skipped"],
                "failed": counts["failed"],
                "results": results,
            },
            ctx.obj.get("output_format", "table"),
            title="Security Patch",
        )
    except (OSError, ValueError, TypeError, AttributeError, RuntimeError) as e:
        abort(ctx, f"Error applying security patches: {e}", from_exception=e)
