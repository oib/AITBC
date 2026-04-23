"""Integration tests for compliance service"""

import pytest
import sys
import sys
from pathlib import Path
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from datetime import datetime


from main import app, KYCRequest, ComplianceReport, TransactionMonitoring, kyc_records, compliance_reports, suspicious_transactions, compliance_rules


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test"""
    kyc_records.clear()
    compliance_reports.clear()
    suspicious_transactions.clear()
    compliance_rules.clear()
    yield
    kyc_records.clear()
    compliance_reports.clear()
    suspicious_transactions.clear()
    compliance_rules.clear()


@pytest.mark.integration
def test_root_endpoint():
    """Test root endpoint"""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "AITBC Compliance Service"
    assert data["status"] == "running"


@pytest.mark.integration
def test_health_check_endpoint():
    """Test health check endpoint"""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "kyc_records" in data
    assert "compliance_reports" in data


@pytest.mark.integration
def test_submit_kyc():
    """Test KYC submission"""
    client = TestClient(app)
    kyc = KYCRequest(
        user_id="user123",
        name="John Doe",
        email="john@example.com",
        document_type="passport",
        document_number="ABC123",
        address={"street": "123 Main St", "city": "New York", "country": "USA"}
    )
    response = client.post("/api/v1/kyc/submit", json=kyc.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "user123"
    assert data["status"] == "approved"
    assert data["risk_score"] == "low"


@pytest.mark.integration
def test_submit_duplicate_kyc():
    """Test submitting duplicate KYC"""
    client = TestClient(app)
    kyc = KYCRequest(
        user_id="user123",
        name="John Doe",
        email="john@example.com",
        document_type="passport",
        document_number="ABC123",
        address={"street": "123 Main St", "city": "New York", "country": "USA"}
    )
    
    # First submission
    client.post("/api/v1/kyc/submit", json=kyc.model_dump())
    
    # Second submission should fail
    response = client.post("/api/v1/kyc/submit", json=kyc.model_dump())
    assert response.status_code == 400


@pytest.mark.integration
def test_get_kyc_status():
    """Test getting KYC status"""
    client = TestClient(app)
    kyc = KYCRequest(
        user_id="user123",
        name="John Doe",
        email="john@example.com",
        document_type="passport",
        document_number="ABC123",
        address={"street": "123 Main St", "city": "New York", "country": "USA"}
    )
    
    # Submit KYC first
    client.post("/api/v1/kyc/submit", json=kyc.model_dump())
    
    # Get KYC status
    response = client.get("/api/v1/kyc/user123")
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "user123"
    assert data["status"] == "approved"


@pytest.mark.integration
def test_get_kyc_status_not_found():
    """Test getting KYC status for nonexistent user"""
    client = TestClient(app)
    response = client.get("/api/v1/kyc/nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_list_kyc_records():
    """Test listing KYC records"""
    client = TestClient(app)
    response = client.get("/api/v1/kyc")
    assert response.status_code == 200
    data = response.json()
    assert "kyc_records" in data
    assert "total_records" in data


@pytest.mark.integration
def test_create_compliance_report():
    """Test creating compliance report"""
    client = TestClient(app)
    report = ComplianceReport(
        report_type="suspicious_activity",
        description="Suspicious transaction detected",
        severity="high",
        details={"transaction_id": "tx123"}
    )
    response = client.post("/api/v1/compliance/report", json=report.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["severity"] == "high"
    assert data["status"] == "created"


@pytest.mark.integration
def test_list_compliance_reports():
    """Test listing compliance reports"""
    client = TestClient(app)
    response = client.get("/api/v1/compliance/reports")
    assert response.status_code == 200
    data = response.json()
    assert "reports" in data
    assert "total_reports" in data


@pytest.mark.integration
def test_monitor_transaction():
    """Test transaction monitoring"""
    client = TestClient(app)
    tx = TransactionMonitoring(
        transaction_id="tx123",
        user_id="user123",
        amount=1000.0,
        currency="BTC",
        counterparty="counterparty1",
        timestamp=datetime.utcnow()
    )
    response = client.post("/api/v1/monitoring/transaction", json=tx.model_dump(mode='json'))
    assert response.status_code == 200
    data = response.json()
    assert data["transaction_id"] == "tx123"
    assert "risk_score" in data


@pytest.mark.integration
def test_monitor_suspicious_transaction():
    """Test monitoring suspicious transaction"""
    client = TestClient(app)
    tx = TransactionMonitoring(
        transaction_id="tx123",
        user_id="user123",
        amount=100000.0,
        currency="BTC",
        counterparty="high_risk_entity_1",
        timestamp=datetime.utcnow()
    )
    response = client.post("/api/v1/monitoring/transaction", json=tx.model_dump(mode='json'))
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "flagged"
    assert len(data["flags"]) > 0


@pytest.mark.integration
def test_list_monitored_transactions():
    """Test listing monitored transactions"""
    client = TestClient(app)
    response = client.get("/api/v1/monitoring/transactions")
    assert response.status_code == 200
    data = response.json()
    assert "transactions" in data
    assert "total_transactions" in data


@pytest.mark.integration
def test_create_compliance_rule():
    """Test creating compliance rule"""
    client = TestClient(app)
    rule_data = {
        "name": "High Value Transaction Rule",
        "description": "Flag transactions over $50,000",
        "type": "transaction_monitoring",
        "conditions": {"min_amount": 50000},
        "actions": ["flag", "report"],
        "severity": "high"
    }
    response = client.post("/api/v1/rules/create", json=rule_data)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "High Value Transaction Rule"
    assert data["active"] is True


@pytest.mark.integration
def test_list_compliance_rules():
    """Test listing compliance rules"""
    client = TestClient(app)
    response = client.get("/api/v1/rules")
    assert response.status_code == 200
    data = response.json()
    assert "rules" in data
    assert "total_rules" in data


@pytest.mark.integration
def test_compliance_dashboard():
    """Test compliance dashboard"""
    client = TestClient(app)
    response = client.get("/api/v1/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "risk_distribution" in data
    assert "recent_activity" in data
