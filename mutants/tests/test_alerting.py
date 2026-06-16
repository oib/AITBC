"""Tests for aitbc.alerting"""

from aitbc.alerting import Alert, AlertSeverity, AlertStatus


class TestAlert:
    def test_alert_creation(self):
        alert = Alert(id="1", severity=AlertSeverity.ERROR, title="Test", message="Message", source="test")
        assert alert.id == "1"
        assert alert.severity == AlertSeverity.ERROR
        assert alert.status == AlertStatus.ACTIVE

    def test_alert_to_dict(self):
        alert = Alert(id="1", severity=AlertSeverity.WARNING, title="Test", message="Message", source="test")
        d = alert.to_dict()
        assert d["id"] == "1"
        assert d["severity"] == "warning"
