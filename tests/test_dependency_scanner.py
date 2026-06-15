"""
Dependency Scanner Tests
Tests for AITBC dependency vulnerability scanning utilities
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from aitbc.dependency_scanner import (
    DependencyScanner,
    VulnerabilityReport,
    check_vulnerability_thresholds,
    run_dependency_scan,
)


class TestVulnerabilityReport:
    """Test VulnerabilityReport dataclass"""

    def test_vulnerability_report_creation(self):
        """Test VulnerabilityReport creation"""
        report = VulnerabilityReport(
            package="test-package",
            version="1.0.0",
            vulnerability_id="CVE-2024-1234",
            severity="HIGH",
            description="Test vulnerability",
            fix_available=True,
            fixed_version="1.0.1",
        )
        assert report.package == "test-package"
        assert report.version == "1.0.0"
        assert report.vulnerability_id == "CVE-2024-1234"
        assert report.severity == "HIGH"
        assert report.fix_available is True

    def test_vulnerability_report_without_fix(self):
        """Test VulnerabilityReport without fix available"""
        report = VulnerabilityReport(
            package="test-package",
            version="1.0.0",
            vulnerability_id="CVE-2024-1234",
            severity="HIGH",
            description="Test vulnerability",
            fix_available=False,
            fixed_version=None,
        )
        assert report.fix_available is False
        assert report.fixed_version is None


class TestDependencyScanner:
    """Test DependencyScanner class"""

    def test_initialization_default(self):
        """Test DependencyScanner initialization with defaults"""
        scanner = DependencyScanner()
        assert scanner.requirements_file == Path("pyproject.toml")
        assert scanner._vulnerabilities == []

    def test_initialization_custom_file(self):
        """Test DependencyScanner initialization with custom file"""
        custom_path = Path("custom-requirements.txt")
        scanner = DependencyScanner(requirements_file=custom_path)
        assert scanner.requirements_file == custom_path

    @patch("aitbc.dependency_scanner.subprocess.run")
    def test_scan_with_pip_audit_no_vulnerabilities(self, mock_run):
        """Test scan_with_pip_audit when no vulnerabilities found"""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        scanner = DependencyScanner()
        results = scanner.scan_with_pip_audit()

        assert results == []
        mock_run.assert_called_once()

    @patch("aitbc.dependency_scanner.subprocess.run")
    def test_scan_with_pip_audit_with_vulnerabilities(self, mock_run):
        """Test scan_with_pip_audit with vulnerabilities"""
        audit_data = {
            "dependencies": [
                {
                    "name": "requests",
                    "version": "2.25.0",
                    "vulnerabilities": [
                        {
                            "id": "CVE-2021-33503",
                            "severity": "HIGH",
                            "description": "Test vulnerability",
                            "fix_versions": ["2.26.0"],
                        }
                    ],
                }
            ]
        }
        mock_run.return_value = Mock(returncode=1, stdout=json.dumps(audit_data), stderr="")

        scanner = DependencyScanner()
        results = scanner.scan_with_pip_audit()

        assert len(results) == 1
        assert results[0].package == "requests"
        assert results[0].vulnerability_id == "CVE-2021-33503"

    @patch("aitbc.dependency_scanner.subprocess.run")
    def test_scan_with_pip_audit_not_found(self, mock_run):
        """Test scan_with_pip_audit when pip-audit not found"""
        mock_run.side_effect = FileNotFoundError()

        scanner = DependencyScanner()
        results = scanner.scan_with_pip_audit()

        assert results == []

    @patch("aitbc.dependency_scanner.subprocess.run")
    def test_scan_with_pip_audit_timeout(self, mock_run):
        """Test scan_with_pip_audit when timeout occurs"""
        from subprocess import TimeoutExpired

        mock_run.side_effect = TimeoutExpired("pip-audit", 300)

        scanner = DependencyScanner()
        results = scanner.scan_with_pip_audit()

        assert results == []

    @patch("aitbc.dependency_scanner.subprocess.run")
    def test_scan_with_pip_audit_invalid_json(self, mock_run):
        """Test scan_with_pip_audit with invalid JSON output"""
        mock_run.return_value = Mock(returncode=1, stdout="invalid json", stderr="")

        scanner = DependencyScanner()
        results = scanner.scan_with_pip_audit()

        assert results == []

    @patch("aitbc.dependency_scanner.subprocess.run")
    def test_scan_with_bandit_no_issues(self, mock_run):
        """Test scan_with_bandit when no issues found"""
        mock_run.return_value = Mock(returncode=0, stdout=json.dumps({"results": []}), stderr="")

        scanner = DependencyScanner()
        results = scanner.scan_with_bandit()

        assert results == []

    @patch("aitbc.dependency_scanner.subprocess.run")
    def test_scan_with_bandit_with_issues(self, mock_run):
        """Test scan_with_bandit with security issues"""
        bandit_data = {
            "results": [{"code": "test code", "filename": "test.py", "issue_text": "Test issue", "severity": "HIGH"}]
        }
        mock_run.return_value = Mock(returncode=1, stdout=json.dumps(bandit_data), stderr="")

        scanner = DependencyScanner()
        results = scanner.scan_with_bandit()

        assert len(results) == 1
        assert results[0]["issue_text"] == "Test issue"

    @patch("aitbc.dependency_scanner.subprocess.run")
    def test_scan_with_bandit_not_found(self, mock_run):
        """Test scan_with_bandit when bandit not found"""
        mock_run.side_effect = FileNotFoundError()

        scanner = DependencyScanner()
        results = scanner.scan_with_bandit()

        assert results == []

    @patch("aitbc.dependency_scanner.subprocess.run")
    def test_scan_with_bandit_custom_dir(self, mock_run):
        """Test scan_with_bandit with custom target directory"""
        mock_run.return_value = Mock(returncode=0, stdout=json.dumps({"results": []}), stderr="")

        scanner = DependencyScanner()
        results = scanner.scan_with_bandit(target_dir=Path("/custom/path"))

        assert results == []
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0]
        assert "/custom/path" in call_args[0]

    def test_parse_pip_audit_output(self):
        """Test _parse_pip_audit_output method"""
        audit_data = {
            "dependencies": [
                {
                    "name": "requests",
                    "version": "2.25.0",
                    "vulnerabilities": [
                        {
                            "id": "CVE-2021-33503",
                            "severity": "HIGH",
                            "description": "Test vulnerability",
                            "fix_versions": ["2.26.0"],
                        }
                    ],
                }
            ]
        }

        scanner = DependencyScanner()
        results = scanner._parse_pip_audit_output(audit_data)

        assert len(results) == 1
        assert results[0].package == "requests"
        assert results[0].fix_available is True
        assert results[0].fixed_version == "2.26.0"

    def test_parse_pip_audit_output_no_fix(self):
        """Test _parse_pip_audit_output with no fix available"""
        audit_data = {
            "dependencies": [
                {
                    "name": "requests",
                    "version": "2.25.0",
                    "vulnerabilities": [
                        {"id": "CVE-2021-33503", "severity": "HIGH", "description": "Test vulnerability", "fix_versions": []}
                    ],
                }
            ]
        }

        scanner = DependencyScanner()
        results = scanner._parse_pip_audit_output(audit_data)

        assert len(results) == 1
        assert results[0].fix_available is False
        assert results[0].fixed_version is None

    @patch("aitbc.dependency_scanner.DependencyScanner.scan_with_pip_audit")
    @patch("aitbc.dependency_scanner.DependencyScanner.scan_with_bandit")
    def test_generate_report(self, mock_bandit, mock_pip_audit):
        """Test generate_report method"""
        mock_pip_audit.return_value = [
            VulnerabilityReport(
                package="requests",
                version="2.25.0",
                vulnerability_id="CVE-2021-33503",
                severity="HIGH",
                description="Test",
                fix_available=True,
                fixed_version="2.26.0",
            )
        ]
        mock_bandit.return_value = [{"issue_text": "Test issue"}]

        scanner = DependencyScanner()
        report = scanner.generate_report()

        assert "timestamp" in report
        assert report["dependency_vulnerabilities"] == 1
        assert report["security_issues"] == 1
        assert "severity_breakdown" in report
        assert "vulnerabilities" in report
        assert "bandit_issues" in report

    def test_save_report(self):
        """Test save_report method"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "report.json"

            scanner = DependencyScanner()

            with patch.object(scanner, "generate_report", return_value={"test": "data"}):
                scanner.save_report(output_file)

            assert output_file.exists()
            with open(output_file) as f:
                content = json.load(f)
                assert content == {"test": "data"}


