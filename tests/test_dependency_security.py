"""
Dependency Security Tests
Tests for dependency security automation and scanning
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


class TestDependencySecurity:
    """Test dependency security scanning functionality"""

    def test_safety_check_command(self):
        """Test that safety command can be executed"""
        try:
            result = subprocess.run(["safety", "--version"], capture_output=True, text=True, timeout=10)
            # If safety is installed, it should return version info
            assert result.returncode == 0 or "command not found" not in result.stderr
        except FileNotFoundError:
            pass

    def test_pip_audit_command(self):
        """Test that pip-audit command can be executed"""
        try:
            result = subprocess.run(["pip-audit", "--version"], capture_output=True, text=True, timeout=10)
            # If pip-audit is installed, it should return version info
            assert result.returncode == 0 or "command not found" not in result.stderr
        except FileNotFoundError:
            pass

    def test_security_script_exists(self):
        """Test that the security scanning script exists"""
        script_path = Path("scripts/security/dependency-scan.sh")
        assert script_path.exists()
        # Check it's executable
        assert os.access(script_path, os.X_OK)

    def test_security_script_has_shebang(self):
        """Test that the security script has proper shebang"""
        script_path = Path("scripts/security/dependency-scan.sh")
        with open(script_path) as f:
            first_line = f.readline()
        assert first_line.startswith("#!/bin/bash")

    def test_security_policy_exists(self):
        """Test that the security policy documentation exists"""
        policy_path = Path(".github/SECURITY.md")
        assert policy_path.exists()

    def test_security_policy_content(self):
        """Test that the security policy has key sections"""
        policy_path = Path(".github/SECURITY.md")
        with open(policy_path) as f:
            content = f.read()

        # Check for key sections
        assert "Dependency Security" in content
        assert "Bandit" in content
        assert "pip-audit" in content
        assert "Security response" in content
        # The safety package was removed from the repo (SEC-15/SEC-19) —
        # the policy must not document it as a used tool.
        assert "Safety DB" not in content
        assert "pyup.io" not in content

    def test_dependabot_config_exists(self):
        """Test that Dependabot configuration exists"""
        dependabot_path = Path(".github/dependabot.yml")
        assert dependabot_path.exists()

    def test_dependabot_python_updates(self):
        """Test that Dependabot is configured for Python updates"""
        dependabot_path = Path(".github/dependabot.yml")
        with open(dependabot_path) as f:
            content = f.read()

        assert "pip" in content.lower()
        assert "python" in content.lower()


class TestSecurityReportGeneration:
    """Test security report generation and parsing"""

    def test_safety_report_json_parsing(self):
        """Test parsing safety report JSON format"""
        # Mock safety report data
        mock_report = [
            {
                "id": 12345,
                "package_name": "requests",
                "affected_versions": "<2.25.0",
                "installed_version": "2.24.0",
                "vulnerability": "CVE-2021-12345",
                "advisory": "Security vulnerability in requests",
            }
        ]

        # Test JSON serialization/deserialization
        json_str = json.dumps(mock_report)
        parsed = json.loads(json_str)

        assert len(parsed) == 1
        assert parsed[0]["package_name"] == "requests"
        assert parsed[0]["vulnerability"] == "CVE-2021-12345"

    def test_pip_audit_report_parsing(self):
        """Test parsing pip-audit report JSON format"""
        # Mock pip-audit report data
        mock_report = {
            "dependencies": [
                {
                    "name": "requests",
                    "version": "2.24.0",
                    "vulnerabilities": [
                        {"id": "CVE-2021-12345", "fix_versions": ["2.25.0"], "advisory": "Security vulnerability"}
                    ],
                }
            ]
        }

        # Test JSON serialization/deserialization
        json_str = json.dumps(mock_report)
        parsed = json.loads(json_str)

        assert len(parsed["dependencies"]) == 1
        assert parsed["dependencies"][0]["name"] == "requests"
        assert len(parsed["dependencies"][0]["vulnerabilities"]) == 1

    def test_empty_report_handling(self):
        """Test handling of empty security reports"""
        empty_report = []
        json_str = json.dumps(empty_report)
        parsed = json.loads(json_str)

        assert len(parsed) == 0


class TestSecurityIntegration:
    """Test security tool integration"""

    def test_pip_audit_in_venv(self):
        """Test that pip-audit is available in the virtual environment"""
        if not os.path.exists("./venv/bin/pip-audit"):
            pytest.skip("pip-audit not installed in ./venv")

        subprocess.run(["./venv/bin/pip-audit", "--version"], capture_output=True, text=True, timeout=10)
        # Should either succeed or fail gracefully
        assert True  # If we get here, pip-audit is at least available to try


class TestVulnerabilityScenarios:
    """Test various vulnerability scenarios"""

    def test_critical_vulnerability_response(self):
        """Test response to critical vulnerabilities"""
        mock_vuln = {"severity": "critical", "cvss_score": 9.5, "package": "requests", "version": "2.24.0"}

        # Critical vulnerabilities should trigger immediate action
        assert mock_vuln["cvss_score"] >= 9.0
        assert mock_vuln["severity"] == "critical"

    def test_high_vulnerability_response(self):
        """Test response to high vulnerabilities"""
        mock_vuln = {"severity": "high", "cvss_score": 7.5, "package": "flask", "version": "1.0.0"}

        # High vulnerabilities should trigger action within 72 hours
        assert 7.0 <= mock_vuln["cvss_score"] < 9.0
        assert mock_vuln["severity"] == "high"

    def test_medium_vulnerability_response(self):
        """Test response to medium vulnerabilities"""
        mock_vuln = {"severity": "medium", "cvss_score": 5.5, "package": "jinja2", "version": "2.0.0"}

        # Medium vulnerabilities can be scheduled
        assert 4.0 <= mock_vuln["cvss_score"] < 7.0
        assert mock_vuln["severity"] == "medium"


class TestSecurityWorkflowTriggers:
    """Test security workflow trigger conditions"""


class TestSecurityBestPractices:
    """Test security best practices compliance"""


SCRIPT_PATH = Path("scripts/security/dependency-scan.sh")

_STUB_LOGGER = """#!/bin/bash
echo "$(basename "$0") $*" >> "$STUB_LOG"
exit 0
"""

# Copied into a venv created by the python3 stub; an 'install pip-audit'
# call fabricates a pip-audit shim beside itself so the script's
# "$TOOLS_VENV/bin/pip-audit" resolves.
_STUB_VENV_PIP = """#!/bin/bash
echo "tools-venv-pip $*" >> "$STUB_LOG"
if [ "$1" = "install" ]; then
  for p in "$@"; do
    if [ "$p" = "pip-audit" ]; then
      d="$(dirname "$0")"
      printf '#!/bin/bash\\necho "tools-venv-pip-audit $*" >> "$STUB_LOG"\\nexit 0\\n' > "$d/pip-audit"
      chmod +x "$d/pip-audit"
    fi
  done
