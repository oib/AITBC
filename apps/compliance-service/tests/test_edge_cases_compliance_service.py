"""Edge case and error handling tests for compliance service"""

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


@pytest.mark.unit
def test_kyc_request_empty_fields():
    """Test KYCRequest with empty fields"""
    kyc = KYCRequest(
        user_id="",
        name="",
        email="",
        document_type="",
        document_number="",
        address={}
    )
    assert kyc.user_id == ""
    assert kyc.name == ""


@pytest.mark.unit
def test_compliance_report_invalid_severity():
    """Test ComplianceReport with invalid severity"""
    report = ComplianceReport(
        report_type="test",
        description="test",
        severity="invalid",  # Not in low/medium/high/critical
        details={}
    )
    assert report.severity == "invalid"


@pytest.mark.unit
def test_transaction_monitoring_zero_amount():
    """Test TransactionMonitoring with zero amount"""
    tx = TransactionMonitoring(
        transaction_id="tx123",
        user_id="user123",
        amount=0.0,
        currency="BTC",
        counterparty="counterparty1",
        timestamp=datetime.utcnow()
    )
    assert tx.amount == 0.0


@pytest.mark.unit
def test_transaction_monitoring_negative_amount():
    """Test TransactionMonitoring with negative amount"""
    tx = TransactionMonitoring(
        transaction_id="tx123",
        user_id="user123",
        amount=-1000.0,
        currency="BTC",
        counterparty="counterparty1",
        timestamp=datetime.utcnow()
    )
    assert tx.amount == -1000.0


@pytest.mark.integration
def test_kyc_with_missing_address_fields():
    """Test KYC submission with missing address fields"""
    client = TestClient(app)
    kyc = KYCRequest(
        user_id="user123",
        name="John Doe",
        email="john@example.com",
        document_type="passport",
        document_number="ABC123",
        address={"city": "New York"}  # Missing other fields
    )
    response = client.post("/api/v1/kyc/submit", json=kyc.model_dump())
    assert response.status_code == 200


@pytest.mark.integration
def test_compliance_report_empty_details():
    """Test compliance report with empty details"""
    client = TestClient(app)
    report = ComplianceReport(
        report_type="test",
        description="test",
        severity="low",
        details={}
    )
    response = client.post("/api/v1/compliance/report", json=report.model_dump())
    assert response.status_code == 200


@pytest.mark.integration
def test_compliance_rule_missing_fields():
    """Test compliance rule with missing fields"""
    client = TestClient(app)
    rule_data = {
        "name": "Test Rule"
        # Missing description, type, etc.
    }
    response = client.post("/api/v1/rules/create", json=rule_data)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Rule"


@pytest.mark.integration
def test_dashboard_with_no_data():
    """Test dashboard with no data"""
    client = TestClient(app)
    response = client.get("/api/v1/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_users"] == 0
    assert data["summary"]["total_reports"] == 0
    assert data["summary"]["total_transactions"] == 0


@pytest.mark.integration
def test_monitor_transaction_with_future_timestamp():
    """Test monitoring transaction with future timestamp"""
    client = TestClient(app)
    tx = TransactionMonitoring(
        transaction_id="tx123",
        user_id="user123",
        amount=1000.0,
        currency="BTC",
        counterparty="counterparty1",
        timestamp=datetime(2030, 1, 1)  # Future timestamp
    )
    response = client.post("/api/v1/monitoring/transaction", json=tx.model_dump(mode='json'))
    assert response.status_code == 200


@pytest.mark.integration
def test_monitor_transaction_with_past_timestamp():
    """Test monitoring transaction with past timestamp"""
    client = TestClient(app)
    tx = TransactionMonitoring(
        transaction_id="tx123",
        user_id="user123",
        amount=1000.0,
        currency="BTC",
        counterparty="counterparty1",
        timestamp=datetime(2020, 1, 1)  # Past timestamp
    )
    response = client.post("/api/v1/monitoring/transaction", json=tx.model_dump(mode='json'))
    assert response.status_code == 200


@pytest.mark.integration
def test_kyc_list_with_multiple_records():
    """Test listing KYC with multiple records"""
    client = TestClient(app)
    
    # Create multiple KYC records
    for i in range(5):
        kyc = KYCRequest(
            user_id=f"user{i}",
            name=f"User {i}",
            email=f"user{i}@example.com",
            document_type="passport",
            document_number=f"ABC{i}",
            address={"city": "New York"}
        )
        client.post("/api/v1/kyc/submit", json=kyc.model_dump())
    
    response = client.get("/api/v1/kyc")
    assert response.status_code == 200
    data = response.json()
    assert data["total_records"] == 5
    assert data["approved"] == 5