class TestUtilityFunctions:
    """Test utility functions"""

    @patch("aitbc.dependency_scanner.DependencyScanner")
    def test_run_dependency_scan(self, mock_scanner_class):
        """Test run_dependency_scan function"""
        mock_scanner = Mock()
        mock_scanner.generate_report.return_value = {"test": "data"}
        mock_scanner_class.return_value = mock_scanner

        report = run_dependency_scan()

        assert report == {"test": "data"}
        mock_scanner.generate_report.assert_called_once()

    @patch("aitbc.dependency_scanner.DependencyScanner")
    def test_run_dependency_scan_with_output(self, mock_scanner_class):
        """Test run_dependency_scan with output file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "report.json"

            mock_scanner = Mock()
            mock_scanner.generate_report.return_value = {"test": "data"}
            mock_scanner_class.return_value = mock_scanner

            report = run_dependency_scan(output_file=output_file)

            assert report == {"test": "data"}
            mock_scanner.save_report.assert_called_once_with(output_file)

    def test_check_vulnerability_thresholds_pass(self):
        """Test check_vulnerability_thresholds when within limits"""
        report = {"severity_breakdown": {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 5, "LOW": 10}}

        result = check_vulnerability_thresholds(report)
        assert result is True

    def test_check_vulnerability_thresholds_critical_exceeded(self):
        """Test check_vulnerability_thresholds when critical exceeded"""
        report = {"severity_breakdown": {"CRITICAL": 1, "HIGH": 0, "MEDIUM": 0, "LOW": 0}}

        result = check_vulnerability_thresholds(report, max_critical=0)
        assert result is False

    def test_check_vulnerability_thresholds_high_exceeded(self):
        """Test check_vulnerability_thresholds when high exceeded"""
        report = {"severity_breakdown": {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 0, "LOW": 0}}

        result = check_vulnerability_thresholds(report, max_high=0)
        assert result is False

    def test_check_vulnerability_thresholds_custom_limits(self):
        """Test check_vulnerability_thresholds with custom limits"""
        report = {"severity_breakdown": {"CRITICAL": 0, "HIGH": 5, "MEDIUM": 15, "LOW": 60}}

        result = check_vulnerability_thresholds(report, max_critical=0, max_high=10, max_medium=20, max_low=100)
        assert result is True

    def test_check_vulnerability_thresholds_empty_report(self):
        """Test check_vulnerability_thresholds with empty report"""
        report = {}

        result = check_vulnerability_thresholds(report)
        assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
