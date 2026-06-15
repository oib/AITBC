"""Tests for alerting module"""

import sys
from pathlib import Path

# Add coordinator path for imports
coordinator_path = Path("/opt/aitbc/apps/agent-coordinator/src")
if str(coordinator_path) not in sys.path:
    sys.path.insert(0, str(coordinator_path))

import pytest
from datetime import UTC, datetime, timedelta

from app.monitoring.alerting import (
    AlertSeverity,
    AlertStatus,
    NotificationChannel,
    Alert,
    AlertRule,
    SLAMonitor,
)


class TestAlertSeverity:
    """Test AlertSeverity enum"""

    def test_alert_severity_values(self):
        """Test AlertSeverity enum values"""
        assert AlertSeverity.CRITICAL.value == "critical"
        assert AlertSeverity.WARNING.value == "warning"
        assert AlertSeverity.INFO.value == "info"
        assert AlertSeverity.DEBUG.value == "debug"


class TestAlertStatus:
    """Test AlertStatus enum"""

    def test_alert_status_values(self):
        """Test AlertStatus enum values"""
        assert AlertStatus.ACTIVE.value == "active"
        assert AlertStatus.RESOLVED.value == "resolved"
        assert AlertStatus.SUPPRESSED.value == "suppressed"


class TestNotificationChannel:
    """Test NotificationChannel enum"""

    def test_notification_channel_values(self):
        """Test NotificationChannel enum values"""
        assert NotificationChannel.EMAIL.value == "email"
        assert NotificationChannel.SLACK.value == "slack"
        assert NotificationChannel.WEBHOOK.value == "webhook"
        assert NotificationChannel.LOG.value == "log"


