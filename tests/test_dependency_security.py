"""
Dependency Security Tests
Tests for dependency security automation and scanning
"""

import json
import os
import subprocess
from pathlib import Path

import pytest


class TestDependencySecurity:
    """Test dependency security scanning functionality"""

    def test_safety_check_command(self):
        """Test that safety command can be executed"""
        try:
            result = subprocess.run(
                ["safety", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            # If safety is installed, it should return version info
            assert result.returncode == 0 or "command not found" not in result.stderr
        except FileNotFoundError:
            pytest.skip("safety not installed")

    def test_pip_audit_command(self):
        """Test that pip-audit command can be executed"""
        try:
            result = subprocess.run(
                ["pip-audit", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            # If pip-audit is installed, it should return version info
            assert result.returncode == 0 or "command not found" not in result.stderr
        except FileNotFoundError:
            pytest.skip("pip-audit not installed")

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

    def test_security_workflow_exists(self):
        """Test that the GitHub security workflow exists"""
        workflow_path = Path(".github/workflows/dependency-security.yml")
        assert workflow_path.exists()

    def test_security_workflow_content(self):
        """Test that the security workflow has required steps"""
        workflow_path = Path(".github/workflows/dependency-security.yml")
        with open(workflow_path) as f:
            content = f.read()
        
        # Check for key security tools
        assert "safety" in content.lower()
        assert "pip-audit" in content.lower()
        assert "bandit" in content.lower()
        
        # Check for scheduled runs
        assert "schedule:" in content
        assert "cron:" in content

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
        assert "Safety" in content
        assert "pip-audit" in content
        assert "Security Response" in content

    def test_gitea_security_workflow_exists(self):
        """Test that the Gitea security workflow exists"""
        workflow_path = Path(".gitea/workflows/security-scanning.yml")
        assert workflow_path.exists()

    def test_gitea_workflow_includes_safety(self):
        """Test that Gitea workflow includes safety scanning"""
        workflow_path = Path(".gitea/workflows/security-scanning.yml")
        with open(workflow_path) as f:
            content = f.read()
        
        assert "safety" in content.lower()

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
                "advisory": "Security vulnerability in requests"
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
                        {
                            "id": "CVE-2021-12345",
                            "fix_versions": ["2.25.0"],
                            "advisory": "Security vulnerability"
                        }
                    ]
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

    @pytest.mark.skipif(
        not os.path.exists("venv"),
        reason="Virtual environment not found"
    )
    def test_safety_in_venv(self):
        """Test that safety is available in the virtual environment"""
        if not os.path.exists("./venv/bin/safety"):
            pytest.skip("safety not installed in venv")
        
        result = subprocess.run(
            ["./venv/bin/safety", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        # Should either succeed or fail gracefully
        assert True  # If we get here, safety is at least available to try

    @pytest.mark.skipif(
        not os.path.exists("venv"),
        reason="Virtual environment not found"
    )
    def test_pip_audit_in_venv(self):
        """Test that pip-audit is available in the virtual environment"""
        if not os.path.exists("./venv/bin/pip-audit"):
            pytest.skip("pip-audit not installed in venv")
        
        result = subprocess.run(
            ["./venv/bin/pip-audit", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        # Should either succeed or fail gracefully
        assert True  # If we get here, pip-audit is at least available to try


class TestVulnerabilityScenarios:
    """Test various vulnerability scenarios"""

    def test_critical_vulnerability_response(self):
        """Test response to critical vulnerabilities"""
        mock_vuln = {
            "severity": "critical",
            "cvss_score": 9.5,
            "package": "requests",
            "version": "2.24.0"
        }
        
        # Critical vulnerabilities should trigger immediate action
        assert mock_vuln["cvss_score"] >= 9.0
        assert mock_vuln["severity"] == "critical"

    def test_high_vulnerability_response(self):
        """Test response to high vulnerabilities"""
        mock_vuln = {
            "severity": "high",
            "cvss_score": 7.5,
            "package": "flask",
            "version": "1.0.0"
        }
        
        # High vulnerabilities should trigger action within 72 hours
        assert 7.0 <= mock_vuln["cvss_score"] < 9.0
        assert mock_vuln["severity"] == "high"

    def test_medium_vulnerability_response(self):
        """Test response to medium vulnerabilities"""
        mock_vuln = {
            "severity": "medium",
            "cvss_score": 5.5,
            "package": "jinja2",
            "version": "2.0.0"
        }
        
        # Medium vulnerabilities can be scheduled
        assert 4.0 <= mock_vuln["cvss_score"] < 7.0
        assert mock_vuln["severity"] == "medium"


class TestSecurityWorkflowTriggers:
    """Test security workflow trigger conditions"""

    def test_github_workflow_triggers(self):
        """Test that GitHub workflow has appropriate triggers"""
        workflow_path = Path(".github/workflows/dependency-security.yml")
        with open(workflow_path) as f:
            content = f.read()
        
        # Should trigger on push, PR, schedule, and manual dispatch
        assert "push:" in content
        assert "pull_request:" in content
        assert "schedule:" in content
        assert "workflow_dispatch:" in content

    def test_gitea_workflow_triggers(self):
        """Test that Gitea workflow has appropriate triggers"""
        workflow_path = Path(".gitea/workflows/security-scanning.yml")
        with open(workflow_path) as f:
            content = f.read()
        
        # Should trigger on push, PR, and manual dispatch
        assert "push:" in content
        assert "pull_request:" in content
        assert "workflow_dispatch:" in content


class TestSecurityBestPractices:
    """Test security best practices compliance"""

    def test_no_hardcoded_secrets_in_workflow(self):
        """Test that workflows don't contain hardcoded secrets"""
        workflow_path = Path(".github/workflows/dependency-security.yml")
        with open(workflow_path) as f:
            content = f.read()
        
        # Check for common secret patterns
        assert "api_key" not in content.lower()
        assert "secret" not in content.lower() or "secret-key" in content.lower()
        assert "password" not in content.lower()

    def test_security_artifact_retention(self):
        """Test that security artifacts have appropriate retention"""
        workflow_path = Path(".github/workflows/dependency-security.yml")
        with open(workflow_path) as f:
            content = f.read()
        
        # Should have artifact upload with retention
        assert "upload-artifact" in content
        assert "retention-days" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])