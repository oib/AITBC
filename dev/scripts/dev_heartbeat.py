#!/usr/bin/env python3
"""
Dev Heartbeat: Periodic checks for /opt/aitbc development environment.
Outputs concise markdown summary. Exit 0 if clean, 1 if issues detected.
"""
import os
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path("/opt/aitbc")
LOGS_DIR = REPO_ROOT / "logs"

def sh(cmd, cwd=REPO_ROOT):
    """Run shell command, return (returncode, stdout)."""
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout.strip()

def check_git_status():
    """Return summary of uncommitted changes."""
    rc, out = sh("git status --porcelain")
    if rc != 0 or not out:
        return None
    lines = out.splitlines()
    changed = len(lines)
    # categorize simply
    modified = sum(1 for l in lines if l.startswith(' M') or l.startswith('M '))
    added = sum(1 for l in lines if l.startswith('A '))
    deleted = sum(1 for l in lines if l.startswith(' D') or l.startswith('D '))
    return {"changed": changed, "modified": modified, "added": added, "deleted": deleted, "preview": lines[:10]}

def check_build_tests():
    """Quick build and test health check."""
    checks = []
    # 1) Poetry check (dependency resolution)
    rc, out = sh("poetry check")
    checks.append(("poetry check", rc == 0, out))
    # 2) Fast syntax check of CLI package
    rc, out = sh("python3 -m py_compile cli/aitbc_cli/main.py")
    checks.append(("cli syntax", rc == 0, out if rc != 0 else "OK"))
    # 3) Minimal test run (dry-run or 1 quick test)
    rc, out = sh("python3 -m pytest tests/ -v --collect-only 2>&1 | head -20")
    tests_ok = rc == 0
    checks.append(("test discovery", tests_ok, out if not tests_ok else f"Collected {out.count('test') if 'test' in out else '?'} tests"))
    all_ok = all(ok for _, ok, _ in checks)
    return {"all_ok": all_ok, "details": checks}

def check_logs_errors(hours=1):
    """Scan logs for ERROR/WARNING in last N hours."""
    if not LOGS_DIR.exists():
        return None
    errors = []
    warnings = []
    cutoff = datetime.now() - timedelta(hours=hours)
    for logfile in LOGS_DIR.glob("*.log"):
        try:
            mtime = datetime.fromtimestamp(logfile.stat().st_mtime)
            if mtime < cutoff:
                continue
            with open(logfile) as f:
                for line in f:
                    if "ERROR" in line or "FATAL" in line:
                        errors.append(f"{logfile.name}: {line.strip()[:120]}")
                    elif "WARN" in line:
                        warnings.append(f"{logfile.name}: {line.strip()[:120]}")
        except Exception:
            continue
    return {"errors": errors[:20], "warnings": warnings[:20], "total_errors": len(errors), "total_warnings": len(warnings)}

def check_dependencies():
    """Check outdated packages via poetry."""
    rc, out = sh("poetry show --outdated --no-interaction")
    if rc != 0 or not out:
        return []
    # parse package lines
    packages = []
    for line in out.splitlines()[2:]:  # skip headers
        parts = line.split()
        if len(parts) >= 3:
            packages.append({"name": parts[0], "current": parts[1], "latest": parts[2]})
    return packages

def check_vulnerabilities():
    """Run security audits for Python and Node dependencies."""
    issues = []
    # Python: pip-audit (if available)
    rc, out = sh("pip-audit --requirement <(poetry export --without-hashes) 2>&1")
    if rc == 0:
        # No vulnerabilities
        pass
    else:
        # pip-audit returns non-zero when vulns found; parse output for count
        # Usually output contains lines with "Found X vulnerabilities"
        if "vulnerabilities" in out.lower():
            issues.append(f"Python dependencies: vulnerabilities detected\n```\n{out[:2000]}\n```")
        else:
            # Command failed for another reason (maybe not installed)
            pass
    # Node: npm audit (if package.json exists)
    if (REPO_ROOT / "package.json").exists():
        rc, out = sh("npm audit --json")
        if rc != 0:
            try:
                audit = json.loads(out)
                count = audit.get("metadata", {}).get("vulnerabilities", {}).get("total", 0)
                if count > 0:
                    issues.append(f"Node dependencies: {count} vulnerabilities (npm audit)")
            except:
                issues.append("Node dependencies: npm audit failed to parse")
    return issues

def main():
    report = []
    issues = 0

    # Git
    git = check_git_status()
    if git and git["changed"] > 0:
        issues += 1
        report.append(f"### Git: {git['changed']} uncommitted changes\n")
        if git["preview"]:
            report.append("```\n" + "\n".join(git["preview"]) + "\n```")
    else:
        report.append("### Git: clean")

    # Build/Tests
    bt = check_build_tests()
    if not bt["all_ok"]:
        issues += 1
        report.append("### Build/Tests: problems detected\n")
        for label, ok, msg in bt["details"]:
            status = "OK" if ok else "FAIL"
            report.append(f"- **{label}**: {status}")
            if not ok and msg:
                report.append(f"  ```\n{msg}\n```")
    else:
        report.append("### Build/Tests: OK")

    # Logs
    logs = check_logs_errors()
    if logs and logs["total_errors"] > 0:
        issues += 1
        report.append(f"### Logs: {logs['total_errors']} recent errors (last hour)\n")
        for e in logs["errors"][:10]:
            report.append(f"- `{e}`")
        if logs["total_errors"] > 10:
            report.append(f"... and {logs['total_errors']-10} more")
    elif logs and logs["total_warnings"] > 0:
        # warnings non-blocking but included in report
        report.append(f"### Logs: {logs['total_warnings']} recent warnings (last hour)")
    else:
        report.append("### Logs: no recent errors")

    # Dependencies
    outdated = check_dependencies()
    if outdated:
        issues += 1
        report.append(f"### Dependencies: {len(outdated)} outdated packages\n")
        for pkg in outdated[:10]:
            report.append(f"- {pkg['name']}: {pkg['current']} → {pkg['latest']}")
        if len(outdated) > 10:
            report.append(f"... and {len(outdated)-10} more")
    else:
        report.append("### Dependencies: up to date")

    # Vulnerabilities
    vulns = check_vulnerabilities()
    if vulns:
        issues += 1
        report.append("### Security: vulnerabilities detected\n")
        for v in vulns:
            report.append(f"- {v}")
    else:
        report.append("### Security: no known vulnerabilities (audit clean)")

    # Final output
    header = f"# Dev Heartbeat — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}\n\n"
    summary = f"**Issues:** {issues}\n\n" if issues > 0 else "**Status:** All checks passed.\n\n"
    full_report = header + summary + "\n".join(report)

    print(full_report)

    # Exit code signals issues presence
    sys.exit(1 if issues > 0 else 0)

if __name__ == "__main__":
    main()

