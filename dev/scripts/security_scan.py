#!/usr/bin/env python3
"""
Security vulnerability scanner for AITBC dependencies.
Uses pip-audit to check installed packages in the CLI virtualenv.
"""
import subprocess
import json
import sys

PIP_AUDIT = '/opt/aitbc/cli/venv/bin/pip-audit'

def run_audit():
    try:
        result = subprocess.run([PIP_AUDIT, '--format', 'json'],
                                capture_output=True, text=True, timeout=300)
        if result.returncode not in (0, 1):  # 1 means vulns found, 0 means clean
            return f"❌ pip-audit execution failed (exit {result.returncode}):\n{result.stderr}"
        data = json.loads(result.stdout) if result.stdout else {}
        vulns = data.get('vulnerabilities', [])
        if not vulns:
            return "✅ Security scan: No known vulnerabilities in installed packages."
        # Summarize by severity
        sev_counts = {}
        for v in vulns:
            sev = v.get('severity', 'UNKNOWN')
            sev_counts[sev] = sev_counts.get(sev, 0) + 1
        lines = ["🚨 Security scan: Found vulnerabilities:"]
        for sev, count in sorted(sev_counts.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- {sev}: {count} package(s)")
        # Add top 3 vulnerable packages
        if vulns:
            lines.append("\nTop vulnerable packages:")
            for v in vulns[:3]:
                pkg = v.get('package', 'unknown')
                vuln_id = v.get('vulnerability_id', 'unknown')
                lines.append(f"- {pkg}: {vuln_id}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error during security scan: {str(e)}"

if __name__ == '__main__':
    message = run_audit()
    print(message)
    sys.exit(0)
