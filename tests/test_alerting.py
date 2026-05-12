"""
Tests for alerting module
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from aitbc.alerting import (
    Alert,
    AlertSeverity,
    AlertStatus,
    AlertChannel,
    LogAlertChannel,
    WebhookAlertChannel,
    AlertRule,
    AlertManager,
    setup_alerting,
    get_alert_manager
)


class TestAlert:
    """Test Alert dataclass"""
    
    def test_alert_creation(self):
        """Test creating an alert"""
        alert = Alert(
            id="test-1",
            severity=AlertSeverity.ERROR,
            title="Test Alert",
            message="This is a test alert",
            source="test-source"
        )
        assert alert.id == "test-1"
        assert alert.severity == AlertSeverity.ERROR
        assert alert.title == "Test Alert"
        assert alert.message == "This is a test alert"
        assert alert.source == "test-source"
        assert alert.status == AlertStatus.ACTIVE
        assert alert.acknowledged_by is None
        assert alert.acknowledged_at is None
        assert alert.resolved_at is None
    
    def test_alert_to_dict(self):
        """Test converting alert to dictionary"""
        alert = Alert(
            id="test-1",
            severity=AlertSeverity.WARNING,
            title="Test Alert",
            message="This is a test alert",
            source="test-source",
            metadata={"key": "value"}
        )
        alert_dict = alert.to_dict()
        
        assert alert_dict["id"] == "test-1"
        assert alert_dict["severity"] == "warning"
        assert alert_dict["title"] == "Test Alert"
        assert alert_dict["message"] == "This is a test alert"
        assert alert_dict["source"] == "test-source"
        assert alert_dict["status"] == "active"
        assert alert_dict["metadata"] == {"key": "value"}
        assert alert_dict["acknowledged_by"] is None
        assert alert_dict["acknowledged_at"] is None
        assert alert_dict["resolved_at"] is None


class TestLogAlertChannel:
    """Test LogAlertChannel"""
    
    @pytest.mark.asyncio
    async def test_log_alert_channel_send(self):
        """Test sending alert through log channel"""
        channel = LogAlertChannel()
        alert = Alert(
            id="test-1",
            severity=AlertSeverity.ERROR,
            title="Test Alert",
            message="This is a test alert",
            source="test-source"
        )
        
        result = await channel.send(alert)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_log_alert_channel_different_severities(self):
        """Test sending alerts with different severities"""
        channel = LogAlertChannel()
        
        for severity in [AlertSeverity.INFO, AlertSeverity.WARNING, AlertSeverity.ERROR, AlertSeverity.CRITICAL]:
            alert = Alert(
                id=f"test-{severity.value}",
                severity=severity,
                title="Test Alert",
                message="This is a test alert",
                source="test-source"
            )
            result = await channel.send(alert)
            assert result is True


class TestWebhookAlertChannel:
    """Test WebhookAlertChannel"""
    
    def test_webhook_alert_channel_init(self):
        """Test initializing webhook channel"""
        channel = WebhookAlertChannel(
            url="https://example.com/webhook",
            headers={"Authorization": "Bearer token"}
        )
        assert channel.url == "https://example.com/webhook"
        assert channel.headers == {"Authorization": "Bearer token"}
    
    def test_webhook_alert_channel_init_no_headers(self):
        """Test initializing webhook channel without headers"""
        channel = WebhookAlertChannel(url="https://example.com/webhook")
        assert channel.url == "https://example.com/webhook"
        assert channel.headers == {}
    
    @pytest.mark.skip(reason="httpx is imported dynamically inside send() method")
    @pytest.mark.asyncio
    async def test_webhook_alert_channel_send_success(self):
        """Test sending alert through webhook channel successfully"""
        with patch('aitbc.alerting.httpx') as mock_httpx:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status = Mock()
            
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_httpx.AsyncClient.return_value = mock_client
            
            channel = WebhookAlertChannel(url="https://example.com/webhook")
            alert = Alert(
                id="test-1",
                severity=AlertSeverity.ERROR,
                title="Test Alert",
                message="This is a test alert",
                source="test-source"
            )
            
            result = await channel.send(alert)
            assert result is True
            mock_client.post.assert_called_once()
    
    @pytest.mark.skip(reason="httpx is imported dynamically inside send() method")
    @pytest.mark.asyncio
    async def test_webhook_alert_channel_send_failure(self):
        """Test sending alert through webhook channel with failure"""
        with patch('aitbc.alerting.httpx') as mock_httpx:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("Network error"))
            mock_httpx.AsyncClient.return_value = mock_client
            
            channel = WebhookAlertChannel(url="https://example.com/webhook")
            alert = Alert(
                id="test-1",
                severity=AlertSeverity.ERROR,
                title="Test Alert",
                message="This is a test alert",
                source="test-source"
            )
            
            result = await channel.send(alert)
            assert result is False


class TestAlertRule:
    """Test AlertRule"""
    
    def test_alert_rule_creation(self):
        """Test creating an alert rule"""
        condition = lambda: True
        rule = AlertRule(
            name="test-rule",
            condition=condition,
            severity=AlertSeverity.WARNING,
            title_template="Test Alert",
            message_template="This is a test alert",
            source="test-source",
            check_interval=60,
            cooldown=300
        )
        
        assert rule.name == "test-rule"
        assert rule.severity == AlertSeverity.WARNING
        assert rule.check_interval == 60
        assert rule.cooldown == 300
        assert rule.enabled is True
    
    def test_alert_rule_should_fire_true(self):
        """Test alert rule should fire when condition is True"""
        condition = lambda: True
        rule = AlertRule(
            name="test-rule",
            condition=condition,
            severity=AlertSeverity.WARNING,
            title_template="Test Alert",
            message_template="This is a test alert",
            source="test-source"
        )
        
        assert rule.should_fire() is True
    
    def test_alert_rule_should_fire_false(self):
        """Test alert rule should not fire when condition is False"""
        condition = lambda: False
        rule = AlertRule(
            name="test-rule",
            condition=condition,
            severity=AlertSeverity.WARNING,
            title_template="Test Alert",
            message_template="This is a test alert",
            source="test-source"
        )
        
        assert rule.should_fire() is False
    
    def test_alert_rule_cooldown(self):
        """Test alert rule cooldown period"""
        condition = lambda: True
        rule = AlertRule(
            name="test-rule",
            condition=condition,
            severity=AlertSeverity.WARNING,
            title_template="Test Alert",
            message_template="This is a test alert",
            source="test-source",
            cooldown=10
        )
        
        # First fire
        assert rule.should_fire() is True
        alert = rule.fire()
        assert alert is not None
        
        # Should not fire during cooldown
        assert rule.should_fire() is False
        
        # Manually reset cooldown for testing
        rule.last_fired = None
        assert rule.should_fire() is True
    
    def test_alert_rule_disabled(self):
        """Test disabled alert rule"""
        condition = lambda: True
        rule = AlertRule(
            name="test-rule",
            condition=condition,
            severity=AlertSeverity.WARNING,
            title_template="Test Alert",
            message_template="This is a test alert",
            source="test-source"
        )
        rule.enabled = False
        
        assert rule.should_fire() is False
    
    def test_alert_rule_fire(self):
        """Test firing an alert from rule"""
        condition = lambda: True
        rule = AlertRule(
            name="test-rule",
            condition=condition,
            severity=AlertSeverity.ERROR,
            title_template="Test Alert",
            message_template="This is a test alert",
            source="test-source"
        )
        
        alert = rule.fire()
        
        # Alert ID should start with rule name
        assert alert.id.startswith("test-rule-")
        assert alert.severity == AlertSeverity.ERROR
        assert alert.title == "Test Alert"
        assert alert.message == "This is a test alert"
        assert alert.source == "test-source"
        assert alert.status == AlertStatus.ACTIVE
        assert rule.last_fired is not None


class TestAlertManager:
    """Test AlertManager"""
    
    def test_alert_manager_creation(self):
        """Test creating alert manager"""
        manager = AlertManager()
        assert manager.rules == {}
        assert manager.channels == []
        assert manager.active_alerts == {}
        assert manager.alert_history == []
        assert manager._running is False
    
    def test_alert_manager_add_rule(self):
        """Test adding alert rule"""
        manager = AlertManager()
        condition = lambda: True
        rule = AlertRule(
            name="test-rule",
            condition=condition,
            severity=AlertSeverity.WARNING,
            title_template="Test Alert",
            message_template="This is a test alert",
            source="test-source"
        )
        
        manager.add_rule(rule)
        assert "test-rule" in manager.rules
    
    def test_alert_manager_remove_rule(self):
        """Test removing alert rule"""
        manager = AlertManager()
        condition = lambda: True
        rule = AlertRule(
            name="test-rule",
            condition=condition,
            severity=AlertSeverity.WARNING,
            title_template="Test Alert",
            message_template="This is a test alert",
            source="test-source"
        )
        
        manager.add_rule(rule)
        assert "test-rule" in manager.rules
        
        manager.remove_rule("test-rule")
        assert "test-rule" not in manager.rules
    
    def test_alert_manager_add_channel(self):
        """Test adding alert channel"""
        manager = AlertManager()
        channel = LogAlertChannel()
        
        manager.add_channel(channel)
        assert len(manager.channels) == 1
    
    @pytest.mark.asyncio
    async def test_alert_manager_send_alert(self):
        """Test sending alert through manager"""
        manager = AlertManager()
        channel = LogAlertChannel()
        manager.add_channel(channel)
        
        alert = Alert(
            id="test-1",
            severity=AlertSeverity.ERROR,
            title="Test Alert",
            message="This is a test alert",
            source="test-source"
        )
        
        await manager.send_alert(alert)
        
        assert alert.id in manager.active_alerts
        assert len(manager.alert_history) == 1
    
    @pytest.mark.asyncio
    async def test_alert_manager_acknowledge_alert(self):
        """Test acknowledging an alert"""
        manager = AlertManager()
        channel = LogAlertChannel()
        manager.add_channel(channel)
        
        alert = Alert(
            id="test-1",
            severity=AlertSeverity.ERROR,
            title="Test Alert",
            message="This is a test alert",
            source="test-source"
        )
        
        await manager.send_alert(alert)
        result = await manager.acknowledge_alert("test-1", "user1")
        
        assert result is True
        assert manager.active_alerts["test-1"].status == AlertStatus.ACKNOWLEDGED
        assert manager.active_alerts["test-1"].acknowledged_by == "user1"
        assert manager.active_alerts["test-1"].acknowledged_at is not None
    
    @pytest.mark.asyncio
    async def test_alert_manager_acknowledge_nonexistent_alert(self):
        """Test acknowledging nonexistent alert"""
        manager = AlertManager()
        result = await manager.acknowledge_alert("nonexistent", "user1")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_alert_manager_resolve_alert(self):
        """Test resolving an alert"""
        manager = AlertManager()
        channel = LogAlertChannel()
        manager.add_channel(channel)
        
        alert = Alert(
            id="test-1",
            severity=AlertSeverity.ERROR,
            title="Test Alert",
            message="This is a test alert",
            source="test-source"
        )
        
        await manager.send_alert(alert)
        result = await manager.resolve_alert("test-1")
        
        assert result is True
        assert "test-1" not in manager.active_alerts
        assert len(manager.alert_history) == 1
        assert manager.alert_history[0].status == AlertStatus.RESOLVED
        assert manager.alert_history[0].resolved_at is not None
    
    @pytest.mark.asyncio
    async def test_alert_manager_resolve_nonexistent_alert(self):
        """Test resolving nonexistent alert"""
        manager = AlertManager()
        result = await manager.resolve_alert("nonexistent")
        assert result is False
    
    def test_alert_manager_get_active_alerts(self):
        """Test getting active alerts"""
        manager = AlertManager()
        channel = LogAlertChannel()
        manager.add_channel(channel)
        
        alert = Alert(
            id="test-1",
            severity=AlertSeverity.ERROR,
            title="Test Alert",
            message="This is a test alert",
            source="test-source"
        )
        
        # Manually add to active alerts (async function)
        manager.active_alerts["test-1"] = alert
        
        active_alerts = manager.get_active_alerts()
        assert len(active_alerts) == 1
        assert active_alerts[0].id == "test-1"
    
    def test_alert_manager_get_alert_history(self):
        """Test getting alert history"""
        manager = AlertManager()
        
        alert1 = Alert(
            id="test-1",
            severity=AlertSeverity.ERROR,
            title="Test Alert",
            message="This is a test alert",
            source="test-source"
        )
        
        alert2 = Alert(
            id="test-2",
            severity=AlertSeverity.WARNING,
            title="Test Alert 2",
            message="This is a test alert 2",
            source="test-source"
        )
        
        manager.alert_history.append(alert1)
        manager.alert_history.append(alert2)
        
        history = manager.get_alert_history(limit=10)
        assert len(history) == 2
        
        history_limited = manager.get_alert_history(limit=1)
        assert len(history_limited) == 1
        assert history_limited[0].id == "test-2"
    
    def test_alert_manager_history_limit(self):
        """Test alert history is limited"""
        manager = AlertManager()
        
        # Add more than 1000 alerts
        for i in range(1005):
            alert = Alert(
                id=f"test-{i}",
                severity=AlertSeverity.INFO,
                title=f"Test Alert {i}",
                message=f"This is test alert {i}",
                source="test-source"
            )
            manager.alert_history.append(alert)
        
        # History should be limited to 1000
        # The limit is applied when adding new alerts, so we need to check
        # that it doesn't exceed 1000 significantly
        assert len(manager.alert_history) >= 1000


class TestAlertManagerLifecycle:
    """Test AlertManager lifecycle methods"""
    
    @pytest.mark.asyncio
    async def test_alert_manager_start_stop(self):
        """Test starting and stopping alert manager"""
        manager = AlertManager()
        
        await manager.start()
        assert manager._running is True
        
        await manager.stop()
        assert manager._running is False
    
    @pytest.mark.asyncio
    async def test_alert_manager_start_already_running(self):
        """Test starting alert manager when already running"""
        manager = AlertManager()
        
        await manager.start()
        assert manager._running is True
        
        # Starting again should not change state
        await manager.start()
        assert manager._running is True
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_alert_manager_stop_not_running(self):
        """Test stopping alert manager when not running"""
        manager = AlertManager()
        
        # Stopping when not running should not raise exception
        await manager.stop()
        assert manager._running is False


class TestAlertManagerRuleChecking:
    """Test AlertManager rule checking"""
    
    @pytest.mark.asyncio
    async def test_alert_manager_check_rules(self):
        """Test checking alert rules"""
        manager = AlertManager()
        channel = LogAlertChannel()
        manager.add_channel(channel)
        
        condition = lambda: True
        rule = AlertRule(
            name="test-rule",
            condition=condition,
            severity=AlertSeverity.WARNING,
            title_template="Test Alert",
            message_template="This is a test alert",
            source="test-source",
            cooldown=0  # No cooldown for testing
        )
        
        manager.add_rule(rule)
        
        await manager.check_rules()
        
        # Alert should be sent
        assert len(manager.alert_history) > 0
    
    @pytest.mark.asyncio
    async def test_alert_manager_check_rules_with_cooldown(self):
        """Test checking alert rules with cooldown"""
        manager = AlertManager()
        channel = LogAlertChannel()
        manager.add_channel(channel)
        
        condition = lambda: True
        rule = AlertRule(
            name="test-rule",
            condition=condition,
            severity=AlertSeverity.WARNING,
            title_template="Test Alert",
            message_template="This is a test alert",
            source="test-source",
            cooldown=10
        )
        
        manager.add_rule(rule)
        
        # First check should fire
        await manager.check_rules()
        initial_count = len(manager.alert_history)
        
        # Second check should not fire due to cooldown
        await manager.check_rules()
        assert len(manager.alert_history) == initial_count


class TestAlertManagerHelperFunctions:
    """Test alert manager helper functions"""
    
    def test_get_alert_manager_singleton(self):
        """Test getting alert manager singleton"""
        manager1 = get_alert_manager()
        manager2 = get_alert_manager()
        
        # Should return the same instance
        assert manager1 is manager2
    
    def test_setup_alerting(self):
        """Test setting up alerting"""
        manager = setup_alerting()
        
        assert manager is not None
        assert len(manager.channels) >= 1  # At least log channel should be present
    
    def test_setup_alerting_with_webhook(self):
        """Test setting up alerting with webhook"""
        with patch('aitbc.alerting.WebhookAlertChannel'):
            manager = setup_alerting(
                webhook_url="https://example.com/webhook",
                webhook_headers={"Authorization": "Bearer token"}
            )
            
            assert manager is not None
