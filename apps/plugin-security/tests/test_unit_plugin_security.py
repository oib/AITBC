"""Unit tests for plugin security service"""

import pytest
import sys
import sys
from pathlib import Path
from datetime import datetime


from main import app, SecurityScan, Vulnerability, SecurityReport, calculate_overall_score, generate_recommendations, get_severity_distribution, estimate_scan_time


@pytest.mark.unit
def test_app_initialization():
    """Test that the FastAPI app initializes correctly"""
    assert app is not None
    assert app.title == "AITBC Plugin Security Service"
    assert app.version == "1.0.0"


@pytest.mark.unit
def test_security_scan_model():
    """Test SecurityScan model"""
    scan = SecurityScan(
        plugin_id="plugin_123",
        version="1.0.0",
        plugin_type="cli",
        scan_type="comprehensive",
        priority="high"
    )
    assert scan.plugin_id == "plugin_123"
    assert scan.version == "1.0.0"
    assert scan.plugin_type == "cli"
    assert scan.scan_type == "comprehensive"
    assert scan.priority == "high"


@pytest.mark.unit
def test_vulnerability_model():
    """Test Vulnerability model"""
    vuln = Vulnerability(
        cve_id="CVE-2023-1234",
        severity="high",
        title="Buffer Overflow",
        description="Buffer overflow vulnerability",
        affected_file="file.py",
        line_number=42,
        recommendation="Update to latest version"
    )
    assert vuln.cve_id == "CVE-2023-1234"
    assert vuln.severity == "high"
    assert vuln.title == "Buffer Overflow"
    assert vuln.line_number == 42


@pytest.mark.unit
def test_vulnerability_model_optional_fields():
    """Test Vulnerability model with optional fields"""
    vuln = Vulnerability(
        cve_id=None,
        severity="low",
        title="Minor issue",
        description="Description",
        affected_file="file.py",
        line_number=None,
        recommendation="Fix it"
    )
    assert vuln.cve_id is None
    assert vuln.line_number is None


@pytest.mark.unit
def test_security_report_model():
    """Test SecurityReport model"""
    report = SecurityReport(
        scan_id="scan_123",
        plugin_id="plugin_123",
        version="1.0.0",
        scan_date=datetime.utcnow(),
        scan_duration=120.5,
        overall_score="passed",
        vulnerabilities=[],
        security_metrics={},
        recommendations=[]
    )
    assert report.scan_id == "scan_123"
    assert report.overall_score == "passed"
    assert report.scan_duration == 120.5


@pytest.mark.unit
def test_calculate_overall_score_passed():
    """Test calculate overall score with no vulnerabilities"""
    scan_result = {"vulnerabilities": []}
    score = calculate_overall_score(scan_result)
    assert score == "passed"


@pytest.mark.unit
def test_calculate_overall_score_critical():
    """Test calculate overall score with critical vulnerability"""
    scan_result = {
        "vulnerabilities": [
            {"severity": "critical"},
            {"severity": "low"}
        ]
    }
    score = calculate_overall_score(scan_result)
    assert score == "critical"


@pytest.mark.unit
def test_calculate_overall_score_failed():
    """Test calculate overall score with multiple high vulnerabilities"""
    scan_result = {
        "vulnerabilities": [
            {"severity": "high"},
            {"severity": "high"},
            {"severity": "high"}
        ]
    }
    score = calculate_overall_score(scan_result)
    assert score == "failed"


@pytest.mark.unit
def test_calculate_overall_score_warning():
    """Test calculate overall score with high and medium vulnerabilities"""
    scan_result = {
        "vulnerabilities": [
            {"severity": "high"},
            {"severity": "medium"},
            {"severity": "medium"},
            {"severity": "medium"},
            {"severity": "medium"},
            {"severity": "medium"}
        ]
    }
    score = calculate_overall_score(scan_result)
    assert score == "warning"


@pytest.mark.unit
def test_generate_recommendations_no_vulnerabilities():
    """Test generate recommendations with no vulnerabilities"""
    recommendations = generate_recommendations([])
    assert len(recommendations) == 1
    assert "No security issues detected" in recommendations[0]


@pytest.mark.unit
def test_generate_recommendations_critical():
    """Test generate recommendations with critical vulnerabilities"""
    vulnerabilities = [
        {"severity": "critical"},
        {"severity": "high"}
    ]
    recommendations = generate_recommendations(vulnerabilities)
    assert any("CRITICAL" in r for r in recommendations)
    assert any("HIGH" in r for r in recommendations)


@pytest.mark.unit
def test_get_severity_distribution():
    """Test get severity distribution"""
    vulnerabilities = [
        {"severity": "critical"},
        {"severity": "high"},
        {"severity": "high"},
        {"severity": "medium"},
        {"severity": "low"}
    ]
    distribution = get_severity_distribution(vulnerabilities)
    assert distribution["critical"] == 1
    assert distribution["high"] == 2
    assert distribution["medium"] == 1
    assert distribution["low"] == 1


@pytest.mark.unit
def test_estimate_scan_time_basic():
    """Test estimate scan time for basic scan"""
    time = estimate_scan_time("basic")
    assert time == "1-2 minutes"


@pytest.mark.unit
def test_estimate_scan_time_comprehensive():
    """Test estimate scan time for comprehensive scan"""
    time = estimate_scan_time("comprehensive")
    assert time == "5-10 minutes"


@pytest.mark.unit
def test_estimate_scan_time_deep():
    """Test estimate scan time for deep scan"""
    time = estimate_scan_time("deep")
    assert time == "15-30 minutes"


@pytest.mark.unit
def test_estimate_scan_time_unknown():
    """Test estimate scan time for unknown scan type"""
    time = estimate_scan_time("unknown")
    assert time == "5-10 minutes"
