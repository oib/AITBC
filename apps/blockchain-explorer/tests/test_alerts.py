"""Tests for the alert endpoints (routers/alerts.py).

Prometheus is faked by patching ``alerts._prometheus_get``; the watcher event
log is a real JSON-lines file under ``tmp_path`` selected via AITBC_ALERT_LOG.
"""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

import routers.alerts as alerts_mod
from main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def alert_log(tmp_path, monkeypatch):
    """Point the router at a fresh temp log; returns the path to write into."""
    path = tmp_path / "alerts.log"
    monkeypatch.setenv("AITBC_ALERT_LOG", str(path))
    return path


def _event(event: str, alertname: str | None = None, **extra: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {"event": event, "timestamp_unix": 1_700_000_000, "timestamp": "2023-11-14T00:00:00"}
    if alertname:
        rec.update(
            {
                "alertname": alertname,
                "state": "resolved" if event == "prometheus_alert_resolved" else "firing",
                "severity": "critical",
                "labels": {"alertname": alertname, "node": "node0", "severity": "critical"},
                "active_at": "2023-11-14T00:00:00Z",
            }
        )
    rec.update(extra)
    return rec


def _write_log(path, records: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def _prom(alerts_payload: dict[str, Any] | None, watcher_age: float | None = 5.0):
    """A _prometheus_get replacement serving /api/v1/alerts and /api/v1/query."""

    async def fake(path: str, params: dict[str, str] | None = None) -> dict[str, Any] | None:
        if alerts_payload is None:
            return None
        if path == "/api/v1/alerts":
            return {"status": "success", "data": {"alerts": alerts_payload["alerts"]}}
        if path == "/api/v1/query":
            result = [] if watcher_age is None else [{"value": [0, str(watcher_age)]}]
            return {"status": "success", "data": {"result": result}}
        return None

    return fake


def _prom_alert(name: str, node: str, state: str = "firing", severity: str = "critical") -> dict[str, Any]:
    return {
        "state": state,
        "labels": {"alertname": name, "node": node, "severity": severity},
        "annotations": {"summary": f"{name} summary"},
        "activeAt": "2023-11-14T00:00:00Z",
    }


class TestAlertsLive:
    def test_prometheus_down_no_log(self, client, alert_log, monkeypatch):
        monkeypatch.setattr(alerts_mod, "_prometheus_get", _prom(None))
        body = client.get("/api/alerts").json()
        assert body["prometheus_ok"] is False
        assert body["source"] == "event_log"
        assert body["firing"] == []
        assert body["log_available"] is False
        assert body["watcher"] is None

    def test_prometheus_down_replays_log(self, client, alert_log, monkeypatch):
        _write_log(
            alert_log,
            [
                _event("prometheus_alert_firing", "ServiceDown"),
                _event("prometheus_alert_firing", "ServiceDown", labels={"alertname": "ServiceDown", "node": "node1"}),
                _event("prometheus_alert_resolved", "ServiceDown"),
            ],
        )
        monkeypatch.setattr(alerts_mod, "_prometheus_get", _prom(None))
        body = client.get("/api/alerts").json()
        assert body["prometheus_ok"] is False
        assert [a["alertname"] for a in body["firing"]] == ["ServiceDown"]
        assert body["firing"][0]["node"] == "node1"
        assert body["firing"][0]["silenced"] is False

    def test_prometheus_lists_firing_and_pending(self, client, alert_log, monkeypatch):
        monkeypatch.setattr(
            alerts_mod,
            "_prometheus_get",
            _prom({"alerts": [_prom_alert("ServiceDown", "hub1"), _prom_alert("Stale", "node2", state="pending")]}),
        )
        body = client.get("/api/alerts").json()
        assert body["prometheus_ok"] is True
        assert body["source"] == "prometheus"
        assert [a["alertname"] for a in body["firing"]] == ["ServiceDown"]
        assert [a["alertname"] for a in body["pending"]] == ["Stale"]
        assert body["watcher"]["present"] is True
        assert body["watcher"]["stale"] is False

    def test_silenced_flag_merges_from_log(self, client, alert_log, monkeypatch):
        _write_log(
            alert_log, [_event("prometheus_alert_firing", "ServiceDown", silenced=True, silence_reason="down for maintenance")]
        )
        monkeypatch.setattr(alerts_mod, "_prometheus_get", _prom({"alerts": [_prom_alert("ServiceDown", "node0")]}))
        body = client.get("/api/alerts").json()
        assert body["firing"][0]["silenced"] is True

    def test_silence_expired_clears_flag(self, client, alert_log, monkeypatch):
        _write_log(
            alert_log,
            [
                _event("prometheus_alert_firing", "ServiceDown", silenced=True),
                _event("prometheus_alert_firing", "ServiceDown", via="silence_expired"),
            ],
        )
        monkeypatch.setattr(alerts_mod, "_prometheus_get", _prom({"alerts": [_prom_alert("ServiceDown", "node0")]}))
        body = client.get("/api/alerts").json()
        assert body["firing"][0]["silenced"] is False

    def test_watcher_stale_and_absent(self, client, alert_log, monkeypatch):
        monkeypatch.setattr(alerts_mod, "_prometheus_get", _prom({"alerts": []}, watcher_age=900.0))
        assert client.get("/api/alerts").json()["watcher"]["stale"] is True

        monkeypatch.setattr(alerts_mod, "_prometheus_get", _prom({"alerts": []}, watcher_age=None))
        watcher = client.get("/api/alerts").json()["watcher"]
        assert watcher["present"] is False
        assert watcher["stale"] is True


class TestAlertsHistory:
    def test_missing_log(self, client, alert_log):
        body = client.get("/api/alerts/history").json()
        assert body["events"] == []
        assert body["log_available"] is False

    def test_newest_first_and_limit(self, client, alert_log):
        _write_log(
            alert_log,
            [
                _event("prometheus_alert_firing", "A"),
                _event("prometheus_alert_resolved", "A"),
                _event("prometheus_alert_firing", "B"),
            ],
        )
        body = client.get("/api/alerts/history").json()
        assert [e["alertname"] for e in body["events"]] == ["B", "A", "A"]
        assert body["scanned_events"] == 3

        limited = client.get("/api/alerts/history?limit=2").json()
        assert [e["alertname"] for e in limited["events"]] == ["B", "A"]

    def test_alertname_substring_and_node_filters(self, client, alert_log):
        _write_log(
            alert_log,
            [
                _event("prometheus_alert_firing", "ServiceDown"),
                _event("prometheus_alert_firing", "ServiceDown", labels={"alertname": "ServiceDown", "node": "hub1"}),
                _event("prometheus_alert_firing", "BalanceLow"),
            ],
        )
        body = client.get("/api/alerts/history?alertname=Service").json()
        assert {e["alertname"] for e in body["events"]} == {"ServiceDown"}

        body = client.get("/api/alerts/history?node=hub1").json()
        assert [e["labels"]["node"] for e in body["events"]] == ["hub1"]

    def test_state_filters(self, client, alert_log):
        _write_log(
            alert_log,
            [
                _event("prometheus_alert_firing", "A"),
                _event("prometheus_alert_resolved", "A"),
                _event("prometheus_alert_firing", "B", silenced=True),
            ],
        )
        firing = client.get("/api/alerts/history?state=firing").json()["events"]
        assert {e["alertname"] for e in firing} == {"A", "B"}

        resolved = client.get("/api/alerts/history?state=resolved").json()["events"]
        assert [e["alertname"] for e in resolved] == ["A"]

        silenced = client.get("/api/alerts/history?state=silenced").json()["events"]
        assert [e["alertname"] for e in silenced] == ["B"]

    def test_bad_lines_skipped(self, client, alert_log):
        alert_log.write_text('{"event":"prometheus_alert_firing","alertname":"A"}\nnot json\n\n')
        body = client.get("/api/alerts/history").json()
        assert len(body["events"]) == 1
