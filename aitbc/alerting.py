"""
AITBC Alerting Module
Alerting and notification system for AITBC applications
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from .aitbc_logging import get_logger
import contextlib

logger = get_logger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """Alert status"""

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


@dataclass
class Alert:
    """Alert data structure"""

    id: str
    severity: AlertSeverity
    title: str
    message: str
    source: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: AlertStatus = AlertStatus.ACTIVE
    metadata: dict[str, Any] = field(default_factory=dict)
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert alert to dictionary"""
        return {
            "id": self.id,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "status": self.status.value,
            "metadata": self.metadata,
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class AlertChannel:
    """Base class for alert channels"""

    async def send(self, alert: Alert) -> bool:
        """
        Send alert through this channel

        Args:
            alert: Alert to send

        Returns:
            True if sent successfully, False otherwise
        """
        raise NotImplementedError


class LogAlertChannel(AlertChannel):
    """Log-based alert channel"""

    async def send(self, alert: Alert) -> bool:
        """Send alert to logs"""
        try:
            log_level = {
                AlertSeverity.INFO: logger.info,
                AlertSeverity.WARNING: logger.warning,
                AlertSeverity.ERROR: logger.error,
                AlertSeverity.CRITICAL: logger.critical,
            }.get(alert.severity, logger.info)
            log_level(
                f"Alert [{alert.severity.value.upper()}]: {alert.title}",
                extra={
                    "alert_id": alert.id,
                    "severity": alert.severity.value,
                    "source": alert.source,
                    "metadata": alert.metadata,
                },
            )
            return True
        except Exception as e:
            logger.error("Failed to send log alert: %s", e)
            return False


class WebhookAlertChannel(AlertChannel):
    """Webhook-based alert channel"""

    def __init__(self, url: str, headers: dict[str, str] | None = None):
        """
        Initialize webhook channel

        Args:
            url: Webhook URL
            headers: HTTP headers
        """
        self.url = url
        self.headers = headers or {}

    async def send(self, alert: Alert) -> bool:
        """Send alert via webhook"""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(self.url, json=alert.to_dict(), headers=self.headers, timeout=10.0)
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error("Failed to send webhook alert: %s", e)
            return False


class AlertRule:
    """Alert rule definition"""

    def __init__(
        self,
        name: str,
        condition: Callable[[], bool],
        severity: AlertSeverity,
        title_template: str,
        message_template: str,
        source: str,
        check_interval: int = 60,
        cooldown: int = 300,
        metadata: dict[str, Any] | None = None,
    ):
        """
        Initialize alert rule

        Args:
            name: Rule name
            condition: Function that returns True if alert should fire
            severity: Alert severity
            title_template: Template for alert title
            message_template: Template for alert message
            source: Alert source
            check_interval: Check interval in seconds
            cooldown: Cooldown period in seconds
            metadata: Additional metadata
        """
        self.name = name
        self.condition = condition
        self.severity = severity
        self.title_template = title_template
        self.message_template = message_template
        self.source = source
        self.check_interval = check_interval
        self.cooldown = cooldown
        self.metadata = metadata or {}
        self.last_fired: datetime | None = None
        self.enabled = True

    def should_fire(self) -> bool:
        """Check if alert should fire"""
        if not self.enabled:
            return False
        if self.last_fired:
            time_since_last = (datetime.now(UTC) - self.last_fired).total_seconds()
            if time_since_last < self.cooldown:
                return False
        return self.condition()

    def fire(self) -> Alert:
        """Create alert from this rule"""
        self.last_fired = datetime.now(UTC)
        return Alert(
            id=f"{self.name}-{int(datetime.now(UTC).timestamp())}",
            severity=self.severity,
            title=self.title_template,
            message=self.message_template,
            source=self.source,
            metadata=self.metadata,
        )


class AlertManager:
    """Alert manager for handling alerts and rules"""

    def __init__(self):
        """Initialize alert manager"""
        self.rules: dict[str, AlertRule] = {}
        self.channels: list[AlertChannel] = []
        self.active_alerts: dict[str, Alert] = {}
        self.alert_history: list[Alert] = []
        self._running = False
        self._task: asyncio.Task | None = None

    def add_rule(self, rule: AlertRule) -> None:
        """
        Add alert rule

        Args:
            rule: Alert rule to add
        """
        self.rules[rule.name] = rule
        logger.info("Added alert rule: %s", rule.name)

    def remove_rule(self, name: str) -> None:
        """
        Remove alert rule

        Args:
            name: Rule name
        """
        if name in self.rules:
            del self.rules[name]
            logger.info("Removed alert rule: %s", name)

    def add_channel(self, channel: AlertChannel) -> None:
        """
        Add alert channel

        Args:
            channel: Alert channel to add
        """
        self.channels.append(channel)
        logger.info("Added alert channel: %s", channel.__class__.__name__)

    async def check_rules(self) -> None:
        """Check all alert rules and fire if needed"""
        for rule in self.rules.values():
            try:
                if rule.should_fire():
                    alert = rule.fire()
                    await self.send_alert(alert)
            except Exception as e:
                logger.error("Error checking rule %s: %s", rule.name, e)

    async def send_alert(self, alert: Alert) -> None:
        """
        Send alert through all channels

        Args:
            alert: Alert to send
        """
        self.active_alerts[alert.id] = alert
        self.alert_history.append(alert)
        if len(self.alert_history) > 1000:
            self.alert_history = self.alert_history[-1000:]
        for channel in self.channels:
            try:
                await channel.send(alert)
            except Exception as e:
                logger.error("Failed to send alert through channel: %s", e)

    async def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        """
        Acknowledge an alert

        Args:
            alert_id: Alert ID
            acknowledged_by: User acknowledging the alert

        Returns:
            True if acknowledged successfully
        """
        if alert_id in self.active_alerts:
            alert = self.active_alerts[alert_id]
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_by = acknowledged_by
            alert.acknowledged_at = datetime.now(UTC)
            logger.info("Alert acknowledged: %s by %s", alert_id, acknowledged_by)
            return True
        return False

    async def resolve_alert(self, alert_id: str) -> bool:
        """
        Resolve an alert

        Args:
            alert_id: Alert ID

        Returns:
            True if resolved successfully
        """
        if alert_id in self.active_alerts:
            alert = self.active_alerts[alert_id]
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = datetime.now(UTC)
            del self.active_alerts[alert_id]
            logger.info("Alert resolved: %s", alert_id)
            return True
        return False

    def get_active_alerts(self) -> list[Alert]:
        """Get all active alerts"""
        return list(self.active_alerts.values())

    def get_alert_history(self, limit: int = 100) -> list[Alert]:
        """
        Get alert history

        Args:
            limit: Maximum number of alerts to return

        Returns:
            List of alerts
        """
        return self.alert_history[-limit:]

    async def start(self) -> None:
        """Start alert manager background task"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_checks())
        logger.info("Alert manager started")

    async def stop(self) -> None:
        """Stop alert manager background task"""
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Alert manager stopped")

    async def _run_checks(self) -> None:
        """Background task to check alert rules"""
        while self._running:
            try:
                await self.check_rules()
                min_interval = min((rule.check_interval for rule in self.rules.values()), default=60)
                await asyncio.sleep(min_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in alert check loop: %s", e)
                await asyncio.sleep(60)


_alert_manager: AlertManager | None = None


def get_alert_manager() -> AlertManager:
    """
    Get global alert manager instance

    Returns:
        Alert manager instance
    """
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
        _alert_manager.add_channel(LogAlertChannel())
    return _alert_manager


def setup_alerting(webhook_url: str | None = None, webhook_headers: dict[str, str] | None = None) -> AlertManager:
    """
    Setup alerting system

    Args:
        webhook_url: Optional webhook URL for alerts
        webhook_headers: Optional webhook headers

    Returns:
        Alert manager instance
    """
    manager = get_alert_manager()
    if webhook_url:
        manager.add_channel(WebhookAlertChannel(webhook_url, webhook_headers))
    return manager