class TestAlert:
    """Test Alert dataclass"""

    def test_alert_creation(self):
        """Test creating Alert with default values"""
        now = datetime.now(UTC)
        alert = Alert(
            alert_id="alert-1",
            name="Test Alert",
            description="A test alert",
            severity=AlertSeverity.WARNING,
            status=AlertStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        assert alert.alert_id == "alert-1"
        assert alert.name == "Test Alert"
        assert alert.description == "A test alert"
        assert alert.severity == AlertSeverity.WARNING
        assert alert.status == AlertStatus.ACTIVE
        assert alert.labels == {}
        assert alert.annotations == {}
        assert alert.source == "aitbc-agent-coordinator"
        assert alert.resolved_at is None

    def test_alert_with_values(self):
        """Test creating Alert with custom values"""
        now = datetime.now(UTC)
        alert = Alert(
            alert_id="alert-1",
            name="Test Alert",
            description="A test alert",
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.RESOLVED,
            created_at=now,
            updated_at=now,
            resolved_at=now,
            labels={"env": "prod"},
            annotations={"ticket": "123"},
            source="custom-source",
        )
        assert alert.severity == AlertSeverity.CRITICAL
        assert alert.status == AlertStatus.RESOLVED
        assert alert.resolved_at == now
        assert alert.labels == {"env": "prod"}
        assert alert.annotations == {"ticket": "123"}
        assert alert.source == "custom-source"

    def test_alert_to_dict(self):
        """Test converting Alert to dictionary"""
        now = datetime.now(UTC)
        alert = Alert(
            alert_id="alert-1",
            name="Test Alert",
            description="A test alert",
            severity=AlertSeverity.WARNING,
            status=AlertStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        result = alert.to_dict()
        assert result["alert_id"] == "alert-1"
        assert result["name"] == "Test Alert"
        assert result["severity"] == "warning"
        assert result["status"] == "active"
        assert isinstance(result["created_at"], str)
        assert isinstance(result["updated_at"], str)
        assert result["resolved_at"] is None

    def test_alert_to_dict_with_resolved(self):
        """Test converting Alert with resolved_at to dictionary"""
        now = datetime.now(UTC)
        alert = Alert(
            alert_id="alert-1",
            name="Test Alert",
            description="A test alert",
            severity=AlertSeverity.WARNING,
            status=AlertStatus.RESOLVED,
            created_at=now,
            updated_at=now,
            resolved_at=now,
        )
        result = alert.to_dict()
        assert result["resolved_at"] == now.isoformat()


class TestAlertRule:
    """Test AlertRule dataclass"""

    def test_alert_rule_creation(self):
        """Test creating AlertRule with default values"""
        rule = AlertRule(
            rule_id="rule-1",
            name="Test Rule",
            description="A test rule",
            severity=AlertSeverity.WARNING,
            condition="cpu > 90",
            threshold=90.0,
            duration=timedelta(minutes=5),
        )
        assert rule.rule_id == "rule-1"
        assert rule.name == "Test Rule"
        assert rule.description == "A test rule"
        assert rule.severity == AlertSeverity.WARNING
        assert rule.condition == "cpu > 90"
        assert rule.threshold == 90.0
        assert rule.duration == timedelta(minutes=5)
        assert rule.enabled is True
        assert rule.labels == {}
        assert rule.annotations == {}
        assert rule.notification_channels == []

    def test_alert_rule_with_values(self):
        """Test creating AlertRule with custom values"""
        rule = AlertRule(
            rule_id="rule-1",
            name="Test Rule",
            description="A test rule",
            severity=AlertSeverity.CRITICAL,
            condition="memory > 95",
            threshold=95.0,
            duration=timedelta(minutes=10),
            enabled=False,
            labels={"service": "api"},
            annotations={"runbook": "https://example.com"},
            notification_channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK],
        )
        assert rule.severity == AlertSeverity.CRITICAL
        assert rule.enabled is False
        assert rule.labels == {"service": "api"}
        assert rule.annotations == {"runbook": "https://example.com"}
        assert len(rule.notification_channels) == 2
        assert NotificationChannel.EMAIL in rule.notification_channels
        assert NotificationChannel.SLACK in rule.notification_channels

    def test_alert_rule_to_dict(self):
        """Test converting AlertRule to dictionary"""
        rule = AlertRule(
            rule_id="rule-1",
            name="Test Rule",
            description="A test rule",
            severity=AlertSeverity.WARNING,
            condition="cpu > 90",
            threshold=90.0,
            duration=timedelta(minutes=5),
        )
        result = rule.to_dict()
        assert result["rule_id"] == "rule-1"
        assert result["name"] == "Test Rule"
        assert result["severity"] == "warning"
        assert result["condition"] == "cpu > 90"
        assert result["threshold"] == 90.0
        assert result["duration_seconds"] == 300.0
        assert result["enabled"] is True
        assert result["notification_channels"] == []

    def test_alert_rule_to_dict_with_channels(self):
        """Test converting AlertRule with notification channels to dictionary"""
        rule = AlertRule(
            rule_id="rule-1",
            name="Test Rule",
            description="A test rule",
            severity=AlertSeverity.WARNING,
            condition="cpu > 90",
            threshold=90.0,
            duration=timedelta(minutes=5),
            notification_channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK],
        )
        result = rule.to_dict()
        assert result["notification_channels"] == ["email", "slack"]


class TestSLAMonitor:
    """Test SLAMonitor class"""

    def test_sla_monitor_initialization(self):
        """Test SLAMonitor initialization"""
        monitor = SLAMonitor()
        assert monitor.sla_rules == {}
        assert monitor.sla_metrics == {}
        assert monitor.violations == {}

    def test_add_sla_rule(self):
        """Test adding SLA rule"""
        monitor = SLAMonitor()
        monitor.add_sla_rule(
            sla_id="sla-1",
            name="API Response Time",
            target=0.5,
            window=timedelta(hours=1),
            metric="response_time",
        )
        assert "sla-1" in monitor.sla_rules
        assert monitor.sla_rules["sla-1"]["name"] == "API Response Time"
        assert monitor.sla_rules["sla-1"]["target"] == 0.5
        assert monitor.sla_rules["sla-1"]["metric"] == "response_time"
        assert "sla-1" in monitor.sla_metrics
        assert "sla-1" in monitor.violations

    def test_add_multiple_sla_rules(self):
        """Test adding multiple SLA rules"""
        monitor = SLAMonitor()
        monitor.add_sla_rule(
            sla_id="sla-1",
            name="API Response Time",
            target=0.5,
            window=timedelta(hours=1),
            metric="response_time",
        )
        monitor.add_sla_rule(
            sla_id="sla-2",
            name="Error Rate",
            target=0.01,
            window=timedelta(hours=24),
            metric="error_rate",
        )
        assert len(monitor.sla_rules) == 2
        assert "sla-1" in monitor.sla_rules
        assert "sla-2" in monitor.sla_rules