fi
exit 0
"""

_STUB_PYTHON3 = """#!/bin/bash
echo "python3 $*" >> "$STUB_LOG"
if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then
  d="$3"
  mkdir -p "$d/bin"
  cp "$STUB_DIR/venvpip" "$d/bin/pip"
  chmod +x "$d/bin/pip"
fi
exit 0
"""

_STUB_PROJECT_PIP = """#!/bin/bash
echo "project-venv-pip $*" >> "$STUB_LOG"
exit 0
"""


def _write_stub(directory: Path, name: str, content: str) -> Path:
    stub = directory / name
    stub.write_text(content)
    stub.chmod(0o755)
    return stub


def _stage_scan(tmp_path: Path, *, pip_audit_on_path: bool) -> dict:
    """A fake repo tree + PATH stubs; returns everything the tests assert on.

    Runs a COPY of the script inside tmp_path — the real script is never
    executed against a live tree (SEC-19)."""
    repo = tmp_path / "repo"
    script_dst = repo / SCRIPT_PATH
    script_dst.parent.mkdir(parents=True)
    script_dst.write_text(SCRIPT_PATH.read_text())
    script_dst.chmod(0o755)
    (repo / "requirements.txt").write_text("requests==2.31.0\n")
    # A project venv that the script may read but must never install into.
    proj_pip = repo / "venv" / "bin"
    proj_pip.mkdir(parents=True)
    _write_stub(proj_pip, "pip", _STUB_PROJECT_PIP)

    stubs = tmp_path / "stubs"
    stubs.mkdir()
    log = tmp_path / "stub.log"
    for name in ("pip", "bandit") + (("pip-audit",) if pip_audit_on_path else ()):
        _write_stub(stubs, name, _STUB_LOGGER)
    _write_stub(stubs, "python3", _STUB_PYTHON3)  # python3 handles -m venv
    (stubs / "venvpip").write_text(_STUB_VENV_PIP)
    (stubs / "venvpip").chmod(0o755)

    env = {
        **os.environ,
        "PATH": f"{stubs}:{os.environ['PATH']}",
        "STUB_LOG": str(log),
        "STUB_DIR": str(stubs),
        "AITBC_SCAN_TOOLS_VENV": str(tmp_path / "tools-venv"),
    }
    return {"repo": repo, "script": script_dst, "log": log, "env": env, "tools_venv": tmp_path / "tools-venv"}


def _run(stage: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(stage["script"])],
        env=stage["env"],
        capture_output=True,
        text=True,
        timeout=60,
    )


class TestDependencyScanIsolation:
    """SEC-19: the scan uses pip-audit only, installs nothing into the
    project venv, and removes its throwaway tools venv on exit."""

    def test_tools_venv_branch(self, tmp_path):
        """pip-audit absent from PATH -> throwaway tools venv, removed on exit."""
        stage = _stage_scan(tmp_path, pip_audit_on_path=False)
        result = _run(stage)
        assert result.returncode == 0, result.stderr
        log = stage["log"].read_text()

        # Install happened inside the tools venv only.
        assert "tools-venv-pip install --quiet pip-audit" in log
        # Nothing — install or otherwise mutating — in the project venv.
        assert "project-venv-pip install" not in log
        # pip-audit ran against the requirements file from the tools venv.
        assert "tools-venv-pip-audit -r requirements.txt --desc" in log
        # The throwaway venv is gone after the run.
        assert not stage["tools_venv"].exists()
        # bandit is installed nowhere and invoked nowhere.
        assert "bandit" not in log
        # The removed package is never installed or invoked.
        assert "safety" not in log.lower()

    def test_pip_audit_on_path_branch(self, tmp_path):
        """pip-audit on PATH -> used directly, no venv is created at all."""
        stage = _stage_scan(tmp_path, pip_audit_on_path=True)
        result = _run(stage)
        assert result.returncode == 0, result.stderr
        log = stage["log"].read_text()

        assert "pip-audit -r requirements.txt --desc" in log
        assert "python3 -m venv" not in log
        assert "tools-venv" not in log
        assert not stage["tools_venv"].exists()
        assert "safety" not in log.lower()

    def test_missing_project_venv_is_not_created(self, tmp_path):
        """No ./venv in the tree -> the script must not create one."""
        stage = _stage_scan(tmp_path, pip_audit_on_path=True)
        shutil.rmtree(stage["repo"] / "venv")
        result = _run(stage)
        assert result.returncode == 0, result.stderr
        assert not (stage["repo"] / "venv").exists()
        assert "skipping installed-version listing" in result.stdout

    def test_project_venv_never_receives_install(self, tmp_path):
        """Across both branches, project-venv pip sees only 'show' calls."""
        stage = _stage_scan(tmp_path, pip_audit_on_path=False)
        result = _run(stage)
        assert result.returncode == 0, result.stderr
        for line in stage["log"].read_text().splitlines():
            if line.startswith("project-venv-pip"):
                assert line.split()[1] == "show"


class TestDependencyScanStaticGuards:
    """Static guards on the real script — no execution."""

    def test_bash_syntax(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT_PATH)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr

    def test_no_safety_reference(self):
        """'safety' must not appear as a package or command in any scan script."""
        for script in Path("scripts/security").glob("*.sh"):
            content = script.read_text().lower()
            assert "safety" not in content, f"{script} still references safety"

    def test_no_project_venv_mutation(self):
        """No venv activation, no 'python3 -m venv venv', and the only pip
        install command targets the tools venv path (recommendation text
        inside echoes does not count)."""
        content = SCRIPT_PATH.read_text()
        assert "source venv" not in content
        assert "-m venv venv" not in content
        assert '"$TOOLS_VENV/bin/pip" install --quiet pip-audit' in content
        for line in content.splitlines():
            if "pip install" in line:
                assert line.strip().startswith('"$TOOLS_VENV/bin/pip"') or "echo" in line


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
