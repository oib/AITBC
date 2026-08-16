"""Unit tests for aitbc.alerting."""

from unittest.mock import patch


from aitbc.alerting import (
    Alert,
    AlertManager,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    LogAlertChannel,
    WebhookAlertChannel,
    get_alert_manager,
    setup_alerting,
)


class AlwaysTrueRule(AlertRule):
    def __init__(self, name: str):
        super().__init__(name, lambda: True, AlertSeverity.WARNING, "title", "msg", "test")


class FailingRule(AlertRule):
    def __init__(self, name: str):
        super().__init__(name, lambda: True, AlertSeverity.WARNING, "title", "msg", "test")

    def should_fire(self):
        raise RuntimeError("rule failure")


class TestAlert:
    def test_alert_to_dict(self):
        alert = Alert(
            id="1",
            severity=AlertSeverity.ERROR,
            title="T",
            message="M",
            source="test",
            metadata={"key": "value"},
        )
        d = alert.to_dict()
        assert d["id"] == "1"
        assert d["severity"] == "error"
        assert d["metadata"] == {"key": "value"}


class TestAlertRule:
    def test_should_fire_respects_cooldown(self):
        rule = AlertRule(
            name="test",
            condition=lambda: True,
            severity=AlertSeverity.INFO,
            title_template="T",
            message_template="M",
            source="test",
            cooldown=10,
        )
        rule.fire()
        assert rule.should_fire() is False

    def test_should_fire_disabled(self):
        rule = AlertRule(
            name="test",
            condition=lambda: True,
            severity=AlertSeverity.INFO,
            title_template="T",
            message_template="M",
            source="test",
        )
        rule.enabled = False
        assert rule.should_fire() is False

    def test_fire_creates_alert(self):
        rule = AlertRule(
            name="test",
            condition=lambda: True,
            severity=AlertSeverity.INFO,
            title_template="T",
            message_template="M",
            source="test",
        )
        alert = rule.fire()
        assert alert.severity == AlertSeverity.INFO
        assert alert.title == "T"


class TestAlertManager:
    def test_add_and_remove_rule(self):
        manager = AlertManager()
        rule = AlertRule("r", lambda: True, AlertSeverity.INFO, "T", "M", "test")
        manager.add_rule(rule)
        assert "r" in manager.rules
        manager.remove_rule("r")
        assert "r" not in manager.rules

    def test_add_channel(self):
        manager = AlertManager()
        channel = LogAlertChannel()
        manager.add_channel(channel)
        assert len(manager.channels) == 1

    async def test_send_alert(self):
        manager = AlertManager()
        channel = LogAlertChannel()
        manager.add_channel(channel)
        alert = Alert(id="1", severity=AlertSeverity.INFO, title="T", message="M", source="test")
        await manager.send_alert(alert)
        assert "1" in manager.active_alerts
        assert manager.alert_history == [alert]

    async def test_acknowledge_alert(self):
        manager = AlertManager()
        alert = Alert(id="1", severity=AlertSeverity.INFO, title="T", message="M", source="test")
        manager.active_alerts["1"] = alert
        result = await manager.acknowledge_alert("1", "user")
        assert result is True
        assert alert.status == AlertStatus.ACKNOWLEDGED
        assert alert.acknowledged_by == "user"

    async def test_resolve_alert(self):
        manager = AlertManager()
        alert = Alert(id="1", severity=AlertSeverity.INFO, title="T", message="M", source="test")
        manager.active_alerts["1"] = alert
        result = await manager.resolve_alert("1")
        assert result is True
        assert alert.status == AlertStatus.RESOLVED
        assert "1" not in manager.active_alerts

    async def test_check_rules_fires(self):
        manager = AlertManager()
        manager.add_channel(LogAlertChannel())
        rule = AlwaysTrueRule("fire")
        manager.add_rule(rule)
        await manager.check_rules()
        assert manager.active_alerts

    async def test_check_rules_handles_exception(self):
        manager = AlertManager()
        manager.add_channel(LogAlertChannel())
        rule = FailingRule("fail")
        manager.add_rule(rule)
        await manager.check_rules()
        # No alert should be created; the exception is logged and swallowed.
        assert manager.active_alerts == {}

    async def test_start_and_stop(self):
        manager = AlertManager()

        with patch("aitbc.alerting.asyncio.sleep") as mock_sleep:
            mock_sleep.side_effect = [0]
            await manager.start()
            assert manager._running is True
            await manager.stop()
            assert manager._running is False


class TestLogAlertChannel:
    async def test_send(self):
        channel = LogAlertChannel()
        alert = Alert(id="1", severity=AlertSeverity.INFO, title="T", message="M", source="test")
        assert await channel.send(alert) is True


class TestWebhookAlertChannel:
    async def test_send_success(self):
        class FakeResponse:
            def raise_for_status(self):
                pass

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, *args, **kwargs):
                return FakeResponse()

        with patch("httpx.AsyncClient", FakeClient):
            channel = WebhookAlertChannel("http://example.com")
            alert = Alert(id="1", severity=AlertSeverity.INFO, title="T", message="M", source="test")
            assert await channel.send(alert) is True

    async def test_send_failure(self):
        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, *args, **kwargs):
                raise RuntimeError("network down")

        with patch("httpx.AsyncClient", FakeClient):
            channel = WebhookAlertChannel("http://example.com")
            alert = Alert(id="1", severity=AlertSeverity.INFO, title="T", message="M", source="test")
            assert await channel.send(alert) is False


class TestAlertingSetup:
    def test_get_alert_manager(self):
        manager = get_alert_manager()
        assert isinstance(manager, AlertManager)

    def test_setup_alerting(self):
        manager = setup_alerting(webhook_url="http://example.com")
        assert isinstance(manager, AlertManager)
