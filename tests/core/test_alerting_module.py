"""
Tests for AITBC alerting module (alerting.py)
This module has 0% coverage and 415 statements.
"""

import asyncio
import importlib.util
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Load module directly by file path to avoid namespace conflicts
def load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

alerting = load_module_from_path(
    "aitbc.alerting",
    Path("/opt/aitbc/aitbc/alerting.py")
)


# ============================================================================
# Enum Tests
# ============================================================================

class TestAlertSeverity:
    """Test AlertSeverity enum"""

    def test_severity_values(self):
        assert alerting.AlertSeverity.INFO.value == "info"
        assert alerting.AlertSeverity.WARNING.value == "warning"
        assert alerting.AlertSeverity.ERROR.value == "error"
        assert alerting.AlertSeverity.CRITICAL.value == "critical"


class TestAlertStatus:
    """Test AlertStatus enum"""

    def test_status_values(self):
        assert alerting.AlertStatus.ACTIVE.value == "active"
        assert alerting.AlertStatus.ACKNOWLEDGED.value == "acknowledged"
        assert alerting.AlertStatus.RESOLVED.value == "resolved"


# ============================================================================
# Alert Dataclass Tests
# ============================================================================

class TestAlert:
    """Test Alert dataclass"""

    def test_alert_initialization(self):
        alert = alerting.Alert(
            id="test-1",
            severity=alerting.AlertSeverity.ERROR,
            title="Test Alert",
            message="Test message",
            source="test-source"
        )
        assert alert.id == "test-1"
        assert alert.severity == alerting.AlertSeverity.ERROR
        assert alert.title == "Test Alert"
        assert alert.message == "Test message"
        assert alert.source == "test-source"
        assert alert.status == alerting.AlertStatus.ACTIVE
        assert alert.metadata == {}

    def test_alert_with_metadata(self):
        alert = alerting.Alert(
            id="test-1",
            severity=alerting.AlertSeverity.ERROR,
            title="Test Alert",
            message="Test message",
            source="test-source",
            metadata={"key": "value"}
        )
        assert alert.metadata == {"key": "value"}

    def test_alert_to_dict(self):
        alert = alerting.Alert(
            id="test-1",
            severity=alerting.AlertSeverity.ERROR,
            title="Test Alert",
            message="Test message",
            source="test-source"
        )
        result = alert.to_dict()
        assert result["id"] == "test-1"
        assert result["severity"] == "error"
        assert result["title"] == "Test Alert"
        assert result["status"] == "active"
        assert "timestamp" in result

    def test_alert_with_acknowledgement(self):
        alert = alerting.Alert(
            id="test-1",
            severity=alerting.AlertSeverity.ERROR,
            title="Test Alert",
            message="Test message",
            source="test-source",
            acknowledged_by="user1",
            acknowledged_at=datetime.utcnow()
        )
        result = alert.to_dict()
        assert result["acknowledged_by"] == "user1"
        assert result["acknowledged_at"] is not None

    def test_alert_with_resolution(self):
        alert = alerting.Alert(
            id="test-1",
            severity=alerting.AlertSeverity.ERROR,
            title="Test Alert",
            message="Test message",
            source="test-source",
            resolved_at=datetime.utcnow()
        )
        result = alert.to_dict()
        assert result["resolved_at"] is not None


# ============================================================================
# Alert Channel Tests
# ============================================================================

class TestAlertChannel:
    """Test AlertChannel base class"""

    def test_alert_channel_not_implemented(self):
        channel = alerting.AlertChannel()
        with pytest.raises(NotImplementedError):
            asyncio.run(channel.send(alerting.Alert(
                id="test",
                severity=alerting.AlertSeverity.INFO,
                title="Test",
                message="Test",
                source="test"
            )))


