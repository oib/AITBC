import json
import logging
import os
from collections import deque
from datetime import datetime, timedelta
from typing import Any
from urllib import error, request

logger = logging.getLogger(__name__)


class AlertDispatcher:
    def __init__(self, cooldown_seconds: int = 300, max_history: int = 100):
        self.cooldown_seconds = cooldown_seconds
        self._last_sent: dict[str, datetime] = {}
        self._history: deque[dict[str, Any]] = deque(maxlen=max_history)

    def dispatch(self, alerts: dict[str, dict[str, Any]]) -> dict[str, Any]:
        triggered = {
            name: alert for name, alert in alerts.items() if alert.get("triggered")
        }
        results: dict[str, Any] = {
            "triggered_count": len(triggered),
            "sent": [],
            "suppressed": [],
            "failed": [],
            "channel": self._channel_name(),
        }

        for name, alert in triggered.items():
            if self._is_suppressed(name):
                results["suppressed"].append(name)
                self._record_alert(name, alert, delivery_status="suppressed")
                continue

            try:
                self._deliver(name, alert)
                self._last_sent[name] = datetime.utcnow()
                results["sent"].append(name)
                self._record_alert(name, alert, delivery_status="sent")
            except Exception as exc:
                logger.error("Alert delivery failed for %s: %s", name, exc)
                results["failed"].append({"name": name, "error": str(exc)})
                self._record_alert(name, alert, delivery_status="failed", error_message=str(exc))

        return results

    def get_recent_alerts(self, severity: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        alerts = list(self._history)
        if severity:
            alerts = [alert for alert in alerts if alert["severity"] == severity]
        limit = max(limit, 0)
        if limit == 0:
            return []
        return list(reversed(alerts[-limit:]))

    def reset_history(self) -> None:
        self._history.clear()

    def _is_suppressed(self, name: str) -> bool:
        last_sent = self._last_sent.get(name)
        if last_sent is None:
            return False
        return datetime.utcnow() - last_sent < timedelta(seconds=self.cooldown_seconds)

    def _record_alert(
        self,
        name: str,
        alert: dict[str, Any],
        delivery_status: str,
        error_message: str | None = None,
    ) -> None:
        timestamp = datetime.utcnow().isoformat()
        record = {
            "id": f"metrics_alert_{name}_{int(datetime.utcnow().timestamp() * 1000)}",
            "deployment_id": None,
            "severity": alert.get("status", "critical"),
            "message": f"Threshold triggered for {name}",
            "timestamp": timestamp,
            "resolved": False,
            "source": "coordinator_metrics",
            "channel": self._channel_name(),
            "delivery_status": delivery_status,
            "value": alert.get("value"),
            "threshold": alert.get("threshold"),
        }
        if error_message is not None:
            record["error"] = error_message
        self._history.append(record)

    def _deliver(self, name: str, alert: dict[str, Any]) -> None:
        webhook_url = os.getenv("AITBC_ALERT_WEBHOOK_URL", "").strip()
        payload = {
            "name": name,
            "status": alert.get("status", "critical"),
            "value": alert.get("value"),
            "threshold": alert.get("threshold"),
            "timestamp": datetime.utcnow().isoformat(),
        }

        if webhook_url:
            body = json.dumps(payload).encode("utf-8")
            webhook_request = request.Request(
                webhook_url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with request.urlopen(webhook_request, timeout=5) as response:
                    if response.status >= 400:
                        raise RuntimeError(f"Webhook responded with status {response.status}")
            except error.URLError as exc:
                raise RuntimeError(f"Webhook delivery error: {exc}") from exc
            logger.warning("Alert delivered to webhook: %s", name)
            return

        logger.warning(
            "Alert triggered without external webhook configured: %s value=%s threshold=%s",
            name,
            alert.get("value"),
            alert.get("threshold"),
        )

    def _channel_name(self) -> str:
        return "webhook" if os.getenv("AITBC_ALERT_WEBHOOK_URL", "").strip() else "log"


alert_dispatcher = AlertDispatcher()
