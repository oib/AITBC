"""Integration tests for plugin security service"""

import pytest
import sys
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from datetime import datetime


from main import app, SecurityScan, scan_reports, security_policies, scan_queue, vulnerability_database


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test"""
    scan_reports.clear()
    security_policies.clear()
    scan_queue.clear()
    vulnerability_database.clear()
    yield
    scan_reports.clear()
    security_policies.clear()
    scan_queue.clear()
    vulnerability_database.clear()


@pytest.mark.integration
def test_root_endpoint():
    """Test root endpoint"""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "AITBC Plugin Security Service"
    assert data["status"] == "running"


@pytest.mark.integration
def test_health_check_endpoint():
    """Test health check endpoint"""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "total_scans" in data
    assert "queue_size" in data


@pytest.mark.integration
def test_initiate_security_scan():
    """Test initiating a security scan"""
    client = TestClient(app)
    scan = SecurityScan(
        plugin_id="plugin_123",
        version="1.0.0",
        plugin_type="cli",
        scan_type="comprehensive",
        priority="high"
    )
    response = client.post("/api/v1/security/scan", json=scan.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["scan_id"]
    assert data["status"] == "queued"
    assert "queue_position" in data


@pytest.mark.integration
def test_get_scan_status_queued():
    """Test getting scan status for queued scan"""
    client = TestClient(app)
    scan = SecurityScan(
        plugin_id="plugin_123",
        version="1.0.0",
        plugin_type="cli",
        scan_type="basic",
        priority="medium"
    )
    scan_response = client.post("/api/v1/security/scan", json=scan.model_dump())
    scan_id = scan_response.json()["scan_id"]
    
    response = client.get(f"/api/v1/security/scan/{scan_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["scan_id"] == scan_id
    assert data["status"] == "queued"


@pytest.mark.integration
def test_get_scan_status_not_found():
    """Test getting scan status for nonexistent scan"""
    client = TestClient(app)
    response = client.get("/api/v1/security/scan/nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_list_security_reports():
    """Test listing security reports"""
    client = TestClient(app)
    response = client.get("/api/v1/security/reports")
    assert response.status_code == 200
    data = response.json()
    assert "reports" in data
    assert "total_reports" in data


@pytest.mark.integration
def test_list_security_reports_with_filters():
    """Test listing security reports with filters"""
    client = TestClient(app)
    response = client.get("/api/v1/security/reports?plugin_id=plugin_123&status=completed")
    assert response.status_code == 200
    data = response.json()
    assert "reports" in data


@pytest.mark.integration
def test_list_vulnerabilities():
    """Test listing vulnerabilities"""
    client = TestClient(app)
    response = client.get("/api/v1/security/vulnerabilities")
    assert response.status_code == 200
    data = response.json()
    assert "vulnerabilities" in data
    assert "total_vulnerabilities" in data


@pytest.mark.integration
def test_list_vulnerabilities_with_filters():
    """Test listing vulnerabilities with filters"""
    client = TestClient(app)
    response = client.get("/api/v1/security/vulnerabilities?severity=high&plugin_id=plugin_123")
    assert response.status_code == 200
    data = response.json()
    assert "vulnerabilities" in data


@pytest.mark.integration
def test_create_security_policy():
    """Test creating a security policy"""
    client = TestClient(app)
    policy = {
        "name": "Test Policy",
        "description": "A test security policy",
        "rules": ["rule1", "rule2"],
        "severity_thresholds": {
            "critical": 0,
            "high": 0,
            "medium": 5,
            "low": 10
        },
        "plugin_types": ["cli", "web"]
    }
    response = client.post("/api/v1/security/policies", json=policy)
    assert response.status_code == 200
    data = response.json()
    assert data["policy_id"]
    assert data["name"] == "Test Policy"
    assert data["active"] is True


@pytest.mark.integration
def test_list_security_policies():
    """Test listing security policies"""
    client = TestClient(app)
    response = client.get("/api/v1/security/policies")
    assert response.status_code == 200
    data = response.json()
    assert "policies" in data
    assert "total_policies" in data


@pytest.mark.integration
def test_get_security_dashboard():
    """Test getting security dashboard"""
    client = TestClient(app)
    response = client.get("/api/v1/security/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert "dashboard" in data
    assert "total_scans" in data["dashboard"]
    assert "vulnerabilities" in data["dashboard"]


@pytest.mark.integration
def test_scan_priority_queueing():
    """Test that scans are queued by priority"""
    client = TestClient(app)
    
    # Add low priority scan
    scan_low = SecurityScan(
        plugin_id="plugin_low",
        version="1.0.0",
        plugin_type="cli",
        scan_type="basic",
        priority="low"
    )
    client.post("/api/v1/security/scan", json=scan_low.model_dump())
    
    # Add critical priority scan
    scan_critical = SecurityScan(
        plugin_id="plugin_critical",
        version="1.0.0",
        plugin_type="cli",
        scan_type="basic",
        priority="critical"
    )
    response = client.post("/api/v1/security/scan", json=scan_critical.model_dump())
    scan_id = response.json()["scan_id"]
    
    # Critical scan should be at position 1
    response = client.get(f"/api/v1/security/scan/{scan_id}")
    data = response.json()
    assert data["queue_position"] == 1