class TestLogAlertChannel:
    """Test LogAlertChannel"""

    def test_log_alert_channel_info(self):
        channel = alerting.LogAlertChannel()
        alert = alerting.Alert(
            id="test-1",
            severity=alerting.AlertSeverity.INFO,
            title="Info Alert",
            message="Info message",
            source="test"
        )
        result = asyncio.run(channel.send(alert))
        assert result is True

    def test_log_alert_channel_warning(self):
        channel = alerting.LogAlertChannel()
        alert = alerting.Alert(
            id="test-1",
            severity=alerting.AlertSeverity.WARNING,
            title="Warning Alert",
            message="Warning message",
            source="test"
        )
        result = asyncio.run(channel.send(alert))
        assert result is True

    def test_log_alert_channel_error(self):
        channel = alerting.LogAlertChannel()
        alert = alerting.Alert(
            id="test-1",
            severity=alerting.AlertSeverity.ERROR,
            title="Error Alert",
            message="Error message",
            source="test"
        )
        result = asyncio.run(channel.send(alert))
        assert result is True

    def test_log_alert_channel_critical(self):
        channel = alerting.LogAlertChannel()
        alert = alerting.Alert(
            id="test-1",
            severity=alerting.AlertSeverity.CRITICAL,
            title="Critical Alert",
            message="Critical message",
            source="test"
        )
        result = asyncio.run(channel.send(alert))
        assert result is True


class TestWebhookAlertChannel:
    """Test WebhookAlertChannel"""

    def test_webhook_channel_initialization(self):
        channel = alerting.WebhookAlertChannel("https://example.com/webhook")
        assert channel.url == "https://example.com/webhook"
        assert channel.headers == {}

    def test_webhook_channel_with_headers(self):
        headers = {"Authorization": "Bearer token"}
        channel = alerting.WebhookAlertChannel("https://example.com/webhook", headers)
        assert channel.headers == headers

    def test_webhook_channel_send_success(self):
        # Skip if httpx is not available
        try:
            import httpx
        except ImportError:
            pytest.skip("httpx not available")
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.raise_for_status = Mock()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            channel = alerting.WebhookAlertChannel("https://example.com/webhook")
            alert = alerting.Alert(
                id="test-1",
                severity=alerting.AlertSeverity.ERROR,
                title="Test Alert",
                message="Test message",
                source="test"
            )
            result = asyncio.run(channel.send(alert))
            assert result is True

    def test_webhook_channel_send_failure(self):
        # Skip if httpx is not available
        try:
            import httpx
        except ImportError:
            pytest.skip("httpx not available")
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=Exception("Network error"))
            
            channel = alerting.WebhookAlertChannel("https://example.com/webhook")
            alert = alerting.Alert(
                id="test-1",
                severity=alerting.AlertSeverity.ERROR,
                title="Test Alert",
                message="Test message",
                source="test"
            )
            result = asyncio.run(channel.send(alert))
            assert result is False


# ============================================================================
# Alert Rule Tests
# ============================================================================

class TestAlertRule:
    """Test AlertRule class"""

    def test_alert_rule_initialization(self):
        condition = lambda: True
        rule = alerting.AlertRule(
            name="test-rule",
            condition=condition,
            severity=alerting.AlertSeverity.WARNING,
            title_template="Test Alert",
            message_template="Test message",
            source="test-source"
        )
        assert rule.name == "test-rule"
        assert rule.condition == condition
        assert rule.severity == alerting.AlertSeverity.WARNING
        assert rule.check_interval == 60
        assert rule.cooldown == 300
        assert rule.enabled is True
        assert rule.last_fired is None

    def test_alert_rule_custom_interval(self):
        condition = lambda: True
        rule = alerting.AlertRule(
            name="test-rule",
            condition=condition,
            severity=alerting.AlertSeverity.WARNING,
            title_template="Test Alert",
            message_template="Test message",
            source="test-source",
            check_interval=30,
            cooldown=600
        )
        assert rule.check_interval == 30
        assert rule.cooldown == 600

    def test_should_fire_condition_true(self):
        rule = alerting.AlertRule(
            name="test-rule",
            condition=lambda: True,
            severity=alerting.AlertSeverity.WARNING,
            title_template="Test Alert",
            message_template="Test message",
            source="test-source"
        )
        assert rule.should_fire() is True

    def test_should_fire_condition_false(self):
        rule = alerting.AlertRule(
            name="test-rule",
            condition=lambda: False,
            severity=alerting.AlertSeverity.WARNING,
            title_template="Test Alert",
            message_template="Test message",
            source="test-source"
        )
        assert rule.should_fire() is False

    def test_should_fire_disabled(self):
        rule = alerting.AlertRule(
            name="test-rule",
            condition=lambda: True,
            severity=alerting.AlertSeverity.WARNING,
            title_template="Test Alert",
            message_template="Test message",
            source="test-source"
        )
        rule.enabled = False
        assert rule.should_fire() is False

    def test_should_fire_in_cooldown(self):
        rule = alerting.AlertRule(
            name="test-rule",
            condition=lambda: True,
            severity=alerting.AlertSeverity.WARNING,
            title_template="Test Alert",
            message_template="Test message",
            source="test-source",
            cooldown=60
        )
        rule.last_fired = datetime.utcnow()
        assert rule.should_fire() is False

    def test_should_fire_cooldown_expired(self):
        rule = alerting.AlertRule(
            name="test-rule",
            condition=lambda: True,
            severity=alerting.AlertSeverity.WARNING,
            title_template="Test Alert",
            message_template="Test message",
            source="test-source",
            cooldown=0.01
        )
        rule.last_fired = datetime.utcnow()
        import time
        time.sleep(0.02)
        assert rule.should_fire() is True

    def test_fire_alert(self):
        rule = alerting.AlertRule(
            name="test-rule",
            condition=lambda: True,
            severity=alerting.AlertSeverity.ERROR,
            title_template="Test Alert",
            message_template="Test message",
            source="test-source"
        )
        alert = rule.fire()
        assert alert.severity == alerting.AlertSeverity.ERROR
        assert alert.title == "Test Alert"
        assert alert.message == "Test message"
        assert alert.source == "test-source"
        assert alert.id.startswith("test-rule-")
        assert rule.last_fired is not None


