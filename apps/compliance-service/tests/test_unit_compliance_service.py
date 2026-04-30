"""Unit tests for compliance service"""

import pytest
import sys
import sys
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import datetime, UTC


from main import app, KYCRequest, ComplianceReport, TransactionMonitoring, calculate_transaction_risk, check_suspicious_patterns


@pytest.mark.unit
def test_app_initialization():
    """Test that the FastAPI app initializes correctly"""
    assert app is not None
    assert app.title == "AITBC Compliance Service"
    assert app.version == "1.0.0"


@pytest.mark.unit
def test_kyc_request_model():
    """Test KYCRequest model"""
    kyc = KYCRequest(
        user_id="user123",
        name="John Doe",
        email="john@example.com",
        document_type="passport",
        document_number="ABC123",
        address={"street": "123 Main St", "city": "New York", "country": "USA"}
    )
    assert kyc.user_id == "user123"
    assert kyc.name == "John Doe"
    assert kyc.email == "john@example.com"
    assert kyc.document_type == "passport"
    assert kyc.document_number == "ABC123"
    assert kyc.address["city"] == "New York"


@pytest.mark.unit
def test_compliance_report_model():
    """Test ComplianceReport model"""
    report = ComplianceReport(
        report_type="suspicious_activity",
        description="Suspicious transaction detected",
        severity="high",
        details={"transaction_id": "tx123"}
    )
    assert report.report_type == "suspicious_activity"
    assert report.description == "Suspicious transaction detected"
    assert report.severity == "high"
    assert report.details["transaction_id"] == "tx123"


@pytest.mark.unit
def test_transaction_monitoring_model():
    """Test TransactionMonitoring model"""
    tx = TransactionMonitoring(
        transaction_id="tx123",
        user_id="user123",
        amount=1000.0,
        currency="BTC",
        counterparty="counterparty1",
        timestamp=datetime.now(datetime.UTC)
    )
    assert tx.transaction_id == "tx123"
    assert tx.user_id == "user123"
    assert tx.amount == 1000.0
    assert tx.currency == "BTC"
    assert tx.counterparty == "counterparty1"


@pytest.mark.unit
def test_calculate_transaction_risk_low():
    """Test risk calculation for low risk transaction"""
    tx = TransactionMonitoring(
        transaction_id="tx123",
        user_id="user123",
        amount=50.0,
        currency="BTC",
        counterparty="counterparty1",
        timestamp=datetime(2026, 1, 1, 10, 0, 0)  # Business hours
    )
    risk = calculate_transaction_risk(tx)
    assert risk == "low"


@pytest.mark.unit
def test_calculate_transaction_risk_medium():
    """Test risk calculation for medium risk transaction"""
    tx = TransactionMonitoring(
        transaction_id="tx123",
        user_id="user123",
        amount=5000.0,
        currency="BTC",
        counterparty="counterparty1",
        timestamp=datetime(2026, 1, 1, 10, 0, 0)
    )
    risk = calculate_transaction_risk(tx)
    assert risk == "medium"


@pytest.mark.unit
def test_calculate_transaction_risk_high():
    """Test risk calculation for high risk transaction"""
    tx = TransactionMonitoring(
        transaction_id="tx123",
        user_id="user123",
        amount=20000.0,
        currency="BTC",
        counterparty="counterparty1",
        timestamp=datetime(2026, 1, 1, 8, 0, 0)  # Outside business hours
    )
    risk = calculate_transaction_risk(tx)
    assert risk == "high"


@pytest.mark.unit
def test_check_suspicious_patterns_high_value():
    """Test suspicious pattern detection for high value"""
    tx = TransactionMonitoring(
        transaction_id="tx123",
        user_id="user123",
        amount=100000.0,
        currency="BTC",
        counterparty="counterparty1",
        timestamp=datetime.now(datetime.UTC)
    )
    flags = check_suspicious_patterns(tx)
    assert "high_value_transaction" in flags


@pytest.mark.unit
def test_check_suspicious_patterns_high_risk_counterparty():
    """Test suspicious pattern detection for high risk counterparty"""
    tx = TransactionMonitoring(
        transaction_id="tx123",
        user_id="user123",
        amount=1000.0,
        currency="BTC",
        counterparty="high_risk_entity_1",
        timestamp=datetime.now(datetime.UTC)
    )
    flags = check_suspicious_patterns(tx)
    assert "high_risk_counterparty" in flags


@pytest.mark.unit
def test_check_suspicious_patterns_none():
    """Test suspicious pattern detection with no flags"""
    tx = TransactionMonitoring(
        transaction_id="tx123",
        user_id="user123",
        amount=1000.0,
        currency="BTC",
        counterparty="safe_counterparty",
        timestamp=datetime.now(datetime.UTC)
    )
    flags = check_suspicious_patterns(tx)
    assert len(flags) == 0