# ============================================================================
# Alert Manager Tests
# ============================================================================

class TestAlertManager:
    """Test AlertManager class"""

    def test_alert_manager_initialization(self):
        manager = alerting.AlertManager()
        assert manager.rules == {}
        assert manager.channels == []
        assert manager.active_alerts == {}
        assert manager.alert_history == []
        assert manager._running is False

    def test_add_rule(self):
        manager = alerting.AlertManager()
        rule = alerting.AlertRule(
            name="test-rule",
            condition=lambda: True,
            severity=alerting.AlertSeverity.WARNING,
            title_template="Test",
            message_template="Test",
            source="test"
        )
        manager.add_rule(rule)
        assert "test-rule" in manager.rules
        assert manager.rules["test-rule"] == rule

    def test_remove_rule(self):
        manager = alerting.AlertManager()
        rule = alerting.AlertRule(
            name="test-rule",
            condition=lambda: True,
            severity=alerting.AlertSeverity.WARNING,
            title_template="Test",
            message_template="Test",
            source="test"
        )
        manager.add_rule(rule)
        manager.remove_rule("test-rule")
        assert "test-rule" not in manager.rules

    def test_remove_nonexistent_rule(self):
        manager = alerting.AlertManager()
        # Should not raise
        manager.remove_rule("nonexistent")

    def test_add_channel(self):
        manager = alerting.AlertManager()
        channel = alerting.LogAlertChannel()
        manager.add_channel(channel)
        assert len(manager.channels) == 1
        assert manager.channels[0] == channel

    def test_send_alert(self):
        manager = alerting.AlertManager()
        channel = alerting.LogAlertChannel()
        manager.add_channel(channel)
        
        alert = alerting.Alert(
            id="test-1",
            severity=alerting.AlertSeverity.INFO,
            title="Test",
            message="Test",
            source="test"
        )
        asyncio.run(manager.send_alert(alert))
        
        assert "test-1" in manager.active_alerts
        assert len(manager.alert_history) == 1

    def test_send_alert_history_limit(self):
        manager = alerting.AlertManager()
        channel = alerting.LogAlertChannel()
        manager.add_channel(channel)
        
        # Add more than 1000 alerts
        for i in range(1005):
            alert = alerting.Alert(
                id=f"test-{i}",
                severity=alerting.AlertSeverity.INFO,
                title="Test",
                message="Test",
                source="test"
            )
            asyncio.run(manager.send_alert(alert))
        
        # History should be limited to 1000
        assert len(manager.alert_history) == 1000

    def test_acknowledge_alert(self):
        manager = alerting.AlertManager()
        alert = alerting.Alert(
            id="test-1",
            severity=alerting.AlertSeverity.INFO,
            title="Test",
            message="Test",
            source="test"
        )
        manager.active_alerts["test-1"] = alert
        
        result = asyncio.run(manager.acknowledge_alert("test-1", "user1"))
        assert result is True
        assert alert.status == alerting.AlertStatus.ACKNOWLEDGED
        assert alert.acknowledged_by == "user1"
        assert alert.acknowledged_at is not None

    def test_acknowledge_nonexistent_alert(self):
        manager = alerting.AlertManager()
        result = asyncio.run(manager.acknowledge_alert("nonexistent", "user1"))
        assert result is False

    def test_resolve_alert(self):
        manager = alerting.AlertManager()
        alert = alerting.Alert(
            id="test-1",
            severity=alerting.AlertSeverity.INFO,
            title="Test",
            message="Test",
            source="test"
        )
        manager.active_alerts["test-1"] = alert
        
        result = asyncio.run(manager.resolve_alert("test-1"))
        assert result is True
        assert alert.status == alerting.AlertStatus.RESOLVED
        assert alert.resolved_at is not None
        assert "test-1" not in manager.active_alerts

    def test_resolve_nonexistent_alert(self):
        manager = alerting.AlertManager()
        result = asyncio.run(manager.resolve_alert("nonexistent"))
        assert result is False

    def test_get_active_alerts(self):
        manager = alerting.AlertManager()
        alert1 = alerting.Alert(
            id="test-1",
            severity=alerting.AlertSeverity.INFO,
            title="Test",
            message="Test",
            source="test"
        )
        alert2 = alerting.Alert(
            id="test-2",
            severity=alerting.AlertSeverity.WARNING,
            title="Test",
            message="Test",
            source="test"
        )
        manager.active_alerts["test-1"] = alert1
        manager.active_alerts["test-2"] = alert2
        
        alerts = manager.get_active_alerts()
        assert len(alerts) == 2
        assert alert1 in alerts
        assert alert2 in alerts

    def test_get_alert_history(self):
        manager = alerting.AlertManager()
        for i in range(10):
            alert = alerting.Alert(
                id=f"test-{i}",
                severity=alerting.AlertSeverity.INFO,
                title="Test",
                message="Test",
                source="test"
            )
            manager.alert_history.append(alert)
        
        history = manager.get_alert_history(limit=5)
        assert len(history) == 5

    def test_get_alert_history_default_limit(self):
        manager = alerting.AlertManager()
        for i in range(10):
            alert = alerting.Alert(
                id=f"test-{i}",
                severity=alerting.AlertSeverity.INFO,
                title="Test",
                message="Test",
                source="test"
            )
            manager.alert_history.append(alert)
        
        history = manager.get_alert_history()
        assert len(history) == 10

    def test_start_stop(self):
        manager = alerting.AlertManager()
        asyncio.run(manager.start())
        assert manager._running is True
        assert manager._task is not None
        
        asyncio.run(manager.stop())
        assert manager._running is False

    def test_start_already_running(self):
        manager = alerting.AlertManager()
        asyncio.run(manager.start())
        # Should not raise
        asyncio.run(manager.start())
        asyncio.run(manager.stop())

    def test_stop_not_running(self):
        manager = alerting.AlertManager()
        # Should not raise
        asyncio.run(manager.stop())

    def test_check_rules(self):
        manager = alerting.AlertManager()
        channel = alerting.LogAlertChannel()
        manager.add_channel(channel)
        
        rule = alerting.AlertRule(
            name="test-rule",
            condition=lambda: True,
            severity=alerting.AlertSeverity.WARNING,
            title_template="Test",
            message_template="Test",
            source="test"
        )
        manager.add_rule(rule)
        
        asyncio.run(manager.check_rules())
        # Should have fired and sent alert
        assert len(manager.alert_history) > 0


# ============================================================================
# Global Functions Tests
# ============================================================================

class TestGlobalFunctions:
    """Test global alerting functions"""

    def test_get_alert_manager_singleton(self):
        # Reset global instance
        alerting._alert_manager = None
        manager1 = alerting.get_alert_manager()
        manager2 = alerting.get_alert_manager()
        assert manager1 is manager2

    def test_get_alert_manager_default_channel(self):
        alerting._alert_manager = None
        manager = alerting.get_alert_manager()
        assert len(manager.channels) == 1
        assert isinstance(manager.channels[0], alerting.LogAlertChannel)

    def test_setup_alerting_no_webhook(self):
        alerting._alert_manager = None
        manager = alerting.setup_alerting()
        assert len(manager.channels) == 1

    def test_setup_alerting_with_webhook(self):
        alerting._alert_manager = None
        manager = alerting.setup_alerting(
            webhook_url="https://example.com/webhook",
            webhook_headers={"Authorization": "Bearer token"}
        )
        assert len(manager.channels) == 2
        assert isinstance(manager.channels[1], alerting.WebhookAlertChannel)
